# 模块3：Web应用测试与漏洞验证

本文覆盖模块 3 的以下工具：
`burpsuite`、`nikto`、`nuclei`、`dalfox`、`jaeles`、`http-intruder`、`dotdotpwn`。

## 使用前准备

通用依赖安装（补充Web测试类工具基础环境）：
```bash
sudo apt-get update
sudo apt-get install -y curl wget git python3 python3-pip golang
```

确保 Go 安装目录加入 PATH（如未配置）：
```bash
export PATH="$PATH:$(go env GOPATH)/bin"
```

## 模块3涉及工具

| Tool | 做什么的 | `tools/*.yaml` 支持情况 |
|------|----------|-------------------------|
| burpsuite | Web应用渗透测试全流程工具（代理/扫描/爆破/漏洞验证） | 已接入，`enabled: true`（CLI模式） |
| nikto | Web服务器漏洞扫描（配置错误/高危文件/CVE检测） | 已接入，`enabled: true` |
| nuclei | 基于模板的多维度漏洞扫描（Web/网络漏洞验证） | 已接入，`enabled: true` |
| dalfox | XSS漏洞专项扫描与验证（主动/被动检测+利用） | 已接入，`enabled: true` |
| jaeles | 自动化Web漏洞扫描（请求篡改+模板化漏洞验证） | 已接入，`enabled: true` |
| http-intruder | HTTP请求爆破/参数篡改/通用Web漏洞探测 | burpsuite中已集成 |
| dotdotpwn | 目录遍历/路径穿越漏洞扫描与验证 | 已接入，`enabled: true` |

## 1) burpsuite

用途：Web应用渗透测试全流程工具，支持流量代理、自动扫描、密码爆破、漏洞手动验证、请求篡改等核心能力，覆盖Web测试全生命周期。

安装（Ubuntu 推荐 snap 安装社区版）：
```bash
sudo snap install burpsuite-ce
```

简单测试：
```bash
# 启动Burp Suite CLI模式（适合框架集成）
burpsuite-ce --headless --project-file /tmp/burp-project.burp --config-file /tmp/burp-config.json
# 或启动GUI模式（手动验证）
burpsuite-ce
```

框架支持评价：中高。CLI模式已接入框架，核心扫描/验证能力可调用；GUI模式需手动操作，适合深度漏洞验证，封装复杂度略高。

## 2) nikto

用途：开源Web服务器漏洞扫描工具，检测常见配置错误、高危文件/目录、过时组件、CVE漏洞等，覆盖Apache/Nginx/IIS等主流Web服务。

安装：
```bash
sudo apt-get install -y nikto
```

简单测试：
```bash
nikto -h http://127.0.0.1
```

框架支持评价：高。参数封装完整，扫描规则可自定义，适合Web服务基础漏洞快速探测。

## 3) nuclei

用途：基于YAML模板的高性能漏洞扫描工具，覆盖Web应用、网络服务、API等多维度漏洞验证，支持自定义模板扩展，适合批量漏洞快速检测。

安装：
```bash
go install github.com/projectdiscovery/nuclei/v3/cmd/nuclei@latest
# 拉取官方漏洞模板（首次使用）
nuclei -update-templates
```

简单测试：
```bash
nuclei -u http://127.0.0.1 -t cves/2023/ -severity high
```

框架支持评价：高。模板生态完善，参数设计灵活，框架已完整接入，适合批量Web漏洞验证场景。

## 4) dalfox

用途：XSS漏洞专项扫描工具，支持主动/被动检测、参数污染、DOM XSS探测、自动化利用验证，是Web前端漏洞测试的核心工具。

安装：
```bash
go install github.com/hahwul/dalfox/v2@latest
```

简单测试：
```bash
dalfox scan http://127.0.0.1/test.php?param=1
```

框架支持评价：高。XSS检测逻辑成熟，参数封装简洁，适合前端漏洞自动化验证。

## 5) jaeles

用途：自动化Web漏洞扫描工具，通过请求篡改、模板匹配实现漏洞验证，支持自定义POC/EXP，覆盖SQLi、SSRF、RCE等常见Web漏洞。

安装：
```bash
# 方式1：Go安装
go install github.com/jaeles-project/jaeles@latest
# 方式2：下载二进制（推荐，避免编译依赖）
curl -s https://raw.githubusercontent.com/jaeles-project/jaeles/main/install.sh | bash
```

简单测试：
```bash
jaeles scan -u http://127.0.0.1 -s ~/jaeles-signatures/generic/detect/
```

框架支持评价：中高。已接入框架，扫描能力依赖签名模板完整性，适合定制化Web漏洞验证。

## 6) http-intruder

用途：轻量HTTP请求爆破工具，支持参数篡改、头部伪造、弱口令爆破、通用Web漏洞（SQLi/SSRF）初步探测。

安装：
```bash
pip3 install http-intruder
```

简单测试：
```bash
http-intruder -u http://127.0.0.1/login.php -p "username=admin&password=FUZZ" -w /usr/share/wordlists/rockyou.txt
```

框架支持评价：中。配置已存在，但默认 `enabled: false`，需先在 [tools/http-intruder.yaml](/home/zhaoshuai/workspace_cyber/LNU-SecLLM/tools/http-intruder.yaml:1) 改为 `true`；参数封装较基础，适合简单爆破场景。

## 7) dotdotpwn

用途：目录遍历/路径穿越漏洞专项扫描工具，支持多种协议（HTTP/FTP/SMB）的路径穿越验证，可自定义payload字典。

安装：
```bash
sudo apt-get install -y dotdotpwn
# 或源码安装（获取最新版本）
git clone https://github.com/wireghoul/dotdotpwn.git
cd dotdotpwn
sudo cp dotdotpwn.pl /usr/local/bin/
```

简单测试：
```bash
dotdotpwn -m http -h 127.0.0.1 -f /etc/passwd
```

框架支持评价：中高。已接入框架，路径穿越检测逻辑成熟，效果依赖payload字典与目标环境。

## 在框架里验证“是否支持”的最小步骤

1. 确认工具命令存在：`tool --help` 或 `tool -v`（burpsuite 用 `burpsuite-ce --help`）。
2. 确认对应 YAML 存在且 `enabled: true`（http-intruder 需手动修改）。
3. 在框架内对该工具发起一次最小参数调用（如扫描本地测试Web服务）。
4. 观察是否返回正常输出或可解释错误（例如目标无响应、权限不足、模板缺失）。

## 备注

- `burpsuite` 社区版部分高级功能受限，CLI模式需提前配置扫描策略。
- `nuclei`、`dalfox`、`jaeles` 依赖网络环境与模板更新，建议定期执行 `nuclei -update-templates`、`jaeles update`。
- `nikto` 扫描结果易被WAF拦截，可结合代理（如burpsuite）调整请求特征。
- 所有工具仅允许对授权测试目标（如本地测试靶机、自建Web服务）使用，禁止未授权扫描外部目标。
- `dotdotpwn` 部分场景需自定义payload，默认字典可能覆盖不全新型路径穿越绕过方式。