"""Reimilia —— 基于 .md 描述的通用项目部署器。

本包只负责「读 md → 拉仓库 → 按 md 执行安装」，不提供业务功能。
"""

from __future__ import annotations

__version__ = "0.2.0"
APP_NAME = "Reimilia"
DEFAULT_REMOTE_REPO = "https://github.com/Reimilia617/Reimilia.git"

__all__ = ["__version__", "APP_NAME", "DEFAULT_REMOTE_REPO"]
