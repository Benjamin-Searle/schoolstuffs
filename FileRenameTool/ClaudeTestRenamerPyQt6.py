#!/usr/bin/env python3
"""
File Renaming Tool
Requires: pip install PyQt6 PyMuPDF Pillow python-docx
"""

import sys
import os
import re
import shutil
import imghdr
import struct
import tempfile
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QFileDialog, QScrollArea,
    QFrame, QSizePolicy, QMessageBox, QDialog, QSplitter
)
from PyQt6.QtCore import Qt, QSize, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QPixmap, QImage, QFont, QColor, QPalette, QIcon, QKeySequence, QShortcut

# ─────────────────────────── optional deps ───────────────────────────

try:
    import fitz  # PyMuPDF
    HAS_FITZ = True
except ImportError:
    HAS_FITZ = False

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    from docx import Document as DocxDocument
    from docx.shared import Inches
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


def render_pdf_preview(filepath: Path, max_w: int, max_h: int) -> QPixmap | None:
    if not HAS_FITZ:
        return None
    try:
        doc = fitz.open(str(filepath))
        page = doc[0]
        # Low-res render
        scale = min(max_w / page.rect.width, max_h / page.rect.height, 1.5)
        mat = fitz.Matrix(scale, scale)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        img = QImage(pix.samples, pix.width, pix.height,
                     pix.stride, QImage.Format.Format_RGB888)
        doc.close()
        return QPixmap.fromImage(img)
    except Exception:
        return None


def render_image_preview(filepath: Path, max_w: int, max_h: int) -> QPixmap | None:
    px = QPixmap(str(filepath))
    if px.isNull():
        return None
    return px.scaled(max_w, max_h, Qt.AspectRatioMode.KeepAspectRatio,
                     Qt.TransformationMode.SmoothTransformation)


def render_docx_preview(filepath: Path, max_w: int, max_h: int) -> QPixmap | None:
    """Convert first page of docx to image via PDF intermediary if PyMuPDF available."""
    if not HAS_DOCX or not HAS_FITZ:
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

        px = render_pdf_preview(Path(tmp.name), max_w, max_h)
        os.unlink(tmp.name)
        return px
    except Exception:
        return None


# ─────────────────────────── sidebar item ────────────────────────────

class SidebarItem(QFrame):
    clicked = pyqtSignal(int)

    def __init__(self, index: int, name: str, parent=None):
        super().__init__(parent)
        self.index = index
        self.setFixedHeight(36)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setObjectName("SidebarItem")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)

        self.num = QLabel(f"{index + 1}.")
        self.num.setFixedWidth(28)
        self.num.setObjectName("SidebarNum")

        self.lbl = QLabel(name)
        self.lbl.setObjectName("SidebarLabel")
        self.lbl.setMaximumWidth(SIDEBAR_W - 60)

        layout.addWidget(self.num)
        layout.addWidget(self.lbl, 1)
        self.set_active(False)

    def set_active(self, active: bool):
        self.setProperty("active", active)
        self.style().unpolish(self)
        self.style().polish(self)

    def mousePressEvent(self, event):
        self.clicked.emit(self.index)


# ─────────────────────────── zoom window ─────────────────────────────

