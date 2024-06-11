"""Common functions."""

from dataclasses import dataclass
import datetime as dt
import logging
from pathlib import Path
import pkgutil
import re
import tarfile
import tempfile
import time
import zipfile

import markdown
from markdown.treeprocessors import Treeprocessor
from markdown.extensions import Extension
import puremagic
import pypandoc

import formats


LOGGER = logging.getLogger("jimmy")


###########################################################
# general
###########################################################


def get_available_formats() -> list[str]:
    return [module.name for module in pkgutil.iter_modules(formats.__path__)]


def is_image(file_: Path) -> bool:
    return puremagic.from_file(file_, mime=True).startswith("image/")


def try_transfer_dicts(source: dict, target: dict, keys: list[str | tuple[str, str]]):
    """Try to transfer values from one to another dict if they exist."""
    for key in keys:
        if isinstance(key, tuple):
            source_key, target_key = key
        else:
            source_key = target_key = key
        if (value := source.get(source_key)) is not None:
            target[target_key] = value


###########################################################
# operations on note body
###########################################################


def split_h1_title_from_body(markdown_):
    splitted_markdown = markdown_.split("\n", 1)
    match len(splitted_markdown):
        case 1:
            title = splitted_markdown[0]
            body = ""
        case 2:
            title, body = splitted_markdown
    return title.lstrip("# "), body.lstrip()


@dataclass
class MarkdownLink:
    """
    Represents a markdown:
    - link: https://www.markdownguide.org/basic-syntax/#links
    - image: https://www.markdownguide.org/basic-syntax/#images-1
    """

    text: str
    url: str
    # TODO: ignored for now
    # title: str = ""
    is_image: bool = False

    @property
    def is_web_link(self) -> bool:
        # not robust, but sufficient for now
        return self.url.startswith("http")

    @property
    def is_mail_link(self) -> bool:
        return self.url.startswith("mailto:")

    def __str__(self) -> str:
        prefix = "!" if self.is_image else ""
        return f"{prefix}[{self.text}]({self.url})"


class LinkExtractor(Treeprocessor):
    # We need to unescape manually. Reference: "UnescapeTreeprocessor"
    # https://github.com/Python-Markdown/markdown/blob/3.6/markdown/treeprocessors.py#L454
    RE = re.compile(rf"{markdown.util.STX}(\d+){markdown.util.ETX}")

    def _unescape(self, m: re.Match[str]) -> str:
        return "\\" + chr(int(m.group(1)))

    def unescape(self, text: str) -> str:
        return self.RE.sub(self._unescape, text)

    def run(self, root):
        # pylint: disable=no-member
        # TODO: Find a better way.
        self.md.images = []
        self.md.links = []
        for image in root.findall(".//img"):
            self.md.images.append(
                MarkdownLink(
                    self.unescape(image.get("alt")), image.get("src"), is_image=True
                )
            )
        for link in root.findall(".//a"):
            url = link.get("href")
            if (title := link.get("title")) is not None:
                # TODO: This is not robust against titles with single quotation marks.
                url += f' "{title}"'
            self.md.links.append(MarkdownLink(link.text, url))


class LinkExtractorExtension(Extension):
    def extendMarkdown(self, md):
        link_extension = LinkExtractor(md)
        md.treeprocessors.register(link_extension, "link_extension", 15)


MD = markdown.Markdown(extensions=[LinkExtractorExtension()])


def get_markdown_links(text: str) -> list:
    """
    >>> get_markdown_links("![](image.png)")
    [MarkdownLink(text='', url='image.png', is_image=True)]
    >>> get_markdown_links("![abc](image (1).png)")
    [MarkdownLink(text='abc', url='image (1).png', is_image=True)]
    >>> get_markdown_links("[mul](tiple) [links](...)") # doctest: +NORMALIZE_WHITESPACE
    [MarkdownLink(text='mul', url='tiple', is_image=False),
     MarkdownLink(text='links', url='...', is_image=False)]
    >>> get_markdown_links("![desc \\[reference\\]](Image.png){#fig:leanCycle}")
    [MarkdownLink(text='desc \\\\[reference\\\\]', url='Image.png', is_image=True)]
    >>> get_markdown_links('[link](internal "Example Title")')
    [MarkdownLink(text='link', url='internal "Example Title"', is_image=False)]
    >>> get_markdown_links('[link](#internal)')
    [MarkdownLink(text='link', url='#internal', is_image=False)]
    >>> get_markdown_links('[link](:/custom)')
    [MarkdownLink(text='link', url=':/custom', is_image=False)]
    >>> get_markdown_links('[weblink](https://duckduckgo.com)')
    [MarkdownLink(text='weblink', url='https://duckduckgo.com', is_image=False)]
    """
    # Based on: https://stackoverflow.com/a/29280824/7410886
    MD.convert(text)
    return MD.images + MD.links  # pylint: disable=no-member


