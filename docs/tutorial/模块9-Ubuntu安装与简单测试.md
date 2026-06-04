# 模块9：密码破解/取证 / 隐写 / CTF（Ubuntu 安装与简单测试）

本文覆盖模块 9 的以下工具：
`hashcat`、`john`、`hydra`、`hash-identifier`、`foremost`、`exiftool`、`steghide`、`stegsolve`、`fcrackzip`、`pdfcrack`、`cyberchef`。

## 使用前准备

先更新包管理器并安装通用依赖，确保工具安装/运行环境正常：
```bash
sudo apt-get update
sudo apt-get install -y curl wget git build-essential
# 解压经典密码字典（多数破解工具需用到）
sudo gunzip /usr/share/wordlists/rockyou.txt.gz 2>/dev/null || true
```

## 模块9涉及工具

| Tool | 做什么的 | `tools/*.yaml` 支持情况 |
|------|----------|-------------------------|
| hashcat | 高性能多算法密码哈希破解（支持CPU/GPU加速） | 已接入，`enabled: true` |
| john | John the Ripper，多类型哈希破解工具 | 已接入，`enabled: true` |
| hydra | 多协议在线密码爆破工具 | 已接入，`enabled: true` |
| hash-identifier | 哈希值类型快速识别 | 已接入，`enabled: true` |
| foremost | 基于文件签名的取证/数据恢复工具 | 已接入，`enabled: true` |
| exiftool | 文件元数据提取与分析（CTF隐写常用） | 已接入，`enabled: true` |
| steghide | 图片/音频隐写（嵌入/提取隐藏文件） | 已接入，`enabled: true` |
| stegsolve | 隐写分析工具（CTF经典） | 已淘汰不可用，无配置 |
| fcrackzip | ZIP压缩包密码破解 | 已接入，`enabled: true` |
| pdfcrack | PDF文档密码破解 | 已接入，`enabled: true` |
| cyberchef | 多功能CTF编码/解码/加密解密工具（网页/本地版） | 已接入，`enabled: true` |

## 1) hashcat

用途：高性能密码哈希破解工具，支持MD5、SHA系列、NTLM、Linux系统哈希等几乎所有常见算法，支持CPU/GPU加速，是密码破解核心工具。

安装：
```bash
sudo apt update
sudo apt install hashcat -y
```
# 下载字典
#创建大模型需要的字典目录（必须建）
sudo mkdir -p /usr/share/wordlists

#直接下载最常用的 rockyou 字典到指定路径
sudo wget https://github.com/danielmiessler/SecLists/raw/master/Passwords/Leaked-Databases/rockyou.txt -O /usr/share/wordlists/rockyou.txt

#验证文件是否存在（执行后能看到文件就是成功）
ls /usr/share/wordlists/
简单测试：
```bash
hashcat --version
hashcat -h
# 步骤1：生成测试MD5哈希（echo -n "123456" | md5sum 得到 e10adc3949ba59abbe56e057f20f883e）
# 步骤2：用字典破解该哈希
hashcat -m 0 e10adc3949ba59abbe56e057f20f883e /usr/share/wordlists/rockyou.txt --force
```

框架支持评价：高。参数封装完整，主流哈希类型全覆盖，GPU加速需额外配置驱动但不影响基础使用。

## 2) john

用途：John the Ripper（简称为JR），多场景哈希破解工具，支持Linux/Windows系统哈希、应用层哈希（如MySQL、PostgreSQL），内置字典/暴力/掩码等破解模式。

安装：
```bash
sudo apt update
sudo apt install john -y
```

简单测试：
```bash
john --version
john --help
# 自带测试文件，直接破解
john /usr/share/john/password.lst

# 步骤1：创建包含测试哈希的文件
echo "testuser:e10adc3949ba59abbe56e057f20f883e" > test_hashes.txt
# 步骤2：破解MD5格式哈希
john --format=raw-md5 test_hashes.txt --wordlist=/usr/share/wordlists/rockyou.txt
```

框架支持评价：高。经典破解工具，封装完善，适配CTF/取证多数场景。

## 3) hydra

用途：在线密码爆破工具，支持SSH、FTP、HTTP(S)、MySQL、RDP、SMB等数十种协议，适合针对网络服务的密码枚举。

安装：
```bash
sudo apt update
sudo apt install hydra -y
```

简单测试：
```bash
hydra --version
hydra -h
# 查看支持的破解协议（FTP/SSH/SMB/MySQL 等）
hydra -L
```

框架支持评价：高。协议覆盖全面，参数封装清晰，CTF/渗透测试高频使用。

## 4) hash-identifier

用途：快速识别哈希值对应的算法类型，解决“拿到哈希但不知道算法”的问题，辅助后续破解。

