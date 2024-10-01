"""Common Markdown functions."""

from dataclasses import dataclass, field
import logging
import re

import markdown
from markdown.treeprocessors import Treeprocessor
from markdown.extensions import Extension
import pypandoc


LOGGER = logging.getLogger("jimmy")


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
class MarkdownTable:
    """Construct a Markdown table from lists."""

    header_rows: list[list[str]] = field(default_factory=list)
    data_rows: list[list[str]] = field(default_factory=list)
    caption: str = ""

    def create_md(self) -> str:
        # column sanity check
        columns = [len(row) for row in self.header_rows + self.data_rows]
        if len(set(columns)) not in (0, 1):
            LOGGER.warning(f"Amount of columns differs: {columns}")

        def create_md_row(cells: list[str]) -> str:
            return "| " + " | ".join(cells) + " |"

        rows_md = []
        for row in self.header_rows:
            rows_md.append(create_md_row(row))
        if self.header_rows:
            separator = ["---"] * len(self.header_rows[0])
            rows_md.append(create_md_row(separator))
        for row in self.data_rows:
            rows_md.append(create_md_row(row))

        caption = self.caption + "\n\n" if self.caption else ""
        return caption + "\n".join(rows_md) + "\n"


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
                # TODO: This is not robust against titles with quotation marks.
                if url:
                    url += f' "{title}"'
                else:
                    url = title  # don't add a title if there is no url
            self.md.links.append(MarkdownLink(link.text, url))


class LinkExtractorExtension(Extension):
    def extendMarkdown(self, md):  # noqa: N802
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
    # pylint: disable=no-member
    MD.convert(text)
    try:
        md_images = [*MD.images]  # new list, because it gets cleared
        MD.images.clear()
    except AttributeError:
        md_images = []
    try:
        md_links = [*MD.links]
        MD.links.clear()
    except AttributeError:
        md_links = []
    return md_images + md_links


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


def markup_to_markdown(text: str, format_: str = "html") -> str:
    return pypandoc.convert_text(text, PANDOC_OUTPUT_FORMAT, format=format_)