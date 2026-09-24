"""md 描述文件解析。

格式（详见 docs/md-format.md）::

    [Reimilia_Build]

    BUILD_LANG="rust"
    BUILD_HTTP="https://example.com/x.git"
    REQUIRES_ROOT="true"

    bash:
    git clone --depth 1 "$BUILD_HTTP" "$REIMILIA_WORKDIR/src"
    cd "$REIMILIA_WORKDIR/src"
    reimilia_elevate ./install.sh

设计要点：

* ``[Reimilia_XXX]`` 开启一个 section，一个文件里可以有多个；
* section 内的 ``KEY="value"`` 会作为环境变量注入 ``bash:`` 块；
* ``bash:`` 之后的每一行原样收集为**一段脚本**（不是逐行执行），
  因此 ``cd`` / 变量赋值 / ``if`` / heredoc 都能正常工作；
* markdown 代码围栏与 ``#`` 注释会被忽略。
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

MARKER_RE = re.compile(r"^\[(Reimilia_[A-Za-z_][A-Za-z0-9_]*)\]\s*$")
ASSIGN_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$")
#: 项目指向支持 https / http（需显式放行）/ file（本地或离线部署）
URL_RE = re.compile(r"(?:https?|file)://[^\s)\]\"'<>`]+")
FENCE_RE = re.compile(r"^\s*```")

BASH_KEYWORDS = ("bash:", "bash :", "shell:")


def _strip_quotes(value: str) -> str:
    """去掉赋值右侧的成对引号。"""
    value = value.strip()
    for quote in ('"', "'"):
        if len(value) >= 2 and value.startswith(quote) and value.endswith(quote):
            return value[1:-1]
    return value


def parse_assignments(text: str) -> dict[str, str]:
    """解析纯 ``KEY="value"`` 配置文件（配置文件的解析规则与 md 一致）。"""
    result: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("["):
            continue
        match = ASSIGN_RE.match(line)
        if match:
            result[match.group(1)] = _strip_quotes(match.group(2))
    return result


@dataclass
class Section:
    """一个 ``[Reimilia_XXX]`` 段。"""

    marker: str | None = None
    variables: dict[str, str] = field(default_factory=dict)
    commands: list[str] = field(default_factory=list)

    @property
    def has_commands(self) -> bool:
        return any(line.strip() for line in self.commands)


@dataclass
class MdDoc:
    """解析后的 md 文件。"""

    path: Path | None
    text: str
    sections: list[Section] = field(default_factory=list)

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()

    @property
    def marker(self) -> str | None:
        return self.sections[0].marker if self.sections else None

    @property
    def variables(self) -> dict[str, str]:
        merged: dict[str, str] = {}
        for section in self.sections:
            merged.update(section.variables)
        return merged

    @property
    def commands(self) -> list[str]:
        if not self.sections:
            return []
        return self.sections[0].commands

    @property
    def script(self) -> str:
        return "\n".join(self.commands)

    @property
    def url(self) -> str | None:
        """文件中出现的第一个 http(s) 链接（用于 ``[Reimilia_Repo]``）。"""
        match = URL_RE.search(self.text)
        return match.group(0).rstrip(".,;") if match else None

    def primary_section(self) -> Section:
        if not self.sections:
            return Section()
        return self.sections[0]


def parse_md_text(text: str, path: Path | None = None) -> MdDoc:
    text = text.lstrip("\ufeff")
    doc = MdDoc(path=path, text=text)
    current: Section | None = None
    in_bash = False

    for raw in text.splitlines():
        line = raw.rstrip("\n").rstrip("\r")
        stripped = line.strip()

        # markdown 代码围栏直接忽略
        if FENCE_RE.match(line):
            continue

        marker_match = MARKER_RE.match(stripped)
        if marker_match:
            current = Section(marker=marker_match.group(1))
            doc.sections.append(current)
            in_bash = False
            continue

        if current is None:
            # 还没有出现任何 section：允许正文/标题，全部忽略
            continue

        if not in_bash:
            lowered = stripped.lower()
            if any(lowered.startswith(keyword) for keyword in BASH_KEYWORDS):
                in_bash = True
                # 支持 "bash: cmd" 这种同行写法
                inline = stripped.split(":", 1)[1].strip()
                if inline:
                    current.commands.append(inline)
                continue
            if not stripped or stripped.startswith("#"):
                continue
            assign = ASSIGN_RE.match(stripped)
            if assign:
                current.variables[assign.group(1)] = _strip_quotes(assign.group(2))
            continue

        # bash 块内：原样保留（含缩进），仅跳过空行与围栏
        if not stripped:
            current.commands.append("")
            continue
        current.commands.append(line)

    return doc


def parse_md_file(path: Path) -> MdDoc:
    return parse_md_text(path.read_text(encoding="utf-8", errors="replace"), path=path)


def load_repo_dir(repo_dir: Path) -> dict[str, str]:
    """扫描部署器仓库的 ``repo/``：``{项目名: 项目仓库地址}``。"""
    projects: dict[str, str] = {}
    if not repo_dir.is_dir():
        return projects
    for md_file in sorted(repo_dir.glob("*.md")):
        doc = parse_md_file(md_file)
        if doc.url:
            projects[md_file.stem] = doc.url
    return projects