安装：
```bash
# 1. 更新源 
sudo apt update
# 安装换行符转换工具（必备）
sudo apt install dos2unix -y
# 2. 克隆官方源码
git clone https://github.com/blackploit/hash-identifier.git

# 3. 进入工具目录
cd hash-identifier
# 转换文件为Linux格式（删除\r错误字符）
dos2unix hash-id.py
# 4. 启动工具（核心命令）
python3 hash-id.py

sudo cp hash-id.py /usr/local/bin/hash-identifier
sudo chmod +x /usr/local/bin/hash-identifier

#全局运行
echo "alias hash-identifier='python3 ~/桌面/hash-identifier/hash-id.py'" >> ~/.bashrc && source ~/.bashrc

# 5. 终端输入
hash-identifier
```

简单测试：
```bash
# 交互式运行，输入测试哈希 e10adc3949ba59abbe56e057f20f883e 即可识别类型
hash-identifier
```

框架支持评价：高。轻量工具，接入无门槛，哈希类型识别效率高。


## 5) foremost

用途：基于文件头/尾签名的取证工具，可从磁盘镜像、原始数据中恢复图片、文档、压缩包等文件，CTF取证题常用。

安装：
```bash
# 更新软件源列表（确保获取最新版本）
sudo apt update
# 安装foremost包（自动处理所有依赖）
sudo apt install -y foremost
# 检查版本并查看帮助信息
foremost -h
```

简单测试：
```bash
# 步骤1：创建测试文件
echo "test forensic data" > test.txt
# 步骤2：从测试文件中提取数据（示例验证工具可用性）
foremost -i test.txt -o /tmp/foremost_test
```

框架支持评价：高。取证场景适配良好，参数简单易调用。

## 6) exiftool

用途：读取/编辑/分析文件元数据，尤其擅长图片（JPG/PNG）、视频、文档的元数据提取，CTF隐写题中常用来找隐藏的GPS、拍摄信息、备注等。

安装：
```bash
# 更新软件源
sudo apt update

# 安装ExifTool（包名是libimage-exiftool-perl）
sudo apt install -y libimage-exiftool-perl
# 查看版本号
exiftool -ver

# 查看帮助信息
exiftool -h
# 查看单个文件的所有元数据
exiftool photo.jpg

# 只查看指定标签（如拍摄时间、相机型号、GPS位置）
exiftool -DateTimeOriginal -Model -GPSPosition photo.jpg

# 查看所有GPS相关信息
exiftool -gps:all photo.jpg
```

简单测试：
```bash
# 提取图片元数据（替换 test.jpg 为实际图片文件）
exiftool test.jpg
```

框架支持评价：高。元数据提取能力全面，接入无任何问题。

## 7) steghide

用途：隐写术工具，可将文件嵌入到JPG/BMP图片、WAV/AIFF音频中，也可提取隐藏的文件，是CTF隐写题的核心工具之一。

安装：
```bash
#一、官方包管理器安装
# 更新软件源
sudo apt update

# 安装steghide
sudo apt install -y steghide
# 查看版本号
steghide --version

# 查看帮助信息
steghide --help

#二、源码安装
# 1. 安装编译依赖
sudo apt install -y git build-essential libmcrypt-dev libmhash-dev

# 2. 克隆社区维护的最新源码
git clone https://github.com/StegHigh/steghide.git
cd steghide

# 3. 编译安装
./configure
make
sudo make install

# 4. 验证版本
steghide --version
```

简单测试：
```bash
# 步骤1：准备测试文件
echo "CTF{hidden_secret}" > secret.txt
# 步骤2：将secret.txt嵌入到test.jpg，设置密码123456
steghide embed -cf test.jpg -ef secret.txt -p 123456
# 步骤3：从图片中提取隐藏文件
steghide extract -sf test.jpg -p 123456 -xf extracted_secret.txt
```

框架支持评价：高。隐写嵌入/提取流程封装完整，CTF场景适配性强。

## 8) stegsolve

用途：曾是CTF隐写分析的经典工具，支持图片通道分析、位平面提取、数据篡改检测等功能。
### 状态说明：已淘汰不可用
- 淘汰原因：该工具基于Java开发且长期无维护，Ubuntu 20.04及以上版本存在严重的依赖兼容问题（如Java版本不匹配、SWT库缺失），即使手动编译源码也无法正常启动；且当前CTF场景中已被zsteg、binwalk、exiftool增强版等现代工具完全替代，无实际使用价值。
- 安装与测试：无有效安装方式，新版系统下无可用的运行命令，因此无对应的安装/测试步骤。
- 框架支持评价：无。无对应的YAML配置，框架未接入也无接入计划。

## 9) fcrackzip

