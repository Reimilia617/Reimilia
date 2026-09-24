#!/usr/bin/env bash
# 把 Reimilia 打包成单文件可执行程序 dist/reimilia
#
# 用法：
#   ./build.sh                 # 建 venv + 装 PyInstaller + 打包 + 冒烟测试
#   ./build.sh --no-venv       # 用当前 python 环境里的 PyInstaller
#   ./build.sh --recreate-venv # 删掉旧 venv 重建
#
# 产物：dist/reimilia（单文件，内含 WebUI 静态页与内置 repo/ 列表）
#
# 关于 pip：Debian/Ubuntu 上如果没装 python3-venv，
# `python3 -m venv` 会生成一个**没有 pip、也没有 activate 脚本**的环境
# （而且不一定报错）。所以本脚本不依赖 `source bin/activate`，
# 并且会在检测到 pip 缺失时自动用 get-pip.py 引导（不需要 root）。
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

PYTHON="${PYTHON:-python3}"
VENV_DIR="${VENV_DIR:-.venv-build}"
USE_VENV=1
RECREATE=0
VENV_PY=""

usage() {
  cat <<'EOF'
把 Reimilia 打包成单文件可执行程序。

用法:
  ./build.sh                 建 venv + 装 PyInstaller + 打包 + 冒烟测试
  ./build.sh --no-venv       用当前 python 环境里的 PyInstaller
  ./build.sh --recreate-venv 删掉旧 venv 重建
  ./build.sh --help

环境变量:
  PYTHON     指定解释器（默认 python3）
  VENV_DIR   虚拟环境位置（默认 .venv-build）
EOF
}

die() { printf '\n错误 / error: %s\n' "$*" >&2; exit 1; }

for arg in "$@"; do
  case "$arg" in
    --no-venv)       USE_VENV=0 ;;
    --recreate-venv) RECREATE=1 ;;
    -h|--help)       usage; exit 0 ;;
    *) die "未知参数 / unknown option: $arg（用 --help 看用法）" ;;
  esac
done

# ---------------------------------------------------------------
# 虚拟环境
# ---------------------------------------------------------------
prepare_venv() {
  if [ "$RECREATE" -eq 1 ] && [ -e "$VENV_DIR" ]; then
    echo "==> 删除旧虚拟环境: $VENV_DIR"
    rm -rf "$VENV_DIR"
  fi

  if [ -x "$VENV_DIR/bin/python" ] && "$VENV_DIR/bin/python" -c "import sys" >/dev/null 2>&1; then
    echo "==> 复用虚拟环境: $VENV_DIR"
  else
    echo "==> 创建虚拟环境: $VENV_DIR"
    create_venv
    [ -x "$VENV_DIR/bin/python" ] || die "虚拟环境创建后找不到 $VENV_DIR/bin/python"
  fi

  VENV_PY="$VENV_DIR/bin/python"
}

# Debian/Ubuntu 没装 python3-venv 时，`python3 -m venv` 会因为没有 ensurepip
# 而失败（还把错误打到 stdout，看起来很像脚本崩了）。这里先探测 ensurepip，
# 缺了就直接用 --without-pip 建，pip 交给 ensure_pip() 用 get-pip.py 补上
# —— 全程不需要 root。
create_venv() {
  rm -rf "$VENV_DIR"

  local with_pip=1 errfile
  if ! "$PYTHON" -c "import ensurepip" >/dev/null 2>&1; then
    with_pip=0
    echo "==> 当前 Python 缺少 ensurepip（Debian/Ubuntu 未装 python3-venv）"
    echo "    改用 --without-pip 创建，稍后用 get-pip.py 补上 pip（不需要 root）"
  fi

  errfile="$(mktemp)"
  if [ "$with_pip" -eq 1 ]; then
    "$PYTHON" -m venv "$VENV_DIR" >"$errfile" 2>&1 && { rm -f "$errfile"; return 0; }
  else
    "$PYTHON" -m venv --without-pip "$VENV_DIR" >"$errfile" 2>&1 && { rm -f "$errfile"; return 0; }
  fi

  echo "==> 创建虚拟环境失败:"
  sed 's/^/    /' "$errfile" || true
  rm -f "$errfile"
  rm -rf "$VENV_DIR"
  die "无法创建虚拟环境。请安装 venv 支持后重试:
       Debian/Ubuntu: sudo apt install python3-venv
       Fedora/RHEL:   sudo dnf install python3-virtualenv
       Arch:          sudo pacman -S python-virtualenv
     或者自己准备好 PyInstaller 后跳过 venv: ./build.sh --no-venv"
}

have_pip() { "$VENV_PY" -m pip --version >/dev/null 2>&1; }

