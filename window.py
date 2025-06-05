# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import os
import pathlib
import typing
import logging
import string
import tkinter as tk
import orjson
from tkinter import filedialog, messagebox
from PIL import ImageTk, Image
from threading import Thread
from send2trash import send2trash

import util

logger = logging.getLogger(__name__)

class GifImageTk:
    def __init__(self, canvas, x, y, img: Image.Image, resize_thb: None|tuple[int, int] = None):
        self.canvas = canvas
        self.x = x
        self.y = y

        self.image = img
        self.frames = []
        self.current_frame = 0
        self.captured_size = (0, 0)
        self.resize_thb = resize_thb

        for _ in range(3):
            if not self.continue_load_frame():
                break
        else:
            self.thr = Thread(target=self.continue_load, daemon=True)
            self.thr.start()
        
        self.delay = int(self.image.info.get("duration", 100))
        
        if self.frames:
            self.x -= self.captured_size[0] // 2
            self.y -= self.captured_size[1] // 2
    def start(self):
        if not self.frames:
            logger.warning("GifImageTk.start: no frames to animate")
            return
        if not self.canvas.winfo_exists():
            logger.warning("GifImageTk.start: canvas does not exist")
            return
        self.image_id = self.canvas.create_image(self.x, self.y, image=self.frames[0], anchor="nw")
        self.stopped = False
        self.animate()
    def continue_load_frame(self) -> bool:
        try:
            frame = self.image.copy()
            if self.resize_thb is not None:
                frame.thumbnail(self.resize_thb, Image.Resampling.LANCZOS)
            self.captured_size = frame.size
            self.frames.append(ImageTk.PhotoImage(frame))
            self.image.seek(len(self.frames))
        except EOFError:
            return False
        except (OSError, AttributeError, ValueError) as e:
            logger.error(f"GifImageTk.continue_load_frame: error processing frame: {e}")
            return False
        else:
            return True
    def continue_load(self):
        while self.continue_load_frame():
            pass
        logger.debug("GifImageTk.continue_load: finished loading frames")
    def destroy(self):
        self.stopped = True
        if self.image_id and self.canvas.winfo_exists():
            try:
                self.canvas.delete(self.image_id)
            except tk.TclError:
                pass
        self.image_id = None
        self.frames = []
    def animate(self):
        if self.stopped:
            if self.image_id and self.canvas.winfo_exists():
                try:
                    self.canvas.delete(self.image_id)
                except tk.TclError: pass
                self.image_id = None
            return

        if self.frames and self.canvas.winfo_exists():
            self.current_frame = (self.current_frame + 1) % len(self.frames)
            try:
                if self.image_id:
                    self.canvas.itemconfig(self.image_id, image=self.frames[self.current_frame])
                else:
                    logger.warning("GifImageTk.animate: image_id is None, cannot update")
                    self.stopped = True
                    return
            except tk.TclError as e:
                logger.warning(f"GifImageTk.animate: TclError while updating canvas: {e}, stopping")
                self.stopped = True
                if self.image_id: self.canvas.delete(self.image_id)
                self.image_id = None
                return
            self.canvas.after(self.delay, self.animate)
        elif not self.frames and self.image_id and self.canvas.winfo_exists():
            try:
                self.canvas.delete(self.image_id)
            except tk.TclError: pass
            self.image_id = None

