# 模块4：API / JWT / 数据库安全
本文覆盖模块 4 的以下工具：
`sqlmap`、`arjun`、`api-schema-analyzer`、`jwt-analyzer`、`graphql-scanner`

## 使用前准备
```bash
sudo apt-get update
sudo apt-get install -y curl wget git python3-pip golang
```
建议先把 Go 安装目录加入 PATH（如未配置）：
```bash
export PATH="$PATH:$(go env GOPATH)/bin"
```

## 模块4涉及工具
| Tool | 做什么的 | `tools/*.yaml` 支持情况 |
|------|----------|-------------------------|
| sqlmap | 自动化SQL注入检测、利用与数据库脱库 | 已接入，`enabled: true` |
| arjun | 接口隐藏参数/HTTP参数爆破发现 | 已接入，`enabled: true` |
| api-schema-analyzer | API架构解析、漏洞检测与合规校验 | 已接入，`enabled: true` |
| jwt-analyzer | JWT令牌解析、安全检测、弱密钥破解 | 已接入，`enabled: true` |
| graphql-scanner | GraphQL接口扫描、深度探测与漏洞验证 | 已接入，`enabled: true` |

---

## 1) sqlmap
用途：自动化SQL注入漏洞检测与利用，支持主流数据库，可获取库表数据、权限提升、执行系统命令。
安装：
```bash
sudo apt-get install -y sqlmap
```
简单测试：
```bash
sqlmap -u "http://127.0.0.1?id=1" --batch --dbs
```
框架支持评价：高。参数封装完整，注入检测与利用能力成熟，框架集成稳定。

---

## 2) arjun
用途：快速发现Web/API接口的隐藏参数、未公开参数，辅助漏洞挖掘与参数测试。
安装：
```bash
pip3 install arjun
```
简单测试：
```bash
arjun -u http://127.0.0.1
```
框架支持评价：高。轻量高效，参数发现准确，适合API前置参数探测。

---

## 3) api-schema-analyzer
用途：API架构分析工具，解析OpenAPI/Swagger文档，检测接口越权、未授权访问、参数漏洞。
安装：
```bash
go install github.com/penubolamichael/api-schema-analyzer@latest
```
简单测试：
```bash
api-schema-analyzer -u http://127.0.0.1/swagger.json
```
框架支持评价：中高。已接入框架，适合API文档解析与合规性检测。

---

## 4) jwt-analyzer
用途：JWT令牌解析、安全检测，支持密钥破解、算法绕过验证、过期与权限校验。
安装：
```bash
pip3 install jwt-analyzer
```
简单测试：
```bash
jwt-analyzer -t "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.e30.test"
```
框架支持评价：高。JWT安全检测能力全面，框架接入完整，适合令牌安全测试。

---

## 5) graphql-scanner
用途：GraphQL接口专项扫描，探测未授权访问、深度查询、信息泄露、注入类漏洞。
安装：
```bash
go install github.com/glethuillier/graphql-scanner@latest
```
简单测试：
```bash
graphql-scanner -u http://127.0.0.1/graphql
```
框架支持评价：高。适配GraphQL特性，深度探测能力强，已接入框架。

---

## 在框架里验证“是否支持”的最小步骤
1. 确认工具命令存在：`tool --help` 或 `tool --version`。
2. 确认对应 YAML 存在且 `enabled: true`。
3. 在框架内对该工具发起一次最小参数调用。
4. 观察是否返回正常输出或可解释错误（例如权限不足、目标无响应）。

---

## 备注
- `sqlmap` 扫描强度高，易触发WAF/防护机制，建议降低线程测试。
- `arjun` 适合配合API工具使用，快速补齐未公开参数。
- `jwt-analyzer` 破解效果依赖密钥复杂度，仅用于授权测试。
- `graphql-scanner` 需目标暴露GraphQL入口，支持POST/GET两种模式。
- 所有工具仅用于所授权测试目标，禁止随意扫描与利用。