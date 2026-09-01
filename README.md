# Universal Local File Searcher

Search names or keywords across an entire folder of mixed file types —
spreadsheets, documents, presentations, PDFs, and more — from a single
search box. Everything runs 100% locally. No file contents are ever
uploaded, sent to an API, or leave your machine.

## Quick start (Windows)

1. Install Python 3.10+ from https://www.python.org/downloads/ if you don't
   already have it (check "Add python.exe to PATH" during install).
2. Double-click `run.bat`.
   - It creates a virtual environment, installs dependencies, and opens
     http://127.0.0.1:5000 in your browser automatically.
3. In the app: paste or browse to your main folder, click **Choose Main
   Folder & Index**, wait for indexing to finish, then search.

### Optional: enable `.doc` / `.ppt` (legacy Office) support

Old binary Word/PowerPoint files need an external converter since there's
no pure-Python reader for those formats. Install **LibreOffice**
(https://www.libreoffice.org/download/) to enable them. If it's missing,
those files show up under "Failed" with a message telling you exactly
what to install — the app never pretends to support something it can't
actually read.

## Supported formats (22)

| Category | Formats |
|---|---|
| Excel | `.xlsx`, `.xlsm`, `.xls` |
| Word | `.docx`, `.doc` (needs LibreOffice) |
| PowerPoint | `.pptx`, `.ppt` (needs LibreOffice) |
| PDF | `.pdf` |
| OpenDocument | `.ods`, `.odt` |
| CSV | `.csv`, `.tsv` |
| Text | `.txt`, `.log` |
| Data | `.json`, `.xml`, `.yaml`, `.yml` |
| Web | `.html`, `.htm` |
| Email | `.eml` |
| RTF | `.rtf` |

Every format preserves *where* a match was found: sheet/cell, page
number, slide number, table row/column, paragraph, JSON key path, XML
tag path, or email header/body line — never just "found in this file."

Not supported yet (by design): OCR / scanned PDFs, Markdown, `.pages`,
`.numbers`, `.key`, Google Sheets API, AI/semantic search, cloud services.

## Search features

- **Ranked relevance**: exact phrase match > all-terms match > filename
  match > partial match, in that order.
- **Filename search**: finds files by name even if the term never appears
  in the content (clearly labeled "Filename Match" vs "Content Match").
- **Filters**: restrict search to specific file-type categories, and to
  the current main folder (recursive) or just its top level.
- **Sort**: by relevance, file name, file type, file path, or match count.
- **Grouped, always-open results**: multiple matches in one file are
  grouped under a single card, with every match visible immediately —
  nothing is hidden behind a click.
- **Preview panel**: click any match to see it with surrounding context
  and quick actions (Open File / Open Folder / Copy Path).
- **Keyboard shortcuts**: `Ctrl+K` focuses search, `Enter` searches, `Esc`
  clears.

## Indexing settings

Open **⚙ Indexing settings** on the main screen:

- **Max file size (MB)** — skip files larger than this during indexing
  (default 200MB, 0 = no limit). Useful for huge exports or media-heavy
  folders where giant files would slow indexing without being what you're
  actually searching for. Skipped files are reported separately from
  failed/unsupported ones.
- **Extra folders to skip** — comma-separated folder names to exclude on
  top of the built-in defaults (`.git`, `node_modules`, etc).
- **Force full re-index** — rescanning the same folder is incremental by
  default (see below); check this to bypass that and re-parse every file
  from scratch, e.g. after upgrading the app or troubleshooting a parser.

Your last-used folder and these settings are remembered in your browser
(not shared anywhere) so you don't have to re-enter them next time. A
light/dark theme toggle is also available and remembered the same way.

## Incremental rescanning & parallel parsing

- **Rescan** re-indexes the *same* root folder incrementally: files whose
  modification time hasn't changed since the last run are left alone
  entirely (not re-read, not re-parsed), new/changed files are
  (re-)parsed, and files that were deleted from disk are removed from the
  index. Indexing a *different* folder (or checking "Force full
  re-index") always does a full, from-scratch index instead.
- Parsing runs across a small thread pool (up to 16 workers) instead of
  one file at a time, so indexing a folder with many files — lots of
  PDFs or Office documents especially — is noticeably faster. Database
  writes always happen on a single thread, so this doesn't affect
  correctness or ordering.

## How it works

```
Choose Folder
     ↓
Recursive scan of every file (skips oversized files per your settings)
     ↓
Same folder as last time and not "Force full re-index"?
     ↓ yes                                    ↓ no
Skip files with an unchanged mtime      Wipe index, parse everything
     ↓                                        ↓
Parse remaining/changed files in parallel (thread pool)
     ↓
Extract content → normalize into a Record (sheet/cell/row/column/page/slide/location)
     ↓
Store in SQLite (file_index.sqlite3) + FTS5 full-text index
     ↓
Search box queries the FTS5 index, then ranks/filters/groups results in Python
```

- `parsers/` — one file per format, all implementing the same
  `BaseParser.parse(file_path) -> ParseResult` interface. Adding a new
  format later means adding one new parser file and registering it (plus
  a category/icon) in `parsers/__init__.py` — nothing else changes.
- `database.py` — SQLite schema, FTS5 index, and the ranking/filtering/
  grouping search logic, plus `get_file_mtimes`/`delete_files` used for
  incremental rescans.
- `indexer.py` — recursive folder walk, size/skip-folder settings,
  incremental-vs-full decision, and a thread pool that dispatches each
  file to its parser. One bad file never stops the rest of indexing.
- `app.py` — Flask API + serves the single-page UI in `static/index.html`.

## Files & folders

```
UniversalFileSearcher/
├── run.bat                    <- double-click to start on Windows
├── requirements.txt
├── app.py                     <- Flask server & API
├── database.py                <- SQLite + FTS5 search index + ranking
├── indexer.py                 <- recursive scan + incremental rescan + parallel parsing
├── folder_picker.py           <- native folder-choose dialog helper
├── parsers/
│   ├── base_parser.py          <- shared interface (Record, ParseResult)
│   ├── xlsx_parser.py / xls_parser.py
│   ├── pdf_parser.py
│   ├── csv_parser.py           <- also handles .tsv
│   ├── docx_parser.py / doc_parser.py
│   ├── pptx_parser.py / ppt_parser.py
│   ├── ods_parser.py / odt_parser.py
│   ├── rtf_parser.py
│   ├── txt_parser.py           <- .txt and .log
│   ├── json_parser.py / xml_parser.py / yaml_parser.py
│   ├── html_parser_local.py
│   └── eml_parser.py
└── static/
    └── index.html              <- single-page UI
```

A `file_index.sqlite3` database is created next to `app.py` the first
time you index a folder — this is your local search index and never
leaves your machine.

## Running manually (any OS)

```bash
pip install -r requirements.txt
python app.py
```

Then open http://127.0.0.1:5000
