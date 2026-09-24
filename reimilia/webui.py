"""WebUI：只用标准库实现的本地 HTTP 界面（浏览项目 / 一键部署 / SSE 实时日志）。

安全取舍：

* 默认只监听 ``127.0.0.1``；对外暴露需要自己承担风险（没有认证）；
* 部署目标由**服务端**根据项目名解析，绝不接受前端传来的 URL，
  否则任何网页都能 POST 一个任意仓库让本机执行其安装脚本；
* 额外用 ``Origin`` 校验 + 强制 ``Content-Type: application/json``
  挡住跨站表单提交（两者都过不了浏览器预检）。
"""

from __future__ import annotations

import json
import threading
import time
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from . import __version__, paths
from .config import Settings
from .deploy import (
    DeployError,
    Reporter,
    deploy_project,
    list_projects,
    redact_url,
)

TASK_TTL = 3600
MAX_HISTORY = 20000
_KINDS = {"auto", "build", "binary"}


class Task:
    """一次部署任务：历史日志可重放，支持多个 SSE 订阅者。"""

    def __init__(self, task_id: str, project: str, kind: str) -> None:
        self.id = task_id
        self.project = project
        self.kind = kind
        self.created = time.time()
        self.finished = False
        self.result: dict[str, object] | None = None
        self._events: list[dict] = []
        self._cond = threading.Condition()

    def emit(self, item: dict) -> None:
        with self._cond:
            if len(self._events) < MAX_HISTORY:
                self._events.append(item)
            elif len(self._events) == MAX_HISTORY:
                self._events.append({"type": "log", "level": "warn", "msg": "[日志过多，已截断]"})
            self._cond.notify_all()

    def finish(self, result: dict | None) -> None:
        with self._cond:
            self.finished = True
            self.result = result
            self._cond.notify_all()

    def stream(self, cursor: int, timeout: float = 15.0) -> tuple[list[dict], int, bool]:
        """返回 ``(新事件, 新 cursor, 是否结束)``。"""
        with self._cond:
            if cursor < len(self._events):
                return self._events[cursor:], len(self._events), False
            if self.finished:
                return [], cursor, True
            self._cond.wait(timeout)
            batch = self._events[cursor:]
            return batch, len(self._events), self.finished and not batch


class Registry:
    def __init__(self) -> None:
        self._tasks: dict[str, Task] = {}
        self._lock = threading.Lock()

    def create(self, project: str, kind: str) -> Task:
        task = Task(uuid.uuid4().hex[:12], project, kind)
        with self._lock:
            self._tasks[task.id] = task
            self._prune_locked()
        return task

    def get(self, task_id: str) -> Task | None:
        with self._lock:
            return self._tasks.get(task_id)

    def _prune_locked(self) -> None:
        now = time.time()
        stale = [
            tid
            for tid, task in self._tasks.items()
            if task.finished and now - task.created > TASK_TTL
        ]
        for tid in stale:
            self._tasks.pop(tid, None)


