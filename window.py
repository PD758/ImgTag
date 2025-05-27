# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import os, pathlib, typing
import tkinter as tk
from tkinter import filedialog
from PIL import ImageTk, Image
import csv

import util

class Window(tk.Tk):
    def __init__(self):
        super().__init__()
        
        self.image_list:    list[pathlib.Path] = []
        self.image_iter:    int = 0
        self.window_size:   tuple[int, int] = (1, 1)
        
        self._raw_image:    None|Image.Image = None
        self._image:        None|Image.Image = None
        self._image_cl:     None|ImageTk.PhotoImage|ImageTk.BitmapImage = None
        self._image_cl_id:  None|int = None
        
        self.init_widgets()
        self.render_widgets()
        self.register_hotkeys()
        
        self.update_idletasks()
    
        self.window_size: tuple[int, int] = (self.winfo_width(), self.winfo_height())
        
        self.resizelast_detect = 0
        
    def load_tags(self, image_path: str) -> tuple[str]:
        if os.path.exists('.'.join(image_path.split('.')[:-1]) + '.tags.csv'):
            with open('.'.join(image_path.split('.')[:-1]) + '.tags.csv') as f:
                fc = csv.reader(f)
                return list(zip(*(list(fc)[1:])))[0]
        else:
            return tuple()
    def save_tags(self, image_path: str, tag_list: typing.Iterable[str]):
        with open('.'.join(image_path.split('.')[:-1]) + '.tags.csv', 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(('tag_name',))
            writer.writerows(((t,) for t in tag_list))
    def load_file(self):
        picked_dir = filedialog.askdirectory(mustexist=True)
        if picked_dir:
            files = util.rec_listdir(picked_dir,
                            lambda path: util.check_ends(path, [".png", ".jpg", ".jpeg", ".bmp"], ignore_case=True))
            self.image_list = files
            self.image_iter = 0
            self.reload_image()
        else:
            print("Pick canceled")
    def reload_image(self):
        if self.image_list:
            print("reloading image", self.image_list[self.image_iter])
            self._raw_image = Image.open(self.image_list[self.image_iter])
            self.flush_image()
    def d_flush_image(self):
        self.flush_image(_recprotect=False)
    def flush_image(self, _recprotect = True):
        if self.image_list and self._raw_image is not None:
            print("flushing image")
            cw = self.image.winfo_width()
            ch = self.image.winfo_height()
            if (cw < 10 or ch < 10) and _recprotect:
                self.after(10, self.d_flush_image)
                return
            self._image = self._raw_image.copy()
            self._image.thumbnail((cw, ch), Image.Resampling.LANCZOS)
            self._image_cl = ImageTk.PhotoImage(self._image)
            x_center = cw / 2
            y_center = ch / 2
            if self._image_cl_id is None:
                self._image_cl_id = self.image.create_image(x_center, y_center, image=self._image_cl)
            else:
                self.image.itemconfig(self._image_cl_id, image=self._image_cl)
                self.image.coords(self._image_cl_id, x_center, y_center)
    def handle_next(self, *a, **kw):
        if self.image_list:
            self.image_iter += 1
            self.image_iter %= len(self.image_list)
            self.reload_image()
    def handle_previous(self, *a, **kw):
        if self.image_list:
            self.image_iter -= 1
            self.image_iter %= len(self.image_list)
            self.reload_image()
    def keypress_callback(self, event: tk.Event):
        if event.char == 'a':
            self.handle_previous()
        elif event.char == 'd':
            self.handle_next()
    def resizelast_detect_f(self, f_detect_i: int):
        if f_detect_i == self.resizelast_detect:
            self.flush_image()
            self.resizelast_detect = 0
    def handle_resize(self, event):
        if (event.width, event.height) != self.window_size:
            self.window_size = (event.width, event.height)
            self.resizelast_detect += 1
            self.after(50, self.resizelast_detect_f, self.resizelast_detect)
    def init_widgets(self):
        self.loadButton = tk.Button(self, text="Load from folder", command=self.load_file)
        self.image = tk.Canvas(self, width=100, height=100)
    def render_widgets(self):
        self.loadButton.pack()
        self.image.pack(fill=tk.BOTH, expand=True)
    def register_hotkeys(self):
        self.bind_all("<KeyPress>", self.keypress_callback)
        self.bind("<Key-Left>", self.handle_previous)
        self.bind("<Key-Right>", self.handle_next)
        self.bind("<Configure>", self.handle_resize)
