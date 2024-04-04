"""Importer for many (note) formats to Joplin."""

import argparse
from datetime import datetime
import importlib
from pathlib import Path
import pkgutil
from typing import Tuple

import pypandoc

import api_helper
import apps
import importer
from intermediate_format import Note, Notebook


# https://stackoverflow.com/a/287944/7410886
COLOR_SUCCESS = "\033[92m"
COLOR_FAIL = "\033[91m"
COLOR_END = "\033[0m"


def convert_folder(folder: Path, parent: Notebook) -> Tuple[Notebook, list]:
    """Default conversion function for folders."""
    for item in folder.iterdir():
        if item.is_file():
            try:
                parent = convert_file(item, parent)
                print(f"- {COLOR_SUCCESS}{item.name}{COLOR_END}")
            except Exception as exc:  # pylint: disable=broad-except
                print(f"- {COLOR_FAIL}{item.name}{COLOR_END}: {str(exc).strip()[:120]}")
        else:
            new_parent = convert_folder(
                item,
                Notebook(
                    {
                        "title": item.name,
                        "user_created_time": item.stat().st_ctime * 1000,
                        "user_updated_time": item.stat().st_mtime * 1000,
                    }
                ),
            )
            parent.child_notebooks.append(new_parent)
    return parent


def convert_file(file_: Path, parent: Notebook) -> Tuple[Notebook, list]:
    """Default conversion function for files. Uses pandoc directly."""
    if file_.suffix in (".md", ".txt"):
        note_body = file_.read_text()
    else:
        # markdown output formats: https://pandoc.org/chunkedhtml-demo/8.22-markdown-variants.html
        # Joplin follows CommonMark: https://joplinapp.org/help/apps/markdown
        note_body = pypandoc.convert_file(file_, "commonmark_x")
    parent.child_notes.append(
        Note(
            {
                "title": file_.stem,
                "body": note_body,
                "user_created_time": file_.stat().st_ctime * 1000,
                "user_updated_time": file_.stat().st_mtime * 1000,
                "source_application": "joplin_custom_importer",
            }
        )
    )
    return parent


def convert_all_inputs(inputs, app):
    # parent notebook
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    source_app = "Joplin Custom Importer" if app is None else app
    parent = Notebook({"title": f"{now} - Import from {source_app}"})
    for single_input in inputs:
        # Convert the input data to an intermediate representation
        # that can be used by the importer later.
        # Try to use an app specific converter. If there is none,
        # fall back to the default converter.
        try:
            module = importlib.import_module(f"apps.{app}")
            conversion_function = module.convert
        except ModuleNotFoundError:
            conversion_function = (
                convert_file if single_input.is_file() else convert_folder
            )
        # TODO: children are added to the parent node / node tree implicitly
        note_tree = conversion_function(single_input, parent)
    return note_tree


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "input", type=Path, nargs="+", help="The input file(s) or folder(s)."
    )
    # specific apps that need a special handling
    parser.add_argument(
        "--app",
        choices=[module.name for module in pkgutil.iter_modules(apps.__path__)],
        help="The source application.",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Don't connect to the Joplin API."
    )
    args = parser.parse_args()

    if not args.dry_run:
        # create the connection to Joplin first to fail fast in case of a problem
        api = api_helper.get_api()

    note_tree = convert_all_inputs(args.input, args.app)

    if not args.dry_run:
        # import to Joplin
        joplin_importer = importer.JoplinImporter(api)
        joplin_importer.import_notebook(note_tree)


if __name__ == "__main__":
    main()
