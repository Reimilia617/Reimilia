# Reimilia
一个基于.md描述的通用项目部署器

## Reimilia是什么？
Reimilia是一个部署器，她不负责写功能，只负责把写好的项目装到系统里

她的核心逻辑可以这么说：读仓库md>>找到地址>>获取仓库地址下的配置md>>按照md的说明自动下载编译安装

## 她怎么工作？
1. Reimilia配置菜单内可以配置远程仓库地址，默认是作者的仓库(Github@Reimilia617)，若需要fork使用则需要更改远程仓库地址的指向(指向fork后的你的仓库)
2. 扫描远程仓库内的"repo/"文件夹，里面的每个.md文件都代表一个"可部署的项目"
3. 每个在"repo/"文件夹下的.md文件里都写着项目的主仓库地址
4. Reimilia读取到地址，git clone项目到临时目录
5. clone下来后读取安装说明.md
6. 根据安装说明自动执行编译安装
7. 安装完毕，清理临时文件(已配置的远程仓库地址不会丢失)
- 后续可能会考虑加上支持原来的"install.sh"脚本安装，只需要在安装说明.md内写上脚本路径即可

## 为什么是.md，不是.json/.yaml？
.md是给人看的，同时也是给机器看的
- 人看得懂，能直接编辑
- 机器读得懂，能按照格式解析
- 不需要额外依赖，不需要配置工具

## 定位
Reimilia是独立系列

她是工具层，服务于所有项目(同Sakuya)，今后若需要使用我编写的项目则统一需要使用Reimilia部署

## 为什么用Python写？(暂定)
Reimilia的本质就是"调用命令>>读取文件>>下载>>解压"，Python自带的库就可以完成，不需要管理内存，扔到任何一台Linux都能跑

后面做图形界面看看使用GTK还是WebUI，QT一堆依赖不想用。由于和Sakuya为同级别的工具，同时Sakuya需要Reimilia部署，不考虑将Reimilia接入Sakuya

## 关于md文件读取格式
md文件分为部署器仓库和项目仓库

1. 部署器仓库就是Reimilia的仓库，仓库根目录下存在repo文件夹，里面的md文件的文件名就是需要部署的项目名，同时这个名字会显示在Reimilia内，md文件内部是标准http链接指向项目仓库

示例：
```repo
[Reimilia_Repo]
https://github.com/Reimilia617/Reimilia
```
里面的"[Reimilia_Repo]"表示这个md文件就是Reimilia的指向项目仓库格式

2. 项目仓库的根目录需要有一个"Reimilia_Setup"文件夹，里面需要有如下文件
- "Binary"——使用预编译二进制文件安装
- "Build"——使用源码编译方式安装

示例：
```binary
[Reimilia_Binary]

BUILD_LANG="rust"
BINARY_HTTP="https://github.com/Reimilia617/RTDO-Project/releases/rtdo-0.5.0-x86_64-linux"
FILE_NAME="rtdo"

bash:
mkdir ~/.reimilia_cache
cd ~/.reimilia_cache
curl -o "$FILE_NAME" "$BINARY_HTTP"
...
cd ~
rm -rf ~/.reimilia_cache
```
```build
[Reimilia_Build]

BUILD_LANG="rust"
BUILD_HTTP="https://github.com/Reimilia617/RTDO-Project.git"
REPO_NAME="RTDO_Project"

bash:
mkdir ~/.reimilia_cache
cd ~/.reimilia_cache
git clone "$BUILD_HTTP"
cd "$REPO_NAME"
cargo build --release
...
cd ~
rm -rf ~/.reimilia_cache
```

后续会完善md文件格式

注意：
- 若项目需要使用交互式安装，Reimilia暂时不支持，后续考虑加上这个功能，在安装时遇到需要用户选择的地方就弹出窗口提示选择
- "bash:"需要确保冒号是英文的，且往下的每一行为一条bash代码
- 预编译二进制安装需要指向releases中的二进制文件，源码安装需要指向git网址

## 状态
项目仍在设计阶段，README会持续更新