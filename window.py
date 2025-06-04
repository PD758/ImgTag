# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import os, pathlib, typing, logging
import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import ImageTk, Image
import time
import orjson
from send2trash import send2trash


from threading import Thread

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
        self.captured_size = (0, 0)
        self.resize_thb = resize_thb

        for _ in range(3):
            if not self.continue_load_frame():
                break
        else:
            self.thr = Thread(target=self.continue_load, daemon=True)
            self.thr.start()
        
        self.delay = int(self.image.info.get("duration", 100))
        
        self.x -= self.captured_size[0] // 2
        self.y -= self.captured_size[1] // 2
    def start(self):
        self.image_id = self.canvas.create_image(self.x, self.y, image=self.frames[0], anchor="nw")
        self.stopped = False
        self.animate()
    def continue_load_frame(self) -> bool:
        try:
            cp = self.image.copy()
            if self.resize_thb is not None:
                cp.thumbnail(self.resize_thb, Image.Resampling.LANCZOS)
            self.captured_size = cp.size
            self.frames.append(ImageTk.PhotoImage(cp))
            self.image.seek(len(self.frames))
        except EOFError:
            return False
        except OSError:
            return False
        except AttributeError:
            return False
        except ValueError:
            return False
        else:
            return True
    def continue_load(self):
        while self.continue_load_frame():
            pass
    def destroy(self):
        self.stopped = True
    def animate(self):
        if self.frames and not self.stopped:
            self.current_frame = (self.current_frame + 1) % len(self.frames)
            self.canvas.itemconfig(self.image_id, image=self.frames[self.current_frame])
            self.canvas.after(self.delay, self.animate)
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
        
        self.after(50, self.wupdate)
    
        self.window_size: tuple[int, int] = (self.winfo_width(), self.winfo_height())
        
        self.resizelast_detect = 0
    def load_tags(self, image_path: str) -> list[str]:
        if os.path.exists('.'.join(image_path.split('.')[:-1]) + '.json'):
            with open('.'.join(image_path.split('.')[:-1]) + '.json') as f:
                fc = orjson.loads(f.read())
                return fc["tags"]
        else:
            return list()
    def save_tags(self, image_path: str, tag_list: typing.Iterable[str]):
        if os.path.exists('.'.join(image_path.split('.')[:-1]) + '.json'):
            with open('.'.join(image_path.split('.')[:-1]) + '.json') as f:
                fc = orjson.loads(f.read())
        else:
            fc = {}
        fc["tags"] = tag_list
        with open('.'.join(image_path.split('.')[:-1]) + '.json', 'w', newline='') as f:
            f.write(orjson.dumps(fc).decode('utf-8'))
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
    def handle_tag(self, digit):
        logger.debug("Window.handle_tag: %s", digit)
        if any(tag.startswith('score__') for tag in self.tag_list):
            self.tag_list = [tag for tag in self.tag_list if not tag.startswith('score__')]
        self.tag_list.append('score__%s' % ("10" if digit == '*' else digit))
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
            try:
                self._image = self._raw_image.copy()
            except OSError:
                self.reload_image()
                return
            self._image.thumbnail((cw, ch), Image.Resampling.LANCZOS)
            x_center = cw / 2
            y_center = ch / 2
            if isinstance(self._image_cl, GifImageTk):
                self._image_cl.destroy()
                self._image_cl = None
            if self.image_list[self.image_iter].endswith(".gif"):
                if self._image_cl_id is not None:
                    self.image.delete(self._image_cl_id)
                    self._image_cl_id = None
                self._image_cl = GifImageTk(self.image, x_center, y_center, self._raw_image, (cw, ch))
                self._image_cl.start()
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
        CUT_LENGTH = 350
        if len(tags_fs) > CUT_LENGTH: 
            tags_fs = tags_fs[:CUT_LENGTH//2] + "<...>" + tags_fs[-CUT_LENGTH//2:]
        self.tagList.configure(text=f'Tags: {tags_fs}')
    def handle_next(self, *a, **kw):
        try:
            if self.image_list:
                logger.debug("Window.handle_next: switching to next image")
                self.image_iter += 1
                self.image_iter %= len(self.image_list)
                self.cached_prev = (self._raw_image, self._image_cl)
                if isinstance(self._image_cl, GifImageTk):
                    self._image_cl.destroy()
                self.reload_image()
        except:
            pass
    def handle_previous(self, *a, **kw):
        try:
            if self.image_list:
                logger.debug("Window.handle_previous: switching to previous image")
                self.image_iter -= 1
                self.image_iter %= len(self.image_list)
                self.cached_next = (self._raw_image, self._image_cl)
                if isinstance(self._image_cl, GifImageTk):
                    self._image_cl.destroy()
                self.reload_image()
        except:
            pass
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
            self.after(10, self.wupdate)
    def handle_resize(self, event):
        ww = self.winfo_width()
        wh = self.winfo_height()
        if (ww, wh) != self.window_size:
            self.window_size = (ww, wh)
            self.resizelast_detect += 1
            self.after(75, self.resizelast_detect_f, self.resizelast_detect)
    def handle_delete(self, *args, **kwargs):
        logger.debug("Window.handle_delete: deleting image %s", self.image_list[self.image_iter])
        send2trash(self.image_list[self.image_iter])
        if os.path.exists('.'.join(self.image_list[self.image_iter].split('.')[:-1])+'.json'):
            send2trash('.'.join(self.image_list[self.image_iter].split('.')[:-1])+'.json')
        self.image_list.pop(self.image_iter)
        self.reload_image()
    def init_widgets(self):
        logger.debug("Window.init_widgets")
        self.loadButton = tk.Button(self, text="Load from folder", command=self.load_file)
        self.image = tk.Canvas(self, width=100, height=100)
        
        self.dataGroup = tk.Frame(self)
        self.fileNameLabel = tk.Label(self.dataGroup, text="", font=("Courier", 12, 'bold'))
        
        self.tagList = tk.Label(self.dataGroup, text="Tags: ", font=("Courier", 12, 'italic'))
    def wupdate(self):
        self.tagList.configure(wraplength=self.dataGroup.winfo_width())
    def render_widgets(self):
        logger.debug("Window.render_widgets")
        self.loadButton.grid(row=0, column=0, sticky="nsew")        
        self.dataGroup.grid(row=0, column=1, sticky="nsew")
        self.image.grid(row=1, column=0, columnspan=2, sticky="nsew")
        
        self.fileNameLabel.pack(anchor='w')
        
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
        self.bind("<Delete>", self.handle_delete)
