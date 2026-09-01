"""
app.py

Flask backend for the Universal Local File Searcher.

Runs entirely on 127.0.0.1 -- no file contents ever leave the machine.
Serves the single-page UI (static/index.html) and a small JSON API:

    POST /api/index          { folder, max_file_size_mb?, extra_skip_dirs?, force_full? } -> start indexing (background thread)
    POST /api/rescan         { force_full? }                -> re-index the last-used folder with its last settings.
                                                                 Incremental by default: unchanged files are skipped.
    GET  /api/progress                                   -> poll indexing progress
    GET  /api/search         ?q=...&filters              -> search indexed content (ranked, grouped, filtered)
    GET  /api/supported                                  -> supported extensions + categories + failed/unsupported/skipped lists
    POST /api/open-file      { path }                    -> open a file with the OS default app
    POST /api/open-folder    { path }                    -> open containing folder in file explorer
    POST /api/browse-folder                               -> native OS folder picker (best-effort)

Search query params (all optional except q):
    q                   search text
    search_content      "1"/"0" (default 1)
    search_filenames    "1"/"0" (default 1)
    categories          comma-separated list, e.g. "PDF,Excel"
    scope               "recursive" (default) or "current"
    sort                "relevance" (default) | "name" | "type" | "path" | "matches"
"""

import os
import platform
import subprocess
import sys

from flask import Flask, request, jsonify, send_from_directory

from database import Database
from indexer import Indexer, DEFAULT_MAX_FILE_SIZE_MB
from parsers import SUPPORTED_EXTENSIONS, CATEGORIES

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(APP_DIR, "file_index.sqlite3")
STATIC_DIR = os.path.join(APP_DIR, "static")

app = Flask(__name__, static_folder=STATIC_DIR)

db = Database(DB_PATH)
indexer = Indexer(db)


@app.route("/")
def index():
    return send_from_directory(STATIC_DIR, "index.html")


@app.route("/api/index", methods=["POST"])
def api_index():
    data = request.get_json(force=True, silent=True) or {}
    folder = (data.get("folder") or "").strip()
    if not folder:
        return jsonify({"ok": False, "message": "No folder provided"}), 400

    max_file_size_mb = data.get("max_file_size_mb", DEFAULT_MAX_FILE_SIZE_MB)
    try:
        max_file_size_mb = float(max_file_size_mb) if max_file_size_mb not in (None, "") else 0
    except (TypeError, ValueError):
        max_file_size_mb = DEFAULT_MAX_FILE_SIZE_MB

    extra_skip_dirs_raw = data.get("extra_skip_dirs", "")
    if isinstance(extra_skip_dirs_raw, list):
        extra_skip_dirs = extra_skip_dirs_raw
    else:
        extra_skip_dirs = [d.strip() for d in str(extra_skip_dirs_raw or "").split(",") if d.strip()]

    force_full = bool(data.get("force_full", False))

    ok, message = indexer.start_indexing(
        folder, max_file_size_mb=max_file_size_mb, extra_skip_dirs=extra_skip_dirs, force_full=force_full,
    )
    status_code = 200 if ok else 400
    return jsonify({"ok": ok, "message": message}), status_code


@app.route("/api/rescan", methods=["POST"])
def api_rescan():
    folder = db.get_meta("root_folder") or indexer.progress.snapshot().get("folder")
    if not folder:
        return jsonify({"ok": False, "message": "No folder has been indexed yet"}), 400

    data = request.get_json(force=True, silent=True) or {}
    force_full = bool(data.get("force_full", False))

    max_file_size_mb = db.get_meta("max_file_size_mb", DEFAULT_MAX_FILE_SIZE_MB)
    try:
        max_file_size_mb = float(max_file_size_mb)
    except (TypeError, ValueError):
        max_file_size_mb = DEFAULT_MAX_FILE_SIZE_MB
    extra_skip_dirs_raw = db.get_meta("extra_skip_dirs", "")
    extra_skip_dirs = [d.strip() for d in extra_skip_dirs_raw.split(",") if d.strip()]

    ok, message = indexer.start_indexing(
        folder, max_file_size_mb=max_file_size_mb, extra_skip_dirs=extra_skip_dirs, force_full=force_full,
    )
    status_code = 200 if ok else 400
    return jsonify({"ok": ok, "message": message, "folder": folder}), status_code


