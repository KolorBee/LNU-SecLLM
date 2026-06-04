# 模块7：漏洞利用与PWN（Ubuntu 安装与简单测试）

本文覆盖模块 7 的以下工具：
`metasploit`、`msfvenom`、`pwntools`、`ropper`、`ropgadget`、`one-gadget`、`pwninit`。

## 使用前准备

```bash
sudo apt-get update
sudo apt-get install -y curl wget git python3 python3-pip ruby ruby-dev cargo
```

补充 PWN 常用环境依赖：
```bash
sudo apt-get install -y gcc-multilib gdb gdb-multiarch libc6-dbg:i386
```

## 模块7涉及工具

| Tool | 做什么的 | `tools/*.yaml` 支持情况 |
|------|----------|-------------------------|
| metasploit | 一站式漏洞利用框架，集成漏洞库、exploit、payload、后渗透模块等 | 已接入，`enabled: true` |
| msfvenom | Metasploit 载荷生成工具，定制跨平台/多架构shellcode、恶意程序 | 已接入（归属metasploit套件），`enabled: true` |
| pwntools | CTF/PWN 漏洞利用开发库，辅助编写EXP/ROP链/交互脚本 | 已接入，`enabled: true` |
| ropper | ROP链构造工具，分析二进制文件、提取ROP Gadget/检查保护机制 | 已接入，`enabled: true` |
| ropgadget | 自动化查找二进制文件中的ROP/JOP/SROP Gadget | 已接入，`enabled: true` |
| one-gadget | 快速定位libc中可直接执行system的one-gadget指令 | 已接入，`enabled: true` |
| pwninit | 自动化初始化PWN题目环境（补libc、设权限、修二进制） | 已接入，`enabled: true` |

## 1) metasploit

用途：业界主流的漏洞利用框架，集成海量漏洞exp、payload、后渗透模块，支持漏洞验证、利用与横向移动。

安装：
```bash
# 官方脚本安装（适配Ubuntu 20.04+/22.04+）
curl https://raw.githubusercontent.com/rapid7/metasploit-omnibus/master/config/templates/metasploit-framework-wrappers/msfupdate.erb > msfinstall
chmod +x msfinstall
sudo ./msfinstall
```
# 源码安装
sudo apt install -y build-essential libreadline-dev libssl-dev libpq5 libpq-dev libsqlite3-dev libpcap-dev git-core autoconf postgresql zlib1g-dev libxml2-dev libxslt1-dev
sudo apt install -y ruby-full
git clone https://github.com/rapid7/metasploit-framework.git
cd metasploit-framework
bundle install  # 安装Ruby依赖

简单测试：
```bash
# 启动msf控制台（静默模式，跳过banner）
sudo msfdb init  # 配置PostgreSQL数据库
msfconsole -q
# 执行基础命令验证
msf6 > version
msf6 > search cve:2023 type:exploit
msf6 > exit
```

框架支持评价：高。核心功能已封装，常见漏洞利用场景可直接调用，模块更新及时。

## 2) msfvenom

用途：Metasploit 内置的载荷生成工具，支持跨平台、多架构的shellcode/恶意程序生成，可定制编码器、输出格式。

安装：
```bash
# 安装metasploit后自动附带msfvenom

简单测试：
```bash
# 生成Linux x64反向shell payload（本地测试用）
msfvenom -p linux/x64/shell_reverse_tcp LHOST=127.0.0.1 LPORT=4444 -f elf -o /tmp/shell.elf
# 验证生成的文件
file /tmp/shell.elf
```

框架支持评价：高。作为metasploit套件核心组件，参数封装完整，可直接集成到自动化利用流程。

## 3) pwntools

用途：专为CTF/PWN场景设计的Python库，提供二进制交互、ROP链构造、shellcode生成、调试辅助等功能，简化exp编写。

安装：
```bash
# 安装pwntools（Python3）
pip3 install pwntools
# 增强依赖（提升调试/汇编能力）
sudo apt-get install -y python3-capstone python3-keystone
```

简单测试：
```bash
# 编写测试脚本 /tmp/test_pwn.py
cat > /tmp/test_pwn.py << EOF
from pwn import *

# 本地进程交互测试
p = process('/bin/ls')
print("进程输出：", p.recvline().decode())
p.close()

# ROP Gadget查找示例
rop = ROP('/bin/ls')
print("Ret Gadget地址：", rop.find_gadget(['ret']))
EOF

