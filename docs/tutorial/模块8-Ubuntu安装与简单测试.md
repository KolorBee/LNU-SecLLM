# 模块8：后渗透 / 内网横向 / 枚举（Ubuntu 安装与简单测试）

本文覆盖模块 8 的以下工具：
`linpeas`、`bloodhound`、`impacket`、`responder`、`netexec`、`smbmap`、`rpcclient`、`enum4linux`、`enum4linux-ng`。

## 使用前准备
补充内网渗透常用依赖（如未安装）：
```bash
sudo apt-get update
# 基础依赖
sudo apt-get install -y python3 python3-pip python3-dev git libssl-dev libffi-dev nmap smbclient
# 升级pip确保工具安装兼容
pip3 install --upgrade pip
# 若需Go依赖（如部分工具），复用模块1的Go PATH配置
export PATH="$PATH:$(go env GOPATH)/bin"
```

## 模块8涉及工具
| Tool | 做什么的 | `tools/*.yaml` 支持情况 |
|------|----------|-------------------------|
| linpeas | Linux本地提权枚举，收集系统漏洞、权限、配置等提权线索 | 已接入，`enabled: true` |
| bloodhound | 内网域信息收集/可视化，分析域内权限、横向移动路径 | 已接入，`enabled: true` |
| impacket | 多协议交互库，支持SMB/RPC/AD等，用于凭证利用、横向移动 | 已接入，`enabled: true` |
| responder | LLMNR/NBT-NS/mDNS欺骗，捕获内网凭证哈希 | 已接入，`enabled: true` |
| netexec | 内网批量渗透（原crackmapexec），测试凭证、枚举服务、执行命令 | 已接入，`enabled: true` |
| smbmap | SMB共享枚举，列出共享目录、权限、文件等信息 | 已接入，`enabled: true` |
| rpcclient | RPC协议交互，枚举Windows/Samba用户、组、共享等 | 已接入，`enabled: true` |
| enum4linux | 枚举Windows/Samba主机信息（用户、共享、策略等） | 已接入，`enabled: true` |
| enum4linux-ng | enum4linux升级版，更全面的SMB/NetBIOS枚举，支持多输出格式 | 已接入，`enabled: true` |

## 1) linpeas
用途：Linux本地提权自动化枚举，一键收集系统内核、权限配置、SUID/SGID文件、计划任务、漏洞线索等。

安装：
```bash
# 1. 下载官方最新版脚本（推荐用curl，也可用wget）
curl -L https://github.com/peass-ng/PEASS-ng/releases/latest/download/linpeas.sh -o linpeas.sh

# 2. 赋予执行权限（必须步骤）
chmod +x linpeas.sh

# 3. 移动到系统全局路径（任意命令行直接调用）
sudo mv linpeas.sh /usr/local/bin/linpeas
```

简单测试：
```bash
linpeas --version
```

框架支持评价：高。脚本封装简洁，枚举结果结构化，提权线索易提取。

## 2) bloodhound
用途：内网域环境信息收集与可视化，分析域用户、组、计算机、权限关系，定位横向移动/权限提升路径。

安装：
```bash
# 安装bloodhound.py（命令行版，适配自动化）
pipx install bloodhound
# 如需桌面版（可视化）
sudo snap install bloodhound
```

简单测试：
```bash
# 写入别名配置（永久生效）
echo "alias bloodhound='bloodhound-python'" >> ~/.bashrc
# 创建软链接
sudo ln -s ~/.local/bin/bloodhound-python /usr/local/bin/bloodhound

bloodhound -h
bloodhound --test
# 命令行版收集本地域信息（需域环境/测试靶机）
bloodhound -d testdomain.com -u testuser -p TestPass123! -dc dc01.testdomain.com -c All
```

框架支持评价：中高。已接入，命令行版适配自动化，桌面版需手动可视化分析，效果依赖域环境权限。

## 3) impacket
用途：Python网络协议库，实现SMB/RPC/NTLM/Kerberos等协议，衍生出smbclient、psexec、wmiexec等工具，用于内网凭证利用、横向移动。

安装：
```bash
# 系统级安装（需要sudo）
sudo pip3 install impacket

# 用户级安装（无sudo权限）
pip3 install --user impacket
# 若用户级安装后找不到命令，执行：
echo "export PATH=$HOME/.local/bin:$PATH" >> ~/.bashrc
source ~/.bashrc
```
# pipx安装 
sudo apt install -y pipx
pipx ensurepath
source ~/.bashrc

# 安装Impacket
pipx install impacket

pipx list  # 查看安装状态
impacket-psexec -h


简单测试：
```bash
# 用impacket的smbclient测试SMB连接（替换目标/凭证）
python3 -m impacket.smbclient //192.168.1.100/Shared -U testuser%TestPass123!
```

框架支持评价：高。核心协议库封装完整，衍生工具覆盖内网大部分横向场景。

## 4) responder
用途：内网LLMNR/NBT-NS/mDNS欺骗，响应客户端名称解析请求，捕获NTLMv1/NTLMv2哈希，用于凭证破解/中继。

安装：
```bash
# 克隆官方仓库
# 更新软件源
sudo apt update

# 直接安装（系统官方包，稳定可用）
sudo apt install responder -y
# 测试安装（验证是否成功）
responder --version
responder -h
```

