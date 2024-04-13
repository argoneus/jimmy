"""Convert obsidian notes to the intermediate format."""

from pathlib import Path
from urllib.parse import unquote

import frontmatter

import common
import converter
import intermediate_format as imf


def handle_markdown_links(body: str, root_folder: Path) -> tuple[list, list]:
    # markdown links
    note_links = []
    resources = []
    for file_prefix, description, url in common.get_markdown_links(body):
        if url.startswith("http"):
            continue  # web link
        original_text = f"{file_prefix}[{description}]({url})"
        if url.endswith(".md"):
            # internal link
            linked_note_id = Path(unquote(url)).stem
            note_links.append(imf.NoteLink(original_text, linked_note_id, description))
        else:
            # resource
            resource_path = common.find_file_recursively(root_folder, url)
            if resource_path is None:
                continue
            resources.append(imf.Resource(resource_path, original_text, description))
    return resources, note_links


def handle_wikilink_links(body: str, root_folder: Path) -> tuple[list, list]:
    # https://help.obsidian.md/Linking+notes+and+files/Internal+links
    # wikilink links
    note_links = []
    resources = []
    for file_prefix, url, description in common.get_wikilink_links(body):
        alias = "" if description.strip() == "" else f"|{description}"
        original_text = f"{file_prefix}[[{url}{alias}]]"
        if file_prefix:
            # resource
            resource_path = common.find_file_recursively(root_folder, url)
            if resource_path is None:
                continue
            resources.append(
                imf.Resource(resource_path, original_text, description or url)
            )
        else:
            # internal link
            note_links.append(imf.NoteLink(original_text, url, description or url))
    return resources, note_links


class Converter(converter.BaseConverter):
    def convert(self, file_or_folder: Path):
        self.root_path = file_or_folder
        self.convert_folder(file_or_folder, self.root_notebook)

    def convert_folder(self, folder: Path, parent: imf.Notebook):
        for item in folder.iterdir():
            if item.is_dir() and item.name == ".obsidian":
                continue  # ignore the internal obsidian folder
            if item.is_file():
                if item.suffix != ".md":
                    continue
                note_links = []
                resources = []
                body = item.read_text()

                # Resources can be anywhere:
                # https://help.obsidian.md/Editing+and+formatting/Attachments#Change+default+attachment+location
                wikilink_resources, wikilink_note_links = handle_wikilink_links(
                    body, self.root_path
                )
                markdown_resources, markdown_note_links = handle_markdown_links(
                    body, self.root_path
                )
                resources.extend(wikilink_resources + markdown_resources)
                note_links.extend(wikilink_note_links + markdown_note_links)

                # https://help.obsidian.md/Editing+and+formatting/Tags
                inline_tags = common.get_inline_tags(body, ["#"])

                # frontmatter tags
                # https://help.obsidian.md/Editing+and+formatting/Properties#Default+properties
                frontmatter_ = frontmatter.loads(body)
                frontmatter_tags = frontmatter_.get("tags", [])

                # aliases seem to be only used in the link description
                # frontmatter_.get("aliases", [])

                parent.child_notes.append(
                    imf.Note(
                        {
                            "title": item.stem,
                            "body": body,
                            "source_application": self.app,
                        },
                        tags=[
                            imf.Tag({"title": tag}, tag)
                            for tag in inline_tags + frontmatter_tags
                        ],
                        resources=resources,
                        note_links=note_links,
                        original_id=item.stem,
                    )
                )
            else:
                new_parent = imf.Notebook(
                    {"title": item.name, **common.get_ctime_mtime_ms(item)}
                )
                self.convert_folder(item, new_parent)
                parent.child_notebooks.append(new_parent)
