# Reimilia md 描述格式

Reimilia 只认两种 md 文件：

| 位置 | 角色 | 内容 |
|---|---|---|
| 部署器仓库 `repo/<项目名>.md` | 把项目名指向项目仓库 | 一个仓库地址 |
| 项目仓库 `Reimilia_Setup/{Build,Binary}` | 怎么装这个项目 | 变量声明 + 一段 bash |

> 文件名（去掉 `.md`）就是 Reimilia 界面与 CLI 里显示的项目名。
> `Reimilia_Setup/` 下的文件名就是安装方式名，支持写 `Build` 或 `Build.md`。

---

## 1. 部署器仓库：`repo/<项目名>.md`

```repo
[Reimilia_Repo]
https://github.com/Reimilia617/RTDO-Project

# `#` 开头是注释，会被忽略
# 正文里出现的第一个链接就是项目仓库地址
```

* `[Reimilia_Repo]` 是段标记，必须独占一行；
* 段内第一个 http(s) / `file://` 链接会被当作项目仓库地址；
* 支持 `file:///path/to/repo`，用于离线或本地开发；
* `http://` 默认被拒绝（见 [安全限制](#7-安全限制)）。

---

## 2. 项目仓库：`Reimilia_Setup/Build` 与 `Binary`

```md
[Reimilia_Build]

BUILD_LANG="rust"
BUILD_HTTP="https://github.com/Reimilia617/RTDO-Project.git"
REPO_NAME="RTDO-Project"
REQUIRES_ROOT="true"

bash:
cd "$REIMILIA_WORKDIR"
reimilia_elevate ./rtdo.sh --install
/usr/local/bin/rtdo --version
```

结构固定为三段：

1. **段标记** `[Reimilia_Build]` / `[Reimilia_Binary]`，独占一行；
2. **变量声明** `KEY="value"`，一个一行，会作为环境变量注入下面的 bash；
3. **`bash:`** 之后的所有行原样收集成**一段脚本**。

### 变量声明

* 写法是 `KEY="value"`，单双引号都可以，裸值也接受（`KEY=value`）；
* 只有 `bash:` 之前的部分会被当作变量声明；
* 段标记之前的正文、空行、`#` 注释都会被忽略；
* markdown 代码围栏 ` ``` ` 会被忽略，所以你可以把内容放进代码块里写。

变量名建议全大写；`REQUIRES_ROOT` 是 Reimilia 会特殊处理的保留变量。

### `bash:` 块

这一段就是安装脚本本体，规则只有两条：

1. **整段执行，不是逐行执行**。Reimilia 把 `bash:` 之后的非空行拼成一个文件，
   用 `bash -e <文件>` 跑。因此 `cd`、变量赋值、`if`、`for`、heredoc 全都正常工作。
2. `bash -e`：任何一条命令非零退出就中止，并在日志里打印出错行号。
   想忽略某条命令的失败，自己写 `|| true` 或放进 `if` 判断。

> 早期实现是「一行一个 `subprocess.run`」，那样的 `cd` 不会影响下一行，
> 官方示例里的 `cd xxx` + `curl xxx` 其实是坏的。现在已修正。

### 多段

一个文件里可以写多个 `[Reimilia_XXX]` 段，Reimilia 取第一段。
多个 section 的变量会合并，命令只取第一段。

---

## 3. Reimilia 注入的上下文变量

脚本里可以直接用这些变量，它们由 Reimilia 保证存在：

| 变量 | 含义 |
|---|---|
| `REIMILIA` | 固定为 `1`，用来判断"我正跑在 Reimilia 里" |
| `REIMILIA_PROJECT` | 项目名（`repo/` 里 md 的文件名） |
| `REIMILIA_REPO` | 项目仓库地址 |
| `REIMILIA_WORKDIR` | **项目仓库已被克隆到的目录** —— 就地编译用这个 |
| `REIMILIA_KIND` | 当前安装方式：`Build` 或 `Binary` |
| `REIMILIA_ELEVATE` | 探测到的提权工具（`sudo` / `sudo-force` / `su` / 空串） |
| `REIMILIA_STATE_DIR` | Reimilia 状态目录（默认 `~/.reimilia`） |

注意：Reimilia **已经替你克隆了项目仓库**，所以正常情况下不需要再 `git clone`。
`BUILD_HTTP`、`REPO_NAME` 这类变量是给人和外部工具看的元信息，
真正的构建请基于 `$REIMILIA_WORKDIR`。

变量注入顺序是「md 声明 → Reimilia 内置」，所以 md 里写了 `REIMILIA_WORKDIR="x"` 也不会生效。

---

## 4. `reimilia_elevate` 帮助函数

Reimilia 会在脚本前面注入一小段 prelude，提供提权函数：

```bash
reimilia_elevate <命令> [参数...]     # 以 root 执行命令
```

行为：

* 当前已经是 root → 直接执行；
* 否则用探测到的提权工具执行，并**透传构建工具需要的环境**
  （`HOME`、`PATH`、`CARGO_HOME`、`RUSTUP_HOME`、`GOPATH`、`GOCACHE`、`GOMODCACHE`），
  这样 rustup / go 装在用户家目录时，提权后依然找得到工具链；
* 一个提权工具都没有 → 打印明确错误并返回 127。

提权工具探测顺序（`detect_elevator()`）：

1. 已经是 root → 不需要提权；
2. `sudo -n true` 成功 → `sudo`；
3. `/usr/bin/sudo.real` 存在（说明 sudo 已被别的工具接管，例如 rtdo）→ `sudo-force`；
4. `sudo` → `sudo-force` → `su` 依次兜底。

可以用环境变量 `REIMILIA_ELEVATE` 强制指定。

### `REQUIRES_ROOT="true"`

声明这个变量后，如果当前不是 root 且探测不到任何提权工具，
Reimilia 会在执行脚本**之前**就报错，不会跑到一半才失败。

---

## 5. 安装方式的选择与回退

* 默认顺序由配置 `INSTALL_ORDER` 决定，当前默认是 `Build,Binary`
  （见 `reimilia --show-config`，或改 `~/.reimilia/config`）；
* `reimilia --cli <项目> --kind build|binary` 可以强制只用一种；
* Reimilia 会按顺序尝试，某个方式失败就自动试下一个，并把失败原因写进日志；
* 全部失败才整体失败。

`Reimilia_Setup/` 不存在，或者里面没有带 `bash:` 块的文件时，
Reimilia 会明确报「该项目未接入 Reimilia」，而不是假装部署成功。

---

## 6. 日志与清理

* `bash:` 脚本的 stdout / stderr 会逐行实时回传（CLI 直接打印，WebUI 走 SSE）；
* 项目克隆到 `~/.reimilia/work/<项目名>`，部署结束后删除；
  想留着排查就设 `KEEP_WORKDIR="true"`；
* 部署器仓库缓存到 `~/.reimilia/deployer`。

---

## 7. 安全限制

* **强制 HTTPS**：`repo/*.md` 里的项目地址只接受 `https://`、`ssh`、
  `git@`、`file://`（本地）和显式放行的 `http://`；
* 检测到 `GIT_SSL_NO_VERIFY` 会直接拒绝运行，除非配置 `ALLOW_INSECURE="true"`；
* **部署目标由服务端解析**：WebUI 的 `/api/deploy` 只接受项目名，
  不接受请求方传来的 URL —— 否则任何网页都能让本机去 clone 并执行任意仓库的安装脚本；
* WebUI 另加 `Origin` 校验与 `Content-Type: application/json` 强制要求，
  挡住跨站表单提交；
* 安装脚本本身以**你的身份**执行（需要 root 的步骤由你显式提权），
  所以部署前请确认项目仓库可信。

### 尚未实现：GPG 签名校验

[主 README](../README.md#关于签名未实现) 里描述的 `.sig` 签名校验机制**还没有实现**：

* 目前不会读取 `keys/`，也不会因为缺少 `.sig` 而拒绝部署；
* 项目仓库的 `Reimilia_Setup/` 暂时不需要提供 `.sig`；
* 等实现之后，这里会补上公钥缓存、`Rule.txt` 关闸开关与验证流程的说明。

在那之前，请把「只部署自己信任的仓库」当作唯一的安全边界。

---

## 8. 完整示例

部署器仓库 `repo/demo.md`：

```md
[Reimilia_Repo]
https://github.com/you/demo.git
```

项目仓库 `Reimilia_Setup/Build`：

```md
[Reimilia_Build]

BUILD_LANG="rust"
REQUIRES_ROOT="true"

bash:
cd "$REIMILIA_WORKDIR"
echo "项目 $REIMILIA_PROJECT 正在以 $REIMILIA_KIND 方式安装"

cargo build --release

# 只有这一步需要 root
reimilia_elevate install -D -m 0755 target/release/demo /usr/local/bin/demo

/usr/local/bin/demo --version
```

项目仓库 `Reimilia_Setup/Binary`：

```md
[Reimilia_Binary]

ASSET_BASE="https://github.com/you/demo/releases/latest/download"
REQUIRES_ROOT="true"

bash:
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

curl -fsSL "$ASSET_BASE/demo-$(uname -m)-linux" -o "$tmp/demo"
chmod 0755 "$tmp/demo"
reimilia_elevate install -D -m 0755 "$tmp/demo" /usr/local/bin/demo
/usr/local/bin/demo --version
```
