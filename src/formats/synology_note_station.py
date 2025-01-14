"""Convert Synology Note Station notes to the intermediate format."""

from dataclasses import dataclass, field
import difflib
import json
from pathlib import Path
import re

from bs4 import BeautifulSoup

import common
import converter
import intermediate_format as imf
import markdown_lib


@dataclass
class Attachment:
    """Represents a Note Station attachment."""

    filename: Path
    md5: str
    refs: list[str] = field(default_factory=list)
    titles: list[str] = field(default_factory=list)


def streamline_html(content_html: str) -> str:
    # hack: In the original data, the attachment_id is stored in the
    # "ref" attribute. Mitigate by storing it in the "src" attribute.
    content_html = re.sub("<img.*?ref=", "<img src=", content_html,flags=re.DOTALL)

    # another hack: make the first row of a table to the header
    soup = BeautifulSoup(content_html, "html.parser")
    for table in soup.find_all("table"):
        # Remove all divs, since they cause pandoc to fail converting the table.
        # https://stackoverflow.com/a/32064299/7410886
        for div in table.find_all("div"):
            div.unwrap()

        for row_index, row in enumerate(table.find_all("tr")):
            for td in row.find_all("td"):
                # tables seem to be headerless always
                # make first row to header
                if row_index == 0:
                    td.name = "th"

        # remove "tbody"
        if (body := table.find("tbody")) is not None:
            body.unwrap()

    return str(soup)


