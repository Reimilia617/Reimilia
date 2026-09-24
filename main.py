#!/usr/bin/env python3
"""Reimilia 入口。

用法::

    python3 main.py                # 启动 WebUI（默认）
    python3 main.py --cli          # 终端交互部署
    python3 main.py --cli --list   # 只看有哪些项目

这个文件同时是 PyInstaller 的打包入口（见 Reimilia.spec），
打包后产出的单文件可执行程序名字是 ``reimilia``。
"""

from __future__ import annotations

import sys

from reimilia.app import main

if __name__ == "__main__":
    sys.exit(main())