# 运行脚本
python3 /tmp/test_pwn.py
```

框架支持评价：高。API封装友好，已接入框架，适合自动化编写/执行PWN利用脚本。

## 4) ropper

用途：专注于ROP链构造的工具，可分析ELF/Mach-O等二进制文件，提取ROP/JOP Gadget、检查保护机制（PIE/RELRO等）。

安装：
```bash
# 安装pipx
sudo apt update
sudo apt install -y pipx
# 初始化 pipx（配置环境变量）
pipx ensurepath
# 安装ropper
pipx install ropper
# 验证安装
ropper -v
```

简单测试：
```bash
# 分析/bin/ls的保护机制+提取ret gadget
ropper -f /bin/ls --check
ropper -f /bin/ls --search "ret"
```

框架支持评价：高。参数设计简洁，已接入框架，适合ROP链自动化构造场景。

## 5) ropgadget

用途：全量扫描二进制文件中的各类Gadget（ROP/JOP/SROP），支持按指令、寄存器、长度筛选，是ROP开发核心工具。

安装：
```bash
# pipx安装ROPgadget
pipx install ropgadget

# 验证
# 查看版本（最快测试）
ROPgadget --version

# 查看帮助
ROPgadget -h
```

简单测试：
```bash
# 扫描/bin/ls中的ret gadget
ROPgadget --binary /bin/ls --only "ret"
# 筛选x86_64架构的pop rdi; ret gadget
ROPgadget --binary /bin/ls --arch x86_64 --only "pop rdi; ret"
```

框架支持评价：高。已接入框架，Gadget检索速度快，适配多架构场景。

## 6) one-gadget

用途：快速定位libc库中可直接触发system("/bin/sh")的one-gadget指令，无需构造完整ROP链，提升PWN效率。

安装：
```bash
# Ruby gem安装one-gadget
sudo gem install one-gadget

# 查看版本（最快测试）
one_gadget -v
```

简单测试：
```bash
# 查找系统默认libc的one-gadget
one-gadget /lib/x86_64-linux-gnu/libc.so.6
# 查找自定义libc文件的one-gadget（如题目提供的libc）
one-gadget /tmp/libc.so.6
```

框架支持评价：中高。已接入框架，但效果依赖libc版本与环境（如栈对齐），需结合实际调试。

## 7) pwninit

用途：自动化初始化PWN题目环境，自动修补二进制文件（设置setuid、关闭ASLR）、下载匹配的libc/ld、生成初始化脚本。

安装：
```bash
# cargo安装（需Rust工具链）
cargo install pwninit
# 备选二进制安装方式
# wget https://github.com/io12/pwninit/releases/latest/download/pwninit -O /usr/local/bin/pwninit
# chmod +x /usr/local/bin/pwninit
```

简单测试：
```bash
# 初始化测试环境
mkdir /tmp/pwn_test && cd /tmp/pwn_test
cp /bin/ls ./pwn_bin # 模拟PWN题目二进制
pwninit --bin pwn_bin --libc /lib/x86_64-linux-gnu/libc.so.6
# 查看初始化结果
ls -l
```

框架支持评价：中高。已接入框架，自动化程度高，但需目标二进制文件符合常规PWN题目格式。

## 在框架里验证“是否支持”的最小步骤

1. 确认工具命令存在：`tool --help` 或 `tool --version`（如`msfconsole -v`、`one-gadget -v`、`pwninit -h`）。
2. 确认对应 YAML 存在且 `enabled: true`（msfvenom归属metasploit.yaml）。
3. 在框架内对该工具发起一次最小参数调用（如`msfvenom -p linux/x64/shell_tcp -f raw`、`python3 -c "from pwn import *; print(ROP('/bin/ls'))"`）。
4. 观察是否返回正常输出或可解释错误（例如权限不足、libc文件不存在）。

## 备注

- `metasploit` 首次启动需初始化数据库（`msfdb init`），否则部分功能受限；运行需≥2GB内存，低配置机器可能卡顿。
- `pwntools`、`ropper`、`ropgadget` 依赖Python环境，建议用虚拟环境（`venv`）避免依赖冲突。
- `one-gadget` 的结果需实际调试验证（部分one-gadget要求特定寄存器值/栈对齐）。
- `pwninit` 仅适用于CTF/PWN题目场景，生产环境慎用（涉及权限修改、关闭ASLR）。
- 所有工具的本地测试优先使用系统自带二进制（如/bin/ls），禁止对外部目标进行未授权测试。