class ZoomWindow(QDialog):
    def __init__(self, pixmap: QPixmap, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Preview — Click to close")
        self.setModal(False)

        screen = QApplication.primaryScreen().availableGeometry()
        max_w = int(screen.width() * 0.85)
        max_h = int(screen.height() * 0.85)

        scaled = pixmap.scaled(max_w, max_h,
                               Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.SmoothTransformation)

        lbl = QLabel()
        lbl.setPixmap(scaled)
        lbl.setCursor(Qt.CursorShape.PointingHandCursor)
        lbl.mousePressEvent = lambda _: self.close()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(lbl)

        self.resize(scaled.width(), scaled.height())


# ─────────────────────────── main window ─────────────────────────────

class FileRenamer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("File Renamer")
        self.folder: Path | None = None
        self.files: list[Path] = []
        self.current_index: int = 0
        self.sidebar_items: list[SidebarItem] = []
        self._full_pixmap: QPixmap | None = None  # for zoom

        self._build_ui()
        self._apply_styles()
        self.setFixedSize(SIDEBAR_W + PREVIEW_W + 80, 720)

    # ─── UI construction ───────────────────────────────────────────

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── sidebar ──────────────────────────────────────────────
        sidebar_container = QWidget()
        sidebar_container.setFixedWidth(SIDEBAR_W)
        sidebar_container.setObjectName("Sidebar")
        sb_layout = QVBoxLayout(sidebar_container)
        sb_layout.setContentsMargins(0, 0, 0, 0)
        sb_layout.setSpacing(0)

        sb_header = QLabel("FILES")
        sb_header.setObjectName("SidebarHeader")
        sb_header.setFixedHeight(44)
        sb_header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sb_layout.addWidget(sb_header)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setObjectName("SidebarScroll")

        self.sidebar_widget = QWidget()
        self.sidebar_widget.setObjectName("SidebarInner")
        self.sidebar_layout = QVBoxLayout(self.sidebar_widget)
        self.sidebar_layout.setContentsMargins(0, 0, 0, 0)
        self.sidebar_layout.setSpacing(0)
        self.sidebar_layout.addStretch()

        self.scroll_area.setWidget(self.sidebar_widget)
        sb_layout.addWidget(self.scroll_area, 1)
        outer.addWidget(sidebar_container)

        # ── main panel ───────────────────────────────────────────
        main_panel = QWidget()
        main_panel.setObjectName("MainPanel")
        main_layout = QVBoxLayout(main_panel)
        main_layout.setContentsMargins(24, 20, 24, 20)
        main_layout.setSpacing(14)

        # top bar: folder button + progress
        top_bar = QHBoxLayout()
        self.folder_btn = QPushButton("📂  Choose Folder")
        self.folder_btn.setObjectName("FolderBtn")
        self.folder_btn.clicked.connect(self.choose_folder)
        self.folder_btn.setFixedHeight(38)

        self.progress_lbl = QLabel("")
        self.progress_lbl.setObjectName("ProgressLabel")
        self.progress_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        top_bar.addWidget(self.folder_btn)
        top_bar.addStretch()
        top_bar.addWidget(self.progress_lbl)
        main_layout.addLayout(top_bar)

        # preview area — fixed size box
        self.preview_frame = QFrame()
        self.preview_frame.setObjectName("PreviewFrame")
        self.preview_frame.setFixedSize(PREVIEW_W, PREVIEW_H)
        self.preview_frame.setCursor(Qt.CursorShape.PointingHandCursor)
        self.preview_frame.mousePressEvent = self._zoom_preview

        preview_inner = QVBoxLayout(self.preview_frame)
        preview_inner.setContentsMargins(0, 0, 0, 0)

        self.preview_lbl = QLabel("No preview")
        self.preview_lbl.setObjectName("PreviewLabel")
        self.preview_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_lbl.setFixedSize(PREVIEW_W, PREVIEW_H)
        preview_inner.addWidget(self.preview_lbl)

        main_layout.addWidget(self.preview_frame)

        # file type chip + original name
        meta_row = QHBoxLayout()
        self.type_chip = QLabel("")
        self.type_chip.setObjectName("TypeChip")
        self.orig_name_lbl = QLabel("")
        self.orig_name_lbl.setObjectName("OrigName")
        meta_row.addWidget(self.type_chip)
        meta_row.addWidget(self.orig_name_lbl, 1)
        main_layout.addLayout(meta_row)

        # text input
        self.name_input = QLineEdit()
        self.name_input.setObjectName("NameInput")
        self.name_input.setPlaceholderText("Type new file name here…")
        self.name_input.setFixedHeight(42)
        self.name_input.textChanged.connect(self._update_preview_name)
        main_layout.addWidget(self.name_input)

        # live name preview
        preview_name_row = QHBoxLayout()
        preview_name_row.setContentsMargins(4, 0, 0, 0)
        arrow_lbl = QLabel("→")
        arrow_lbl.setObjectName("Arrow")
        self.preview_name_lbl = QLabel("")
        self.preview_name_lbl.setObjectName("PreviewNameLabel")
        preview_name_row.addWidget(arrow_lbl)
        preview_name_row.addWidget(self.preview_name_lbl, 1)
        main_layout.addLayout(preview_name_row)

        # buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self.skip_btn = QPushButton("Skip")
        self.skip_btn.setObjectName("SkipBtn")
        self.skip_btn.setFixedHeight(42)
        self.skip_btn.clicked.connect(self.skip_file)

        self.delete_btn = QPushButton("Delete")
        self.delete_btn.setObjectName("DeleteBtn")
        self.delete_btn.setFixedHeight(42)
        self.delete_btn.clicked.connect(self.delete_file)

        self.rename_btn = QPushButton("Rename  ↵")
        self.rename_btn.setObjectName("RenameBtn")
        self.rename_btn.setFixedHeight(42)
        self.rename_btn.clicked.connect(self.rename_file)

        btn_row.addWidget(self.skip_btn)
        btn_row.addWidget(self.delete_btn)
        btn_row.addStretch()
        btn_row.addWidget(self.rename_btn)
        main_layout.addLayout(btn_row)

        outer.addWidget(main_panel, 1)

        # Enter key shortcut
        enter_sc = QShortcut(QKeySequence(Qt.Key.Key_Return), self)
        enter_sc.activated.connect(self.rename_file)
        enter_sc2 = QShortcut(QKeySequence(Qt.Key.Key_Enter), self)
        enter_sc2.activated.connect(self.rename_file)

        self._set_controls_enabled(False)

    # ─── styles ────────────────────────────────────────────────────

    def _apply_styles(self):
        self.setStyleSheet("""
        QMainWindow, QWidget {
            background-color: #0f1117;
            color: #e8e8e8;
            font-family: 'Segoe UI', 'Helvetica Neue', sans-serif;
        }

        /* ── sidebar ── */
        QWidget#Sidebar {
            background-color: #161820;
            border-right: 1px solid #2a2d3a;
        }
        QLabel#SidebarHeader {
            background-color: #1e2030;
            color: #7c85a0;
            font-size: 10px;
            font-weight: 700;
            letter-spacing: 3px;
            border-bottom: 1px solid #2a2d3a;
        }
        QScrollArea#SidebarScroll {
            border: none;
            background: transparent;
        }
        QScrollArea#SidebarScroll QScrollBar:vertical {
            width: 4px;
            background: transparent;
        }
        QScrollArea#SidebarScroll QScrollBar::handle:vertical {
            background: #3a3d52;
            border-radius: 2px;
        }
        QScrollArea#SidebarScroll QScrollBar::add-line:vertical,
        QScrollArea#SidebarScroll QScrollBar::sub-line:vertical { height: 0; }

        QWidget#SidebarInner { background: transparent; }

        QFrame#SidebarItem {
            background: transparent;
            border-bottom: 1px solid #1e2030;
        }
        QFrame#SidebarItem:hover {
            background: #1e2030;
        }
        QFrame#SidebarItem[active="true"] {
            background: #252840;
            border-left: 3px solid #6c8eff;
        }
        QLabel#SidebarNum {
            color: #3e4257;
            font-size: 10px;
            font-weight: 600;
        }
        QFrame#SidebarItem[active="true"] QLabel#SidebarNum {
            color: #6c8eff;
        }
        QLabel#SidebarLabel {
            color: #9098b5;
            font-size: 11px;
        }
        QFrame#SidebarItem[active="true"] QLabel#SidebarLabel {
            color: #d0d5f0;
        }

        /* ── main panel ── */
        QWidget#MainPanel {
            background: #0f1117;
        }

        QPushButton#FolderBtn {
            background: #1e2030;
            color: #8a93b5;
            border: 1px solid #2a2d3a;
            border-radius: 8px;
            padding: 0 16px;
            font-size: 13px;
            font-weight: 600;
        }
        QPushButton#FolderBtn:hover {
            background: #252840;
            color: #c8d0f0;
            border-color: #4a4d6a;
        }

        QLabel#ProgressLabel {
            color: #4a5070;
            font-size: 12px;
            font-weight: 600;
            letter-spacing: 1px;
        }

        QFrame#PreviewFrame {
            background: #090b10;
            border: 1px solid #1e2535;
            border-radius: 10px;
        }
        QLabel#PreviewLabel {
            color: #2a3050;
            font-size: 13px;
        }

        QLabel#TypeChip {
            background: #1e2535;
            color: #6c8eff;
            font-size: 10px;
            font-weight: 700;
            letter-spacing: 2px;
            padding: 3px 10px;
            border-radius: 4px;
        }
        QLabel#OrigName {
            color: #3e4a6a;
            font-size: 11px;
            font-style: italic;
            padding-left: 8px;
        }

        QLineEdit#NameInput {
            background: #161820;
            color: #e8ecff;
            border: 1px solid #2a2d3a;
            border-radius: 8px;
            padding: 0 14px;
            font-size: 15px;
            font-weight: 500;
            selection-background-color: #3a4a8a;
        }
        QLineEdit#NameInput:focus {
            border-color: #4a5aaa;
            background: #1a1c28;
        }

        QLabel#Arrow {
            color: #3a4060;
            font-size: 16px;
            padding-right: 4px;
        }
        QLabel#PreviewNameLabel {
            color: #6c8eff;
            font-size: 13px;
            font-weight: 600;
            font-family: 'Consolas', 'Courier New', monospace;
        }

        QPushButton#SkipBtn {
            background: #1a1c28;
            color: #6a7090;
            border: 1px solid #2a2d3a;
            border-radius: 8px;
            font-size: 13px;
            font-weight: 600;
            padding: 0 20px;
        }
        QPushButton#SkipBtn:hover {
            background: #222435;
            color: #9098b5;
        }

        QPushButton#DeleteBtn {
            background: #1f1218;
            color: #8a4055;
            border: 1px solid #3a2030;
            border-radius: 8px;
            font-size: 13px;
            font-weight: 600;
            padding: 0 20px;
        }
        QPushButton#DeleteBtn:hover {
            background: #2a1520;
            color: #d06080;
            border-color: #6a3045;
        }

        QPushButton#RenameBtn {
            background: #1e2a5a;
            color: #8aabff;
            border: 1px solid #2a3a7a;
            border-radius: 8px;
            font-size: 13px;
            font-weight: 700;
            padding: 0 28px;
        }
        QPushButton#RenameBtn:hover {
            background: #253580;
            color: #c0d8ff;
            border-color: #4a5aaa;
        }
        QPushButton#RenameBtn:disabled, QPushButton#SkipBtn:disabled,
        QPushButton#DeleteBtn:disabled {
            opacity: 0.3;
        }

        QMessageBox {
            background: #161820;
        }
        """)

    # ─── folder selection ──────────────────────────────────────────

    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder", str(Path.home()))
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
            self.preview_lbl.setText("No supported files found.")
            self.progress_lbl.setText("")

    # ─── sidebar ──────────────────────────────────────────────────

    def _build_sidebar(self):
        # Clear existing
        for item in self.sidebar_items:
            item.setParent(None)
        self.sidebar_items.clear()

        # Remove stretch
        while self.sidebar_layout.count():
            self.sidebar_layout.takeAt(0)

        for i, f in enumerate(self.files):
            item = SidebarItem(i, f.name)
            item.clicked.connect(self._jump_to)
            self.sidebar_items.append(item)
            self.sidebar_layout.addWidget(item)

        self.sidebar_layout.addStretch()

    def _update_sidebar_active(self, index: int):
        for i, item in enumerate(self.sidebar_items):
            item.set_active(i == index)
        # Scroll to active
        if 0 <= index < len(self.sidebar_items):
            QTimer.singleShot(50, lambda: self.scroll_area.ensureWidgetVisible(
                self.sidebar_items[index]))

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
        self._update_sidebar_active(index)
        self.progress_lbl.setText(f"{index + 1} / {len(self.files)}")

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
        self.type_chip.setText(ext.upper())
        self.orig_name_lbl.setText(f"  {filepath.name}")

        # Render preview
        self._full_pixmap = None
        pixmap = None
        if ext == "pdf":
            pixmap = render_pdf_preview(working_path, PREVIEW_W - 2, PREVIEW_H - 2)
        elif ext in ("png", "jpg"):
            pixmap = render_image_preview(working_path, PREVIEW_W - 2, PREVIEW_H - 2)
        elif ext == "docx":
            pixmap = render_docx_preview(working_path, PREVIEW_W - 2, PREVIEW_H - 2)

        if pixmap and not pixmap.isNull():
            self._full_pixmap = pixmap
            self.preview_lbl.setPixmap(
                pixmap.scaled(PREVIEW_W - 2, PREVIEW_H - 2,
                              Qt.AspectRatioMode.KeepAspectRatio,
                              Qt.TransformationMode.SmoothTransformation)
            )
        else:
            self.preview_lbl.setPixmap(QPixmap())
            self.preview_lbl.setText(f"[{ext.upper()} — no preview available]")

        # Pre-fill name input with current stem, select all
        stem = filepath.stem
        self.name_input.setText(stem)
        self.name_input.selectAll()
        self.name_input.setFocus()
        self._update_preview_name(stem)

    def _update_preview_name(self, text: str):
        if not hasattr(self, "_current_ext"):
            return
        norm = normalize_name(text)
        if norm:
            self.preview_name_lbl.setText(f"{norm}.{self._current_ext}")
        else:
            self.preview_name_lbl.setText("")

    # ─── actions ──────────────────────────────────────────────────

    def rename_file(self):
        if not self.files or self.current_index >= len(self.files):
            return
        raw = self.name_input.text().strip()
        norm = normalize_name(raw)
        if not norm:
            self.name_input.setFocus()
            return

        filepath = self.files[self.current_index]
        dest = safe_destination(self.folder, norm, self._current_ext)

        try:
            filepath.rename(dest)
        except PermissionError:
            self._show_readonly_error()
            return
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))
            return

        # Update sidebar label
        if self.current_index < len(self.sidebar_items):
            self.sidebar_items[self.current_index].lbl.setText(dest.name)

        self.files[self.current_index] = dest
        self._advance()

    def skip_file(self):
        self._advance_skip()

    def delete_file(self):
        if not self.files or self.current_index >= len(self.files):
            return
        filepath = self.files[self.current_index]
        reply = QMessageBox.question(
            self, "Confirm Delete",
            f"Permanently delete\n{filepath.name}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            filepath.unlink()
        except PermissionError:
            self._show_readonly_error()
            return
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))
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
        if idx < len(self.sidebar_items):
            item = self.sidebar_items.pop(idx)
            item.setParent(None)
        # Re-number remaining sidebar items
        for i in range(idx, len(self.sidebar_items)):
            self.sidebar_items[i].index = i
            self.sidebar_items[i].num.setText(f"{i + 1}.")
        self.progress_lbl.setText(f"{idx + 1} / {len(self.files)}")

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
        self.preview_lbl.setPixmap(QPixmap())
        self.preview_lbl.setText("✓  All files processed")
        self.name_input.clear()
        self.preview_name_lbl.setText("")
        self.orig_name_lbl.setText("")
        self.type_chip.setText("")
        self.progress_lbl.setText("Done")
        self._set_controls_enabled(False)
        self._update_sidebar_active(-1)

    def _show_readonly_error(self):
        dlg = QMessageBox(self)
        dlg.setWindowTitle("Permission Error")
        dlg.setText("This file is read-only and cannot be modified.")
        dlg.addButton("Continue", QMessageBox.ButtonRole.AcceptRole)
        dlg.exec()

    def _set_controls_enabled(self, enabled: bool):
        self.rename_btn.setEnabled(enabled)
        self.skip_btn.setEnabled(enabled)
        self.delete_btn.setEnabled(enabled)
        self.name_input.setEnabled(enabled)

    def _zoom_preview(self, event):
        if self._full_pixmap and not self._full_pixmap.isNull():
            dlg = ZoomWindow(self._full_pixmap, self)
            dlg.show()


# ─────────────────────────── entry point ─────────────────────────────

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # Dark fusion palette base
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(15, 17, 23))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(232, 232, 232))
    palette.setColor(QPalette.ColorRole.Base, QColor(22, 24, 32))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(26, 28, 40))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(22, 24, 32))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(200, 200, 200))
    palette.setColor(QPalette.ColorRole.Text, QColor(232, 232, 232))
    palette.setColor(QPalette.ColorRole.Button, QColor(30, 32, 48))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(200, 200, 220))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(58, 74, 138))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
    app.setPalette(palette)

    win = FileRenamer()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