简单测试：
```bash
# 监听内网网卡（替换eth0为实际网卡）
# 小写 -i + 你的网卡名（eth0/ens33）
sudo responder -i eth0
# 基础监听（推荐）
sudo responder -i eth0

# 开启详细日志 + Web代理模块
sudo responder -i eth0 -v -w
```

框架支持评价：高。参数封装就绪，监听/欺骗逻辑完整，需内网环境+网卡权限。

## 5) netexec
用途：内网批量渗透工具（原CrackMapExec），支持SMB/SSH/RDP等协议，批量测试凭证、枚举共享、执行命令、提权检测等。

安装：
```bash
# 安装
sudo apt update && sudo apt install -y curl gnupg2
# 添加官方 GPG 密钥
curl -fsSL https://apt.netexec.app/KEY.gpg | gpg --dearmor | sudo tee /usr/share/keyrings/netexec-archive-keyring.gpg >/dev/null
# 添加官方源
echo "deb [signed-by=/usr/share/keyrings/netexec-archive-keyring.gpg] https://apt.netexec.app/ ./" | sudo tee /etc/apt/sources.list.d/netexec.list
# 安装
sudo apt update && sudo apt install netexec -y



```

简单测试：
```bash
# 扫描本地SMB
nxc smb 127.0.0.1
```

框架支持评价：高。参数设计覆盖内网常见场景，批量处理能力强，适配自动化流程。

## 6) smbmap
用途：轻量SMB共享枚举工具，快速列出目标SMB共享目录、权限、文件列表，支持匿名访问/凭证验证。

安装：
# pipx直接安装
pipx install smbmap
pipx ensurepath
source ~/.bashrc
smbmap --help
```
# apt直接安装
sudo apt update
sudo apt install smbmap -y


简单测试：
```bash
smbmap -H 127.0.0.1
```

框架支持评价：高。轻量无依赖，枚举结果简洁，适合快速SMB侦察。

## 7) rpcclient
用途：RPC协议客户端，交互Windows/Samba的RPC服务，枚举用户、组、共享、域信息、密码策略等。

安装：
```bash
# 更新软件源
sudo apt update

# 安装 samba 工具包（内置 rpcclient）
sudo apt install samba-common-bin -y
```

简单测试：
```bash
rpcclient -h
rpcclient -U "" -N 目标IP -c "enumdomusers"
```

框架支持评价：中高。原生命令封装，枚举指令丰富，但需手动拼接命令，自动化需适配参数。

## 8) enum4linux
用途：Linux下一站式Windows/Samba枚举工具，整合smbclient、rpcclient等，批量枚举用户、组、共享、密码策略、SID等。
Ubuntu 官方软件源没有 enum4linux，所以 apt 和 pipx 都装不了

安装：
```bash
# 1. snap直接安装
sudo snap install enum4linux
```
# 2. 源码安装
安装依赖
sudo apt update && sudo apt install git perl libnet-smb-crypt-perl -y

克隆官方源码
git clone https://github.com/CiscoCXSecurity/enum4linux.git

进入文件夹
cd enum4linux

赋予执行权限
chmod +x enum4linux.pl

创建全局软链接（任意终端都能输 enum4linux 调用）
sudo ln -s $(pwd)/enum4linux.pl /usr/local/bin/enum4linux


简单测试：
```bash
enum4linux -h
# 全量枚举目标信息（替换目标）
enum4linux -a 192.168.1.100
```

框架支持评价：高。一键式枚举，结果全面，适合内网快速侦察Windows/Samba主机。

## 9) enum4linux-ng
用途：enum4linux升级版，支持更多枚举项（如Kerberos、LDAP）、多输出格式（JSON/CSV），适配现代内网环境。

安装：
```bash
# 安装依赖
sudo apt update && sudo apt install git python3-impacket python3-yaml python3-colorama python3-prompt-toolkit -y
# 下载工具源码（放到桌面）
cd ~/桌面
git clone https://github.com/cddmp/enum4linux-ng.git
# 创建永久命令（任意终端直接用 enum4linux-ng）

echo "alias enum4linux-ng='python3 ~/桌面/enum4linux-ng/enum4linux-ng.py'" >> ~/.bashrc
source ~/.bashrc
```

简单测试：
```bash
enum4linux-ng -h
# 匿名全自动枚举Windows靶机
enum4linux-ng -A 目标IP
```

框架支持评价：高。功能更全面，输出结构化，适配自动化解析，已接入框架。

## 在框架里验证“是否支持”的最小步骤
1. 确认工具命令可执行：`tool --help` / `python3 tool.py --help`（脚本类）。
2. 确认对应 YAML 存在且 `enabled: true`。
3. 在框架内对该工具发起最小参数调用（如本地/内网测试靶机）。
4. 观察是否返回正常输出或可解释错误（如权限不足、目标无SMB服务、域环境缺失）。

## 备注
- `responder`、`linpeas`（root模式）、`netexec`（SMB枚举）等需root权限。
- `bloodhound`、`impacket`、`enum4linux` 效果依赖内网域/Windows环境，本机测试需搭建Samba/域靶机。
- 所有工具仅可在授权环境测试，禁止对未授权目标执行内网渗透操作。
- `netexec` 部分功能依赖impacket，需确保impacket版本兼容。