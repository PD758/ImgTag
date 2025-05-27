# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import os, pathlib, typing
import tkinter as tk
from tkinter import filedialog
from PIL import ImageTk
import csv

import util

class Window(tk.Tk):
    def __init__(self):
        super().__init__()
        self.init_widgets()
        self.render_widgets()
        self.image_list: list[pathlib.Path] = []
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
            writer.writerows([['tag_name']] + [[t] for t in tag_list])
    def load_file(self):
        picked_dir = filedialog.askdirectory(mustexist=True)
        if picked_dir:
            files = util.rec_listdir(picked_dir,
                            lambda path: util.check_ends(path, [".png", ".jpg", ".jpeg", ".bmp"], ignore_case=True))
            for f in files:
                d = list(self.load_tags(f)) + ["test"]
                print(f, d)
                if d:
                    self.save_tags(f, d)
        else:
            print("Pick canceled")
    def init_widgets(self):
        self.loadButton = tk.Button(self, text="Load from folder", command=self.load_file)
    def render_widgets(self):
        self.loadButton.pack()
