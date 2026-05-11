#!/usr/bin/env python3
"""
File Renaming Tool - Tkinter Version
Requires: pip install PyMuPDF Pillow python-docx
"""

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import sys
import os
import re
import shutil
import struct
import tempfile
import threading
from pathlib import Path

# ─────────────────────────── optional deps ───────────────────────────

try:
    import fitz  # PyMuPDF
    HAS_FITZ = True
except ImportError:
    HAS_FITZ = False

try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    from docx import Document as DocxDocument
    HAS_DOCX = True
except ImportError:
    HAS_DOCX = False

# ─────────────────────────── constants ───────────────────────────────

PREVIEW_W = 520
PREVIEW_H = 380
SIDEBAR_W = 220

SUPPORTED_TYPES = {
    "pdf": "pdf",
    "png": "png",
    "jpg": "jpg",
    "jpeg": "jpg",
    "docx": "docx",
}

MAGIC_BYTES = [
    (b"%PDF", "pdf"),
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"\xff\xd8\xff", "jpg"),
    (b"PK\x03\x04", "docx"),  # ZIP-based; further check done later
]

# ─────────────────────────── helpers ─────────────────────────────────

def detect_extension(filepath: Path) -> str | None:
    """Read file magic bytes to determine type. Returns extension or None."""
    try:
        with open(filepath, "rb") as f:
            header = f.read(16)
        for magic, ext in MAGIC_BYTES:
            if header.startswith(magic):
                if ext == "docx":
                    # ZIP could be many things; trust it for now
                    return "docx"
                return ext
    except Exception:
        pass
    return None


def normalize_name(raw: str) -> str:
    """Lowercase, replace spaces/hyphens with underscores, strip bad chars."""
    name = raw.strip().lower()
    name = re.sub(r"[\s\-]+", "_", name)
    name = re.sub(r"[^\w]", "", name)
    name = re.sub(r"_+", "_", name).strip("_")
    return name


def safe_destination(folder: Path, stem: str, ext: str) -> Path:
    """Return a path that doesn't collide, appending _01, _02 … as needed."""
    candidate = folder / f"{stem}.{ext}"
    if not candidate.exists():
        return candidate
    counter = 1
    while True:
        candidate = folder / f"{stem}_{counter:02d}.{ext}"
        if not candidate.exists():
            return candidate
        counter += 1


def render_pdf_preview(filepath: Path, max_w: int, max_h: int, zoom: bool = False) -> ImageTk.PhotoImage | None:
    if not HAS_FITZ or not HAS_PIL:
        return None
    try:
        doc = fitz.open(str(filepath))
        page = doc[0]
        # Low-res render for preview, high for zoom
        scale = 3.0 if zoom else min(max_w / page.rect.width, max_h / page.rect.height, 1.5)
        mat = fitz.Matrix(scale, scale)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        doc.close()
        return ImageTk.PhotoImage(img)
    except Exception:
        return None


def render_image_preview(filepath: Path, max_w: int, max_h: int, zoom: bool = False) -> ImageTk.PhotoImage | None:
    if not HAS_PIL:
        return None
    try:
        img = Image.open(str(filepath))
        if not zoom:
            img.thumbnail((max_w, max_h))
        return ImageTk.PhotoImage(img)
    except Exception:
        return None


def render_docx_preview(filepath: Path, max_w: int, max_h: int, zoom: bool = False) -> ImageTk.PhotoImage | None:
    """Convert first page of docx to image via PDF intermediary if PyMuPDF available."""
    if not HAS_DOCX or not HAS_FITZ or not HAS_PIL:
        return None
    try:
        # Write first ~50 lines of text to a temp PDF via fitz text page
        doc = DocxDocument(str(filepath))
        lines = []
        for para in doc.paragraphs[:60]:
            if para.text.strip():
                lines.append(para.text)
        if not lines:
            return None

        # Build a simple PDF with the text
        pdf_doc = fitz.open()
        page = pdf_doc.new_page(width=595, height=842)
        y = 50
        for line in lines[:40]:
            if y > 780:
                break
            page.insert_text((40, y), line[:100], fontsize=10, color=(0, 0, 0))
            y += 16

        tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        tmp.close()
        pdf_doc.save(tmp.name)
        pdf_doc.close()

        px = render_pdf_preview(Path(tmp.name), max_w, max_h, zoom)
        os.unlink(tmp.name)
        return px
    except Exception:
        return None


# ─────────────────────────── sidebar item ────────────────────────────

# Removed SidebarItem, using Listbox instead


# ─────────────────────────── zoom window ─────────────────────────────

