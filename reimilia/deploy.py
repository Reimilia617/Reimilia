"""部署流程：解析部署器仓库 → 拉取项目 → 执行 Reimilia_Setup。

与旧版实现的区别（均为修复，而非重构癖好）：

1. **bash 块整段执行**，不再逐行 ``subprocess.run``。
   旧版里 ``cd ~/.reimilia_cache`` 对下一行毫无影响，README 给出的示例
   （curl / git clone 安装）实际上是坏的。
2. **提权交给 md**。Reimilia 只负责探测可用提权工具并注入
   ``reimilia_elevate`` 帮助函数，需要 root 的步骤在 md 里显式调用。
3. **URL 不再由前端传入**，避免任意代码执行 / CSRF。
4. 失败可回退：``Build`` 失败自动尝试 ``Binary``（或反之）。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable
from urllib.parse import urlsplit, urlunsplit

from . import paths
from .config import Settings, local_repo_path
from .mdparse import MdDoc, load_repo_dir, parse_md_file

SETUP_DIR_NAME = "Reimilia_Setup"
INSTALL_KINDS = ("Build", "Binary")

#: md 里声明后由 Reimilia 特殊处理、不注入给 bash 的变量
RESERVED_VARS = {"REQUIRES_ROOT"}


class DeployError(RuntimeError):
    """部署过程中的可预期错误（会以友好文案展示给用户）。"""


# ============================================================
# 事件上报：CLI 直接打印，WebUI 推进队列
# ============================================================
class Reporter:
    """把部署过程中的日志 / 事件解耦出来，CLI 与 WebUI 共用同一套流程。"""

    def __init__(
        self,
        on_log: Callable[[str, str], None] | None = None,
        on_event: Callable[[str, dict], None] | None = None,
    ) -> None:
        self._on_log = on_log
        self._on_event = on_event

    def log(self, message: str = "", level: str = "info") -> None:
        if self._on_log is not None:
            self._on_log(message, level)

    def warn(self, message: str) -> None:
        self.log(message, "warn")

    def error(self, message: str) -> None:
        self.log(message, "error")

    def event(self, event_name: str, **data: object) -> None:
        if self._on_event is not None:
            self._on_event(event_name, data)


def redact_url(url: str) -> str:
    """日志里不打印 URL 中的账号密码。"""
    try:
        parts = urlsplit(url)
    except ValueError:
        return url
    if "@" not in parts.netloc:
        return url
    host = parts.netloc.rsplit("@", 1)[1]
    return urlunsplit((parts.scheme, f"***@{host}", parts.path, parts.query, parts.fragment))


# ============================================================
# 安全 / 环境检查
# ============================================================
def ensure_secure_url(url: str, settings: Settings) -> None:
    """强制 HTTPS（本地路径与 ssh 除外），并拒绝被关掉 TLS 校验的环境。"""
    if os.environ.get("GIT_SSL_NO_VERIFY") and not settings.allow_insecure:
        raise DeployError(
            "检测到 GIT_SSL_NO_VERIFY，TLS 校验已被关闭。"
            "如确实要放弃校验，请设置 ALLOW_INSECURE=\"true\"。"
        )
    if local_repo_path(url) is not None:
        return
    if url.startswith(("git@", "ssh://")):
        return
    if url.startswith("https://"):
        return
    if url.startswith("http://") and not settings.allow_insecure:
        raise DeployError(f"拒绝非 HTTPS 地址（如需放行请设置 ALLOW_INSECURE=\"true\"）: {redact_url(url)}")
    if not url.startswith(("http://", "https://")):
        raise DeployError(f"无法识别的仓库地址: {redact_url(url)}")


def git_env() -> dict[str, str]:
    """构造 git 子进程环境：绝不继承 GIT_SSL_NO_VERIFY，禁用交互式账号输入。"""
    env = {k: v for k, v in os.environ.items() if k != "GIT_SSL_NO_VERIFY"}
    if not (sys.stdin and sys.stdin.isatty()):
        env.setdefault("GIT_TERMINAL_PROMPT", "0")
    env.setdefault("GIT_ADVICE", "0")
    return env


def _try_command(argv: list[str], timeout: float = 6.0) -> bool:
    try:
        proc = subprocess.run(
            argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=timeout
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return proc.returncode == 0


def detect_elevator() -> str:
    """探测可用的提权工具，返回命令名（``sudo`` / ``sudo-force`` / ``su`` / 空串）。

    顺序刻意如此：

    1. 已经是 root → 不需要；
    2. 能免密 ``sudo`` → 说明 sudo 可用且未被接管；
    3. ``/usr/bin/sudo.real`` 存在 → sudo 已被 rtdo 之类工具接管，改用 ``sudo-force``；
    4. 退回交互式 ``sudo``，再退 ``sudo-force``，最后 ``su``。
    """
    override = os.environ.get("REIMILIA_ELEVATE")
    if override is not None:
        return override.strip()
    if os.geteuid() == 0:
        return ""

    sudo = shutil.which("sudo")
    sudo_force = shutil.which("sudo-force")
    su = shutil.which("su")

    if sudo and _try_command([sudo, "-n", "true"]):
        return sudo
    if sudo_force and _try_command([sudo_force, "-n", "true"]):
        return sudo_force
    if Path("/usr/bin/sudo.real").exists() and sudo_force:
        return sudo_force
    if sudo:
        return sudo
    if sudo_force:
        return sudo_force
    if su:
        return "su"
    return ""


# ============================================================
# 执行 md 里的 bash 块
# ============================================================
PRELUDE = r'''
# ===== Reimilia prelude (自动生成，请勿依赖其内部实现) =====
reimilia_log() { printf '[reimilia] %s\n' "$*"; }

reimilia_quote() {
  local out="" a
  for a in "$@"; do out="$out $(printf '%q' "$a")"; done
  printf '%s' "${out# }"
}

# reimilia_elevate <命令> [参数...]  —— 以 root 执行命令
reimilia_elevate() {
  if [ "$#" -eq 0 ]; then return 0; fi
  if [ "$(id -u)" -eq 0 ]; then "$@"; return $?; fi
  local tool="${REIMILIA_ELEVATE:-}"
  if [ -z "$tool" ]; then
    printf '[reimilia] 需要 root 权限，但未找到 sudo / sudo-force / su\n' >&2
    return 127
  fi
  if [ "$tool" = "su" ]; then
    su -c "$(reimilia_quote "$@")" root
    return $?
  fi
  # 带上构建工具需要的环境：提权后 rustup / go 仍能找到工具链
  local -a extra=() name
  for name in HOME PATH CARGO_HOME RUSTUP_HOME GOPATH GOCACHE GOMODCACHE; do
    if [ -n "${!name:-}" ]; then extra+=("$name=${!name}"); fi
  done
  if [ "${#extra[@]}" -gt 0 ]; then
    "$tool" env "${extra[@]}" "$@"
  else
    "$tool" "$@"
  fi
}

_reimilia_on_error() {
  printf '[reimilia] 命令失败（退出码 %s），脚本第 %s 行\n' "$1" "$2" >&2
}
set -E
trap '_reimilia_on_error "$?" "$LINENO"' ERR
# ===== end prelude =====
'''


def build_env(
    settings: Settings,
    *,
    project: str,
    repo_url: str,
    workdir: Path,
    kind: str,
    md_vars: dict[str, str],
    elevator: str,
) -> dict[str, str]:
    """md 变量 + Reimilia 上下文变量 → 子进程环境。"""
    env = dict(os.environ)
    # md 声明在前，内置变量在后：内置变量不可被 md 覆盖
    for key, value in md_vars.items():
        if key not in RESERVED_VARS:
            env[key] = value
    env.update(
        {
            "REIMILIA": "1",
            "REIMILIA_PROJECT": project,
            "REIMILIA_REPO": repo_url,
            "REIMILIA_WORKDIR": str(workdir),
            "REIMILIA_KIND": kind,
            "REIMILIA_ELEVATE": elevator,
            "REIMILIA_STATE_DIR": str(paths.state_dir()),
        }
    )
    return env


def run_script(
    script: str,
    *,
    env: dict[str, str],
    cwd: Path,
    reporter: Reporter,
    stdin: int | None = None,
    label: str = "setup",
) -> int:
    """把整段脚本写入临时文件后用 ``bash -e`` 执行，并实时转发输出。"""
    full = PRELUDE + "\n" + script + "\n"
    fd, tmp_name = tempfile.mkstemp(prefix=f"reimilia-{label}-", suffix=".sh")
    script_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(full)
        script_path.chmod(0o700)

        proc = subprocess.Popen(
            ["bash", "-e", str(script_path)],
            cwd=str(cwd),
            env=env,
            stdin=stdin,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert proc.stdout is not None
        try:
            for line in proc.stdout:
                reporter.log(line.rstrip("\n"))
        finally:
            proc.stdout.close()
        return proc.wait()
    finally:
        script_path.unlink(missing_ok=True)


# ============================================================
# 部署器仓库
# ============================================================
def deployer_root(settings: Settings, reporter: Reporter, *, force: bool = False) -> Path:
    """取得部署器仓库根目录（本地目录直接用，远程 clone 到缓存）。"""
    local = local_repo_path(settings.remote_repo)
    if local is not None:
        reporter.log(f"使用本地部署器仓库: {local}")
        return local

    ensure_secure_url(settings.remote_repo, settings)
    cache = paths.deployer_cache_dir()
    now = time.time()

    if not force and cache.is_dir():
        stamp = cache / ".reimilia-stamp"
        try:
            cached_at = float(stamp.read_text(encoding="utf-8").strip()) if stamp.is_file() else cache.stat().st_mtime
        except (OSError, ValueError):
            cached_at = 0.0
        if now - cached_at < settings.deployer_ttl:
            reporter.log(f"使用部署器仓库缓存（{int(now - cached_at)}s 前）")
            return cache

    tmp = cache.with_name(cache.name + ".tmp")
    reporter.log(f"克隆部署器仓库: {redact_url(settings.remote_repo)}")
    try:
        if tmp.exists():
            shutil.rmtree(tmp, ignore_errors=True)
        tmp.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                "git",
                "clone",
                "--depth",
                str(settings.clone_depth),
                "--",
                settings.remote_repo,
                str(tmp),
            ],
            check=True,
            capture_output=True,
            text=True,
            env=git_env(),
        )
        (tmp / ".reimilia-stamp").write_text(str(now), encoding="utf-8")
        if cache.exists():
            shutil.rmtree(cache, ignore_errors=True)
        tmp.rename(cache)
    except subprocess.CalledProcessError as exc:
        shutil.rmtree(tmp, ignore_errors=True)
        detail = (exc.stderr or "").strip().splitlines()
        hint = detail[-1] if detail else str(exc)
        if cache.is_dir():
            reporter.warn(f"克隆失败，改用本地缓存: {hint}")
            return cache
        raise DeployError(f"克隆部署器仓库失败: {hint}") from exc
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    return cache


def list_projects(settings: Settings, reporter: Reporter, *, force: bool = False) -> dict[str, str]:
    """``{项目名: 仓库地址}``。"""
    root = deployer_root(settings, reporter, force=force)
    projects = load_repo_dir(root / "repo")
    if not projects:
        bundled = paths.bundled_repo_dir()
        if bundled.is_dir() and bundled.resolve() != (root / "repo").resolve():
            projects = load_repo_dir(bundled)
            if projects:
                reporter.warn("部署器仓库未提供可部署项目，回退到内置 repo/ 列表")
    return projects


# ============================================================
# 项目仓库 / Reimilia_Setup
# ============================================================
@dataclass
class SetupPlan:
    kind: str
    path: Path
    doc: MdDoc
    variables: dict[str, str] = field(default_factory=dict)

    @property
    def script(self) -> str:
        return self.doc.script


def load_setup_plans(project_dir: Path, order: Iterable[str]) -> list[SetupPlan]:
    setup_dir = project_dir / SETUP_DIR_NAME
    if not setup_dir.is_dir():
        raise DeployError(
            f"该项目未接入 Reimilia：仓库根目录缺少 {SETUP_DIR_NAME}/ "
            "（需要 Binary 与/或 Build 文件）"
        )

    plans: list[SetupPlan] = []
    for kind in order:
        for candidate in (setup_dir / kind, setup_dir / f"{kind.lower()}.md", setup_dir / f"{kind}.md"):
            if not candidate.is_file():
                continue
            doc = parse_md_file(candidate)
            if not doc.primary_section().has_commands:
                continue
            plans.append(SetupPlan(kind=kind, path=candidate, doc=doc, variables=doc.variables))
            break
    return plans


def fetch_project(project: str, repo_url: str, settings: Settings, reporter: Reporter) -> Path:
    ensure_secure_url(repo_url, settings)
    workroot = paths.work_cache_dir()
    workroot.mkdir(parents=True, exist_ok=True)
    target = workroot / project
    if target.exists():
        shutil.rmtree(target, ignore_errors=True)

    reporter.log(f"克隆项目: {redact_url(repo_url)}")
    try:
        subprocess.run(
            [
                "git",
                "clone",
                "--depth",
                str(settings.clone_depth),
                "--",
                repo_url,
                str(target),
            ],
            check=True,
            capture_output=True,
            text=True,
            env=git_env(),
        )
    except subprocess.CalledProcessError as exc:
        shutil.rmtree(target, ignore_errors=True)
        detail = (exc.stderr or "").strip().splitlines()
        hint = detail[-1] if detail else str(exc)
        raise DeployError(f"克隆项目失败: {hint}") from exc
    return target


def _stdin_for(interactive: bool) -> int | None:
    if interactive:
        return None
    return subprocess.DEVNULL


def deploy_project(
    *,
    project: str,
    repo_url: str,
    settings: Settings,
    reporter: Reporter,
    kind: str | None = None,
    interactive: bool = True,
) -> dict[str, object]:
    """完整部署一个项目，返回结果摘要。"""
    if kind:
        normalized = kind.strip().capitalize()
        if normalized not in INSTALL_KINDS:
            raise DeployError(f"未知的安装方式: {kind}（可选 Build / Binary）")
        order: tuple[str, ...] = (normalized,)
    else:
        order = settings.install_order

    elevator = detect_elevator()
    if elevator:
        reporter.log(f"提权工具: {elevator}")
    else:
        reporter.log("提权工具: 无（当前为 root 或系统未提供 sudo/su）")

    workdir = fetch_project(project, repo_url, settings, reporter)
    reporter.event("stage", stage="setup", project=project)

    try:
        plans = load_setup_plans(workdir, order)
        if not plans:
            available = [p.name for p in sorted((workdir / SETUP_DIR_NAME).glob("*")) if p.is_file()]
            raise DeployError(
                f"{SETUP_DIR_NAME}/ 中没有可执行的安装说明（尝试顺序: {', '.join(order)}；"
                f"现有文件: {', '.join(available) or '无'}）"
            )

        reporter.log("安装方式顺序: " + " → ".join(plan.kind for plan in plans))
        failures: list[str] = []

        for index, plan in enumerate(plans):
            requires_root = str(plan.variables.get("REQUIRES_ROOT", "")).strip().lower() in {
                "1",
                "true",
                "yes",
                "on",
            }
            if requires_root and os.geteuid() != 0 and not elevator:
                failures.append(f"{plan.kind}: 需要 root，但未找到可用提权工具")
                reporter.error(failures[-1])
                continue

            reporter.event("stage", stage="install", project=project, kind=plan.kind)
            reporter.log("")
            reporter.log(f"===== 使用 {plan.kind} 方式安装 =====")

            env = build_env(
                settings,
                project=project,
                repo_url=repo_url,
                workdir=workdir,
                kind=plan.kind,
                md_vars=plan.variables,
                elevator=elevator,
            )
            code = run_script(
                plan.script,
                env=env,
                cwd=workdir,
                reporter=reporter,
                stdin=_stdin_for(interactive),
                label=plan.kind.lower(),
            )

            if code == 0:
                reporter.log("")
                reporter.log(f"{project} 部署完成 ✓（{plan.kind}）")
                return {
                    "ok": True,
                    "project": project,
                    "kind": plan.kind,
                    "workdir": str(workdir),
                    "exit_code": 0,
                }

            failures.append(f"{plan.kind}: 退出码 {code}")
            remaining = [p.kind for p in plans[index + 1 :]]
            if remaining:
                reporter.warn(f"{plan.kind} 失败（退出码 {code}），回退尝试: {', '.join(remaining)}")

        raise DeployError("所有安装方式均失败 —— " + "；".join(failures))
    finally:
        if settings.keep_workdir:
            reporter.log(f"保留工作目录: {workdir}")
        else:
            shutil.rmtree(workdir, ignore_errors=True)
            reporter.event("stage", stage="cleanup", project=project)
