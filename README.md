# 🔎 Universal File Searcher

A fast and powerful **local file search application** built with Python and Flask.

Search for file names or keywords across an entire folder containing multiple file types — including spreadsheets, documents, presentations, PDFs, and more — from a single search interface.

🔒 **Everything runs 100% locally. Your files are never uploaded to the cloud, sent to an API, or shared with third-party services.**

## ✨ Features

* 🔍 Search inside file contents and filenames
* 📁 Recursive folder scanning
* ⚡ Fast full-text search using SQLite FTS5
* 🔄 Smart incremental indexing and rescanning
* 🚀 Parallel file processing for faster indexing
* 🎯 Relevance-based search ranking
* 📂 File type filtering and sorting
* 👀 Match preview with surrounding context
* 📌 Shows exactly where matches are found
* ⌨️ Useful keyboard shortcuts
* 🌙 Light and dark mode
* 🔒 100% local and private

## 📄 Supported Formats

| Category     | Formats                          |
| ------------ | -------------------------------- |
| Excel        | `.xlsx`, `.xlsm`, `.xls`         |
| Word         | `.docx`, `.doc`*                 |
| PowerPoint   | `.pptx`, `.ppt`*                 |
| PDF          | `.pdf`                           |
| OpenDocument | `.ods`, `.odt`                   |
| CSV          | `.csv`, `.tsv`                   |
| Text         | `.txt`, `.log`                   |
| Data         | `.json`, `.xml`, `.yaml`, `.yml` |
| Web          | `.html`, `.htm`                  |
| Email        | `.eml`                           |
| RTF          | `.rtf`                           |

> * Legacy `.doc` and `.ppt` files require **LibreOffice**.

The application preserves the location of every match, such as:

**PDF page • Excel sheet/cell • PowerPoint slide • Word paragraph • JSON key path • XML tag path • Email content**

---

## 🖥️ Requirements

* Python **3.10 or newer**
* Windows, macOS, or Linux

For Windows users, download Python from the official Python website and make sure to select:

**Add Python to PATH**

---

# 🚀 Quick Start

## Windows

### 1. Download or Clone the Repository

```bash
git clone YOUR_REPOSITORY_URL
cd UniversalFileSearcher
```

Alternatively, download the repository as a ZIP file and extract it.

### 2. Run the Application

Simply double-click:

```text
run.bat
```

The script will automatically:

* Create a virtual environment
* Install the required dependencies
* Start the application

### 3. Open the Application

Open your browser and visit:

```text
http://127.0.0.1:5000
```

---

## 💻 Manual Installation

Install the dependencies:

```bash
pip install -r requirements.txt
```

Start the application:

```bash
python app.py
```

Then open:

```text
http://127.0.0.1:5000
```

---

# 📖 How to Use

1. ▶️ Start the application.
2. 📁 Choose the main folder containing your files.
3. ⚡ Click **Choose Main Folder & Index**.
4. ⏳ Wait for indexing to finish.
5. 🔍 Enter a keyword or filename.
6. 📂 Browse, filter, and sort your results.
7. 👀 Preview the match or open the file directly.

---

# ⚡ Smart Indexing

Universal File Searcher uses **incremental indexing** to improve performance.

When rescanning the same folder:

* ✅ Unchanged files are skipped.
* 🆕 New files are indexed.
* 🔄 Modified files are re-indexed.
* 🗑️ Deleted files are removed from the index.

Files are also processed in parallel to make indexing large folders faster.

You can enable **Force Full Re-index** when you want to completely rebuild the search index.

---

# 🔒 Privacy

Your privacy is important.

Universal File Searcher runs entirely on your computer.

* ❌ No cloud storage
* ❌ No file uploads
* ❌ No external API required
* ❌ No third-party data sharing
* ✅ Your files remain on your computer

The local search database is stored in:

```text
file_index.sqlite3
```

This file contains the local search index and never leaves your machine.

---

# ⚠️ Limitations

Currently not supported:

* OCR for scanned PDFs
* AI or semantic search
* Cloud synchronization
* Google Sheets integration
* Apple Pages, Numbers, and Keynote files

---

# 👨‍💻 Author

Developed by **ApamBalik1337**.

⭐ If you find this project useful, please consider giving the repository a star!