WIKILINK_LINK_REGEX = re.compile(r"(!)?\[\[(.+?)(?:\|(.+?))?\]\]")


def get_wikilink_links(text: str) -> list:
    return WIKILINK_LINK_REGEX.findall(text)


def get_inline_tags(text: str, start_characters: list[str]) -> list[str]:
    """
    >>> get_inline_tags("# header", ["#"])
    []
    >>> get_inline_tags("### h3", ["#"])
    []
    >>> get_inline_tags("#tag", ["#"])
    ['tag']
    >>> get_inline_tags("#tag abc", ["#"])
    ['tag']
    >>> sorted(get_inline_tags("#tag @abc", ["#", "@"]))
    ['abc', 'tag']
    """
    # TODO: can possibly be combined with todoist.split_labels()
    tags = set()
    for word in text.split():
        if (
            any(word.startswith(char) for char in start_characters)
            and len(word) > 1
            # exclude words like "###"
            and any(char not in start_characters for char in word)
        ):
            tags.add(word[1:])
    return list(tags)


# markdown output formats:
# https://pandoc.org/chunkedhtml-demo/8.22-markdown-variants.html
# Don't use "commonmark_x". There would be too many noise.
PANDOC_OUTPUT_FORMAT = "markdown_strict+pipe_tables+backtick_code_blocks-raw_html"


def html_text_to_markdown(html_text: str) -> str:
    return pypandoc.convert_text(html_text, PANDOC_OUTPUT_FORMAT, format="html")


###########################################################
# folder operations
###########################################################


def get_single_child_folder(parent_folder: Path) -> Path:
    """If there is only a single subfolder, return it."""
    child_folders = [f for f in parent_folder.iterdir() if f.is_dir()]
    assert len(child_folders) == 1
    return child_folders[0]


def get_temp_folder() -> Path:
    """Return a temporary folder."""
    return Path(tempfile.gettempdir()) / f"joplin_export_{int(time.time() * 1000)}"


def extract_tar(input_: Path) -> Path:
    """Extract a tar file to a new temporary directory."""
    temp_folder = get_temp_folder()
    with tarfile.open(input_) as tar_ref:
        tar_ref.extractall(temp_folder)
    return temp_folder


def extract_zip(input_: Path, file_to_extract: str | None = None) -> Path:
    """Extract a zip file to a new temporary directory."""
    temp_folder = get_temp_folder()
    with zipfile.ZipFile(input_) as zip_ref:
        if file_to_extract is None:
            zip_ref.extractall(temp_folder)
        else:
            zip_ref.extract(file_to_extract, temp_folder)
    return temp_folder


def find_file_recursively(root_folder: Path, url: str) -> Path | None:
    potential_matches = list(root_folder.glob(f"**/{url}"))
    if not potential_matches:
        LOGGER.debug(f"Couldn't find match for resource {url}")
        return None
    if len(potential_matches) > 1:
        LOGGER.debug(f"Found too many matches for resource {url}")
    return potential_matches[0]


###########################################################
# datetime helpers
###########################################################


def get_ctime_mtime_ms(item: Path) -> dict:
    data = {}
    if (ctime_ms := int(item.stat().st_ctime * 1000)) > 0:
        data["user_created_time"] = ctime_ms
    if (mtime_ms := int(item.stat().st_mtime * 1000)) > 0:
        data["user_updated_time"] = mtime_ms
    return data


def datetime_to_ms(datetime_: dt.datetime) -> int:
    return int(datetime_.timestamp() * 1000)


def current_unix_ms() -> int:
    return datetime_to_ms(dt.datetime.now())


def date_to_unix_ms(date_: dt.date) -> int:
    # https://stackoverflow.com/a/61886944/7410886
    return datetime_to_ms(
        dt.datetime(year=date_.year, month=date_.month, day=date_.day)
    )


def iso_to_unix_ms(iso_time: str) -> int:
    return datetime_to_ms(dt.datetime.fromisoformat(iso_time))
