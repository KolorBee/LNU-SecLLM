# 模块1：网络扫描与资产发现（Ubuntu 安装与简单测试）

本文覆盖模块 1 的以下工具：
`nmap`、`masscan`、`rustscan`、`arp-scan`、`nbtscan`、`autorecon`、`lightx`、`amass`、`subfinder`、`dnsenum`、`fierce`。

## 使用前准备

```bash
sudo apt-get update
sudo apt-get install -y curl wget git
```

建议先把 Go 安装目录加入 PATH（如未配置）：

```bash
export PATH="$PATH:$(go env GOPATH)/bin"
```

## 模块1涉及工具

| Tool | 做什么的 | `tools/*.yaml` 支持情况 |
|------|----------|-------------------------|
| nmap | 端口/服务探测，NSE 脚本扫描 | 已接入，`enabled: true` |
| masscan | 高速端口扫描 | 已接入，`enabled: true` |
| rustscan | 快速端口发现，可选联动 nmap | 已接入，`enabled: true` |
| arp-scan | 局域网 ARP 主机发现 | 已接入，`enabled: true` |
| nbtscan | NetBIOS 信息探测（偏 Windows 资产） | 已接入，`enabled: true` |
| autorecon | 自动化枚举与侦察流程 | 已接入，`enabled: true` |
| lightx | 轻量资产发现扫描 | 已有配置，但默认 `enabled: false` |
| amass | 子域名枚举与资产映射 | 已接入，`enabled: true` |
| subfinder | 被动子域名发现 | 已接入，`enabled: true` |
| dnsenum | DNS 枚举与子域发现 | 已接入，`enabled: true` |
| fierce | DNS 侦察与子域探测 | 已接入，`enabled: true` |

## 1) nmap

用途：网络主机与端口服务探测，支持版本识别与脚本扫描。

安装：
```bash
sudo apt-get install -y nmap
```

简单测试：
```bash
nmap -sT -sV -sC 127.0.0.1
```

框架支持评价：高。参数封装完整，常见扫描场景可直接用。

## 2) masscan

用途：高速端口扫描，适合大范围快速探测。

安装：
```bash
sudo apt-get install -y masscan
```

简单测试：
```bash
sudo masscan 127.0.0.1 -p1-1000 --rate 1000
```

框架支持评价：高。已接入，适合先快扫再交给其他工具深扫。

## 3) rustscan

用途：快速发现开放端口，可选联动 nmap 做后续识别。

安装：
```bash
cargo install rustscan
```

简单测试：
```bash
rustscan -a 127.0.0.1 -r 1-1000 --scripts none
```

框架支持评价：高。参数设计清晰，适合快速端口发现场景。

## 4) arp-scan

用途：在本地二层网络内做 ARP 资产发现。

安装：
```bash
sudo apt-get install -y arp-scan
```

简单测试：
```bash
sudo arp-scan -l
```

框架支持评价：高。局域网发现可直接使用，受网卡与权限影响较大。

## 5) nbtscan

用途：扫描 NetBIOS 名称服务，辅助发现 Windows 主机信息。

安装：
```bash
sudo apt-get install -y nbtscan
```

简单测试：
```bash
nbtscan 127.0.0.1
```

框架支持评价：中高。封装已就绪，但效果依赖目标是否开放相关服务。

## 6) autorecon

用途：自动化侦察流程，结合多工具进行枚举与结果归档。

安装：
```bash
pip install autorecon
```

简单测试：
```bash
autorecon 127.0.0.1 -o /tmp/autorecon
```

框架支持评价：中高。已接入，但真实能力依赖其外部依赖链是否完整。

## 7) lightx

用途：轻量化资产探测与扫描。

安装：
```bash
pip install lightx
```

简单测试：
```bash
lightx -t 127.0.0.1
```

框架支持评价：中。配置已存在，但默认 `enabled: false`，需要先在 [tools/lightx.yaml](/home/zhaoshuai/workspace_cyber/LNU-SecLLM/tools/lightx.yaml:1) 改为 `true`。

## 8) amass

用途：深度子域名枚举、资产关联分析。

安装：
```bash
sudo snap install amass
```

简单测试：
```bash
amass enum -d example.com
```

框架支持评价：高。已接入，适合子域发现和资产扩展。

## 9) subfinder

用途：被动子域名收集，速度快，适合侦察前置阶段。

安装：
```bash
go install github.com/projectdiscovery/subfinder/v2/cmd/subfinder@latest
```

简单测试：
```bash
subfinder -d example.com -silent
```

框架支持评价：高。已接入，参数简单，稳定性较好。

## 10) dnsenum

用途：DNS 枚举、子域与记录探测。

安装：
```bash
sudo apt-get install -y dnsenum
```

简单测试：
```bash
dnsenum example.com
```

框架支持评价：高。已接入，适合 DNS 维度补充。

## 11) fierce

用途：DNS 侦察与子域名探测。

安装：
```bash
sudo apt-get install -y fierce
```

简单测试：
```bash
fierce --domain example.com
```

框架支持评价：高。已接入，可与 `dnsenum`、`amass` 互补使用。

## 在框架里验证“是否支持”的最小步骤

1. 确认工具命令存在：`tool --help` 或 `tool --version`。
2. 确认对应 YAML 存在且 `enabled: true`。
3. 在框架内对该工具发起一次最小参数调用。
4. 观察是否返回正常输出或可解释错误（例如权限不足、目标无响应）。

## 备注

- `masscan`、`arp-scan` 等通常需要 root 权限。
- `amass`、`subfinder`、`dnsenum`、`fierce` 的结果受网络与 DNS 环境影响。
- 若只做本机快速验收，优先使用 `127.0.0.1` 或内网测试靶机，避免对外部目标进行未授权扫描。
