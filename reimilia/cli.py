"""命令行界面：列项目、选项目、执行部署。"""

from __future__ import annotations

import sys

from .config import Settings
from .deploy import DeployError, Reporter, deploy_project, detect_elevator, list_projects

BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[31m"
YELLOW = "\033[33m"
GREEN = "\033[32m"
RESET = "\033[0m"


def _color_enabled(stream) -> bool:
    return bool(getattr(stream, "isatty", lambda: False)()) and not _no_color()


def _no_color() -> bool:
    import os

    return os.environ.get("NO_COLOR") not in (None, "") or os.environ.get("REIMILIA_NO_COLOR") == "1"


class _Painter:
    def __init__(self) -> None:
        self.on = _color_enabled(sys.stdout)

    def paint(self, text: str, color: str) -> str:
        return f"{color}{text}{RESET}" if self.on else text

    def bold(self, text: str) -> str:
        return self.paint(text, BOLD)

    def dim(self, text: str) -> str:
        return self.paint(text, DIM)


def make_reporter(*, quiet: bool = False, stream=None) -> Reporter:
    """终端日志：普通信息走 stdout，警告 / 错误走 stderr，便于 ``| grep``。"""
    painter = _Painter()
    out = stream or sys.stdout

    def on_log(message: str, level: str) -> None:
        target = sys.stderr if level in ("warn", "error") else out
        if quiet and level == "info":
            return
        if level == "warn":
            print(painter.paint(f"! {message}", YELLOW), file=target, flush=True)
        elif level == "error":
            print(painter.paint(f"✗ {message}", RED), file=target, flush=True)
        else:
            print(message, file=target, flush=True)

    return Reporter(on_log=on_log)


def _select_project(projects: dict[str, str]) -> str | None:
    names = list(projects)
    print("\n可用项目:")
    for index, name in enumerate(names, 1):
        print(f"  {index}. {name}")
        print(f"     {projects[name]}")
    try:
        raw = input("\n请选择要部署的项目编号（回车取消）: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return None
    if not raw:
        return None
    if raw.isdigit():
        index = int(raw) - 1
        if 0 <= index < len(names):
            return names[index]
        print("无效的编号")
        return None
    if raw in projects:
        return raw
    print(f"未找到项目: {raw}")
    return None


def _confirm(project: str, url: str, kind: str | None, order: tuple[str, ...]) -> bool:
    print()
    print(f"  项目: {project}")
    print(f"  仓库: {url}")
    print(f"  方式: {kind or ' → '.join(order)}")
    elevator = detect_elevator()
    print(f"  提权: {elevator or ('root' if _is_root() else '无')}")
    print()
    print("安装脚本来自上面的仓库，将以你的身份执行；需要 root 的步骤会调用提权工具。")
    try:
        answer = input("继续部署? [y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return answer in ("y", "yes")


def _is_root() -> bool:
    import os

    return os.geteuid() == 0


def run_cli(
    settings: Settings,
    *,
    projects_requested: list[str] | None = None,
    kind: str | None = None,
    assume_yes: bool = False,
    refresh: bool = True,
    list_only: bool = False,
) -> int:
    painter = _Painter()
    reporter = make_reporter()

    try:
        projects = list_projects(settings, reporter, force=refresh)
    except DeployError as exc:
        reporter.error(str(exc))
        return 1

    if not projects:
        reporter.error("没有找到可部署的项目（检查部署器仓库的 repo/ 目录）")
        return 1

    if list_only:
        print(painter.bold("可部署项目:"))
        for name, url in projects.items():
            print(f"  {name}")
            print(f"    {url}")
        return 0

    targets: list[str] = []
    for name in projects_requested or []:
        if name in projects:
            targets.append(name)
            continue
        matches = [key for key in projects if key.lower() == name.lower()]
        if matches:
            targets.append(matches[0])
        else:
            reporter.error(f"未找到项目: {name}")
            return 2

    if not targets:
        chosen = _select_project(projects)
        if not chosen:
            print("已取消")
            return 0
        targets = [chosen]

    exit_code = 0
    for index, name in enumerate(targets):
        url = projects[name]
        if index and not assume_yes:
            print()
        if not assume_yes and not _confirm(name, url, kind, settings.install_order):
            print("已取消")
            return exit_code
        print()
        print(painter.bold(f"===== 部署 {name} ====="))
        try:
            result = deploy_project(
                project=name,
                repo_url=url,
                settings=settings,
                reporter=reporter,
                kind=kind,
                interactive=True,
            )
        except DeployError as exc:
            reporter.error(str(exc))
            exit_code = 1
            continue
        except KeyboardInterrupt:
            reporter.error("已中断")
            return 130
        if not result.get("ok"):
            exit_code = 1
    return exit_code
