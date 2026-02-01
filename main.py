# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from window import Window
from coloredlogs import install
import logging

logger = logging.getLogger(__name__)

def main():
    logger.info("main")
    w = Window()
    logger.info("created window")
    w.mainloop()
    logger.info("exiting")

if __name__ == "__main__":
    install(level=logging.INFO)
    main()