# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import os, pathlib, typing

def rec_listdir(path: str, filter_files: None|typing.Callable[[str], bool] = None):
    result = []
    for p in os.listdir(path):
        if os.path.isdir(os.path.join(path, p)):
            result.extend(rec_listdir(os.path.join(path, p)))
        elif (filter_files(os.path.join(path, p)) if filter_files is not None else True):
            result.append(os.path.join(path, p))
    return result

def check_ends(str, ends: typing.Iterable[str], ignore_case: bool = False):
    for end in ends:
        if (str.lower() if ignore_case else str).endswith(end):
            return True
    return False
