"""统一入口：默认启动 WebUI，``--cli`` 走终端交互。

被打包成单文件后就是 ``reimilia`` 这个可执行文件。
"""

from __future__ import annotations

import argparse
import sys

from . import APP_NAME, __version__
from . import paths
from .cli import run_cli
from .config import Settings, load_settings, save_setting
from .deploy import DeployError

EPILOG = """\
示例:
  reimilia                                 启动 WebUI（默认）
  reimilia --cli                           终端交互式选择项目并部署
  reimilia --cli --list                    只列出可部署项目
  reimilia --cli RTDO-Project --yes        直接部署指定项目
  reimilia --cli RTDO-Project --kind binary  强制使用预编译二进制安装
  reimilia --repo /path/to/deployer --cli  使用本地部署器仓库（开发用）
  reimilia --set-repo https://github.com/you/Reimilia.git   持久化远程仓库地址
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="reimilia",
        description=f"{APP_NAME} —— 基于 .md 描述的通用项目部署器",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("projects", nargs="*", help="要部署的项目名（省略则在 --cli 下交互选择）")

    mode = parser.add_argument_group("运行模式")
    mode.add_argument("--cli", action="store_true", help="终端模式（默认启动 WebUI）")
    mode.add_argument("--webui", action="store_true", help="显式启动 WebUI")
    mode.add_argument("--list", action="store_true", help="列出可部署项目后退出")
    mode.add_argument("--no-browser", action="store_true", help="启动 WebUI 时不自动打开浏览器")

    target = parser.add_argument_group("部署目标")
    target.add_argument("--repo", metavar="URL", help="临时指定部署器仓库（URL 或本地目录）")
    target.add_argument("--set-repo", metavar="URL", help="把部署器仓库地址写入配置后退出")
    target.add_argument(
        "--kind",
        choices=("auto", "build", "binary"),
        default=None,
        help="强制安装方式（默认按配置的 INSTALL_ORDER 自动尝试并回退）",
    )
    target.add_argument("--yes", "-y", action="store_true", help="跳过确认")
    target.add_argument("--no-refresh", action="store_true", help="不重新拉取部署器仓库")
    target.add_argument("--keep-workdir", action="store_true", help="部署后保留项目工作目录")

    server = parser.add_argument_group("WebUI")
    server.add_argument("--host", metavar="HOST", help="监听地址（默认 127.0.0.1）")
    server.add_argument("--port", metavar="PORT", type=int, help="监听端口（默认 8617）")

    parser.add_argument("--show-config", action="store_true", help="打印生效配置与路径后退出")
    parser.add_argument("--version", "-V", action="version", version=f"{APP_NAME} {__version__}")
    return parser


def _settings_from_args(args: argparse.Namespace) -> Settings:
    overrides: dict[str, str | None] = {}
    if args.repo:
        overrides["REMOTE_REPO"] = args.repo
    if args.host:
        overrides["HOST"] = args.host
    if args.port:
        overrides["PORT"] = str(args.port)
    if args.keep_workdir:
        overrides["KEEP_WORKDIR"] = "true"
    return load_settings(overrides=overrides)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.set_repo:
        try:
            target = save_setting("REMOTE_REPO", args.set_repo)
        except (OSError, KeyError) as exc:
            print(f"写入配置失败: {exc}", file=sys.stderr)
            return 1
        print(f"部署器仓库已设置为: {args.set_repo}")
        print(f"配置文件: {target}")
        return 0

    settings = _settings_from_args(args)

    if args.show_config:
        print(f"{APP_NAME} {__version__}")
        print("路径:")
        for key, value in paths.describe().items():
            print(f"  {key:14} {value}")
        print("配置:")
        for key, value in settings.to_dict().items():
            print(f"  {key:14} {value}")
        return 0

    # --list 只对终端模式有意义，显式指定时不要把用户丢进 WebUI
    if args.list:
        args.cli = True

    # 默认 WebUI；--cli 优先
    if not args.cli:
        from .webui import run_webui

        return run_webui(settings, open_browser=not args.no_browser)

    try:
        return run_cli(
            settings,
            projects_requested=args.projects,
            kind=None if args.kind in (None, "auto") else args.kind,
            assume_yes=args.yes,
            refresh=not args.no_refresh,
            list_only=args.list,
        )
    except KeyboardInterrupt:
        print("\n已取消")
        return 130
    except DeployError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1
