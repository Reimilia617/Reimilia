"""运行时路径解析。

同时支持两种运行形态：

* 源码运行      —— 资源目录 = 仓库根目录；
* PyInstaller 单文件 —— 资源目录 = 解包出来的临时目录 (``sys._MEIPASS``)，
  可写状态一律放到用户目录，绝不写进临时目录（会被清理）。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

#: 状态目录环境变量覆盖项
ENV_HOME = "REIMILIA_HOME"


def is_frozen() -> bool:
    """是否运行在 PyInstaller 打包产物中。"""
    return bool(getattr(sys, "frozen", False))


def resource_dir() -> Path:
    """只读资源目录（``static/``、``repo/``、``keys/`` 模板所在处）。"""
    if is_frozen():
        base = getattr(sys, "_MEIPASS", None)
        if base:
            return Path(base)
    # reimilia/paths.py -> reimilia/ -> 仓库根
    return Path(__file__).resolve().parent.parent


def exe_dir() -> Path:
    """可执行文件 / 入口脚本所在目录。"""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return resource_dir()


def static_dir() -> Path:
    return resource_dir() / "static"


def bundled_repo_dir() -> Path:
    """打包进程序的 repo/ 模板（远程不可用时的兜底）。"""
    return resource_dir() / "repo"


def state_dir() -> Path:
    """可写状态目录：配置、部署器仓库缓存、项目工作目录。"""
    override = os.environ.get(ENV_HOME)
    if override:
        return Path(override).expanduser().resolve()
    return Path.home() / ".reimilia"


def ensure_state_dir() -> Path:
    path = state_dir()
    path.mkdir(parents=True, exist_ok=True)
    return path


def config_file() -> Path:
    return state_dir() / "config"


def deployer_cache_dir() -> Path:
    return state_dir() / "deployer"


def work_cache_dir() -> Path:
    return state_dir() / "work"


def describe() -> dict[str, str]:
    """给 UI / 日志用的路径摘要。"""
    return {
        "frozen": "yes" if is_frozen() else "no",
        "exe_dir": str(exe_dir()),
        "resource_dir": str(resource_dir()),
        "state_dir": str(state_dir()),
        "config_file": str(config_file()),
    }
