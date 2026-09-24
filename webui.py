#!/usr/bin/env python3
"""
Reimilia WebUI —— 基于 Python 标准库的最小 Web 前端
与 Reimilia 部署器配合，提供：项目浏览 / 一键部署 / SSE 实时日志
"""

import json
import queue
import re
import shutil
import subprocess
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# ---------- 配置 ----------
REMOTE_REPO   = "https://github.com/Reimilia617/Reimilia.git"
CACHE_DIR     = Path.home() / ".reimilia_cache"
REPO_DIR_NAME = "repo"
HOST          = "127.0.0.1"     # 只监听本机；改成 0.0.0.0 请务必加认证！
PORT          = 8617
DEPLOYER_TTL  = 300              # 部署器仓库缓存有效期（秒）

# ---------- 运行时状态 ----------
TASKS: dict[str, dict] = {}
TASKS_LOCK = threading.Lock()

_deployer_cache = {"path": None, "ts": 0.0}
_deployer_lock  = threading.Lock()


# ============================================================
# 部署器仓库：拉取 / 解析
# ============================================================
def get_deployer_root(force: bool = False) -> Path:
    """克隆 Reimilia 部署器仓库到本地缓存（带 TTL 缓存）"""
    with _deployer_lock:
        now = time.time()
        cached: Path | None = _deployer_cache["path"]
        if (not force) and cached and cached.exists() and (now - _deployer_cache["ts"] < DEPLOYER_TTL):
            return cached

        target = CACHE_DIR / "deployer"
        if target.exists():
            shutil.rmtree(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "clone", "--depth", "1", REMOTE_REPO, str(target)],
            check=True, capture_output=True, text=True,
        )
        _deployer_cache["path"] = target
        _deployer_cache["ts"] = time.time()
        return target


def parse_repo_md(md_file: Path) -> str | None:
    """从 .md 文件里提取第一个 http(s) 链接"""
    content = md_file.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"https?://\S+", content)
    return m.group(0).strip() if m else None


def list_projects(force_refresh: bool = False) -> dict[str, str]:
    """扫描 repo/ 目录 → {项目名: 仓库地址}"""
    root = get_deployer_root(force=force_refresh)
    repo_dir = root / REPO_DIR_NAME
    projects: dict[str, str] = {}
    if not repo_dir.is_dir():
        return projects
    for md in sorted(repo_dir.glob("*.md")):
        addr = parse_repo_md(md)
        if addr:
            projects[md.stem] = addr
    return projects


# ============================================================
# 部署流程
# ============================================================
def _emit(q: queue.Queue, msg: str) -> None:
    q.put({"type": "log", "msg": msg})


