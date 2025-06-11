# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import os, pathlib, typing, logging

logger = logging.getLogger(__name__)

def rec_listdir(path: str, filter_files: None|typing.Callable[[str], bool] = None) -> list[str]:
    logger.debug(f"rec_listdir: browsing {path}")
    result = []
    for root, _, files in os.walk(path):
        for filename in files:
            full_path = os.path.join(root, filename)
            if filter_files is None or filter_files(full_path):
                result.append(full_path)
    return result

def check_ends(str, ends: typing.Iterable[str], ignore_case: bool = False):
    for end in ends:
        if (str.lower() if ignore_case else str).endswith(end):
            return True
    return False
