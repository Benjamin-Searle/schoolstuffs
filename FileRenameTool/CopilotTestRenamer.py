import os
import tkinter as tk
from tkinter import messagebox, filedialog, Toplevel
from PIL import Image, ImageTk
import fitz
from docx import Document
import zipfile


class FileRenamerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Quick File Renamer")
        self.root.geometry("900x500")
        self.root.resizable(False, False)

        self.folder = filedialog.askdirectory(title="Select Folder")
        if not self.folder:
            root.quit()
            return

        self.files = sorted(os.listdir(self.folder))
        self.index = 0

        # ===== LEFT PANEL =====
        self.left = tk.Frame(root, width=250)
        self.left.pack(side="left", fill="y")

        self.listbox = tk.Listbox(self.left)
        self.listbox.pack(fill="both", expand=True)

        for f in self.files:
            self.listbox.insert(tk.END, f)

        self.listbox.bind("<<ListboxSelect>>", self.jump_to_file)

        # ===== RIGHT PANEL =====
        self.right = tk.Frame(root)
        self.right.pack(side="right", fill="both", expand=True)

        self.preview_label = tk.Label(self.right, cursor="hand2")
        self.preview_label.pack(pady=10)
        self.preview_label.bind("<Button-1>", self.open_zoom)

        self.text_preview = tk.Text(self.right, height=10, width=60)
        self.text_preview.pack()
        self.text_preview.pack_forget()  # hidden by default

        self.entry = tk.Entry(self.right, font=("Arial", 14))
        self.entry.pack(pady=10)
        self.entry.bind("<Return>", self.rename_file)

        btn_frame = tk.Frame(self.right)
        btn_frame.pack()

        tk.Button(btn_frame, text="Skip", command=self.skip_file).pack(side="left", padx=5)
        tk.Button(btn_frame, text="Delete", command=self.delete_file).pack(side="left", padx=5)

        self.progress = tk.Label(self.right)
        self.progress.pack(pady=10)

        self.root.bind("<Control-s>", lambda e: self.skip_file())
        self.root.bind("<Control-d>", lambda e: self.delete_file())

        self.current_preview_image = None
        self.detected_type = None

        self.load_file()

    # ===== FILE TYPE DETECTION =====
    def detect_file_type(self, filepath):
        try:
            with open(filepath, "rb") as f:
                header = f.read(8)

            if header.startswith(b"\x89PNG"):
                return "png"
            elif header.startswith(b"\xFF\xD8\xFF"):
                return "jpg"
            elif header.startswith(b"GIF"):
                return "gif"
            elif header.startswith(b"%PDF"):
                return "pdf"
            elif header.startswith(b"PK"):
                try:
                    with zipfile.ZipFile(filepath) as z:
                        if "word/document.xml" in z.namelist():
                            return "docx"
                    return "zip"
                except:
                    return "zip"
        except:
            pass
        return "unknown"

    def normalize_name(self, name):
        return name.strip().replace(" ", "_").lower()

    def get_unique_filename(self, base_name, extension):
        candidate = base_name
        count = 2

        while True:
            full_path = os.path.join(self.folder, candidate + extension)
            if not os.path.exists(full_path):
                return candidate
            candidate = f"{base_name}_{count:02d}"
            count += 1

    def jump_to_file(self, event):
        if not self.listbox.curselection():
            return
        self.index = self.listbox.curselection()[0]
        self.load_file()

    def load_file(self):
        if self.index >= len(self.files):
            messagebox.showinfo("Done", "No more files!")
            self.root.quit()
            return

        self.file = self.files[self.index]
        self.filepath = os.path.join(self.folder, self.file)

        self.listbox.selection_clear(0, tk.END)
        self.listbox.selection_set(self.index)
        self.listbox.see(self.index)

        name, _ = os.path.splitext(self.file)

        self.entry.delete(0, tk.END)
        self.entry.insert(0, name)

        # ✅ FIX: force focus after UI updates
        self.root.after(50, lambda: self.entry.focus_set())
        self.entry.selection_range(0, tk.END)

        self.progress.config(text=f"File {self.index + 1} of {len(self.files)}")

        self.detected_type = self.detect_file_type(self.filepath)

        self.show_preview()

    def show_preview(self):
        self.preview_label.config(image='')
        self.text_preview.pack_forget()
        self.text_preview.delete("1.0", tk.END)
        self.current_preview_image = None

        try:
            if self.detected_type in ["png", "jpg", "gif"]:
                img = Image.open(self.filepath)

            elif self.detected_type == "pdf":
                doc = fitz.open(self.filepath)
                page = doc[0]
                pix = page.get_pixmap()
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

            elif self.detected_type == "docx":
                doc = Document(self.filepath)
                text = "\n".join([p.text for p in doc.paragraphs[:10]])
                self.text_preview.insert(tk.END, text)
                self.text_preview.pack()
                return

            else:
                self.text_preview.insert(tk.END, f"No preview available\n\n{self.file}")
                self.text_preview.pack()
                return

            self.current_preview_image = img.copy()

            preview = img.copy()
            preview.thumbnail((300, 300))
            self.tk_img = ImageTk.PhotoImage(preview)

            self.preview_label.config(image=self.tk_img)

        except Exception as e:
            self.text_preview.insert(tk.END, str(e))
            self.text_preview.pack()

    def open_zoom(self, event=None):
        if self.current_preview_image is None:
            return

        win = Toplevel(self.root)
        win.title("Zoom Preview")

        img = self.current_preview_image.copy()
        img.thumbnail((1000, 1000))
        tk_img = ImageTk.PhotoImage(img)

        label = tk.Label(win, image=tk_img)
        label.image = tk_img
        label.pack()

    def rename_file(self, event=None):
        raw_name = self.entry.get()
        if not raw_name.strip():
            return

        base_name = self.normalize_name(raw_name)

        ext_map = {
            "png": ".png",
            "jpg": ".jpg",
            "gif": ".gif",
            "pdf": ".pdf",
            "docx": ".docx"
        }
        extension = ext_map.get(self.detected_type, "")

        unique_name = self.get_unique_filename(base_name, extension)

        new_path = os.path.join(self.folder, unique_name + extension)

        try:
            os.rename(self.filepath, new_path)

            self.files[self.index] = unique_name + extension
            self.listbox.delete(self.index)
            self.listbox.insert(self.index, unique_name + extension)

        except Exception as e:
            messagebox.showerror("Error", str(e))
            return

        self.index += 1
        self.load_file()

    def skip_file(self):
        self.index += 1
        self.load_file()

    def delete_file(self):
        confirm = messagebox.askyesno("Delete", f"Delete {self.file}?")
        if confirm:
            os.remove(self.filepath)
            del self.files[self.index]
            self.listbox.delete(self.index)
            self.load_file()


if __name__ == "__main__":
    root = tk.Tk()
    app = FileRenamerApp(root)
    root.mainloop()