"""
indexer.py

Drives the full indexing workflow:

    Choose Folder -> Scan all files -> Detect file type -> Select parser
    -> Extract content -> Normalize content -> Store in SQLite
    -> Build search index -> Ready

Runs in a background thread so the UI can poll progress without blocking.

Two indexing modes:
  - Full index: every file is parsed from scratch and the database is
    wiped first. Used the first time a folder is indexed, whenever a
    *different* folder is chosen, or when "Force full re-index" is
    checked.
  - Incremental rescan: used when re-indexing the same root folder. Files
    whose modification time hasn't changed since the last run are left
    alone (their existing rows/records stay as-is); only new or changed
    files are (re-)parsed, and files that no longer exist on disk are
    removed. This makes routine rescans of a large folder dramatically
    faster.

Parsing itself is parallelized across a small thread pool -- most parser
libraries (PyMuPDF, lxml, openpyxl, etc.) release the GIL during their
underlying C/IO work, so this meaningfully speeds up indexing a folder
with many files, especially PDFs and Office documents. Actual database
writes always happen on the indexer's own thread, so SQLite is only ever
touched from one place.

Configurable settings (all optional, sensible defaults):
  - max_file_size_mb: skip files larger than this (huge files can be slow
    to parse and are rarely what someone is searching for -- default 200MB,
    0/None disables the limit)
  - extra_skip_dirs: additional folder names to skip during the recursive
    scan, on top of the built-in defaults (.git, node_modules, etc.)
  - force_full: ignore the incremental-rescan optimization and re-parse
    every file, even ones that look unchanged
"""

import os
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed

from parsers import get_parser_for
from database import Database

# Directories that are never useful to scan and can be huge / cause noise.
DEFAULT_SKIP_DIR_NAMES = {".git", "node_modules", "__pycache__", "$RECYCLE.BIN", "System Volume Information"}

DEFAULT_MAX_FILE_SIZE_MB = 200

# Parsing is mostly IO/C-extension bound, so a modest thread pool speeds up
# indexing folders with many files without overwhelming the machine.
MAX_PARSE_WORKERS = min(16, (os.cpu_count() or 4) * 2)

# A file's mtime is considered unchanged (and therefore skippable during an
# incremental rescan) if it differs by less than this many seconds. A small
# tolerance avoids false "changed" detections from filesystem float rounding.
MTIME_TOLERANCE_SECONDS = 0.5


class IndexProgress:
    """Thread-safe progress/status shared with the Flask app for polling."""
    def __init__(self):
        self._lock = threading.Lock()
        self.reset()

    def reset(self):
        with self._lock:
            self.status = "idle"  # idle | scanning | indexing | ready | error
            self.folder = None
            self.mode = None  # "full" | "incremental"
            self.total_files_found = 0
            self.processed = 0
            self.indexed = 0
            self.failed = 0
            self.unsupported = 0
            self.skipped = 0
            self.unchanged = 0
            self.current_file = None
            self.error = None

    def snapshot(self):
        with self._lock:
            return {
                "status": self.status,
                "folder": self.folder,
                "mode": self.mode,
                "total_files_found": self.total_files_found,
                "processed": self.processed,
                "indexed": self.indexed,
                "failed": self.failed,
                "unsupported": self.unsupported,
                "skipped": self.skipped,
                "unchanged": self.unchanged,
                "current_file": self.current_file,
                "error": self.error,
            }

    def update(self, **kwargs):
        with self._lock:
            for k, v in kwargs.items():
                setattr(self, k, v)


