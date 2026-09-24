# Reimilia

一个基于 .md 描述的通用项目部署器。

## Reimilia 是什么？

Reimilia 是一个部署器，她不负责写功能，只负责把写好的项目装到系统里。

她的核心逻辑可以这么说：

> 读仓库 md >> 找到项目地址 >> 拉取项目 >> 按 `Reimilia_Setup/` 的说明自动下载编译安装

## 她怎么工作？

1. 拉取部署器仓库（默认是作者的仓库，可改成你 fork 后的地址）；
2. 扫描部署器仓库里的 `repo/` 文件夹，每个 `.md` 文件 = 一个可部署的项目，
   文件名就是显示的项目名，文件里的链接指向项目仓库；
3. 选定项目后，`git clone` 项目仓库到 `~/.reimilia/work/<项目名>`；
4. 读项目仓库根目录的 `Reimilia_Setup/`（`Build` / `Binary`）；
5. 按 md 里的说明执行安装脚本（源码编译或下载预编译产物）；
6. 结束后清理工作目录（部署器仓库的缓存与配置保留）。

## 快速开始

### 方式一：源码运行（开发用）

```bash
git clone https://github.com/Reimilia617/Reimilia.git
cd Reimilia
python3 main.py              # 默认启动 WebUI
python3 main.py --cli        # 终端交互部署
python3 main.py --cli --list # 只看有哪些项目
```

只依赖 Python 3.10+ 的标准库，没有任何第三方依赖。

### 方式二：打包成单文件（日常用）

```bash
./build.sh                   # 建 venv + 装 PyInstaller + 打包 + 冒烟测试
sudo install -m 0755 dist/reimilia /usr/local/bin/reimilia
reimilia                     # WebUI
reimilia --cli RTDO-Project --yes
```

打包细节（PyInstaller 版本要求、打了什么进去、跨发行版 glibc 问题、排障）
见 [docs/packaging.md](docs/packaging.md)。

### 命令行速查

```bash
reimilia                                   # 启动 WebUI（默认，自动开浏览器）
reimilia --cli                             # 终端交互式选择项目
reimilia --cli --list                      # 列出可部署项目
reimilia --cli RTDO-Project --yes          # 直接部署，跳过确认
reimilia --cli RTDO-Project --kind build   # 强制源码编译
reimilia --cli RTDO-Project --kind binary  # 强制用预编译产物
reimilia --repo /path/to/deployer --cli    # 用本地部署器仓库（开发 / 离线）
reimilia --set-repo <URL>                  # 持久化远程仓库地址
reimilia --show-config                     # 看生效配置与所有路径
reimilia --version
```

## 当前状态

Reimilia 是 Beta，但主流程已经是能用的。老实列一下：

| 能力 | 状态 |
|---|---|
| 读 `repo/*.md` 列出可部署项目 | ✅ 已实现 |
| 读 `Reimilia_Setup/{Build,Binary}` 并执行 | ✅ 已实现 |
| md 里的 `KEY="value"` 变量注入 bash | ✅ 已实现 |
| `bash:` 块整段执行（`cd` / `if` / heredoc 都正常） | ✅ 已实现 |
| 安装方式自动回退（Build 失败 → Binary） | ✅ 已实现 |
| 需要 root 的步骤自动提权（`reimilia_elevate`） | ✅ 已实现 |
| WebUI（项目列表 / 一键部署 / SSE 实时日志） | ✅ 已实现 |
| 单文件打包（PyInstaller） | ✅ 已实现 |
| 交互式安装（脚本中途向用户提问） | ❌ 未实现 |
| GPG 签名校验 | ❌ **未实现**，见下 |
| 兼容旧的 `install.sh` 脚本安装 | ❌ 未实现 |

## 配置文件

配置文件在 `~/.reimilia/config`，格式和 md 里的变量声明一样，是 `KEY="value"`：

```ini
REMOTE_REPO="https://github.com/Reimilia617/Reimilia.git"
INSTALL_ORDER="Build,Binary"
HOST="127.0.0.1"
PORT="8617"
DEPLOYER_TTL="300"
KEEP_WORKDIR="false"
ALLOW_INSECURE="false"
CLONE_DEPTH="1"
```

| 键 | 说明 |
|---|---|
| `REMOTE_REPO` | 部署器仓库地址，支持 http(s) / ssh / **本地目录** |
| `INSTALL_ORDER` | 同时存在 Build 与 Binary 时的尝试顺序 |
| `HOST` / `PORT` | WebUI 监听地址与端口（默认 `127.0.0.1:8617`） |
| `DEPLOYER_TTL` | 部署器仓库缓存有效期（秒，WebUI 用） |
| `KEEP_WORKDIR` | 部署后保留 `~/.reimilia/work/<项目>` 便于排查 |
| `ALLOW_INSECURE` | 允许 `http://` 与关闭 TLS 校验（不推荐） |
| `CLONE_DEPTH` | `git clone --depth` 的值 |

优先级：**默认值 < 配置文件 < 环境变量（`REIMILIA_<键>`）< 命令行参数**。

改远程仓库地址有三种办法：

```bash
reimilia --set-repo https://github.com/you/Reimilia.git   # 写进配置
reimilia --repo /path/to/your/repo --cli                  # 只本次生效
REIMILIA_REMOTE_REPO=https://github.com/you/Reimilia.git reimilia --cli
```

## 状态目录

所有可写数据都在 `~/.reimilia/`（可用 `REIMILIA_HOME` 改）：

```
~/.reimilia/
├── config      配置
├── deployer/   部署器仓库缓存
└── work/       项目工作目录（部署完会删）
```

以前的 `~/.reimilia_cache` 已经不用了。

## 为什么是 .md，不是 .json / .yaml？