class ZoomWindow(tk.Toplevel):
    def __init__(self, photo: ImageTk.PhotoImage, parent=None):
        super().__init__(parent)
        self.title("Preview — Click to close")
        self.resizable(True, True)

        img = ImageTk.getimage(photo)
        zoomed_photo = ImageTk.PhotoImage(img)

        lbl = tk.Label(self, image=zoomed_photo)
        lbl.image = zoomed_photo  # keep reference
        lbl.pack(fill=tk.BOTH, expand=True)
        lbl.bind("<Button-1>", lambda e: self.destroy())

        # Set initial size to fit image, but allow resize
        self.geometry(f"{img.width}x{img.height}")

        self.geometry(f"{img.width}x{img.height}")


# ─────────────────────────── main window ─────────────────────────────

class FileRenamer(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("File Renamer")
        self.geometry(f"{SIDEBAR_W + PREVIEW_W + 80}x720")
        self.resizable(False, False)
        self.configure(bg="#0f1117")

        self.folder: Path | None = None
        self.files: list[Path] = []
        self.current_index: int = 0
        self.sidebar_items: list[SidebarItem] = []
        self._full_photo: ImageTk.PhotoImage | None = None  # for zoom

        self._build_ui()
        self._apply_styles()

    # ─── UI construction ───────────────────────────────────────────

    def _build_ui(self):
        # Main container
        main_frame = tk.Frame(self, bg="#0f1117")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Sidebar
        sidebar_frame = tk.Frame(main_frame, bg="#161820", width=SIDEBAR_W)
        sidebar_frame.pack(side=tk.LEFT, fill=tk.Y)
        sidebar_frame.pack_propagate(False)

        sb_header = tk.Label(sidebar_frame, text="FILES", bg="#1e2030", fg="#7c85a0", font=("Segoe UI", 10, "bold"), anchor="center")
        sb_header.pack(fill=tk.X, pady=(0,1))

        self.scroll_frame = tk.Frame(sidebar_frame, bg="#161820")
        self.scroll_frame.pack(fill=tk.BOTH, expand=True)

        self.listbox = tk.Listbox(self.scroll_frame, bg="#161820", fg="#9098b5", font=("Segoe UI", 11), selectbackground="#252840", selectforeground="#d0d5f0", selectmode=tk.SINGLE, activestyle="none", height=20, bd=0, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.scroll_frame, orient=tk.VERTICAL, command=self.listbox.yview)
        self.listbox.config(yscrollcommand=scrollbar.set)

        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.listbox.bind("<<ListboxSelect>>", self._on_listbox_select)

        # Main panel
        main_panel = tk.Frame(main_frame, bg="#0f1117")
        main_panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=24, pady=20)

        # Top bar
        top_frame = tk.Frame(main_panel, bg="#0f1117")
        top_frame.pack(fill=tk.X, pady=(0,14))

        self.folder_btn = tk.Button(top_frame, text="📂  Choose Folder", command=self.choose_folder, bg="#1e2030", fg="#8a93b5", font=("Segoe UI", 13, "bold"), relief="raised", bd=1)
        self.folder_btn.pack(side=tk.LEFT)

        self.progress_lbl = tk.Label(top_frame, text="", bg="#0f1117", fg="#4a5070", font=("Segoe UI", 12, "bold"))
        self.progress_lbl.pack(side=tk.RIGHT)

        # Preview area
        self.preview_frame = tk.Frame(main_panel, bg="#090b10", bd=1, relief="solid")
        self.preview_frame.pack(pady=(0,14))
        self.preview_frame.config(width=PREVIEW_W, height=PREVIEW_H)
        self.preview_frame.pack_propagate(False)

        self.preview_lbl = tk.Label(self.preview_frame, text="No preview", bg="#090b10", fg="#2a3050", font=("Segoe UI", 13))
        self.preview_lbl.pack(expand=True)
        self.preview_lbl.bind("<Button-1>", self._zoom_preview)

        # Meta row
        meta_frame = tk.Frame(main_panel, bg="#0f1117")
        meta_frame.pack(fill=tk.X, pady=(0,14))

        self.type_chip = tk.Label(meta_frame, text="", bg="#1e2535", fg="#6c8eff", font=("Segoe UI", 10, "bold"))
        self.type_chip.pack(side=tk.LEFT, padx=(0,8))

        self.orig_name_lbl = tk.Label(meta_frame, text="", bg="#0f1117", fg="#3e4a6a", font=("Segoe UI", 11, "italic"), anchor="w")
        self.orig_name_lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Name input
        self.name_input = tk.Entry(main_panel, bg="#161820", fg="#e8ecff", font=("Segoe UI", 15), insertbackground="#e8ecff", selectbackground="#3a4a8a")
        self.name_input.pack(fill=tk.X, pady=(0,14), ipady=10)
        self.name_input.bind("<KeyRelease>", self._update_preview_name)

        # Preview name
        preview_name_frame = tk.Frame(main_panel, bg="#0f1117")
        preview_name_frame.pack(fill=tk.X, pady=(0,14))

        arrow_lbl = tk.Label(preview_name_frame, text="→", bg="#0f1117", fg="#3a4060", font=("Segoe UI", 16))
        arrow_lbl.pack(side=tk.LEFT)

        self.preview_name_lbl = tk.Label(preview_name_frame, text="", bg="#0f1117", fg="#6c8eff", font=("Consolas", 13, "bold"), anchor="w")
        self.preview_name_lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Buttons
        btn_frame = tk.Frame(main_panel, bg="#0f1117")
        btn_frame.pack(fill=tk.X)

        self.skip_btn = tk.Button(btn_frame, text="Skip", command=self.skip_file, bg="#1a1c28", fg="#6a7090", font=("Segoe UI", 13, "bold"), relief="raised", bd=1)
        self.skip_btn.pack(side=tk.LEFT, padx=(0,10))

        self.delete_btn = tk.Button(btn_frame, text="Delete", command=self.delete_file, bg="#1f1218", fg="#8a4055", font=("Segoe UI", 13, "bold"), relief="raised", bd=1)
        self.delete_btn.pack(side=tk.LEFT)

        self.rename_btn = tk.Button(btn_frame, text="Rename  ↵", command=self.rename_file, bg="#1e2a5a", fg="#8aabff", font=("Segoe UI", 13, "bold"), relief="raised", bd=1)
        self.rename_btn.pack(side=tk.RIGHT)

        # Bind Enter key
        self.bind("<Return>", lambda e: self.rename_file())
        self.bind("<F12>", lambda e: self.delete_file())
        self.bind("<F8>", lambda e: self.skip_file())
        self.name_input.focus_set()

        self._set_controls_enabled(False)

    def _on_listbox_select(self, event):
        selection = self.listbox.curselection()
        if selection:
            self._jump_to(selection[0])

    # ─── styles ────────────────────────────────────────────────────

    def _apply_styles(self):
        # Tkinter styles are applied in widget creation
        pass

    # ─── folder selection ──────────────────────────────────────────

    def choose_folder(self):
        folder = filedialog.askdirectory(title="Select Folder", initialdir=str(Path.home()))
        if not folder:
            return
        self.folder = Path(folder)
        self._load_files()

    def _load_files(self):
        all_files = sorted(
            [f for f in self.folder.iterdir() if f.is_file()],
            key=lambda p: p.name.lower()
        )

        # Filter to supported types (or detectable ones)
        self.files = []
        for f in all_files:
            ext = f.suffix.lstrip(".").lower()
            if ext in SUPPORTED_TYPES:
                self.files.append(f)
            else:
                # Check header
                detected = detect_extension(f)
                if detected:
                    self.files.append(f)
                # else: skip silently

        self._build_sidebar()
        self.current_index = 0
        if self.files:
            self._set_controls_enabled(True)
            self._show_file(0)
        else:
            self._set_controls_enabled(False)
            self.preview_lbl.config(image="", text="No supported files found.")
            self.progress_lbl.config(text="")

    # ─── sidebar ──────────────────────────────────────────────────

    def _build_sidebar(self):
        self.listbox.delete(0, tk.END)
        for i, f in enumerate(self.files):
            self.listbox.insert(tk.END, f"{i+1}. {f.name}")
        if self.files:
            self.listbox.selection_set(self.current_index)
            self.listbox.see(self.current_index)

    def _jump_to(self, index: int):
        if 0 <= index < len(self.files):
            self.current_index = index
            self._show_file(index)

    # ─── file display ─────────────────────────────────────────────

    def _show_file(self, index: int):
        if index >= len(self.files):
            self._done()
            return

        filepath = self.files[index]
        self._build_sidebar()
        self.progress_lbl.config(text=f"{index + 1} / {len(self.files)}")

        # Determine extension
        raw_ext = filepath.suffix.lstrip(".").lower()
        if raw_ext in SUPPORTED_TYPES:
            ext = SUPPORTED_TYPES[raw_ext]
            working_path = filepath
        else:
            detected = detect_extension(filepath)
            if not detected:
                self._advance_skip()
                return
            ext = detected
            # Temporarily rename to add extension for preview
            tmp_path = filepath.with_suffix(f".{ext}")
            try:
                shutil.copy2(filepath, tmp_path)
                working_path = tmp_path
                self._temp_preview_path = tmp_path
            except Exception:
                working_path = filepath
                self._temp_preview_path = None

        self._current_ext = ext
        self.type_chip.config(text=ext.upper())
        self.orig_name_lbl.config(text=f"  {filepath.name}")

        # Render preview
        self._full_photo = None
        self._zoom_photo = None
        photo = None
        zoom_photo = None
        if ext == "pdf":
            photo = render_pdf_preview(working_path, PREVIEW_W - 2, PREVIEW_H - 2)
            zoom_photo = render_pdf_preview(working_path, 0, 0, zoom=True)
        elif ext in ("png", "jpg"):
            photo = render_image_preview(working_path, PREVIEW_W - 2, PREVIEW_H - 2)
            zoom_photo = render_image_preview(working_path, 0, 0, zoom=True)
        elif ext == "docx":
            photo = render_docx_preview(working_path, PREVIEW_W - 2, PREVIEW_H - 2)
            zoom_photo = render_docx_preview(working_path, 0, 0, zoom=True)

        if photo:
            self._full_photo = photo
            self.preview_lbl.config(image=photo, text="")
        else:
            self.preview_lbl.config(image="", text=f"[{ext.upper()} — no preview available]")

        self._zoom_photo = zoom_photo

        # Pre-fill name input with current stem, select all
        stem = filepath.stem
        self.name_input.delete(0, tk.END)
        self.name_input.insert(0, stem)
        self.name_input.select_range(0, tk.END)
        self.name_input.focus_set()
        self._update_preview_name()

    def _update_preview_name(self, event=None):
        if not hasattr(self, "_current_ext"):
            return
        raw = self.name_input.get().strip()
        norm = normalize_name(raw)
        if norm:
            self.preview_name_lbl.config(text=f"{norm}.{self._current_ext}")
        else:
            self.preview_name_lbl.config(text="")

    # ─── actions ──────────────────────────────────────────────────

    def rename_file(self):
        if not self.files or self.current_index >= len(self.files):
            return
        raw = self.name_input.get().strip()
        norm = normalize_name(raw)
        if not norm:
            self.name_input.focus_set()
            return

        filepath = self.files[self.current_index]
        dest = safe_destination(self.folder, norm, self._current_ext)

        try:
            filepath.rename(dest)
        except PermissionError:
            self._show_readonly_error()
            return
        except Exception as e:
            messagebox.showwarning("Error", str(e))
            return

        self.files[self.current_index] = dest
        self._build_sidebar()
        self._advance()

    def skip_file(self):
        self._advance_skip()

    def delete_file(self):
        if not self.files or self.current_index >= len(self.files):
            return
        filepath = self.files[self.current_index]
        try:
            filepath.unlink()
        except PermissionError:
            self._show_readonly_error()
            return
        except Exception as e:
            messagebox.showwarning("Error", str(e))
            return

        self._remove_current_and_advance()

    def _advance(self):
        """Move to next file without removing current from list."""
        next_idx = self.current_index + 1
        if next_idx >= len(self.files):
            self._done()
        else:
            self.current_index = next_idx
            self._show_file(next_idx)

    def _advance_skip(self):
        """Skip current file (leave it), move to next."""
        next_idx = self.current_index + 1
        if next_idx >= len(self.files):
            self._done()
        else:
            self.current_index = next_idx
            self._show_file(next_idx)

    def _remove_current_and_advance(self):
        idx = self.current_index
        self.files.pop(idx)
        self._build_sidebar()
        self.progress_lbl.config(text=f"{idx + 1} / {len(self.files)}")

        if idx >= len(self.files):
            if self.files:
                self.current_index = len(self.files) - 1
                self._show_file(self.current_index)
            else:
                self._done()
        else:
            self.current_index = idx
            self._show_file(idx)

    def _done(self):
        self.preview_lbl.config(image="", text="✓  All files processed")
        self.name_input.delete(0, tk.END)
        self.preview_name_lbl.config(text="")
        self.orig_name_lbl.config(text="")
        self.type_chip.config(text="")
        self.progress_lbl.config(text="Done")
        self._set_controls_enabled(False)
        self._build_sidebar()

    def _show_readonly_error(self):
        messagebox.showinfo("Permission Error", "This file is read-only and cannot be modified.")

    def _set_controls_enabled(self, enabled: bool):
        state = "normal" if enabled else "disabled"
        self.rename_btn.config(state=state)
        self.skip_btn.config(state=state)
        self.delete_btn.config(state=state)
        self.name_input.config(state=state)

    def _zoom_preview(self, event):
        photo = self._zoom_photo or self._full_photo
        if photo:
            ZoomWindow(photo, self)


# ─────────────────────────── entry point ─────────────────────────────

def main():
    app = FileRenamer()
    app.mainloop()


if __name__ == "__main__":
    main()