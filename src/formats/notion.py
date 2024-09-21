"""Convert notion notes to the intermediate format."""

import io
from pathlib import Path
from urllib.parse import unquote
import zipfile

import common
import converter
import intermediate_format as imf


class Converter(converter.BaseConverter):
    accepted_extensions = [".zip"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.id_path_map = {".": "."}

    def prepare_input(self, input_: Path) -> Path:
        temp_folder = common.get_temp_folder()

        # unzip nested zip file in notion format
        with zipfile.ZipFile(input_) as zip_ref:
            for nested_zip_name in zip_ref.namelist():
                with zip_ref.open(nested_zip_name) as nested_zip:
                    nested_zip_filedata = io.BytesIO(nested_zip.read())
                    with zipfile.ZipFile(nested_zip_filedata) as nested_zip_ref:
                        nested_zip_ref.extractall(temp_folder)

        # Flatten folder structure. I. e. move all files to root directory.
        # https://stackoverflow.com/a/50368037/7410886
        for item in temp_folder.iterdir():
            if item.is_dir():
                for file_ in item.iterdir():
                    file_.rename(file_.parents[1] / file_.name)
                item.rmdir()
        return temp_folder

    def convert_directory(self, parent_notebook):
        assert self.root_path is not None
        relative_parent_path = self.id_path_map[parent_notebook.original_id]

        for item in (self.root_path / relative_parent_path).iterdir():
            if item.is_file() and item.suffix.lower() != ".md":
                continue
            # id is appended to filename
            title, _ = item.name.rsplit(" ", 1)

            # propagate the path through all parents
            # separator is always "/"
            _, id_ = item.stem.rsplit(" ", 1)
            if parent_notebook.original_id != ".":
                self.id_path_map[id_] = relative_parent_path + "/" + item.name
            else:
                # TODO: check if "./" works on windows
                self.id_path_map[id_] = item.name

            if item.is_dir():
                child_notebook = imf.Notebook(title, original_id=id_)
                parent_notebook.child_notebooks.append(child_notebook)
                self.convert_directory(child_notebook)
                continue

            self.logger.debug(f'Converting note "{title}"')
            # first line is title, second is whitespace
            body = "\n".join(item.read_text(encoding="utf-8").split("\n")[2:])

            # find links
            resources = []
            note_links = []
            for link in common.get_markdown_links(body):
                if link.is_web_link or link.is_mail_link:
                    continue  # keep the original links
                unquoted_url = unquote(link.url)
                if link.url.endswith(".md"):
                    # internal link
                    _, linked_note_id = Path(unquoted_url).stem.rsplit(" ", 1)
                    note_links.append(
                        imf.NoteLink(str(link), linked_note_id, link.text)
                    )
                elif (self.root_path / unquoted_url).is_file():
                    # resource
                    resources.append(
                        imf.Resource(
                            self.root_path / unquoted_url, str(link), link.text
                        )
                    )
                else:
                    self.logger.debug(f'Unhandled link "{link}"')

            note_imf = imf.Note(
                title,
                body,
                source_application=self.format,
                original_id=id_,
                resources=resources,
                note_links=note_links,
            )
            parent_notebook.child_notes.append(note_imf)

    def convert(self, file_or_folder: Path):
        self.root_path = self.prepare_input(file_or_folder)
        self.root_notebook.original_id = "."
        self.convert_directory(self.root_notebook)
