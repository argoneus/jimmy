# jimmy

Tool to import your notes to Joplin.

:exclamation: Should only be used if the built-in import of Joplin doesn't work.

:exclamation: Make sure your data is imported properly after the script finished.

[![build](https://github.com/marph91/jimmy/actions/workflows/build.yml/badge.svg)](https://github.com/marph91/jimmy/actions/workflows/build.yml)
[![lint](https://github.com/marph91/jimmy/actions/workflows/lint.yml/badge.svg)](https://github.com/marph91/jimmy/actions/workflows/lint.yml)
[![tests](https://github.com/marph91/jimmy/actions/workflows/tests.yml/badge.svg)](https://github.com/marph91/jimmy/actions/workflows/tests.yml)

## Usage

This script requires that the webclipper in Joplin is running. It will connect to Joplin at the first execution.

Grab the executable from the [release page](https://github.com/marph91/jimmy/releases/latest).

```bash
# import a single file supported by pandoc
jimmy libre_office_document.odt

# import multiple files
jimmy plaintext.txt markdown.md

# import all files in a folder
jimmy path/to/folder

# Import all files in a folder. Delete all notes before. I. e. start with a clean workspace.
jimmy path/to/folder --clear-notes

# import a clipto export
jimmy clipto_backup_240401_105154.json --app clipto

# import a Google Keep export
jimmy takeout-20240401T160516Z-001.zip --app google_keep
```

After importing, the notes should be available in a new Joplin notebook named like `YYYY-MM-DD HH:MM:SS - Import`.

## Supported Formats

- Every format that is supported by pandoc. Some formats may need some tweaking, though.
- txt

## Supported Apps

There are many more apps supported implicitly if they export text files to a folder. Just specify the folder and try the import (see [usage](#usage)).

| App | Internal App Name | Export Instructions |
| --- | --- | --- |
| [clipto](https://clipto.pro/) | clipto | [mobile only](https://github.com/clipto-pro/Desktop/issues/21#issuecomment-537401330) |
| [Dynalist](https://dynalist.io/) | dynalist | [link](https://help.dynalist.io/article/79-back-up-your-data) |
| [Google Keep](https://keep.google.com) | google_keep | [via Takeout](https://www.howtogeek.com/694042/how-to-export-your-google-keep-notes-and-attachments/) |
| [Joplin](https://joplinapp.org/) | joplin | [link](https://joplinapp.org/help/apps/import_export/#exporting) |
| [Nimbus Note / FuseBase](https://nimbusweb.me/note/) | nimbus_note | [link](https://nimbusweb.me/guides/settings/how-to-export-notes-to-html-or-pdf/) |
| [Notion](https://www.notion.so/) | notion | [link](https://www.notion.so/de-de/help/export-your-content) [1] |
| [Obsidian](https://obsidian.md/) | obsidian | |
| [Simplenote](https://simplenote.com/) | simplenote | [link](https://simplenote.com/help/#export) |
| [Standard Notes](https://standardnotes.com/) | standard_notes | [link](https://standardnotes.com/help/14/how-do-i-create-and-import-backups-of-my-standard-notes-data) [2] |
| [Synology Note Station](https://www.synology.com/en-global/dsm/feature/note_station) | synology_note_stattion | [link](https://kb.synology.com/en-global/DSM/help/NoteStation/note_station_managing_notes?version=7#t7) |
| [TiddlyWiki](https://tiddlywiki.com/) | tiddlywiki | [JSON only](https://tiddlywiki.com/static/How%2520to%2520export%2520tiddlers.html) [3] |
| [Todo.txt](http://todotxt.org/) | todo_txt | |
| [Todoist](https://todoist.com/) | todoist | [link](https://todoist.com/de/help/articles/introduction-to-backups-ywaJeQbN) [4] |
| [Toodledo](https://www.toodledo.com/) | toodledo | [link](https://www.toodledo.com/tools/import_export.php) [5] |
| [Zoho Notebook](https://www.zoho.com/notebook/) | zoho_notebook | [link](https://help.zoho.com/portal/en/kb/notebook/import-and-export/articles/export-all-your-notecards-from-notebook) [6] |

What is migrated (in most cases)?

- Notes incl. title, content and metadata
- Tags / Labels
- Resources / Attachments
- Internal note links
- Markdown Front Matter
- Inline tags

If something else is not working, please check the issues first. If you can't find anything, feel free to create a new issue. It might be just not implemented yet or a regression. On the other side, the exported data can be sparse. In that case it's not possible to transfer the data with this tool.

---

[1] Choose "Markdown and CSV" and uncheck "Create folder for sub-pages" when exporting.

[2] Note links, attachments and folders are not implemented, since they require a subscription.

[3] Note content is imported in TiddlyWiki's [WikiText format](https://tiddlywiki.com/#WikiText) and not converted to markdown.

[4]

- Uncheck "Use relative data" when exporting.
- Finished todo's are not exported at all.
- Subtasks are converted to regular notes. I. e. they lose their indentation.
- Markdown is not rendered in note titles.

[5] [subtasks](https://www.toodledo.com/info/subtasks.php) and [files](https://www.toodledo.com/organize/files.php) are not implemented, since they require a subscription.

[6]

- Export as HTML.
- Checklists are converted to plain lists. This might change with a newer pandoc version.

## Why Joplin's data API is used?

- Plain markdown: [Tags aren't supported](https://discourse.joplinapp.org/t/import-tags-from-markdown-files/1752).
- JEX: Requires to work with some internals that I would rather not touch.
- Joplin's data API: Straight forward to use and supports all needed functions.