.md 是给人看的，同时也是给机器看的：

* 人看得懂，能直接编辑；
* 机器读得懂，能按格式解析；
* 不需要额外依赖，不需要配置工具。

## md 文件格式

完整格式说明（变量声明规则、`bash:` 块语义、注入的上下文变量、
`reimilia_elevate` 提权帮助函数、安装方式回退、安全限制）
见 **[docs/md-format.md](docs/md-format.md)**。

最短的一个例子 —— 部署器仓库 `repo/demo.md`：

```md
[Reimilia_Repo]
https://github.com/you/demo.git
```

项目仓库 `Reimilia_Setup/Build`：

```md
[Reimilia_Build]

REQUIRES_ROOT="true"

bash:
cd "$REIMILIA_WORKDIR"
cargo build --release
reimilia_elevate install -D -m 0755 target/release/demo /usr/local/bin/demo
/usr/local/bin/demo --version
```

要点：

* `[Reimilia_Repo]` / `[Reimilia_Build]` / `[Reimilia_Binary]` 是段标记，独占一行；
* `KEY="value"` 会作为环境变量注入 `bash:` 块；
* `bash:` 之后的每一行是一段脚本的一部分，**整段**用 `bash -e` 执行
  （所以 `cd`、`if`、`for`、heredoc 都正常，某行失败会中止并报出行号）；
* Reimilia 已经替你克隆好了项目，就地用 `$REIMILIA_WORKDIR` 即可，不必重复 `git clone`。

## 安全

* **强制 HTTPS**：项目地址只接受 `https://`、`ssh` / `git@`、`file://`（本地），
  `http://` 需要显式 `ALLOW_INSECURE="true"`；
* 检测到 `GIT_SSL_NO_VERIFY` 直接拒绝运行；
* **WebUI 不接受前端传来的仓库地址**：`/api/deploy` 只收项目名，由服务端解析成地址。
  否则任何网页都能 POST 一个恶意仓库让本机执行它的安装脚本；
* WebUI 另外校验 `Origin` 并要求 `Content-Type: application/json`，挡跨站提交；
* WebUI 默认只监听 `127.0.0.1`，**没有任何认证**，要对外暴露请自己想清楚；
* 安装脚本以**你自己的身份**执行，需要 root 的地方由你显式提权，
  所以「只部署自己信任的仓库」是目前唯一的安全边界。

### 关于签名（未实现）

README 从最早那版就描述了一套 GPG 签名校验机制（`repo/*.md` 与
`Reimilia_Setup/*` 各配一个 `.sig`、公钥放 `keys/` 并缓存、
`Rule.txt` 里 `true` 表示同意关闭校验）。

**这套机制目前没有实现**，一行代码都没有：

* Reimilia 现在不会读 `keys/`，也不会去验证 `.sig`；
* 缺签名**不会**导致拒绝部署；
* 项目仓库暂时不需要提供 `.sig` 文件。

原因是还在 Beta，而且签名私钥目前没有合适的存放位置。
等实现之后会补上公钥缓存、`Rule.txt` 关闸与验证流程的说明，
在那之前请不要以为有签名保护。

## 为什么用 Python 写？

Reimilia 的本质就是「调用命令 >> 读取文件 >> 下载 >> 解压」，
Python 自带的库就能完成，不用管内存，扔到任何一台 Linux 都能跑。
现在整个项目只依赖标准库 —— 这也是能轻松打成单文件的原因。

## 定位

Reimilia 是独立系列，属于工具层，服务于所有项目（同 Sakuya）。
今后若需要使用作者编写的项目，统一建议用 Reimilia 部署。

## 项目结构

```
Reimilia/
├── main.py                 统一入口（默认 WebUI，--cli 走终端）
├── webui.py                旧入口，等价于 main.py --webui
├── reimilia/               实际实现
│   ├── app.py              参数解析与分发
│   ├── cli.py              终端界面
│   ├── webui.py            标准库 HTTP 服务 + SSE 日志
│   ├── deploy.py           克隆、提权探测、执行 md 脚本、回退
│   ├── mdparse.py          md / 配置文件解析
│   ├── config.py           配置合并与持久化
│   └── paths.py            打包 / 源码两种形态下的路径解析
├── reimilia/__main__.py    支持 python -m reimilia
├── static/index.html       WebUI 页面
├── repo/                   可部署项目列表（每个 md 一个项目）
├── docs/
│   ├── md-format.md        md 描述格式完整说明
│   └── packaging.md        PyInstaller 打包说明
├── Reimilia.spec           PyInstaller 配置
├── build.sh                一键打包脚本
└── .gitignore
```

## 已接入的项目

| 项目 | 说明 |
|---|---|
| [RTDO-Project](https://github.com/Reimilia617/RTDO-Project) | rtdo —— 交互式、环境自适应的提权工具（替代 sudo）。`Reimilia_Setup/` 提供 Build 与 Binary 两种方式 |

## 开发

```bash
python3 main.py --repo . --cli --list    # 直接用当前工作区当部署器仓库
python3 -m compileall reimilia           # 语法检查
```

`--repo` 接受本地目录，所以调 md 格式的时候不用来回 push：

```bash
mkdir -p /tmp/demo-repo/repo
printf '[Reimilia_Repo]\nfile:///tmp/demo-project\n' > /tmp/demo-repo/repo/demo.md
python3 main.py --repo /tmp/demo-repo --cli demo --yes
```

## 许可证与贡献者

MIT License，Copyright (c) 2026 Reimilia617

贡献者：

- **Reimilia617** — 项目发起、需求与产品设计
- **DeepSeek（AI 助手）** — 代码实现、架构设计与文档协作

发现 bug 或有更好的想法，欢迎直接提 issue。
