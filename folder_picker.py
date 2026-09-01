"""
folder_picker.py

Tiny standalone script that pops a native "choose folder" dialog and
prints the chosen absolute path to stdout. Run as a subprocess from
app.py so a folder dialog can appear without blocking Flask's event loop.
Prints nothing if the user cancels or tkinter is unavailable.
"""
import sys

try:
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    folder = filedialog.askdirectory(title="Choose Main Folder")
    root.destroy()
    if folder:
        print(folder)
except Exception:
    sys.exit(0)