class Handler(BaseHTTPRequestHandler):
    server_version = f"Reimilia/{__version__}"
    settings: Settings
    registry: Registry
    index_file: Path

    # ---------- 基础工具 ----------
    def log_message(self, fmt: str, *args) -> None:  # noqa: A003 - 基类约定
        print(f"[WebUI] {self.address_string()} - {fmt % args}")

    def _send(self, status: int, body: bytes, ctype: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, data: object, status: int = 200) -> None:
        self._send(status, json.dumps(data, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _error_json(self, message: str, status: int) -> None:
        self._json({"ok": False, "error": message}, status)

    def _same_origin(self) -> bool:
        origin = self.headers.get("Origin")
        if not origin:
            return True  # 同源 fetch / curl 不带 Origin
        return urlsplit(origin).netloc == (self.headers.get("Host") or "")

    # ---------- GET ----------
    def do_GET(self) -> None:  # noqa: N802 - 基类约定
        parsed = urlsplit(self.path)
        route = parsed.path

        if route in ("/", "/index.html"):
            self._serve_index()
        elif route == "/api/projects":
            self._api_projects(parse_qs(parsed.query))
        elif route == "/api/status":
            self._api_status()
        elif route.startswith("/api/logs/"):
            self._api_logs(route.rsplit("/", 1)[-1])
        else:
            self._error_json("not found", 404)

    def do_POST(self) -> None:  # noqa: N802
        if urlsplit(self.path).path != "/api/deploy":
            self._error_json("not found", 404)
            return
        self._api_deploy()

    # ---------- 静态页 ----------
    def _serve_index(self) -> None:
        if not self.index_file.is_file():
            self._error_json(f"缺少静态页面: {self.index_file}", 500)
            return
        self._send(200, self.index_file.read_bytes(), "text/html; charset=utf-8")

    # ---------- API ----------
    def _api_status(self) -> None:
        info = paths.describe()
        info.update(
            {
                "ok": True,
                "version": __version__,
                "remote_repo": redact_url(self.settings.remote_repo),
                "install_order": list(self.settings.install_order),
                "host": self.settings.host,
                "port": self.settings.port,
            }
        )
        self._json(info)

    def _api_projects(self, query: dict[str, list[str]]) -> None:
        force = query.get("refresh", ["0"])[0] not in ("0", "", "false")
        reporter = Reporter()
        try:
            projects = list_projects(self.settings, reporter, force=force)
        except DeployError as exc:
            self._error_json(str(exc), 502)
            return
        except Exception as exc:  # noqa: BLE001 - 兜底，避免线程崩溃
            self._error_json(f"内部错误: {exc}", 500)
            return
        self._json({"ok": True, "projects": projects})

    def _api_deploy(self) -> None:
        if not self._same_origin():
            self._error_json("拒绝跨站请求", 403)
            return
        ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if ctype != "application/json":
            self._error_json("Content-Type 必须是 application/json", 415)
            return

        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            self._error_json("非法 Content-Length", 400)
            return
        if length <= 0 or length > 64 * 1024:
            self._error_json("请求体为空或过大", 400)
            return

        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._error_json("请求体不是合法 JSON", 400)
            return
        if not isinstance(payload, dict):
            self._error_json("请求体必须是 JSON 对象", 400)
            return

        project = str(payload.get("project") or "").strip()
        kind = str(payload.get("kind") or "auto").strip().lower()
        if kind not in _KINDS:
            self._error_json(f"未知的安装方式: {kind}", 400)
            return
        if not project:
            self._error_json("缺少 project 参数", 400)
            return

        # 关键：URL 由服务端解析，绝不信任前端
        reporter = Reporter()
        try:
            projects = list_projects(self.settings, reporter)
        except DeployError as exc:
            self._error_json(str(exc), 502)
            return

        repo_url = projects.get(project)
        if repo_url is None:
            self._error_json(f"未知项目: {project}", 404)
            return

        task = self.registry.create(project, kind)
        threading.Thread(
            target=_run_task,
            args=(task, repo_url, kind, self.settings),
            daemon=True,
            name=f"deploy-{task.id}",
        ).start()
        self._json({"ok": True, "task_id": task.id, "project": project, "repo": redact_url(repo_url)})

    def _api_logs(self, task_id: str) -> None:
        task = self.registry.get(task_id)
        if task is None:
            self._error_json("task not found", 404)
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

        cursor = 0
        try:
            while True:
                batch, cursor, finished = task.stream(cursor)
                for item in batch:
                    payload = json.dumps(item, ensure_ascii=False)
                    self.wfile.write(f"data: {payload}\n\n".encode("utf-8"))
                if batch:
                    self.wfile.flush()
                    continue
                if finished:
                    result = json.dumps(task.result or {}, ensure_ascii=False)
                    self.wfile.write(f"event: end\ndata: {result}\n\n".encode("utf-8"))
                    self.wfile.flush()
                    break
                self.wfile.write(b": ping\n\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, ValueError):
            pass


def _run_task(task: Task, repo_url: str, kind: str, settings: Settings) -> None:
    def on_log(message: str, level: str) -> None:
        task.emit({"type": "log", "level": level, "msg": message})

    reporter = Reporter(on_log=on_log, on_event=lambda k, d: task.emit({"type": k, **d}))
    kind_arg = None if kind == "auto" else kind
    result: dict[str, object] = {"ok": False, "project": task.project}
    try:
        result = deploy_project(
            project=task.project,
            repo_url=repo_url,
            settings=settings,
            reporter=reporter,
            kind=kind_arg,
            interactive=False,
        )
    except DeployError as exc:
        reporter.error(str(exc))
    except Exception as exc:  # noqa: BLE001 - 别让线程静默死掉
        reporter.error(f"内部错误: {exc!r}")
    finally:
        task.finish(result)


def build_server(settings: Settings, *, index_file: Path | None = None) -> ThreadingHTTPServer:
    handler = type(
        "ReimiliaHandler",
        (Handler,),
        {
            "settings": settings,
            "registry": Registry(),
            "index_file": index_file or (paths.static_dir() / "index.html"),
        },
    )
    server = ThreadingHTTPServer((settings.host, settings.port), handler)
    server.daemon_threads = True
    return server


def run_webui(settings: Settings, *, open_browser: bool = True) -> int:
    try:
        server = build_server(settings)
    except OSError as exc:
        print(f"[Reimilia] 无法监听 {settings.host}:{settings.port} —— {exc}")
        return 1

    url = f"http://{settings.host}:{settings.port}/"
    print(f"[Reimilia] WebUI 已启动: {url}")
    print(f"[Reimilia] 部署器仓库: {redact_url(settings.remote_repo)}")
    print(f"[Reimilia] 安装方式顺序: {' → '.join(settings.install_order)}")
    print(f"[Reimilia] 状态目录: {paths.state_dir()}")
    if settings.host not in ("127.0.0.1", "localhost", "::1"):
        print("[Reimilia] ⚠ 正在监听非本机地址，且没有认证机制，请自行确保网络安全")
    print("[Reimilia] Ctrl+C 退出")

    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[Reimilia] 正在关闭...")
    finally:
        server.shutdown()
        server.server_close()
    return 0