def _run_streaming(cmd: str, q: queue.Queue) -> None:
    """执行 shell 命令，并实时把 stdout/stderr 推给队列"""
    proc = subprocess.Popen(
        cmd, shell=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1,
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        _emit(q, line.rstrip())
    proc.wait()
    if proc.returncode != 0:
        raise RuntimeError(f"命令失败（退出码 {proc.returncode}）: {cmd}")


def execute_setup(project_dir: Path, q: queue.Queue) -> None:
    """读取 Reimilia_Setup/{Binary,Build} 并逐行执行 bash: 段"""
    setup_dir = project_dir / "Reimilia_Setup"
    if not setup_dir.is_dir():
        _emit(q, "未找到 Reimilia_Setup/，跳过安装")
        return

    for kind in ("Binary", "Build"):
        f = setup_dir / kind
        if not f.exists():
            continue
        _emit(q, f"使用 {kind} 方式安装...")
        content = f.read_text(encoding="utf-8", errors="replace")
        in_bash = False
        for line in content.splitlines():
            s = line.strip()
            if s.startswith("bash:"):
                in_bash = True
                continue
            if in_bash:
                if s.startswith("["):      # 遇到下一个 section
                    break
                if s:
                    _emit(q, f"$ {s}")
                    _run_streaming(s, q)
        return
    _emit(q, "未找到可用的安装说明文件")


def deploy_worker(project_name: str, repo_url: str, q: queue.Queue) -> None:
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        project_dir = CACHE_DIR / project_name
        if project_dir.exists():
            shutil.rmtree(project_dir)

        _emit(q, f"克隆项目: {repo_url}")
        subprocess.run(
            ["git", "clone", "--depth", "1", repo_url, str(project_dir)],
            check=True, capture_output=True, text=True,
        )
        execute_setup(project_dir, q)
        shutil.rmtree(project_dir, ignore_errors=True)
        _emit(q, f"{project_name} 部署完成 ✓")
    except Exception as e:
        _emit(q, f"错误: {e}")
    finally:
        q.put({"type": "end"})


# ============================================================
# HTTP 处理
# ============================================================
STATIC_DIR = Path(__file__).resolve().parent / "static"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"[WebUI] {self.address_string()} - {fmt % args}")

    # ---- 工具 ----
    def _json(self, data, status: int = 200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _file(self, path: Path, ctype: str):
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    # ---- GET ----
    def do_GET(self):
        if self.path in ("/", "/index.html"):
            html = STATIC_DIR / "index.html"
            if html.exists():
                self._file(html, "text/html; charset=utf-8")
            else:
                self.send_error(500, "static/index.html 缺失")
        elif self.path.startswith("/api/projects"):
            self._api_projects()
        elif self.path.startswith("/api/logs/"):
            self._api_logs(self.path.rsplit("/", 1)[-1])
        else:
            self.send_error(404)

    # ---- POST ----
    def do_POST(self):
        if self.path == "/api/deploy":
            self._api_deploy()
        else:
            self.send_error(404)

    # ---- API ----
    def _api_projects(self):
        force = "refresh=1" in self.path
        try:
            projects = list_projects(force_refresh=force)
            self._json({"ok": True, "projects": projects})
        except subprocess.CalledProcessError as e:
            err = (e.stderr or "").strip() or str(e)
            self._json({"ok": False, "error": f"克隆部署器失败: {err}"}, 500)
        except Exception as e:
            self._json({"ok": False, "error": str(e)}, 500)

    def _api_deploy(self):
        length = int(self.headers.get("Content-Length", 0))
        try:
            data = json.loads(self.rfile.read(length).decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._json({"ok": False, "error": "invalid json"}, 400)
            return

        project = (data.get("project") or "").strip()
        url     = (data.get("url") or "").strip()
        if not project or not url:
            self._json({"ok": False, "error": "project / url 缺失"}, 400)
            return

        task_id = uuid.uuid4().hex[:12]
        q: queue.Queue = queue.Queue()
        with TASKS_LOCK:
            TASKS[task_id] = {"queue": q, "done": False}

        def runner():
            deploy_worker(project, url, q)
            with TASKS_LOCK:
                TASKS[task_id]["done"] = True

        threading.Thread(target=runner, daemon=True).start()
        self._json({"ok": True, "task_id": task_id})

    def _api_logs(self, task_id: str):
        with TASKS_LOCK:
            task = TASKS.get(task_id)
        if not task:
            self.send_error(404, "task not found")
            return

        # SSE 响应
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

        q: queue.Queue = task["queue"]
        try:
            while True:
                try:
                    item = q.get(timeout=15)
                except queue.Empty:
                    self.wfile.write(b": ping\n\n")   # 心跳保活
                    self.wfile.flush()
                    continue
                if item.get("type") == "end":
                    self.wfile.write(b"event: end\ndata: {}\n\n")
                    self.wfile.flush()
                    break
                payload = json.dumps(item, ensure_ascii=False)
                self.wfile.write(f"data: {payload}\n\n".encode("utf-8"))
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass


# ============================================================
def main():
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"[Reimilia] WebUI 已启动: http://{HOST}:{PORT}")
    print(f"[Reimilia] 缓存目录: {CACHE_DIR}")
    print("[Reimilia] Ctrl+C 退出")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[Reimilia] 正在关闭...")
        server.shutdown()


if __name__ == "__main__":
    main()