class Window(tk.Tk):
    def __init__(self):
        logger.debug("Window.__init__")
        super().__init__()
        
        self.image_list:    list[str] = []
        self.image_iter:    int = 0
        self.window_size:   tuple[int, int] = (1, 1)
        self.tag_list:      list[str] = []
        
        self._raw_image:    None|Image.Image = None
        self._image:        None|Image.Image = None
        self._image_cl:     None|ImageTk.PhotoImage|ImageTk.BitmapImage|GifImageTk = None
        self._image_cl_id:  None|int = None
        
        self.title("Image Tagger")
        self.geometry("900x600")
        
        self.init_widgets()
        self.render_widgets()
        self.register_hotkeys()
        
        self.update_idletasks()
    
        self.window_size: tuple[int, int] = (self.winfo_width(), self.winfo_height())
        
        self.resizelast_detect = 0
        self.protocol("WM_DELETE_WINDOW", self.on_close)
    def load_tags(self, image_path: str) -> list[str]:
        json_path = os.path.splitext(image_path)[0] + '.json'
        if os.path.exists(json_path):
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    fc = orjson.loads(f.read())
                return fc.get("tags", [])
            except Exception as e:
                logger.error("Window.load_tags: Error reading JSON %s: %s", json_path, e)
                return []
        else:
            return []
    def save_tags(self, image_path: str, tag_list: typing.Iterable[str]):
        json_path = os.path.splitext(image_path)[0] + '.json'
        fc = {}
        if os.path.exists(json_path):
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    fc = orjson.loads(f.read())
            except Exception as e:
                logger.warning("Window.save_tags: Could not parse existing JSON %s: %s", json_path, e)
                fc = {}
        fc["tags"] = list(tag_list)
        try:
            with open(json_path, 'wb') as f:
                f.write(orjson.dumps(fc))
        except Exception as e:
            logger.error("Window.save_tags: Error writing JSON %s: %s", json_path, e)
    def load_file(self):
        logger.debug("Window.load_file: asking filepicker")
        picked_dir_raw = filedialog.askdirectory(mustexist=True)
        if picked_dir_raw:
            try:
                picked_dir = str(pathlib.Path(picked_dir_raw).resolve())
            except BaseException as e:
                logger.error("Window.load_file: failed to resolve path %s: %s", picked_dir_raw, e)
                messagebox.showerror("Error", "Failed to resolve path %s: %s" % (picked_dir_raw, e))
                return
            logger.debug("Window.load_file: picked %s", picked_dir)
            files = util.rec_listdir(picked_dir,
                            lambda path: util.check_ends(path, [".png", ".jpg", ".jpeg", ".bmp", ".gif"], ignore_case=True))
            if not files:
                messagebox.showinfo("No files found", "No supported images found in selected directory")
            self.image_list = files
            self.image_iter = 0
            self.reload_image()
        else:
            logger.debug("Window.load_file: canceled")
    def handle_tag(self, digit):
        logger.debug("Window.handle_tag: %s", digit)
        if any(tag.startswith('score__') for tag in self.tag_list):
            self.tag_list = [tag for tag in self.tag_list if not tag.startswith('score__')]
        self.tag_list.append('score__%s' % ("10" if digit == '*' else digit))
        self.save_tags(self.image_list[self.image_iter], self.tag_list)
        self.flush_tags()
    def reload_image(self):
        if not self.image_list:
            return
        
        logger.debug("Window.reload_image: loading image %s", self.image_list[self.image_iter])
        try:
            self._raw_image = Image.open(self.image_list[self.image_iter])
        except BaseException as e:
            logger.error("Window.reload_image: failed to load image %s: %s", self.image_list[self.image_iter], e)
            messagebox.showerror("Error", "Failed to load image %s: %s" % (self.image_list[self.image_iter], e))
            self.image_list.pop(self.image_iter)
            self.image_iter = 0
            self.reload_image()
            return
        pc = (self.image_iter+1) / len(self.image_list) * 100
        self.fileNameLabel.configure(text=f"{pc:.2f}% {self.image_iter+1}/{len(self.image_list)}\t" + self.image_list[self.image_iter])
        self.reload_tags()
        self.flush_image()
    def flush_image(self, _recprotect = True):
        if self.image_list and self._raw_image is not None:
            logger.debug("Window.flush_image: flushing canvas")
            cw = self.image.winfo_width()
            ch = self.image.winfo_height()
            if (cw < 10 or ch < 10) and _recprotect:
                self.after(10, self.flush_image, False)
                return
            try:
                self._image = self._raw_image.copy()
            except OSError:
                self.reload_image()
                return
            self._image.thumbnail((cw, ch), Image.Resampling.LANCZOS)
            x_center = cw / 2
            y_center = ch / 2
            try:
                if self.image_list[self.image_iter].lower().endswith(".gif"):
                    self._image_cl = GifImageTk(self.image, x_center, y_center, self._raw_image, resize_thb=(cw, ch))
                    self._image_cl.start()
                    self._image_cl_id = None
                else:
                    self._image = self._raw_image.copy()
                    self._image.thumbnail((cw, ch), Image.Resampling.LANCZOS)
                    
                    self._image_cl = ImageTk.PhotoImage(self._image)
                    if self._image_cl_id is not None:
                        self.image.delete(self._image_cl_id)
                    self._image_cl_id = self.image.create_image(x_center, y_center, image=self._image_cl)
            except Exception as e:
                logger.error("Window.flush_image: error during image processing/display for %s: %s", self.image_list[self.image_iter], e, exc_info=True)
                messagebox.showerror("Image display error", f"Could not display image: {self.image_list[self.image_iter]}\n{e}")
                self.after(10, self.reload_image)
    def reload_tags(self):
        if self.image_list:
            logger.debug("Window.reload_tags: reloading tags for image %s", self.image_list[self.image_iter])
            self.tag_list = self.load_tags(self.image_list[self.image_iter])
        else:
            self.tag_list = []
        self.flush_tags()
    def flush_tags(self):
        logger.debug("Window.flush_tags")
        tags_fs = ('"' + '", "'.join(self.tag_list) + '"') if self.tag_list else 'None'
        CUT_LENGTH = 360
        if len(tags_fs) > CUT_LENGTH: 
            tags_fs = tags_fs[:CUT_LENGTH//2] + "<...>" + tags_fs[-CUT_LENGTH//2:]
        if hasattr(self, 'tagList') and self.tagList.winfo_exists():
            self.tagList.configure(text=f'Tags: {tags_fs}')
        else:
            logger.warning("Window.flush_tags: tagList widget does not exist.")
    def handle_next(self, *a, **kw):
        if self.image_list:
            logger.debug("Window.handle_next: switching to next image")
            self.image_iter = (self.image_iter + 1) % len(self.image_list)
            self.reload_image()
    def handle_previous(self, *a, **kw):
        if self.image_list:
            logger.debug("Window.handle_previous: switching to previous image")
            self.image_iter = (self.image_iter - 1 + len(self.image_list)) % len(self.image_list)
            self.reload_image()
    def keypress_callback(self, event: tk.Event):
        if event.char == 'a':
            self.handle_previous()
        elif event.char == 'd':
            self.handle_next()
        elif event.char and (event.char in string.digits or event.char == '*'):
            self.handle_tag(event.char)
    def resizelast_detect_f(self, f_detect_i: int):
        if f_detect_i == self.resizelast_detect:
            logger.debug("Window.resizelast_detect_f: detected window resize")
            self.resizelast_detect = 0
            self.flush_image()
    def handle_resize(self, event):
        ww = self.winfo_width()
        wh = self.winfo_height()
        if (ww, wh) != self.window_size:
            self.window_size = (ww, wh)
            self.resizelast_detect += 1
            self.after(75, self.resizelast_detect_f, self.resizelast_detect)
    def handle_delete(self, *args, **kwargs):
        if not self.image_list:
            messagebox.showinfo("Delete", "No image to delete.")
            return
        confirm = messagebox.askyesno("Delete File", f"Are you sure you want to delete:\n{self.image_list[self.image_iter]}\n(and its .json sidecar file, if any)?")
        if not confirm:
            return
        logger.debug("Window.handle_delete: deleting image %s", self.image_list[self.image_iter])
        try:
            send2trash(self.image_list[self.image_iter])
            if os.path.exists('.'.join(self.image_list[self.image_iter].split('.')[:-1])+'.json'):
                send2trash('.'.join(self.image_list[self.image_iter].split('.')[:-1])+'.json')
            self.image_list.pop(self.image_iter)
            self.reload_image()
        except BaseException as e:
            logger.error("Window.handle_delete: %s", e)
            messagebox.showerror("Delete error", f"Failed to delete file: {e}")
    def init_widgets(self):
        logger.debug("Window.init_widgets")
        self.loadButton = tk.Button(self, text="Load from folder", command=self.load_file)
        self.image = tk.Canvas(self, width=100, height=100, highlightthickness=0)
        
        self.dataGroup = tk.Frame(self)
        self.fileNameLabel = tk.Label(self.dataGroup, text="No file loaded", font=("Courier", 12, 'bold'))
        
        self.tagList = tk.Label(self.dataGroup, text="Tags: None", font=("Courier", 12, 'italic'))
    def update_taglist_wraplength(self, event=None):
        if hasattr(self, 'dataGroup') and self.dataGroup.winfo_exists() and \
           hasattr(self, 'tagList') and self.tagList.winfo_exists():
            new_wraplength = max(50, self.dataGroup.winfo_width() - 10)
            if self.tagList.cget("wraplength") != new_wraplength:
                 self.tagList.configure(wraplength=new_wraplength)
    def render_widgets(self):
        logger.debug("Window.render_widgets")
        self.loadButton.grid(row=0, column=0, columnspan=2, sticky="ew", padx=5, pady=5)        
        self.dataGroup.grid(row=1, column=0, columnspan=2, sticky="ew", padx=5)
        self.image.grid(row=2, column=0, columnspan=2, sticky="nsew", padx=5, pady=5)
        
        self.fileNameLabel.pack(anchor='w')
        self.tagList.pack(fill=tk.X, expand=True, anchor='w')

        self.grid_columnconfigure(0, weight=1)
        
        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=0)
        self.grid_rowconfigure(2, weight=1)
    def register_hotkeys(self):
        logger.debug("Window.register_hotkeys")
        self.bind_all("<KeyPress>", self.keypress_callback, add='+')
        self.bind("<Key-Left>", self.handle_previous)
        self.bind("<Key-Right>", self.handle_next)
        self.bind("<Configure>", self.handle_resize)
        self.bind("<Configure>", self.update_taglist_wraplength)
        self.bind("<Delete>", self.handle_delete)
        self.bind("<Escape>", lambda e: self.on_close())
    def on_close(self):
        for after_id in self.tk.eval('after info').split():
            self.after_cancel(after_id)
        #self.destroy()
        exit(0)
