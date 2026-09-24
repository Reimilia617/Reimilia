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

1. 建一个构建用虚拟环境 `.venv-build/`；
2. 确认里面有 pip（**没有就自动补**，见下面「Debian/Ubuntu 没有 pip」）；
3. 装 `pyinstaller>=6.0`；
4. 语法自检 → 调 `Reimilia.spec` 打包；
5. 冒烟测试 `dist/reimilia --version` 与 `--show-config`。

产物：`dist/reimilia`。

常用变体：

```bash
./build.sh --no-venv          # 用当前环境里已有的 PyInstaller
./build.sh --recreate-venv    # 删掉旧 venv 重建
PYTHON=python3.12 ./build.sh  # 指定解释器
VENV_DIR=/tmp/venv ./build.sh # 换个 venv 位置
```

### Debian/Ubuntu 没有 pip 怎么办

`python3 -m venv` 依赖 `python3-venv` 提供的 `ensurepip`。
Debian/Ubuntu 默认**不装**这个包，此时 `python3 -m venv` 会报：

```
The virtual environment was not created successfully because ensurepip is not
available.  On Debian/Ubuntu systems, you need to install the python3-venv
package ...
```

而且这条消息是打到 **stdout** 的，看起来很像脚本崩了；更坑的是它可能
留下一个**没有 pip、也没有 `activate`** 的半成品目录。

`build.sh` 会自动处理这种情况，**不需要 root**：

1. 先探测 `import ensurepip`，缺了就用 `python3 -m venv --without-pip` 建环境；
2. 再用 `ensurepip`（若可用）或官方 `get-pip.py` 把 pip 引导进去；
3. 然后正常装 PyInstaller、打包。

所以在没装 `python3-venv` 的 Debian 13 上，`./build.sh` 也能一次跑通。

想省掉每次引导 pip 的步骤，还是建议装上：

```bash
sudo apt install python3-venv        # Debian / Ubuntu
sudo dnf install python3-virtualenv  # Fedora / RHEL
sudo pacman -S python-virtualenv     # Arch
```

### 为什么不用 `source bin/activate`

因为 `python3 -m venv` 失败时会留下没有 `activate` 的半成品目录，
`source .venv-build/bin/activate` 会直接报「没有那个文件或目录」并中断。
脚本一律用 `.venv-build/bin/python` 绝对路径调用，不依赖 `activate`。

---

## 手动构建

```bash
python3 -m venv .venv-build
.venv-build/bin/python -m pip install "pyinstaller>=6.0"
.venv-build/bin/python -m PyInstaller --clean --noconfirm Reimilia.spec
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

**`ensurepip is not available` / venv 里没有 pip / 没有 activate**
Debian/Ubuntu 没装 `python3-venv`。`./build.sh` 会自动用
`--without-pip` + `get-pip.py` 绕过（不需要 root）；要一劳永逸就
`sudo apt install python3-venv`。细节见上面「Debian/Ubuntu 没有 pip 怎么办」。

**`No module named PyInstaller`**
多半是 venv 没建好或 pip 装到了别的环境。直接跑 `./build.sh`，
它会自己建环境、补 pip、装 PyInstaller。

**`Reimilia.spec` 报 `PYZ() got an unexpected keyword argument`**
PyInstaller 版本低于 6.0。升级：`./build.sh` 会自动检查并报出版本差异。

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

**想从头再来一遍**

```bash
rm -rf .venv-build build dist && ./build.sh --recreate-venv
```
