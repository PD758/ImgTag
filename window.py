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

try:
    import vlc
    import platform
    VLC_SUPPORT = True
except ImportError:
    if typing.TYPE_CHECKING:
        raise
    VLC_SUPPORT = False
    messagebox.showwarning("VLC Missing", "python-vlc library not found. Video playback will be disabled.")

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
    VIDEO_EXTENSIONS = [".mp4", ".avi", ".mov", ".mkv"]
    
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
   
        if VLC_SUPPORT:
            try:
                self.vlc_instance: vlc.Instance = vlc.Instance("--no-xlib" if platform.system() == 'Linux' else "") # type: ignore
                self.vlc_player: vlc.MediaPlayer = self.vlc_instance.media_player_new()
                self.playing_video: bool = False
                self.volume: int = 50
            except BaseException as e:
                logger.error("Window.__init__: Failed to initialize VLC: %s", e)
                messagebox.showerror("VLC Initialization Error", f"Could not initialize VLC player. Video playback will be affected.\nError: {e}")
                globals()["VLC_SUPPORT"] = False
        
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
                            lambda path: util.check_ends(path, [".png", ".jpg", ".jpeg", ".bmp", ".gif"]
                                                         + (self.VIDEO_EXTENSIONS if VLC_SUPPORT else []), ignore_case=True))
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
        
        self._clean_mediasource()
        try:
            assert os.path.exists(self.image_list[self.image_iter]), f"Media {self.image_list[self.image_iter]} does not exist"
        except BaseException as e:
            logger.error("Window.reload_image: failed to load media %s: %s", self.image_list[self.image_iter], e)
            messagebox.showerror("Error", "Failed to load media %s: %s" % (self.image_list[self.image_iter], e))
            self.image_list.pop(self.image_iter)
            self.image_iter = 0
            self.reload_image()
            return
        pc = (self.image_iter+1) / len(self.image_list) * 100
        self.reload_tags()
        if VLC_SUPPORT and os.path.splitext(self.image_list[self.image_iter])[1].lower() in self.VIDEO_EXTENSIONS:
            logger.debug("Window.reload_image: loading video %s", self.image_list[self.image_iter])
            try:
                media: vlc.Media = self.vlc_instance.media_new(self.image_list[self.image_iter])
                if not media:
                    raise RuntimeError("Failed to load video %s" % self.image_list[self.image_iter])
                
                media.parse()
                length = media.get_duration()
                
                media.add_option('input-repeat=65535')
                self.vlc_player.set_media(media)
                media.release()
                self.image.update_idletasks()
                win_id = self.image.winfo_id()
                if platform.system() in ["Windows", "Darwin"]:
                    self.vlc_player.set_hwnd(win_id)
                else:
                    self.vlc_player.set_xwindow(win_id)
                self.playing_video = True
                self.vlc_player.audio_set_volume(self.volume)
                if self.vlc_player.play() == -1:
                    raise RuntimeError(f"Failed to play video {self.image_list[self.image_iter]}")
                mins_f = (length / 1000) // 60
                if mins_f > 0:
                    timespf = f"{int(mins_f):02d}:{int((length / 1000)%60):02d}"
                else:
                    timespf = f"{(length/1000):.1f} sec."
                
                self.curr_timespf = timespf
                
                self.fileNameLabel.configure(text=f"V={self.volume}%\t{pc:.2f}% {self.image_iter+1}/{len(self.image_list)}\t" + self.image_list[self.image_iter] +
                                             f"\t{timespf}")
            except BaseException as e:
                logger.error("Window.reload_image: failed to load video %s: %s", self.image_list[self.image_iter], e)
                messagebox.showerror("Error", f"Failed to load video {self.image_list[self.image_iter]}: {e}")
                self.image_list.pop(self.image_iter)
                self.image_iter = 0
                self.reload_image()
                return
        else:
            try:
                self._raw_image = Image.open(self.image_list[self.image_iter])
            except BaseException as e:
                logger.error("Window.reload_image: failed to load image %s: %s", self.image_list[self.image_iter], e)
                messagebox.showerror("Error", "Failed to load image %s: %s" % (self.image_list[self.image_iter], e))
                self.image_list.pop(self.image_iter)
                self.image_iter = 0
                self.reload_image()
                return
            self.playing_video = False
            self.fileNameLabel.configure(text=f"{pc:.2f}% {self.image_iter+1}/{len(self.image_list)}\t" + self.image_list[self.image_iter])
            self.flush_image()
    def flush_image(self, _recprotect = True):
        
        if VLC_SUPPORT and self.playing_video:
            if hasattr(self, '_image_cl_id') and self._image_cl_id is not None:
                try: self.image.delete(self._image_cl_id)
                except tk.TclError: pass
                self._image_cl_id = None
            return
        
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
    def reload_tags(self, flush: bool = True):
        if self.image_list:
            logger.debug("Window.reload_tags: reloading tags for image %s", self.image_list[self.image_iter])
            self.tag_list = self.load_tags(self.image_list[self.image_iter])
        else:
            self.tag_list = []
        if flush:
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
        elif event.char == 'f':
            self.handle_seek()
        elif event.char == 'j':
            self.jump_10()
        elif event.char == 'h':
            self.back_10()
        elif event.char == ' ':
            self.handle_pause()
        elif event.char and (event.char in string.digits or event.char == '*'):
            self.handle_tag(event.char)
    def resizelast_detect_f(self, f_detect_i: int):
        if f_detect_i == self.resizelast_detect:
            logger.debug("Window.resizelast_detect_f: detected window resize")
            self.resizelast_detect = 0
            if VLC_SUPPORT and not self.playing_video:
                self.flush_image()
    def handle_resize(self, event):
        ww = self.winfo_width()
        wh = self.winfo_height()
        if (ww, wh) != self.window_size:
            self.window_size = (ww, wh)
            self.resizelast_detect += 1
            self.after(125, self.resizelast_detect_f, self.resizelast_detect)
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
            self.image_iter %= len(self.image_list)
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
        self.bind("<Key-Down>", self.volume_down)
        self.bind("<Key-Up>", self.volume_up)
        self.bind("<Configure>", self.handle_resize)
        self.bind("<Configure>", self.update_taglist_wraplength)
        self.bind("<Delete>", self.handle_delete)
        self.bind("<Escape>", lambda e: self.on_close())
    def on_close(self):
        logger.debug("Window.on_close")
        
        self._clean_mediasource()
        
        if VLC_SUPPORT:
            if self.vlc_player:
                self.vlc_player.release()
                del self.vlc_player
            if self.vlc_instance:
                self.vlc_instance.release()
                del self.vlc_instance
        
        for after_id in self.tk.eval('after info').split():
            self.after_cancel(after_id)
        #self.destroy()
        exit(0)
    def _clean_mediasource(self):
        if VLC_SUPPORT:
            if self.playing_video:
                self.playing_video = False
                self.vlc_player.stop()
        if isinstance(self._image_cl, GifImageTk):
            self._image_cl.destroy()
        self._image_cl = None
        if self._image_cl_id is not None:
            if hasattr(self, 'image') and self.image.winfo_exists():
                try:
                    self.image.delete(self._image_cl_id)
                except tk.TclError:
                    pass
            self._image_cl_id = None
        self._raw_image = None
        self._image = None
    def volume_down(self, *args, **kwargs):
        if VLC_SUPPORT and self.playing_video:
            logger.debug("Window.volume_down")
            self.volume = max(0, self.volume - 5)
            self.vlc_player.audio_set_volume(self.volume)
            logger.debug("Window.volume_down: set to %s", self.volume)
            pc = (self.image_iter+1) / len(self.image_list) * 100
            self.fileNameLabel.configure(text=f"V={self.volume}%\t{pc:.2f}% {self.image_iter+1}/{len(self.image_list)}\t" + self.image_list[self.image_iter] + f"\t{self.curr_timespf}")
    def volume_up(self, *args, **kwargs):
        if VLC_SUPPORT and self.playing_video:
            logger.debug("Window.volume_up")
            self.volume = min(100, self.volume + 5)
            self.vlc_player.audio_set_volume(self.volume)
            logger.debug("Window.volume_up: set to %s", self.volume)
            pc = (self.image_iter+1) / len(self.image_list) * 100
            self.fileNameLabel.configure(text=f"V={self.volume}%\t{pc:.2f}% {self.image_iter+1}/{len(self.image_list)}\t" + self.image_list[self.image_iter] + f"\t{self.curr_timespf}")
    def handle_seek(self):
        """search for first media without score"""
        if not self.image_list:
            return
        if not any(tag.startswith("score__") for tag in self.tag_list):
            return
        self.image_iter = 0
        while self.image_iter < len(self.image_list) and any(tag.startswith("score__") for tag in self.tag_list):
            self.image_iter += 1
            self.reload_tags(flush=False)
        self.image_iter %= len(self.image_list)
        self.reload_tags()
        self.reload_image()
    def jump_10(self):
        """forward 10 seconds"""
        if VLC_SUPPORT:
            if self.playing_video:
                logger.debug("Window.jump_10")
                curr = self.vlc_player.get_time()
                if self.vlc_player.get_length() - curr > 10*1000:
                    logger.debug("Window.jump_10: set time to %s", curr + 10 * 1000)
                    self.vlc_player.set_time(curr + 10 * 1000)
    def back_10(self):
        if VLC_SUPPORT:
            if self.playing_video:
                curr = self.vlc_player.get_time()
                nw = max(0, curr - 10*1000)
                logger.debug("Window.back_10: set time to %s", nw)
                self.vlc_player.set_time(nw)
    def handle_pause(self):
        if VLC_SUPPORT:
            if self.playing_video:
                if self.vlc_player.is_playing():
                    self.vlc_player.pause()
                else:
                    self.vlc_player.play()
            