用途：专用于ZIP压缩包的密码破解工具，支持字典攻击、暴力攻击，是CTF中破解加密ZIP包的首选工具。

安装：
```bash
#一、官方包管理器安装（推荐，10 秒完成）
# 更新软件源
sudo apt update

# 安装fcrackzip
sudo apt install -y fcrackzip

#二、源码编译
# 1. 安装编译依赖
sudo apt install -y build-essential

# 2. 下载官方源码
wget http://www.goof.com/pcg/marc/data/fcrackzip-1.0.tar.gz

# 3. 解压并编译
tar xzf fcrackzip-1.0.tar.gz
cd fcrackzip-1.0
./configure
make

# 4. 安装到系统全局
sudo make install
```

简单测试：
```bash
# 步骤1：创建加密ZIP包（示例：zip --password 123456 test.zip test.txt）
# 步骤2：破解ZIP包密码
fcrackzip -u -D -p /usr/share/wordlists/rockyou.txt test.zip
```
fcrackzip 也已经过时，基本不要在现代系统上使用
框架支持评价：高。专用于ZIP破解，参数简洁，CTF场景适配性极佳。

## 10) pdfcrack

用途：PDF文档密码破解工具，支持用户密码（打开PDF的密码）、所有者密码（编辑权限密码）的破解，适配CTF加密PDF场景。

安装：
```bash
#一、官方包管理器安装（推荐，10 秒完成）
# 更新软件源
sudo apt update

# 安装pdfcrack
sudo apt install -y pdfcrack

#二、源码编译
# 1. 安装编译依赖
sudo apt install -y build-essential

# 2. 下载官方最新源码（2025年9月最新版0.21）
wget https://sourceforge.net/projects/pdfcrack/files/pdfcrack/pdfcrack-0.21/pdfcrack-0.21.tar.gz

# 3. 解压并编译
tar xzf pdfcrack-0.21.tar.gz
cd pdfcrack-0.21
make

# 4. 安装到系统全局
sudo make install
```

简单测试：
```bash
# 步骤1：创建加密PDF（示例：用LibreOffice设置密码123456保存为test.pdf）
# 步骤2：破解PDF密码
pdfcrack -w /usr/share/wordlists/rockyou.txt test.pdf
```

pdfcrack 没有完全过时，但已经是 "半淘汰" 状态。它在特定场景下仍能使用，但存在严重的功能和性能局限性，不建议作为主力 PDF 破解工具。
框架支持评价：高。PDF破解场景专用，接入和调用均无问题。

## 11) cyberchef

用途：多功能CTF神器，支持编码（Base64/URL/十六进制等）、解码、加密（AES/DES）、哈希、隐写分析、数据转换、正则匹配等，核心为网页版，也可本地部署。

安装：
```bash
# 安装CyberChef Snap包
sudo snap install cyberchef
cyberchef

#二、源码安装
# 安装Node.js 20.x（官方推荐版本）
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
# 克隆GitHub仓库
git clone https://github.com/gchq/CyberChef.git
cd CyberChef

# 安装依赖
npm install

# 编译生产版本
npm run build
# 使用Python HTTP服务器运行
cd build
python3 -m http.server 8080
```

简单测试：
```bash
# 无命令行测试，打开CyberChef网页后：
# 1. 输入文本 "test123"，添加「To Base64」操作，执行查看编码结果；
# 2. 输入Base64字符串 "dGVzdDEyMw=="，添加「From Base64」操作，执行还原原始文本。
```

框架支持评价：高。框架通过封装网页API或调用本地部署实例接入，`enabled: true`，是CTF场景通用性最强的工具。

## 在框架里验证“是否支持”的最小步骤

1. 确认工具命令存在（stegsolve除外）：执行 `tool --help` 或 `tool --version`，能返回版本/帮助信息即代表命令可用；
2. 确认对应 YAML 存在且 `enabled: true`（stegsolve无YAML配置）；
3. 在框架内对该工具发起一次最小参数调用（如hashcat识别哈希类型、exiftool读取空文件元数据、fcrackzip测试空ZIP包）；
4. 观察是否返回正常输出或可解释错误（如“权限不足”“目标无密码”“文件不存在”，而非“命令未找到”“依赖缺失”）。

## 备注

- `hashcat` 的GPU加速需额外安装NVIDIA/AMD驱动及CUDA/OpenCL环境，纯CPU模式仅影响速度，不影响基础功能；
- `steghide` 依赖文件完整性，损坏的图片/音频无法完成嵌入/提取操作；
- `stegsolve` 已完全淘汰。
- `cyberchef` 本地部署需Node.js 16+版本，低版本Node.js会导致编译失败；
- 所有密码破解/爆破测试必须使用自建的测试文件/服务，严禁对未授权的第三方目标进行测试。