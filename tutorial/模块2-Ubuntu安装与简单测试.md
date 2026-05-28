# 模块2：Web 应用扫描

本文覆盖模块 2 的以下工具：
`sqlmap`、`nikto`、`dirb`、`gobuster`、`feroxbuster`、`ffuf`、`httpx`。

## 使用前准备

```bash
sudo apt-get update
sudo apt-get install -y curl wget git python3 python3-pip
```

建议准备一个本地 Web 服务用于目录扫描工具的最小验收：

```bash
mkdir -p /tmp/webscan-demo/admin
echo "ok" > /tmp/webscan-demo/index.html
echo "admin" > /tmp/webscan-demo/admin/index.html
cd /tmp/webscan-demo
python3 -m http.server 8000
```

另开一个终端后，本文中的本地测试目标统一使用：

```bash
http://127.0.0.1:8000
```

## 模块2涉及工具

| Tool | 做什么的 | `tools/*.yaml` 支持情况 |
|------|----------|-------------------------|
| sqlmap | 自动化 SQL 注入检测与验证 | 已接入，`enabled: true` |
| nikto | Web 服务器漏洞与配置问题扫描 | 已接入，`enabled: true` |
| dirb | Web 目录和文件枚举 | 已接入，`enabled: true` |
| gobuster | 目录、文件、DNS、虚拟主机枚举 | 已接入，`enabled: true` |
| feroxbuster | 快速递归内容发现 | 已接入，`enabled: true` |
| ffuf | 快速 Web Fuzz，目录、参数、虚拟主机发现 | 已接入，`enabled: true` |
| httpx | HTTP 服务探测、存活检测、标题/状态码/指纹收集 | README/角色中已列出，但当前未发现独立 `tools/httpx.yaml` |

## 1) sqlmap

用途：自动化 SQL 注入检测、漏洞验证与数据库信息枚举。

安装：
```bash
sudo apt-get install -y sqlmap
```

简单测试：
```bash
sqlmap --version
```

对授权靶场进行最小检测时，可使用类似命令：

```bash
sqlmap -u "http://127.0.0.1/vulnerable.php?id=1" --batch --level=1 --risk=1
```

框架支持评价：高。已接入 [tools/sqlmap.yaml](/home/zhaoshuai/workspace_cyber/LNU-SecLLM/tools/sqlmap.yaml:1)，支持 URL、POST 数据、Cookie、测试级别和附加参数。建议默认带 `--batch`，避免自动化执行时等待交互输入。

## 2) nikto

用途：扫描 Web 服务器已知漏洞、危险文件、默认页面和常见配置问题。

安装：
```bash
sudo apt-get install -y nikto
```

简单测试：
```bash
nikto -h http://127.0.0.1:8000
```

框架支持评价：高。已接入 [tools/nikto.yaml](/home/zhaoshuai/workspace_cyber/LNU-SecLLM/tools/nikto.yaml:1)，适合快速做 Web 服务器基线检查。`nikto` 发现问题时可能返回退出码 `1`，当前配置已将其视为允许退出码。

## 3) dirb

用途：使用字典暴力枚举 Web 目录和文件。

安装：
```bash
sudo apt-get install -y dirb
```

简单测试：
```bash
dirb http://127.0.0.1:8000 /usr/share/dirb/wordlists/common.txt
```

框架支持评价：高。已接入 [tools/dirb.yaml](/home/zhaoshuai/workspace_cyber/LNU-SecLLM/tools/dirb.yaml:1)，参数模型简单，适合低成本验证隐藏路径、备份文件和常见管理入口。

## 4) gobuster

用途：快速内容发现，支持 `dir`、`dns`、`fuzz`、`vhost` 等模式。

安装：
```bash
sudo apt-get install -y gobuster
```

简单测试：
```bash
gobuster dir -u http://127.0.0.1:8000 -w /usr/share/wordlists/dirb/common.txt
```

如果系统没有 `/usr/share/wordlists/dirb/common.txt`，可以改用：

```bash
gobuster dir -u http://127.0.0.1:8000 -w /usr/share/dirb/wordlists/common.txt
```

框架支持评价：高。已接入 [tools/gobuster.yaml](/home/zhaoshuai/workspace_cyber/LNU-SecLLM/tools/gobuster.yaml:1)，默认模式为 `dir`，可通过参数切换到 DNS、Fuzz 或虚拟主机扫描。

## 5) feroxbuster

用途：高速递归目录和文件发现，适合对 Web 站点做更深入的内容枚举。

安装：
```bash
sudo apt-get install -y feroxbuster
```

如果 Ubuntu 源中没有该包，可使用 Cargo 安装：

```bash
cargo install feroxbuster
```

简单测试：
```bash
feroxbuster -u http://127.0.0.1:8000 -w /usr/share/dirb/wordlists/common.txt -t 10
```

框架支持评价：高。已接入 [tools/feroxbuster.yaml](/home/zhaoshuai/workspace_cyber/LNU-SecLLM/tools/feroxbuster.yaml:1)，支持目标、字典、线程数和附加参数。递归扫描请求量较大，建议先控制线程与深度。

## 6) ffuf

用途：快速 Web Fuzz，可用于目录发现、参数发现、虚拟主机发现和响应过滤。

安装：
```bash
sudo apt-get install -y ffuf
```

如果 Ubuntu 源中没有该包，可使用 Go 安装：

```bash
go install github.com/ffuf/ffuf/v2@latest
```

简单测试：
```bash
ffuf -u http://127.0.0.1:8000/FUZZ -w /usr/share/dirb/wordlists/common.txt -mc 200,301,302,403
```

框架支持评价：高。已接入 [tools/ffuf.yaml](/home/zhaoshuai/workspace_cyber/LNU-SecLLM/tools/ffuf.yaml:1)，URL 中需要使用 `FUZZ` 作为占位符。适合和 `gobuster`、`feroxbuster` 互补，用状态码、大小、词数等过滤器降低噪声。

## 7) httpx

用途：批量 HTTP 服务探测，常用于确认 URL 存活、状态码、标题、Web 指纹和响应信息。

注意：这里的 `httpx` 指 ProjectDiscovery 的命令行工具，不是 Python 的 `httpx` 库。

安装：
```bash
go install github.com/projectdiscovery/httpx/cmd/httpx@latest
```

建议先把 Go 安装目录加入 PATH（如未配置）：

```bash
export PATH="$PATH:$(go env GOPATH)/bin"
```

简单测试：
```bash
echo "http://127.0.0.1:8000" | httpx -status-code -title -tech-detect
```

框架支持评价：中。README 和多个角色配置中已经列出 `httpx`，但当前未发现独立的 `tools/httpx.yaml`。如需在框架内直接调用 ProjectDiscovery `httpx`，建议补充对应 YAML；若只是需要 HTTP 请求能力，当前已有 [tools/http-framework-test.yaml](/home/zhaoshuai/workspace_cyber/LNU-SecLLM/tools/http-framework-test.yaml:1) 作为基于 Python `httpx` 库的 HTTP 测试工具。
