#!/usr/bin/env python3
"""
Reimilia 最小化实现
功能：读取 repo/ 下的 .md 文件，克隆项目仓库，执行安装说明
"""

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

# ---------- 配置 ----------
REMOTE_REPO = "https://github.com/Reimilia617/Reimilia.git"  # 部署器仓库地址
CACHE_DIR = Path.home() / ".reimilia_cache"                    # 临时缓存目录
REPO_DIR_NAME = "repo"                                         # 存放项目 .md 的文件夹名


def fetch_deployer_repo(remote_url: str, target_dir: Path) -> Path:
    """克隆部署器仓库到本地缓存"""
    if target_dir.exists():
        shutil.rmtree(target_dir)
    print(f"[Reimilia] 正在克隆部署器仓库: {remote_url}")
    subprocess.run(
        ["git", "clone", "--depth", "1", remote_url, str(target_dir)],
        check=True,
    )
    return target_dir


def parse_repo_md(md_file: Path) -> str | None:
    """从 .md 文件中提取项目仓库的 HTTP 地址"""
    content = md_file.read_text(encoding="utf-8")
    # 匹配标准 http(s) 链接
    match = re.search(r"https?://\S+", content)
    if match:
        return match.group(0).strip()
    return None


def list_deployable_projects(repo_root: Path) -> dict[str, str]:
    """扫描 repo/ 文件夹，返回 {项目名: 仓库地址} 的映射"""
    projects = {}
    repo_dir = repo_root / REPO_DIR_NAME
    if not repo_dir.is_dir():
        print(f"[Reimilia] 未找到 {REPO_DIR_NAME}/ 目录")
        return projects

    for md_file in sorted(repo_dir.glob("*.md")):
        project_name = md_file.stem
        addr = parse_repo_md(md_file)
        if addr:
            projects[project_name] = addr
            print(f"[Reimilia] 发现项目: {project_name} -> {addr}")
        else:
            print(f"[Reimilia] 跳过 {md_file.name}: 未找到仓库地址")
    return projects


def execute_setup(project_dir: Path) -> None:
    """读取并执行项目仓库中的 Reimilia_Setup 安装说明"""
    setup_dir = project_dir / "Reimilia_Setup"
    if not setup_dir.is_dir():
        print("[Reimilia] 未找到 Reimilia_Setup/，跳过安装")
        return

    # 优先尝试 Binary 安装，其次 Build
    for install_type in ("Binary", "Build"):
        setup_md = setup_dir / install_type
        if not setup_md.exists():
            continue

        print(f"[Reimilia] 使用 {install_type} 方式安装...")
        content = setup_md.read_text(encoding="utf-8")

        # 提取 bash: 之后的每一行作为命令执行
        in_bash = False
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("bash:"):
                in_bash = True
                continue
            if in_bash:
                if stripped.startswith("["):  # 遇到下一个 section 标记，停止
                    break
                if stripped:
                    print(f"  $ {stripped}")
                    subprocess.run(stripped, shell=True, check=True)
        return

    print("[Reimilia] 未找到可用的安装说明文件")


def deploy(project_name: str, repo_url: str) -> None:
    """部署单个项目：克隆 -> 执行安装 -> 清理"""
    if CACHE_DIR.exists():
        shutil.rmtree(CACHE_DIR)
    CACHE_DIR.mkdir(parents=True)

    # 1. 克隆项目到临时目录
    project_clone_dir = CACHE_DIR / project_name
    print(f"[Reimilia] 克隆项目: {repo_url}")
    subprocess.run(
        ["git", "clone", "--depth", "1", repo_url, str(project_clone_dir)],
        check=True,
    )

    # 2. 读取并执行安装说明
    execute_setup(project_clone_dir)

    # 3. 清理临时文件（保留配置）
    print(f"[Reimilia] 清理临时文件: {CACHE_DIR}")
    shutil.rmtree(CACHE_DIR)
    print(f"[Reimilia] {project_name} 部署完成 ✓")


def main():
    # 克隆部署器仓库
    deployer_root = fetch_deployer_repo(REMOTE_REPO, CACHE_DIR / "deployer")

    # 扫描可部署项目
    projects = list_deployable_projects(deployer_root)
    if not projects:
        print("[Reimilia] 没有找到可部署的项目")
        return

    # 交互式选择项目
    names = list(projects.keys())
    print("\n可用项目:")
    for i, name in enumerate(names, 1):
        print(f"  {i}. {name}")

    try:
        choice = int(input("\n请选择要部署的项目编号: ")) - 1
        if 0 <= choice < len(names):
            deploy(names[choice], projects[names[choice]])
        else:
            print("无效的选择")
    except (ValueError, KeyboardInterrupt):
        print("\n已取消")


if __name__ == "__main__":
    main()