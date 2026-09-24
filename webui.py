#!/usr/bin/env python3
"""Reimilia WebUI 入口（保留旧调用方式）。

等价于 ``python3 main.py --webui``；建议直接使用 ``main.py`` 或打包后的
``reimilia``。
"""

from __future__ import annotations

import sys

from reimilia.app import main

if __name__ == "__main__":
    sys.exit(main(["--webui", *sys.argv[1:]]))
