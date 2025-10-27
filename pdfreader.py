# pdf_reader_full.py
import fitz  # PyMuPDF
import json
import os
from functools import partial

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.button import Button
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.filechooser import FileChooserIconView
from kivy.uix.textinput import TextInput
from kivy.uix.spinner import Spinner
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.scrollview import ScrollView
from kivy.graphics.texture import Texture
from kivy.core.window import Window

DATA_FILE = "data.json"
MAX_RECENT = 10

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

class PDFReader(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(orientation="vertical", spacing=6, padding=6, **kwargs)

        # state
        self.doc = None
        self.file_path = None
        self.file_key = None
        self.page_number = 0
        self.zoom = 2.0  # default zoom
        self.data = load_data()
        if "recent" not in self.data:
            self.data["recent"] = []
        if "files" not in self.data:
            self.data["files"] = {}

        # Top control bar
        controls = GridLayout(cols=10, size_hint=(1, None), height=40, spacing=4)
        self.open_btn = Button(text="📂 Open", size_hint_x=None, width=80)
        self.prev_btn = Button(text="⬅ Prev", size_hint_x=None, width=80)
        self.next_btn = Button(text="Next ➡", size_hint_x=None, width=80)
        self.zoom_out_btn = Button(text="➖ Zoom", size_hint_x=None, width=80)
        self.zoom_in_btn = Button(text="➕ Zoom", size_hint_x=None, width=80)

        self.page_input = TextInput(text="", multiline=False, size_hint_x=None, width=80, hint_text="Page")
        self.go_btn = Button(text="Go", size_hint_x=None, width=60)

        self.bookmark_btn = ToggleButton(text="☆ Bookmark", size_hint_x=None, width=100)
        self.dark_toggle = ToggleButton(text="🌙 Dark", size_hint_x=None, width=100)

        # Recent files spinner and bookmarks spinner
        self.recent_spinner = Spinner(text="Recent", values=self._recent_display_values(), size_hint_x=None, width=150)
        self.bookmarks_spinner = Spinner(text="Bookmarks", values=self._empty_values(), size_hint_x=None, width=150)

        # Bind controls
        self.open_btn.bind(on_press=self.open_pdf_dialog)
        self.prev_btn.bind(on_press=self.prev_page)
        self.next_btn.bind(on_press=self.next_page)
        self.zoom_out_btn.bind(on_press=self.zoom_out)
        self.zoom_in_btn.bind(on_press=self.zoom_in)
        self.go_btn.bind(on_press=self.jump_to_page)
        self.bookmark_btn.bind(on_press=self.toggle_bookmark)
        self.dark_toggle.bind(on_press=self.toggle_dark)
        self.recent_spinner.bind(text=self.recent_selected)
        self.bookmarks_spinner.bind(text=self.bookmark_selected)

        # pack controls
        controls.add_widget(self.open_btn)
        controls.add_widget(self.prev_btn)
        controls.add_widget(self.next_btn)
        controls.add_widget(self.zoom_out_btn)
        controls.add_widget(self.zoom_in_btn)
        controls.add_widget(self.page_input)
        controls.add_widget(self.go_btn)
        controls.add_widget(self.bookmark_btn)
        controls.add_widget(self.dark_toggle)
        controls.add_widget(self.recent_spinner)

        # Image display area + right side bookmarks spinner
        display_area = BoxLayout(orientation="horizontal", spacing=6)

        self.image = Image(allow_stretch=True, keep_ratio=True)
        self.page_label = Label(text="No PDF Loaded", size_hint=(1, None), height=30)

        # right panel for bookmarks list (scrollable)
        right_panel = BoxLayout(orientation="vertical", size_hint=(0.22, 1))
        right_panel_label = Label(text="Bookmarks", size_hint=(1, None), height=30)
        self.bookmarks_list_layout = GridLayout(cols=1, size_hint_y=None, spacing=4)
        self.bookmarks_list_layout.bind(minimum_height=self.bookmarks_list_layout.setter('height'))
        bookmarks_scroll = ScrollView(size_hint=(1, 1))
        bookmarks_scroll.add_widget(self.bookmarks_list_layout)
        right_panel.add_widget(right_panel_label)
        right_panel.add_widget(bookmarks_scroll)

        display_area.add_widget(self.image)
        display_area.add_widget(right_panel)

        self.add_widget(controls)
        self.add_widget(display_area)
        self.add_widget(self.page_label)

        # apply saved ui prefs (dark mode)
        ui = self.data.get("ui", {})
        if ui.get("dark_mode"):
            self.dark_toggle.state = "down"
            self._apply_dark_mode(True)
        else:
            self._apply_dark_mode(False)

        # fill bookmarks spinner from selection later
        self._refresh_recent_spinner()
        self._refresh_bookmarks_ui()

    # ---------- UI helpers ----------
    def _recent_display_values(self):
        vals = []
        for p in self.data.get("recent", []):
            try:
                base = os.path.basename(p)
            except Exception:
                base = p
            vals.append(f"{base} — {p}")
        return vals if vals else ["(none)"]

    def _empty_values(self):
        return ["(none)"]

    def _refresh_recent_spinner(self):
        self.recent_spinner.values = self._recent_display_values()
        if self.recent_spinner.values:
            self.recent_spinner.text = "Recent"
        else:
            self.recent_spinner.text = "Recent"

    def _refresh_bookmarks_ui(self):
        # update spinner values and right side list
        values = []
        self.bookmarks_list_layout.clear_widgets()
        if self.file_key and self.file_key in self.data["files"]:
            bms = self.data["files"][self.file_key].get("bookmarks", [])
            for p in sorted(set(bms)):
                values.append(str(p + 1))
                btn = Button(text=f"Page {p+1}", size_hint_y=None, height=36)
                btn.bind(on_press=partial(self._load_bookmark_button, p))
                self.bookmarks_list_layout.add_widget(btn)
        if values:
            self.bookmarks_spinner.values = values
            self.bookmarks_spinner.text = "Bookmarks"
        else:
            self.bookmarks_spinner.values = ["(none)"]
            self.bookmarks_spinner.text = "Bookmarks"

    def _load_bookmark_button(self, p, *args):
        self.page_number = p
        self.show_page()

    def _apply_dark_mode(self, on: bool):
        if on:
            Window.clearcolor = (0.08, 0.08, 0.08, 1)  # dark bg
            self.page_label.color = (1, 1, 1, 1)
            self.dark_toggle.text = "☀ Light"
        else:
            Window.clearcolor = (1, 1, 1, 1)
            self.page_label.color = (0, 0, 0, 1)
            self.dark_toggle.text = "🌙 Dark"

    # ---------- File open / recent ----------
    def open_pdf_dialog(self, instance):
        chooser = FileChooserIconView(filters=["*.pdf"], path=os.getcwd())
        chooser.bind(on_submit=self.load_pdf_from_chooser)
        # replace main content temporarily with chooser
        self.clear_widgets()
        top = BoxLayout(orientation="vertical")
        top.add_widget(chooser)
        back_btn = Button(text="Cancel", size_hint=(1, None), height=40)
        back_btn.bind(on_press=lambda *a: self._restore_ui())
        top.add_widget(back_btn)
        self.add_widget(top)

    def _restore_ui(self):
        # rebuild base UI by reinitializing app (simple approach)
        self.clear_widgets()
        # re-add widgets in same layout by calling __init__ partial setup
        # Instead of recreating object, call parent App.build replacement.
        # For simplicity, we'll just reload app root via App.get_running_app().stop() and restart
        # But to avoid stopping app, we manually rebuild minimal UI:
        # (Recreate content by reading saved data)
        self.__init__()  # reinitialize widget (resets state but reads data.json)
        # If there was an open doc, reopen it
        if self.file_path:
            try:
                self.doc = fitz.open(self.file_path)
                self.file_key = os.path.basename(self.file_path)
                self.page_number = self.data.get("files", {}).get(self.file_key, {}).get("last_page", 0)
                self.zoom = self.data.get("files", {}).get(self.file_key, {}).get("zoom", self.zoom)
                self.show_page()
            except Exception:
                pass

    def load_pdf_from_chooser(self, chooser, selection, touch):
        if not selection:
            return
        path = selection[0]
        self._open_file_path(path)

    def _open_file_path(self, path):
        try:
            doc = fitz.open(path)
        except Exception as e:
            self.page_label.text = f"Error opening: {e}"
            return
        self.doc = doc
        self.file_path = path
        filename = os.path.basename(path)
        self.file_key = filename

        # ensure file entry exists
        files = self.data.setdefault("files", {})
        if filename not in files:
            files[filename] = {"path": path, "last_page": 0, "bookmarks": [], "zoom": self.zoom}
        else:
            # update path in case moved
            files[filename]["path"] = path

        # recent list
        rec = self.data.setdefault("recent", [])
        if path in rec:
            rec.remove(path)
        rec.insert(0, path)
        if len(rec) > MAX_RECENT:
            rec = rec[:MAX_RECENT]
        self.data["recent"] = rec

        # resume last page & zoom if present
        self.page_number = files[filename].get("last_page", 0)
        self.zoom = files[filename].get("zoom", self.zoom)

        save_data(self.data)
        self._refresh_recent_spinner()
        self._refresh_bookmarks_ui()

        # rebuild UI main (instead of chooser view)
        self.clear_widgets()
        # Recreate top controls and display (quick and safe way)
        self.__init__()

        # reopen doc in new instance state
        self.doc = fitz.open(path)
        self.file_path = path
        self.file_key = filename
        self.show_page()

    # ---------- Rendering ----------
    def show_page(self):
        if not self.doc:
            return
        # clamp page_number
        if self.page_number < 0:
            self.page_number = 0
        if self.page_number >= self.doc.page_count:
            self.page_number = self.doc.page_count - 1

        page = self.doc.load_page(self.page_number)
        # use zoom factor for matrix
        mat = fitz.Matrix(self.zoom, self.zoom)
        pix = page.get_pixmap(matrix=mat, alpha=False)  # alpha False gives RGB
        # create Kivy texture
        mode = 'rgb' if pix.alpha == 0 else 'rgba'
        w, h = pix.width, pix.height
        texture = Texture.create(size=(w, h))
        # PyMuPDF pix.samples is bytes in RGB(A) order
        if pix.alpha:
            texture.blit_buffer(pix.samples, colorfmt='rgba', bufferfmt='ubyte')
        else:
            texture.blit_buffer(pix.samples, colorfmt='rgb', bufferfmt='ubyte')
        texture.flip_vertical()
        self.image.texture = texture

        # update label
        total = self.doc.page_count
        self.page_label.text = f"📄 {os.path.basename(self.file_path or '')} — Page {self.page_number + 1} / {total} — Zoom: {self.zoom:.2f}x"

        # save last page and zoom
        if self.file_key:
            files = self.data.setdefault("files", {})
            entry = files.setdefault(self.file_key, {"path": self.file_path, "last_page": 0, "bookmarks": [], "zoom": self.zoom})
            entry["last_page"] = self.page_number
            entry["zoom"] = self.zoom
            entry["path"] = self.file_path
            save_data(self.data)

        # update bookmark button state
        self._update_bookmark_button_state()
        self._refresh_bookmarks_ui()

    # ---------- Navigation ----------
    def next_page(self, instance):
        if not self.doc:
            return
        if self.page_number < self.doc.page_count - 1:
            self.page_number += 1
            self.show_page()

    def prev_page(self, instance):
        if not self.doc:
            return
        if self.page_number > 0:
            self.page_number -= 1
            self.show_page()

    def zoom_in(self, instance):
        # increase zoom moderately
        self.zoom = min(self.zoom * 1.25, 6.0)
        self.show_page()

    def zoom_out(self, instance):
        self.zoom = max(self.zoom / 1.25, 0.5)
        self.show_page()

    def jump_to_page(self, instance):
        if not self.doc:
            return
        text = self.page_input.text.strip()
        if not text:
            return
        try:
            p = int(text) - 1
        except ValueError:
            self.page_label.text = "Invalid page number"
            return
        if 0 <= p < self.doc.page_count:
            self.page_number = p
            self.show_page()
        else:
            self.page_label.text = f"Page out of range (1-{self.doc.page_count})"

    # ---------- Bookmarks ----------
    def toggle_bookmark(self, instance):
        if not self.file_key:
            return
        files = self.data.setdefault("files", {})
        entry = files.setdefault(self.file_key, {"path": self.file_path, "last_page": 0, "bookmarks": [], "zoom": self.zoom})
        bms = set(entry.get("bookmarks", []))
        if self.page_number in bms:
            bms.remove(self.page_number)
            instance.text = "☆ Bookmark"
            instance.state = "normal"
        else:
            bms.add(self.page_number)
            instance.text = "★ Bookmarked"
            instance.state = "down"
        entry["bookmarks"] = sorted(list(bms))
        save_data(self.data)
        self._refresh_bookmarks_ui()

    def _update_bookmark_button_state(self):
        if not self.file_key:
            self.bookmark_btn.state = "normal"
            self.bookmark_btn.text = "☆ Bookmark"
            return
        entry = self.data.get("files", {}).get(self.file_key, {})
        if self.page_number in entry.get("bookmarks", []):
            self.bookmark_btn.state = "down"
            self.bookmark_btn.text = "★ Bookmarked"
        else:
            self.bookmark_btn.state = "normal"
            self.bookmark_btn.text = "☆ Bookmark"

    def recent_selected(self, spinner, text):
        # spinner text is like "name — /full/path"
        if " — " in text:
            parts = text.split(" — ", 1)
            path = parts[1]
            if os.path.exists(path):
                self._open_file_path(path)
            else:
                self.page_label.text = "File not found (moved/removed)."

    def bookmarks_spinner_selected(self, *args):
        pass

    def bookmark_selected(self, spinner, text):
        if not text or text == "(none)":
            return
        try:
            p = int(text) - 1
        except Exception:
            return
        self.page_number = p
        self.show_page()

    # ---------- Dark mode ----------
    def toggle_dark(self, instance):
        on = instance.state == "down"
        self._apply_dark_mode(on)
        ui = self.data.setdefault("ui", {})
        ui["dark_mode"] = on
        save_data(self.data)


class PDFApp(App):
    def build(self):
        self.title = "Kivy PDF Reader — Full"
        return PDFReader()

if __name__ == "__main__":
    PDFApp().run()
