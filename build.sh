#!/usr/bin/env bash
# 把 Reimilia 打包成单文件可执行程序 dist/reimilia
#
# 用法：
#   ./build.sh              # 建 venv + 装 PyInstaller + 打包 + 冒烟测试
#   ./build.sh --no-venv    # 直接用当前 python 环境里的 PyInstaller
#   ./build.sh --keep-venv  # 保留 .venv-build（默认就保留，仅作说明）
#
# 产物：dist/reimilia（单文件，内含 WebUI 静态页与内置 repo/ 列表）
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

PYTHON="${PYTHON:-python3}"
VENV_DIR="${VENV_DIR:-.venv-build}"
USE_VENV=1

for arg in "$@"; do
  case "$arg" in
    --no-venv) USE_VENV=0 ;;
    -h|--help)
      sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *) echo "未知参数: $arg" >&2; exit 2 ;;
  esac
done

if [ "$USE_VENV" -eq 1 ]; then
  if [ ! -d "$VENV_DIR" ]; then
    echo "==> 创建虚拟环境: $VENV_DIR"
    "$PYTHON" -m venv "$VENV_DIR"
  fi
  # shellcheck disable=SC1091
  . "$VENV_DIR/bin/activate"
  PYTHON="python"
fi

if ! "$PYTHON" -c "import PyInstaller" >/dev/null 2>&1; then
  echo "==> 安装 PyInstaller"
  "$PYTHON" -m pip install --quiet --upgrade pip
  "$PYTHON" -m pip install --quiet --upgrade "pyinstaller>=6.0"
fi

echo "==> 语法自检"
"$PYTHON" -m compileall -q reimilia main.py webui.py

echo "==> 打包"
"$PYTHON" -m PyInstaller --clean --noconfirm Reimilia.spec

BIN="$HERE/dist/reimilia"
echo
echo "==> 冒烟测试: $BIN --version"
"$BIN" --version
echo "==> 冒烟测试: $BIN --show-config"
"$BIN" --show-config

cat <<EOF

打包完成 / build finished
  产物 / artifact : $BIN
  体积 / size     : $(du -h "$BIN" | cut -f1)
  运行 / run      : $BIN              # WebUI
                    $BIN --cli        # 终端部署
  安装 / install  : sudo install -m 0755 "$BIN" /usr/local/bin/reimilia

提示：运行时会读写 ~/.reimilia（配置 / 缓存 / 工作目录），
      可用 REIMILIA_HOME 改到别处。单文件每次启动会解包到临时目录，
      首次启动比源码运行慢一点属正常现象。
EOF
