# 用 PyInstaller 打包成单文件

目标：把 Reimilia 打成一个可执行文件，扔到任何 x86_64 Linux 上就能跑，
不需要目标机器装 Python、pip 或任何第三方库。

Reimilia 本身**只用 Python 标准库**，唯一的构建期依赖就是 PyInstaller。

---

## 一键构建

```bash
./build.sh
```

脚本会：

1. 建一个构建用虚拟环境 `.venv-build/`（Debian/Ubuntu 的 PEP 668
   「externally-managed-environment」限制会挡住直接 `pip install`，用 venv 绕过去）；
2. 装 `pyinstaller>=6.0`；
3. 语法自检 → 调 `Reimilia.spec` 打包；
4. 冒烟测试 `dist/reimilia --version` 与 `--show-config`。

产物：`dist/reimilia`。

常用变体：

```bash
./build.sh --no-venv          # 用当前环境里已有的 PyInstaller
PYTHON=python3.12 ./build.sh  # 指定解释器
VENV_DIR=/tmp/venv ./build.sh # 换个 venv 位置
```

---

## 手动构建

```bash
python3 -m venv .venv-build
. .venv-build/bin/activate
pip install "pyinstaller>=6.0"
pyinstaller --clean --noconfirm Reimilia.spec
./dist/reimilia --version
```

要求 **PyInstaller >= 6.0**：`Reimilia.spec` 用的是 6.x 的写法
（`PYZ(a.pure)`，单文件 `EXE(pyz, a.scripts, a.binaries, a.datas, ...)`）。
PyInstaller 5.x 的 `PYZ(a.pure, a.zipped_data, cipher=...)` 写法已经移除，
用 5.x 会直接报错。

---

## 打包进去了什么

`Reimilia.spec` 里的 `datas`：

| 源 | 包内路径 | 用途 |
|---|---|---|
| `static/` | `static/` | WebUI 页面 |
| `repo/` | `repo/` | 内置项目列表（远程仓库拉不到时的兜底） |

`reimilia/paths.py` 用 `sys._MEIPASS` 定位这些只读资源：

```python
def resource_dir() -> Path:
    if is_frozen():                       # PyInstaller 运行时会设 sys.frozen
        return Path(sys._MEIPASS)         # 单文件每次启动解包的临时目录
    return Path(__file__).resolve().parent.parent
```

**可写的东西一律不放进包内**，而是走用户目录：

| 内容 | 路径 | 环境变量覆盖 |
|---|---|---|
| 配置 | `~/.reimilia/config` | `REIMILIA_HOME` |
| 部署器仓库缓存 | `~/.reimilia/deployer` | 同上 |
| 项目工作目录 | `~/.reimilia/work/<项目>` | 同上 |

单文件模式下 `_MEIPASS` 是临时目录，**进程退出就没了**，所以绝不能往那里写东西。

---

## 安装到系统

```bash
sudo install -m 0755 dist/reimilia /usr/local/bin/reimilia
reimilia --version
```

之后：

```bash
reimilia                 # 默认启动 WebUI（会自动打开浏览器）
reimilia --cli           # 终端交互部署
reimilia --cli --list    # 列出可部署项目
```

`--no-browser` 可以关掉自动开浏览器（无桌面环境时有用）。

---

## 单文件模式的注意事项

* **首次启动稍慢**：单文件每次运行都会把自己解包到临时目录，几百毫秒到一两秒；
* **体积**：主要来自 Python 解释器与标准库，通常 10–20 MB 量级。
  `Reimilia.spec` 里已经 `excludes` 掉 `tkinter`、`unittest`、`setuptools`、
  `pip` 等用不到的东西；
* **不支持交叉编译**：PyInstaller 不做交叉编译，
  要 aarch64 的产物就得在 aarch64 机器（或对应容器 / CI runner）上跑一次 `./build.sh`；
* **没有签名**：打包产物不带任何签名，某些杀软 / EDR 可能对自解压行为敏感；
* **提权仍会弹到终端**：WebUI 里部署需要 root 的步骤时，
  `sudo` 直接读写 `/dev/tty`，密码提示出现在**启动 Reimilia 的那个终端**里。
  以服务方式启动（无终端）时请改用 `reimilia --cli`，或用 `REIMILIA_ELEVATE` 指定
  免密提权方式。

---

## 故障排查

**`No module named PyInstaller`**
venv 没激活，或者装到了系统 Python 上被 PEP 668 拦了。用 `./build.sh` 走 venv。

**`ModuleNotFoundError: reimilia` 运行时报错**
打包时 `Analysis(['main.py'])` 需要能 import 到 `reimilia/` 包。
确认在仓库根目录执行 `pyinstaller`，且 `reimilia/__init__.py` 存在。

**WebUI 打开是空白 / 报「缺少静态页面: .../_MEIPASS/static/index.html」**
`static/` 没被打进去。确认 `Reimilia.spec` 的 `datas` 里有 `("static", "static")`，
并且没有漏掉 `--clean`。

**二进制换台机器就跑不起来**
PyInstaller 产物依赖目标机器的 glibc 版本：在较新的发行版上构建，
跑到较老的发行版上会报 `GLIBC_2.xx not found`。
要在老系统上跑，就在老系统（或对应的容器）里构建。

**想确认自己跑的是打包版还是源码版**

```bash
reimilia --show-config | head -4      # frozen: yes / no
```
