"""配置解析：默认值 < 配置文件 < 环境变量 < 命令行参数。

配置文件位于 ``~/.reimilia/config``（可用 ``REIMILIA_HOME`` 改目录），
格式与 md 里的变量声明一致：``KEY="value"``。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from . import DEFAULT_REMOTE_REPO
from . import paths
from .mdparse import parse_assignments

ENV_PREFIX = "REIMILIA_"

#: 默认配置。``INSTALL_ORDER`` 决定同时存在 Binary/Build 时先试哪个。
DEFAULTS: dict[str, str] = {
    "REMOTE_REPO": DEFAULT_REMOTE_REPO,
    "INSTALL_ORDER": "Build,Binary",
    "HOST": "127.0.0.1",
    "PORT": "8617",
    "DEPLOYER_TTL": "300",
    "KEEP_WORKDIR": "false",
    "ALLOW_INSECURE": "false",
    "CLONE_DEPTH": "1",
}

#: 可以在配置文件 / 环境变量里覆盖的键
EDITABLE = tuple(DEFAULTS)

_TRUTHY = {"1", "true", "yes", "on"}


def _as_bool(value: str | bool | None, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return value.strip().lower() in _TRUTHY


def _as_int(value: str | int | None, default: int) -> int:
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class Settings:
    """一次运行内使用的最终配置。"""

    remote_repo: str = DEFAULT_REMOTE_REPO
    install_order: tuple[str, ...] = ("Build", "Binary")
    host: str = "127.0.0.1"
    port: int = 8617
    deployer_ttl: int = 300
    keep_workdir: bool = False
    allow_insecure: bool = False
    clone_depth: int = 1
    source: Path | None = None
    values: dict[str, str] = field(default_factory=dict)

    @property
    def is_local_repo(self) -> bool:
        return local_repo_path(self.remote_repo) is not None

    def to_dict(self) -> dict[str, str]:
        return {
            "remote_repo": self.remote_repo,
            "install_order": ",".join(self.install_order),
            "host": self.host,
            "port": str(self.port),
            "deployer_ttl": str(self.deployer_ttl),
            "keep_workdir": "true" if self.keep_workdir else "false",
            "allow_insecure": "true" if self.allow_insecure else "false",
            "clone_depth": str(self.clone_depth),
            "config_file": str(self.source) if self.source else "",
        }


def local_repo_path(remote: str) -> Path | None:
    """如果 ``remote`` 是本地目录（含 ``file://``），返回其路径。

    这样开发时可以 ``--repo .`` 直接使用工作区，不必先推送到远端。
    """
    if not remote:
        return None
    if remote.startswith("file://"):
        candidate = Path(remote[len("file://") :])
    elif "://" in remote or remote.startswith("git@"):
        return None
    else:
        candidate = Path(remote).expanduser()
    try:
        if candidate.is_dir():
            return candidate.resolve()
    except OSError:
        return None
    return None


def load_config_file(path: Path | None = None) -> tuple[dict[str, str], Path]:
    """读取配置文件；文件不存在时返回空配置。"""
    target = path or paths.config_file()
    if not target.is_file():
        return {}, target
    try:
        text = target.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}, target
    return parse_assignments(text), target


def load_settings(
    *,
    overrides: dict[str, str | None] | None = None,
    config_path: Path | None = None,
    use_env: bool = True,
) -> Settings:
    """按 默认值 → 配置文件 → 环境变量 → 显式 overrides 的顺序合并配置。"""
    raw = dict(DEFAULTS)

    file_values, resolved_path = load_config_file(config_path)
    for key in EDITABLE:
        if key in file_values:
            raw[key] = file_values[key]

    if use_env:
        for key in EDITABLE:
            env_value = os.environ.get(ENV_PREFIX + key)
            if env_value is not None and env_value != "":
                raw[key] = env_value

    for key, value in (overrides or {}).items():
        if value is None:
            continue
        raw[key.upper()] = str(value)

    order = tuple(
        part.strip().capitalize()
        for part in raw.get("INSTALL_ORDER", "").split(",")
        if part.strip()
    )
    order = tuple(kind for kind in order if kind in ("Build", "Binary")) or ("Build", "Binary")

    return Settings(
        remote_repo=raw.get("REMOTE_REPO") or DEFAULT_REMOTE_REPO,
        install_order=order,
        host=raw.get("HOST") or "127.0.0.1",
        port=_as_int(raw.get("PORT"), 8617),
        deployer_ttl=_as_int(raw.get("DEPLOYER_TTL"), 300),
        keep_workdir=_as_bool(raw.get("KEEP_WORKDIR")),
        allow_insecure=_as_bool(raw.get("ALLOW_INSECURE")),
        clone_depth=max(1, _as_int(raw.get("CLONE_DEPTH"), 1)),
        source=resolved_path,
        values=raw,
    )


def save_setting(key: str, value: str, config_path: Path | None = None) -> Path:
    """写入 / 更新单个配置项，返回配置文件路径。"""
    key = key.upper()
    if key not in EDITABLE:
        raise KeyError(f"未知配置项: {key}")

    target = config_path or paths.config_file()
    target.parent.mkdir(parents=True, exist_ok=True)

    values, _ = load_config_file(target)
    values[key] = value

    lines = ["# Reimilia 配置（KEY=\"value\"，可用 REIMILIA_<KEY> 环境变量临时覆盖）", ""]
    for name in EDITABLE:
        current = values.get(name, DEFAULTS[name])
        lines.append(f'{name}="{current}"')
    lines.append("")
    target.write_text("\n".join(lines), encoding="utf-8")
    return target
