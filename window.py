# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import os, pathlib, typing, logging
import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import ImageTk, Image
import csv

import string

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
        self.stopped = False
        self.captured_size = (0, 0)

        try:
            while True:
                cp = self.image.copy()
                if resize_thb is not None:
                    cp.thumbnail(resize_thb, Image.Resampling.LANCZOS)
                self.captured_size = cp.size
                self.frames.append(ImageTk.PhotoImage(cp))
                self.image.seek(len(self.frames))
        except EOFError:
            pass
        
        self.x -= self.captured_size[0] // 2
        self.y -= self.captured_size[1] // 2

        self.image_id = self.canvas.create_image(self.x, self.y, image=self.frames[0], anchor="nw")
        self.animate()
    def destroy(self):
        self.stopped = True
    def animate(self):
        if self.frames and not self.stopped:
            self.current_frame = (self.current_frame + 1) % len(self.frames)
            self.canvas.itemconfig(self.image_id, image=self.frames[self.current_frame])
            delay = int(self.image.info.get("duration", 100))
            self.canvas.after(delay, self.animate)
        elif self.stopped:
            self.canvas.delete(self.image_id)

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
        
    def load_tags(self, image_path: str) -> list[str]:
        if os.path.exists('.'.join(image_path.split('.')[:-1]) + '.tags.csv'):
            with open('.'.join(image_path.split('.')[:-1]) + '.tags.csv') as f:
                fc = csv.reader(f)
                return list(list(zip(*(list(fc)[1:])))[0])
        else:
            return list()
    def save_tags(self, image_path: str, tag_list: typing.Iterable[str]):
        with open('.'.join(image_path.split('.')[:-1]) + '.tags.csv', 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(('tag_name',))
            writer.writerows(((t,) for t in tag_list))
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
            self.image_list = files
            self.image_iter = 0
            self.reload_image()
        else:
            logger.debug("Window.load_file: canceled")
    def handle_tag(self, digit: int):
        logger.debug("Window.handle_tag: %d", digit)
        if any(tag.startswith('score__') for tag in self.tag_list):
            self.tag_list = [tag for tag in self.tag_list if not tag.startswith('score__')]
        if self.tagType.get() == 'bool':
            self.tag_list.append('score__1' if digit == 1 else 'score__0')
        else:
            self.tag_list.append('score__%d' % digit)
        self.save_tags(self.image_list[self.image_iter], self.tag_list)
        self.flush_tags()
    def reload_image(self):
        if self.image_list:
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
            self.fileNameLabel.configure(text=self.image_list[self.image_iter])
            self.reload_tags()
            self.flush_image()
    def flush_image(self, _recprotect = True):
        if self.image_list and self._raw_image is not None:
            logger.debug("Window.flush_image: flushing canvas")
            self.flush_tags()
            cw = self.image.winfo_width()
            ch = self.image.winfo_height()
            if (cw < 10 or ch < 10) and _recprotect:
                self.after(10, self.flush_image, False)
                return
            self._image = self._raw_image.copy()
            self._image.thumbnail((cw, ch), Image.Resampling.LANCZOS)
            x_center = cw / 2
            y_center = ch / 2
            if isinstance(self._image_cl, GifImageTk):
                self._image_cl.destroy()
                self._image_cl = None
            if self.image_list[self.image_iter].endswith(".gif"):
                self._image_cl = GifImageTk(self.image, x_center, y_center, self._raw_image, (cw, ch))
            else:
                self._image_cl = ImageTk.PhotoImage(self._image)
                if self._image_cl_id is None:
                    self._image_cl_id = self.image.create_image(x_center, y_center, image=self._image_cl)
                else:
                    self.image.itemconfig(self._image_cl_id, image=self._image_cl)
                    self.image.coords(self._image_cl_id, x_center, y_center)
    def reload_tags(self):
        if self.image_list:
            logger.debug("Window.reload_tags: reloading tags for image %s", self.image_list[self.image_iter])
            self.tag_list = self.load_tags(self.image_list[self.image_iter])
            self.flush_tags()
    def flush_tags(self):
        logger.debug("Window.flush_tags")
        tags_fs = ('"' + '", "'.join(self.tag_list) + '"') if self.tag_list else 'None'
        self.tagList.configure(text=f'Tags: {tags_fs}')
    def handle_next(self, *a, **kw):
        if self.image_list:
            logger.debug("Window.handle_next: switching to next image")
            self.image_iter += 1
            self.image_iter %= len(self.image_list)
            self.reload_image()
    def handle_previous(self, *a, **kw):
        if self.image_list:
            logger.debug("Window.handle_previous: switching to previous image")
            self.image_iter -= 1
            self.image_iter %= len(self.image_list)
            self.reload_image()
    def keypress_callback(self, event: tk.Event):
        if event.char == 'a':
            self.handle_previous()
        elif event.char == 'd':
            self.handle_next()
        elif event.char and event.char in string.digits:
            self.handle_tag(int(event.char))
    def resizelast_detect_f(self, f_detect_i: int):
        if f_detect_i == self.resizelast_detect:
            logger.debug("Window.resizelast_detect_f: detected window resize")
            self.flush_image()
            self.resizelast_detect = 0
    def handle_resize(self, event):
        ww = self.winfo_width()
        wh = self.winfo_height()
        if (ww, wh) != self.window_size:
            self.window_size = (ww, wh)
            self.resizelast_detect += 1
            self.after(50, self.resizelast_detect_f, self.resizelast_detect)
    def init_widgets(self):
        logger.debug("Window.init_widgets")
        self.loadButton = tk.Button(self, text="Load from folder", command=self.load_file)
        self.image = tk.Canvas(self, width=100, height=100)
        
        self.dataGroup = tk.Frame(self)
        self.fileNameLabel = tk.Label(self.dataGroup, text="", font=("Courier", 12, 'bold'))
        
        self.tagType = tk.StringVar(self)
        self.tagType.set("bool") 
        self.tagTypeMenuLabel = tk.Label(self.dataGroup, text="Tag type:")
        self.tagTypeMenu = tk.OptionMenu(self.dataGroup, self.tagType, "bool", "digit")
        
        self.tagList = tk.Label(self.dataGroup, text="Tags: ", font=("Courier", 12, 'italic'))
    def render_widgets(self):
        logger.debug("Window.render_widgets")
        self.loadButton.grid(row=0, column=0, sticky="nsew")        
        self.dataGroup.grid(row=0, column=1, sticky="nsew")
        self.image.grid(row=1, column=0, columnspan=2, sticky="nsew")
        
        self.fileNameLabel.pack(anchor='w')
        self.tagTypeMenuLabel.pack(anchor='e')
        self.tagTypeMenu.pack(anchor='e')
        
        self.tagList.pack(anchor='sw')

        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=3)
        
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=10)
    def register_hotkeys(self):
        logger.debug("Window.register_hotkeys")
        self.bind_all("<KeyPress>", self.keypress_callback)
        self.bind("<Key-Left>", self.handle_previous)
        self.bind("<Key-Right>", self.handle_next)
        self.bind("<Configure>", self.handle_resize)