ensure_pip() {
  if have_pip; then
    return 0
  fi

  echo "==> 该虚拟环境里没有 pip"

  if "$VENV_PY" -c "import ensurepip" >/dev/null 2>&1; then
    echo "==> 尝试 ensurepip"
    if "$VENV_PY" -m ensurepip --upgrade >/dev/null 2>&1; then
      if have_pip; then return 0; fi
    fi
  fi

  echo "==> 用官方 get-pip.py 引导 pip（不需要 root）"
  local tmp url
  tmp="$(mktemp -d)"
  url="https://bootstrap.pypa.io/get-pip.py"
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL --retry 3 --retry-delay 2 "$url" -o "$tmp/get-pip.py" || true
  elif command -v wget >/dev/null 2>&1; then
    wget -qO "$tmp/get-pip.py" "$url" || true
  else
    rm -rf "$tmp"
    die "既没有 curl 也没有 wget，无法下载 get-pip.py。请先 sudo apt install python3-venv"
  fi

  if [ -s "$tmp/get-pip.py" ]; then
    "$VENV_PY" "$tmp/get-pip.py" --quiet || true
  fi
  rm -rf "$tmp"

  if have_pip; then
    echo "    pip 引导成功。下次可以 sudo apt install python3-venv，省掉这一步"
    return 0
  fi

  die "无法在该环境里获得 pip。请任选一种：
  1) 安装 venv 支持（推荐，一劳永逸）:
       Debian/Ubuntu:  sudo apt install python3-venv
       Fedora/RHEL:    sudo dnf install python3-virtualenv
       Arch:           sudo pacman -S python-virtualenv
  2) 自己装好 PyInstaller 后跳过 venv:
       $VENV_PY -m pip install 'pyinstaller>=6.0'  &&  ./build.sh --no-venv
  3) 手动把 pip 引导进 venv:
       $VENV_PY https://bootstrap.pypa.io/get-pip.py"
}

# ---------------------------------------------------------------
# PyInstaller
# ---------------------------------------------------------------
ensure_pyinstaller() {
  if ! "$VENV_PY" -c "import PyInstaller" >/dev/null 2>&1; then
    echo "==> 安装 PyInstaller (>=6.0)"
    "$VENV_PY" -m pip install --quiet --disable-pip-version-check --upgrade "pyinstaller>=6.0" \
      || die "安装 PyInstaller 失败（网络问题？）"
    "$VENV_PY" -c "import PyInstaller" >/dev/null 2>&1 || die "PyInstaller 安装后仍无法导入"
  fi

  local version major
  version="$("$VENV_PY" -c 'import PyInstaller; print(PyInstaller.__version__)')"
  major="${version%%.*}"
  if [ "$major" -lt 6 ]; then
    die "Reimilia.spec 需要 PyInstaller >= 6.0，当前是 $version。
     升级: $VENV_PY -m pip install -U 'pyinstaller>=6.0'"
  fi
  echo "==> PyInstaller $version"
}

# ---------------------------------------------------------------
main() {
  if [ "$USE_VENV" -eq 1 ]; then
    prepare_venv
    ensure_pip
  else
    VENV_PY="$PYTHON"
    echo "==> 跳过 venv，使用: $VENV_PY"
    if ! "$VENV_PY" -c "import PyInstaller" >/dev/null 2>&1; then
      if "$VENV_PY" -m pip --version >/dev/null 2>&1; then
        echo "==> 当前环境没有 PyInstaller，尝试安装"
        "$VENV_PY" -m pip install --quiet --disable-pip-version-check --upgrade "pyinstaller>=6.0" || true
      fi
    fi
    if ! "$VENV_PY" -c "import PyInstaller" >/dev/null 2>&1; then
      die "当前环境没有 PyInstaller，且无法自动安装。请先执行:
       $VENV_PY -m pip install 'pyinstaller>=6.0'
     或者去掉 --no-venv，让脚本自己建虚拟环境。"
    fi
  fi

  ensure_pyinstaller

  echo "==> 语法自检"
  "$VENV_PY" -m compileall -q reimilia main.py webui.py

  echo "==> 打包"
  "$VENV_PY" -m PyInstaller --clean --noconfirm Reimilia.spec

  local bin="$HERE/dist/reimilia"
  [ -x "$bin" ] || die "打包结束但没有找到可执行文件: $bin"

  echo
  echo "==> 冒烟测试: $bin --version"
  "$bin" --version
  echo "==> 冒烟测试: $bin --show-config"
  "$bin" --show-config

  cat <<EOF

打包完成 / build finished
  产物 / artifact : $bin
  体积 / size     : $(du -h "$bin" | cut -f1)
  运行 / run      : $bin              # WebUI
                    $bin --cli        # 终端部署
  安装 / install  : sudo install -m 0755 "$bin" /usr/local/bin/reimilia

提示：运行时会读写 ~/.reimilia（配置 / 缓存 / 工作目录），
      可用 REIMILIA_HOME 改到别处。单文件每次启动会解包到临时目录，
      首次启动比源码运行慢一点属正常现象。
EOF
}

main