@app.route("/api/progress")
def api_progress():
    snapshot = indexer.progress.snapshot()
    if snapshot["status"] == "ready":
        snapshot["stats"] = db.get_stats()
        snapshot["root_folder"] = db.get_meta("root_folder")
        snapshot["last_indexed_at"] = db.get_meta("last_indexed_at")
    return jsonify(snapshot)


@app.route("/api/search")
def api_search():
    query = request.args.get("q", "")
    search_content = request.args.get("search_content", "1") == "1"
    search_filenames = request.args.get("search_filenames", "1") == "1"
    sort_by = request.args.get("sort", "relevance")
    scope = request.args.get("scope", "recursive")

    categories_param = request.args.get("categories", "")
    categories = [c for c in categories_param.split(",") if c] or None

    root_folder = db.get_meta("root_folder")
    current_folder_only = scope == "current"

    result = db.search(
        query,
        search_content=search_content,
        search_filenames=search_filenames,
        categories=categories,
        scope_folder=root_folder,
        current_folder_only=current_folder_only,
        sort_by=sort_by,
    )

    breakdown = {}
    for f in result["files"]:
        breakdown[f["category"]] = breakdown.get(f["category"], 0) + 1

    return jsonify({
        "query": query,
        "total_matches": result["total_matches"],
        "total_files": result["total_files"],
        "breakdown": breakdown,
        "files": result["files"],
    })


@app.route("/api/supported")
def api_supported():
    return jsonify({
        "extensions": SUPPORTED_EXTENSIONS,
        "categories": CATEGORIES,
        "stats": db.get_stats(),
        "failed": db.get_failed_files(),
        "unsupported": db.get_unsupported_files(),
        "skipped": db.get_skipped_files(),
        "settings": {
            "max_file_size_mb": db.get_meta("max_file_size_mb", DEFAULT_MAX_FILE_SIZE_MB),
            "extra_skip_dirs": db.get_meta("extra_skip_dirs", ""),
        },
    })


@app.route("/api/open-file", methods=["POST"])
def api_open_file():
    data = request.get_json(force=True, silent=True) or {}
    path = data.get("path", "")
    return jsonify(_open_path(path, reveal_only=False))


@app.route("/api/open-folder", methods=["POST"])
def api_open_folder():
    data = request.get_json(force=True, silent=True) or {}
    path = data.get("path", "")
    return jsonify(_open_path(path, reveal_only=True))


@app.route("/api/browse-folder", methods=["POST"])
def api_browse_folder():
    """
    Best-effort native folder picker. Browsers cannot give a web page an
    absolute filesystem path, so we shell out to a tiny tkinter dialog
    running on the same machine (this app is local-only by design). If no
    display/tkinter is available, the frontend falls back to manual path
    entry -- this endpoint is a convenience, not a requirement.
    """
    try:
        result = subprocess.run(
            [sys.executable, os.path.join(APP_DIR, "folder_picker.py")],
            capture_output=True, text=True, timeout=120,
        )
        folder = (result.stdout or "").strip()
        if folder:
            return jsonify({"ok": True, "folder": folder})
        return jsonify({"ok": False, "message": "No folder selected"})
    except Exception as e:
        return jsonify({"ok": False, "message": f"Native picker unavailable: {e}"})


def _open_path(path: str, reveal_only: bool):
    if not path:
        return {"ok": False, "message": "No path provided"}

    target = os.path.dirname(path) if reveal_only else path
    if not os.path.exists(target):
        return {"ok": False, "message": f"Path does not exist: {target}"}

    system = platform.system()
    try:
        if system == "Windows":
            if reveal_only:
                subprocess.run(["explorer", "/select,", path])
            else:
                os.startfile(target)  # type: ignore[attr-defined]
        elif system == "Darwin":
            subprocess.run(["open", "-R", path] if reveal_only else ["open", target])
        else:
            subprocess.run(["xdg-open", target])
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "message": str(e)}


if __name__ == "__main__":
    print("Universal Local File Searcher")
    print(f"Supported formats ({len(SUPPORTED_EXTENSIONS)}): {', '.join(SUPPORTED_EXTENSIONS)}")
    print("Open http://127.0.0.1:5000 in your browser")
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)