class Converter(converter.BaseConverter):
    accepted_extensions = [".nsx"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.available_resources = []

    def find_parent_notebook(self, parent_id: str) -> imf.Notebook:
        for notebook in self.root_notebook.child_notebooks:
            if notebook.original_id == parent_id:
                return notebook
        self.logger.debug(f"Couldn't find parent notebook with id {parent_id}")
        return self.root_notebook

    def handle_markdown_links(
        self, title: str, body: str, note_id_title_map: dict
    ) -> tuple[imf.Resources, imf.NoteLinks]:
        resources = []
        note_links = []
        for link in markdown_lib.common.get_markdown_links(body):
            if link.is_web_link or link.is_mail_link:
                continue  # keep the original links

            if link.url.startswith("notestation://"):
                # internal link
                # Linked note ID doesn't correspond to the real note ID. For example:
                # - filename: note_VW50aXRsZWQgTm90ZTE2MTM0MDQ5NDQ2NzY=
                # - link: notestation://remote/self/1026_1547KOMP551EN92DDB4FIOFUNK
                # TODO: Is there a connection between the ID's?
                # _, linked_note_id = link.url.rsplit("/", 1)

                # try to map by title similarity
                def get_match_ratio(id_, link_text=link.text):
                    return difflib.SequenceMatcher(
                        None, link_text, note_id_title_map[id_]
                    ).ratio()

                best_match_id = max(note_id_title_map, key=get_match_ratio)
                note_links.append(imf.NoteLink(str(link), best_match_id, link.text))
            else:
                # resource
                # Find resource file by "ref".
                matched_resources = [
                    res for res in self.available_resources if link.url in res.refs
                ]
                if len(matched_resources) != 1:
                    self.logger.debug(
                        "Found too less or too many resources: "
                        f"{len(matched_resources)} "
                        f'(note: "{title}", original link: "{link}")'
                    )
                    continue
                resource = matched_resources[0]
                for resource_title in resource.titles:
                    resources.append(
                        imf.Resource(
                            resource.filename, str(link), link.text or resource_title
                        )
                    )
        return resources, note_links

    def convert_notebooks(self, input_json: dict):
        for notebook_id in input_json["notebook"]:
            notebook = json.loads(
                (self.root_path / notebook_id).read_text(encoding="utf-8")
            )

            self.root_notebook.child_notebooks.append(
                imf.Notebook(notebook["title"], original_id=notebook_id)
            )

    def map_resources_by_hash(self, note: dict) -> imf.Resources:
        resources: imf.Resources = []
        if note.get("attachment") is None:
            return resources
        for note_resource in note["attachment"].values():
            # TODO: access directly by filename (e. g. "file_<md5>")
            for file_resource in self.available_resources:
                if note_resource["md5"] == file_resource.md5:
                    if (ref := note_resource.get("ref")) is not None:
                        # The same resource can be linked multiple times.
                        file_resource.refs.append(ref)
                        file_resource.titles.append(note_resource["name"])
                    else:
                        # The attachment is not referenced. Add it here.
                        # Referenced attachments are added later.
                        resources.append(
                            imf.Resource(
                                file_resource.filename, title=note_resource["name"]
                            )
                        )
                    break
        return resources

    def postprocess_onenote_notes(self, note_content: str) -> str:
        # remove all blank lines.  With OneNote converted notes in Synology Notes,
        # legitimate blank lines from the original note content contain a space.
        despaced_content = re.compile(r"\n+", re.UNICODE).sub('\n', note_content)
        # first line is the title, so use h1
        processed_content = f'# {despaced_content}'
        # make the next two lines bold (date and time)
        processed_content = re.sub(r"\n(.*)",r"\n**\1**", processed_content, 2, re.UNICODE)
        # add a blank line after the title, date, and time header
        processed_content = re.sub(r"(\*\*[0-9]+:[0-9]+\s+[A|P]M\*\*)\n", r"\1\n\n", processed_content, 1, re.UNICODE)
        # convert "&gt;" and "&lt;" to > and <
        processed_content = re.sub(r"&gt;", r">", processed_content, flags=re.UNICODE)
        processed_content = re.sub(r"&lt;", r"<", processed_content,re.UNICODE)
        return processed_content

    def deduplicate_note_title(self, parent_notebook: imf.Notebook , note_imf: imf.Note, includes_date: bool = False, max_name_length: int = 50):
        # ensure note title is unique
        if note_imf.title[:max_name_length] in [note.title[:max_name_length] for note in parent_notebook.child_notes]:
            # title already exists, so need to de-dupe
            if includes_date:
                self.logger.warning(f'Note already exists, so adding created timestamp (H-M): {note_imf.title}')
                note_imf.title += " " + note_imf.created.strftime("%H%M")
            else:
                # truncate string's last 10 chars before adding date
                if len(note_imf.title) >= max_name_length:
                    self.logger.warning(f"Truncating title as length exceeds {max_name_length}")
                    note_imf.title = note_imf.title[:max_name_length - 11]
                self.logger.warning(f'Note already exists, so adding created timestamp (m-d-Y): {note_imf.title}')
                note_imf.title += " " + note_imf.created.strftime("%m-%d-%Y")
                self.deduplicate_note_title(parent_notebook, note_imf, includes_date = True)
        else:
            return

    def clean_task_note(self, note_content: str) -> str:
       # fix formatting of some recent task notes due to dark mode reader browser plugin
       # remove all bold and existing headers (#)
       debold_content = re.sub(r"(\*\*)|(#+\s)", r"", note_content, re.UNICODE)
       # ensure header is h1
       hdr_content = re.sub(r"(.*)\n", r"# \1\n", debold_content, 1, re.UNICODE)
       # ensure week lines are headers
       hdr_content = re.sub(r"(First|Second|Third|Fourth|Fifth)\s*([W|w]eek)", r"# \1 \2", hdr_content, re.UNICODE)
       return hdr_content

    @common.catch_all_exceptions
    def convert_note(self, note_id, note_id_title_map):
        note = json.loads((self.root_path / note_id).read_text(encoding="utf-8"))

        if note["parent_id"].rsplit("_")[-1] == "#00000000":
            self.logger.debug(f"Ignoring note in trash \"{note['title']}\"")
            return
        title = note["title"]
        self.logger.debug(f'Converting note "{title}"')

        # resources / attachments
        resources = self.map_resources_by_hash(note)

        note_links: imf.NoteLinks = []
        onenote = False
        if (content_html := note.get("content")) is not None:
            content_html = streamline_html(content_html)
            # replace empty divs with a space for easier postprocessing and to retain original
            # Synology Notes format line spacing.
            content_html = re.sub(r"<div></div>", "<div>&nbsp;</div>", content_html, re.UNICODE)
            content_markdown = markdown_lib.common.markup_to_markdown(content_html)
            content_md_cleaned = ""
            if re.search(r"Created with OneNote", content_markdown):
                onenote = True
                #self.logger.debug(f"Handling OneNote note: {title}")
                content_md_cleaned = self.postprocess_onenote_notes(content_markdown)
            else:
                content_md_cleaned = re.compile(r"\n+", re.UNICODE).sub('\n', content_markdown)
                # convert "&gt;" and "&lt;" to > and <
                content_md_cleaned = re.sub(r"&gt;", r">", content_md_cleaned, flags=re.UNICODE)
                content_md_cleaned = re.sub(r"&lt;", r"<", content_md_cleaned,re.UNICODE)
                if re.search(r"First (W|w)eek", content_md_cleaned):
                    self.logger.debug(f"Cleaning task note: {title}")
                    content_md_cleaned = self.clean_task_note(content_md_cleaned)
                #content_md_cleaned = content_markdown
             # note title only needed for debug message
            resources_referenced, note_links = self.handle_markdown_links(
                note["title"], content_md_cleaned, note_id_title_map
            )
            resources.extend(resources_referenced)
            body = content_md_cleaned
        else:
            body = ""

        note_imf = imf.Note(
            title,
            body,
            created=common.timestamp_to_datetime(note["ctime"]),
            updated=common.timestamp_to_datetime(note["mtime"]),
            source_application=self.format,
            tags=[imf.Tag(imf.normalize_obsidian_tag(tag)) for tag in note.get("tag", [])],
            resources=resources,
            note_links=note_links,
            original_id=note_id,
        )
        if onenote:
            note_imf.tags.append(imf.Tag("OneNote"))
        #self.logger.debug(f'Note tags: {note_imf.tags}')
        if (latitude := note.get("latitude")) is not None:
            note_imf.latitude = latitude
        if (longitude := note.get("longitude")) is not None:
            note_imf.longitude = longitude

        parent_notebook = self.find_parent_notebook(note["parent_id"])
#        if note_imf.title in [note.title for note in parent_notebook.child_notes]:
#            # title already exists, so need to de-dupe
#            self.logger.warning(f'Note already exists, so adding created timestamp: {note_imf.title}')
#            note_imf.title += " " + note_imf.created.strftime("%m-%d-%Y")
        self.deduplicate_note_title(parent_notebook, note_imf)
        parent_notebook.child_notes.append(note_imf)

    def convert(self, file_or_folder: Path):
        # pylint: disable=too-many-locals
        input_json = json.loads(
            (self.root_path / "config.json").read_text(encoding="utf-8")
        )

        # TODO: What is input_json["shortcut"]?
        # TODO: Are nested notebooks possible?

        self.convert_notebooks(input_json)

        # dirty hack: Only option to map the files from file system
        # to the note content is by MD5 hash.
        for item in sorted(self.root_path.iterdir()):
            if item.is_file() and item.stem.startswith("file_"):
                if item.stem.startswith("file_thumb"):
                    continue  # ignore thumbnails
                # Don't use the actual hash: hashlib.md5(item.read_bytes()).hexdigest()
                # It can change. So we need to take the hash from the filename.
                self.available_resources.append(
                    Attachment(item, item.stem.split("_")[-1])
                )

        # for internal links, we need to store the note titles
        note_id_title_map = {}
        for note_id in input_json["note"]:
            note = json.loads((self.root_path / note_id).read_text(encoding="utf-8"))
            note_id_title_map[note_id] = note["title"]

        for note_id in input_json["note"]:
            self.convert_note(note_id, note_id_title_map)
