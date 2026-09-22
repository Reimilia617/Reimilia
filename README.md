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
- 后续可能会考虑加上支持原来的"install.sh"脚本安装(兼容模式)，只需要在安装说明.md内写上脚本路径即可

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

## 也许是为了安全？(实验性)
为了保证md文件在下载时，下载下来的md文件还是原来的那个md文件，而不是被攻击者篡改过的包含恶意代码的md文件，我做出了以下决策

以下的签名均使用GPG签名
1.  部署器仓库根目录的repo文件夹内必须有一个和md文件名(带后缀)匹配的sig签名文件，我会使用自己的私钥进行签名，若没有则拒绝访问
- 若后续需要fork我的仓库使用可选择不使用验证机制，否则请手动创建GPG私钥进行签名并将公钥硬编码至gpg.cpp内，如果你有更好的方法欢迎提issus或我合并你的代码进主线
- Reimilia使用~~硬编码进去的公钥验证~~(详情见该内容第三部分)，不通过则拒绝访问md文件内的项目指向网址

2. 同时被指向的项目仓库下的Reimilia_Setup文件夹内每个md文件都需要一个对应的sig签名文件，若没有则拒绝访问
- 依旧一个私钥签名天下，如果需要部署的项目的sig签名文件验证不通过则拒绝访问

- 为了保证安全，我可能会更换GPG密钥(其实是私钥弄不见了)，所以请及时更新Reimilia版本，也请各位有兴趣对我的项目二次开发的创作者们能勤快地更新或保管自己的私钥，也请记得使用自己的私钥签名和硬编码公钥重新签名(>_<)

3. 如何保证Reimilia内硬编码的公钥是正确的？

- ~~我目前的想法是下载Reimilia时同时分发一个sha256验证文件~~，但是如果我的Github账号被攻击了或者是黑客操控下载到了被修改过的Reimilia和对应的sha256，验证时没有任何问题，但是执行起来就完全是去验证版本，可以直接执行恶意代码，则前面做的所有事情都是无用功

- 以后Reimilia不用硬编码公钥，直接远程读取仓库根目录的keys文件夹内的公钥，强制走HTTPS和TLS验证，如果系统连TLS验证都做不到说明系统环境已经不可信了(:P)
 
- Reimilia首次启动时会缓存仓库内的公钥，除非用户手动更新

- 宇宙级免责声明：我目前只负责怎么让Reimilia更快更智能更安全地部署项目，我并没有办法解决怎么信任Reimilia这个软件的问题，这本身就是个信任链危机，如果你并不认可我的软件非要抬杠那你也大可不用，我该说的都说了，也希望这个项目可以长久发展下去吧，早日摆脱手写bash安装(TAT)

4. 关闭验证(不推荐)(-_-ll)

- 如果需要关闭签名验证，只需要点击"关闭验证"，然后还不行，还需要去Reimilia运行目录下找到Rule.txt，将里面的false改成true即可，一旦同意了这个文件，通过Reimilia下载的文件内含恶意代码或挖矿病毒导致电脑成为矿机，则Reimilia原作者概不负责！！！

- 注意，Rule.txt中~~"flase"~~"false"(啊啊啊，怎么还拼写错误了QAQ)代表未确认取消验证，"true"代表同意取消验证，不要弄错了！！！

5. 我打算加个检测
- 就是如果运行的是我的官方版Reimilia，则运行时会提示"您现在运行的是由"Github@Reimilia617"编译的Reimilia"

- 如果别人改了我的源代码，即使只动了一个空格打开Reimilia时都会提示"注意！您现在运行的是由"Github@匿名"编译的Reimilia，若在使用过程中出现任何问题导致电脑损坏或数据泄漏，则Reimilia原作者概不负责！"如果二次制作的这个人连自己名字都没写那真的就会像上面那样显示(qwq)

- 只是没想好怎么实现，因为也不能用公钥验证自己，只能向上面那样了，谁编译的就让谁负责(内心OS：早知道不做验证机制了，真出了事还要找我QAQ)

- 算了算了，不实际，这个东西实际写起来太难了

6. 总结：“信任链如果从一开始就从未被信任，那还谈何信任？”

## 状态
项目仍在设计阶段，README会持续更新