class Indexer:
    def __init__(self, db: Database):
        self.db = db
        self.progress = IndexProgress()
        self._thread = None

    def start_indexing(self, folder_path: str, max_file_size_mb=DEFAULT_MAX_FILE_SIZE_MB,
                        extra_skip_dirs=None, force_full=False):
        """Kick off indexing in a background thread. Returns immediately."""
        if self._thread and self._thread.is_alive():
            return False, "Indexing already in progress"
        if not os.path.isdir(folder_path):
            return False, f"Folder not found: {folder_path}"

        self.progress.reset()
        self._thread = threading.Thread(
            target=self._run,
            args=(folder_path, max_file_size_mb, extra_skip_dirs or [], force_full),
            daemon=True,
        )
        self._thread.start()
        return True, "Indexing started"

    def _run(self, folder_path: str, max_file_size_mb, extra_skip_dirs, force_full: bool):
        try:
            abs_folder = os.path.abspath(folder_path)
            previous_root = self.db.get_meta("root_folder")
            incremental = (not force_full) and previous_root == abs_folder

            self.progress.update(status="scanning", folder=folder_path,
                                  mode="incremental" if incremental else "full")

            existing_mtimes = self.db.get_file_mtimes() if incremental else {}
            if not incremental:
                self.db.reset()

            skip_dirs = set(DEFAULT_SKIP_DIR_NAMES) | {d.strip() for d in extra_skip_dirs if d.strip()}
            max_bytes = int(max_file_size_mb * 1024 * 1024) if max_file_size_mb and max_file_size_mb > 0 else None

            all_files = list(_walk_files(folder_path, skip_dirs))
            self.progress.update(total_files_found=len(all_files), status="indexing")

            indexed = failed = unsupported = skipped = unchanged = 0

            def counts_processed():
                return indexed + failed + unsupported + skipped + unchanged

            # Decide up-front which files can be skipped because they're
            # unchanged since the last run of this same folder -- these
            # never need to touch a parser at all.
            to_process = []
            for file_path in all_files:
                if incremental:
                    try:
                        mtime = os.path.getmtime(file_path)
                    except OSError:
                        mtime = None
                    prev_mtime = existing_mtimes.get(file_path)
                    if mtime is not None and prev_mtime is not None and abs(mtime - prev_mtime) < MTIME_TOLERANCE_SECONDS:
                        unchanged += 1
                        self.progress.update(processed=counts_processed(), unchanged=unchanged)
                        continue
                to_process.append(file_path)

            with ThreadPoolExecutor(max_workers=MAX_PARSE_WORKERS) as executor:
                futures = {
                    executor.submit(_process_one_file, fp, max_bytes, max_file_size_mb): fp
                    for fp in to_process
                }
                for future in as_completed(futures):
                    outcome = future.result()
                    self.progress.update(current_file=outcome["file_path"])

                    if outcome["kind"] == "skipped":
                        self.db.upsert_file_skipped(
                            outcome["file_path"], outcome["file_name"], outcome["ext"], outcome["mtime"],
                            outcome["reason"], file_size=outcome["file_size"],
                        )
                        skipped += 1
                        self.progress.update(processed=counts_processed(), skipped=skipped)

                    elif outcome["kind"] == "unsupported":
                        self.db.upsert_file_unsupported(
                            outcome["file_path"], outcome["file_name"], outcome["ext"], outcome["mtime"],
                            file_size=outcome["file_size"],
                        )
                        unsupported += 1
                        self.progress.update(processed=counts_processed(), unsupported=unsupported)

                    elif outcome["kind"] == "failed":
                        self.db.upsert_file_failed(
                            outcome["file_path"], outcome["file_name"], outcome["ext"], outcome["mtime"],
                            outcome["error"], file_size=outcome["file_size"],
                        )
                        failed += 1
                        self.progress.update(processed=counts_processed(), failed=failed)

                    else:  # "indexed"
                        self.db.upsert_file_indexed(
                            outcome["file_path"], outcome["file_name"], outcome["ext"], outcome["mtime"],
                            outcome["records"], warning=outcome["warning"], file_size=outcome["file_size"],
                        )
                        indexed += 1
                        self.progress.update(processed=counts_processed(), indexed=indexed)

            if incremental:
                # Anything we had a row for that wasn't seen on disk this
                # time around has been deleted/moved -- drop it.
                current_paths = set(all_files)
                stale_paths = [p for p in existing_mtimes.keys() if p not in current_paths]
                self.db.delete_files(stale_paths)

            self.progress.update(status="ready", current_file=None)
            self.db.set_meta("root_folder", abs_folder)
            self.db.set_meta("last_indexed_at", str(time.time()))
            self.db.set_meta("max_file_size_mb", str(max_file_size_mb))
            self.db.set_meta("extra_skip_dirs", ",".join(sorted(skip_dirs - DEFAULT_SKIP_DIR_NAMES)))
        except Exception as e:
            self.progress.update(status="error", error=f"{e}\n{traceback.format_exc(limit=3)}")


def _process_one_file(file_path: str, max_bytes, max_file_size_mb):
    """
    Runs on a worker thread. Does everything that doesn't need to touch the
    database: stat the file, pick a parser, parse it. Returns a plain dict
    describing the outcome -- never raises, so one bad file can never take
    down the pool or the rest of indexing.
    """
    file_name = os.path.basename(file_path)
    ext = os.path.splitext(file_name)[1].lower()

    try:
        mtime = os.path.getmtime(file_path)
        file_size = os.path.getsize(file_path)
    except OSError:
        mtime = None
        file_size = None

    base = dict(file_path=file_path, file_name=file_name, ext=ext, mtime=mtime, file_size=file_size)

    if max_bytes is not None and file_size is not None and file_size > max_bytes:
        return dict(base, kind="skipped",
                    reason=f"File exceeds the {max_file_size_mb} MB size limit "
                           f"({file_size / (1024*1024):.1f} MB) -- raise the limit in Settings to include it.")

    parser = get_parser_for(file_path)
    if parser is None:
        return dict(base, kind="unsupported")

    if not parser.is_dependency_available():
        return dict(base, kind="failed",
                    error=f"Missing dependency for {parser.display_name}. {parser.dependency_message()}")

    try:
        result = parser.parse(file_path)
    except Exception as e:
        # Absolute safety net: a parser must never take down indexing.
        return dict(base, kind="failed", error=f"Unexpected error: {e}\n{traceback.format_exc(limit=2)}")

    if result.success:
        return dict(base, kind="indexed", records=result.records, warning=result.warning)
    return dict(base, kind="failed", error=result.error)


def _walk_files(root_folder: str, skip_dirs):
    """Recursively yield every file path under root_folder, skipping junk dirs."""
    for dirpath, dirnames, filenames in os.walk(root_folder):
        dirnames[:] = [d for d in dirnames if d not in skip_dirs and not d.startswith(".")]
        for name in filenames:
            if name.startswith("~$"):
                # Skip Word/Excel lock files, e.g. ~$Members.xlsx
                continue
            yield os.path.join(dirpath, name)
