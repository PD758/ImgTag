# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import os, pathlib
import tkinter as tk
from tkinter import filedialog
from PIL import ImageTk

import util

class Window(tk.Tk):
    def __init__(self):
        super().__init__()
        self.init_widgets()
        self.render_widgets()
        self.image_list: list[pathlib.Path] = []
    def load_file(self):
        picked_dir = filedialog.askdirectory(mustexist=True)
        if picked_dir:
            files = util.rec_listdir(picked_dir,
                            lambda path: util.check_ends(path, [".png", ".jpg", ".jpeg", ".bmp"], ignore_case=True))
            print(files)
        else:
            print("Pick canceled")
    def init_widgets(self):
        self.loadButton = tk.Button(self, text="Load from folder", command=self.load_file)
    def render_widgets(self):
        self.loadButton.pack()
