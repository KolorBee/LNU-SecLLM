<div align="center">
  <img src="web/static/logo.png" alt="LNU-SecLM Logo" width="200">
</div>

# LNU-SecLM 智御安全社区

[中文](README_CN.md) | [English](README.md)

> **AI 驱动安全，代码守护未来**

LNU-SecLM（智御安全社区）是辽宁大学校园开源安全社区平台，基于 **CyberStrikeAI** 进行二次定制开发，面向校内师生的安全研究、教学实训与竞赛场景。平台采用 **AI 驱动全链路 + 教学整合 + 届次传承** 的设计理念，集成 100+ 安全工具、智能编排引擎、角色化测试、Skills 技能系统与完整的测试生命周期管理能力。通过原生 MCP 协议与 AI 智能体，支持从对话指令到漏洞发现、攻击链分析、知识检索与结果可视化的全流程自动化，为校园安全团队提供可审计、可追溯、可协作的专业测试与学习环境。


## 平台定位

| 维度 | 说明 |
|------|------|
| 项目性质 | 校园开源安全社区平台 |
| 技术底座 | 基于 CyberStrikeAI 的二次定制开发 |
| 目标用户 | 辽大校内师生（安全研究、教学实训、竞赛） |
| 开源许可 | Apache 2.0（适配教学场景，兼顾商业使用与开源合规） |
| 开发模式 | 届次迭代开发，每届学生围绕核心框架持续演进 |
| 核心差异 | AI 驱动全链路 + 教学整合 + 届次传承机制 |

## 功能全景

平台围绕四大功能区块组织，覆盖完整的安全测试与学习闭环：

- **📊 数据看板**：安全态势仪表盘，统一呈现运行中任务、发现漏洞、工具调用次数与工具执行成功率。
- **🛡️ 安全工作台**：AI 对话、信息收集、任务管理、漏洞管理、WebShell 管理、文件管理。
- **🧩 扩展模块**：扩展市场、插件管理，支持能力的灵活拓展与按需接入。
- **⚙️ 智能引擎**：MCP、知识库、Skills 技能、Agents 多代理、角色管理。

## 界面与集成预览

<div align="center">

### 系统仪表盘概览

<img src="./images/dashboard.png" alt="系统仪表盘" width="100%">

*仪表盘提供系统运行状态、安全漏洞严重程度分布、运行概览（批量任务队列 / 工具调用 / 知识库 / Skills）、热门工具与快速操作的全面概览，帮助用户快速了解平台核心功能和当前状态。*

### 核心功能概览

<table>
<tr>
<td width="33.33%" align="center">
<strong>AI 对话</strong><br/>
<img src="./images/web-console.png" alt="AI 对话" width="100%">
</td>
<td width="33.33%" align="center">
<strong>任务管理</strong><br/>
<img src="./images/task-management.png" alt="任务管理" width="100%">
</td>
<td width="33.33%" align="center">
<strong>漏洞管理</strong><br/>
<img src="./images/vulnerability-management.png" alt="漏洞管理" width="100%">
</td>
</tr>
<tr>
<td width="33.33%" align="center">
<strong>WebShell 管理</strong><br/>
<img src="./images/webshell-management.png" alt="WebShell 管理" width="100%">
</td>
<td width="33.33%" align="center">
<strong>MCP 管理</strong><br/>
<img src="./images/mcp-management.png" alt="MCP 管理" width="100%">
</td>
<td width="33.33%" align="center">
<strong>知识库</strong><br/>
<img src="./images/knowledge-base.png" alt="知识库" width="100%">
</td>
</tr>
<tr>
<td width="33.33%" align="center">
<strong>Skills 管理</strong><br/>
<img src="./images/skills.png" alt="Skills 管理" width="100%">
</td>
<td width="33.33%" align="center">
<strong>Agents 管理</strong><br/>
<img src="./images/agent-management.png" alt="Agents 管理" width="100%">
</td>
<td width="33.33%" align="center">
<strong>角色管理</strong><br/>
<img src="./images/role-management.png" alt="角色管理" width="100%">
</td>
</tr>
<tr>
<td width="33.33%" align="center">
<strong>系统设置</strong><br/>
<img src="./images/settings.png" alt="系统设置" width="100%">
</td>
<td width="33.33%" align="center">
<strong>MCP stdio 模式</strong><br/>
<img src="./images/mcp-stdio2.png" alt="MCP stdio 模式" width="100%">
</td>
<td width="33.33%" align="center">
<strong>Burp Suite 插件</strong><br/>
<img src="./images/plugins.png" alt="Burp Suite 插件" width="100%">
</td>
</tr>
</table>

</div>

## 特性速览

- 🤖 兼容 OpenAI/DeepSeek/Claude 等模型的智能决策引擎
- 🔌 原生 MCP 协议，支持 HTTP / stdio / SSE 传输模式以及外部 MCP 接入
- 🧰 100+ 现成工具模版 + YAML 扩展能力
- 📄 大结果分页、压缩与全文检索
- 🔗 攻击链可视化、风险打分与步骤回放
- 🔒 Web 登录保护、审计日志、SQLite 持久化
- 📚 知识库功能：向量检索与混合搜索，为 AI 提供安全专业知识
- 📁 对话分组管理：支持分组创建、置顶、重命名、删除等操作
- 🛡️ 漏洞管理功能：完整的漏洞 CRUD 操作，支持严重程度分级（严重/高危/中危/低危/信息）、状态流转、按对话/严重程度/状态过滤，以及统计看板
- 📋 批量任务管理：创建任务队列，批量添加任务，依次顺序执行，支持任务编辑与状态跟踪
- 🎭 角色化测试：预设安全测试角色（渗透测试、CTF、Web 应用扫描等），支持自定义提示词和工具限制
- 🧩 **多代理模式（Eino DeepAgent）**：可选编排——协调主代理通过 `task` 调度 Markdown 定义的子代理；主代理见 `agents/orchestrator.md` 或 front matter `kind: orchestrator`，子代理为 `agents/*.md`；开启 `multi_agent.enabled` 后聊天可切换单代理/多代理（详见 [多代理说明](docs/MULTI_AGENT_EINO.md)）
- 🎯 Skills 技能系统：20+ 预设安全测试技能（SQL 注入、XSS、API 安全等），可附加到角色或由 AI 按需调用
- 📱 **机器人**：支持钉钉、飞书长连接，在手机端与 LNU-SecLM 对话（配置与命令详见 [机器人使用说明](docs/robot.md)）
- 🐚 **WebShell 管理**：添加与管理 WebShell 连接（兼容冰蝎/蚁剑等），通过虚拟终端执行命令、内置文件管理进行文件操作，并提供按连接维度保存历史的 AI 助手标签页；支持 PHP/ASP/ASPX/JSP 及自定义类型，可配置请求方法与命令参数。
- 🎓 **教学与届次传承**：面向教学实训设计，支持每届学生围绕核心框架持续演进，配套标准化文档与交接机制。

## 插件（Plugins）

可选集成在 `plugins/` 目录下。

- **Burp Suite 插件**：`plugins/burp-suite/cyberstrikeai-burp-extension/`  
  构建产物：`plugins/burp-suite/cyberstrikeai-burp-extension/dist/cyberstrikeai-burp-extension.jar`  
  说明文档：`plugins/burp-suite/cyberstrikeai-burp-extension/README.zh-CN.md`

## 工具概览

系统预置 100+ 渗透/攻防工具，覆盖完整攻击链：

- **网络扫描**：nmap、masscan、rustscan、arp-scan、nbtscan
- **Web 应用扫描**：sqlmap、nikto、dirb、gobuster、feroxbuster、ffuf、httpx
- **漏洞扫描**：nuclei、wpscan、wafw00f、dalfox、xsser
- **子域名枚举**：subfinder、amass、findomain、dnsenum、fierce
- **网络空间搜索引擎**：fofa_search、zoomeye_search
- **API 安全**：graphql-scanner、arjun、api-fuzzer、api-schema-analyzer
- **容器安全**：trivy、clair、docker-bench-security、kube-bench、kube-hunter
- **云安全**：prowler、scout-suite、cloudmapper、pacu、terrascan、checkov
- **二进制分析**：gdb、radare2、ghidra、objdump、strings、binwalk
- **漏洞利用**：metasploit、msfvenom、pwntools、ropper、ropgadget
- **密码破解**：hashcat、john、hashpump
- **取证分析**：volatility、volatility3、foremost、steghide、exiftool
- **后渗透**：linpeas、winpeas、mimikatz、bloodhound、impacket、responder
- **CTF 实用工具**：stegsolve、zsteg、hash-identifier、fcrackzip、pdfcrack、cyberchef
- **系统辅助**：exec、create-file、delete-file、list-files、modify-file

## 基础使用

### 快速上手（一条命令部署）

**环境要求：**
- Go 1.21+ ([下载安装](https://go.dev/dl/))
- Python 3.10+ ([下载安装](https://www.python.org/downloads/))

**一条命令部署：**
```bash
git clone https://github.com/Ed1s0nZ/CyberStrikeAI.git
cd CyberStrikeAI
chmod +x run.sh && ./run.sh
run.sh 脚本会自动完成：

✅ 检查并验证 Go 和 Python 环境
✅ 创建 Python 虚拟环境
✅ 安装 Python 依赖包
✅ 下载 Go 依赖模块
✅ 编译构建项目
✅ 启动服务器
首次配置：

配置 AI 模型 API（首次使用前必填）
启动后访问 http://localhost:8080
进入 设置 → 填写 API 配置信息：
openai:
  api_key: "sk-your-key"
  base_url: "https://api.openai.com/v1"  # 或 https://api.deepseek.com/v1
  model: "gpt-4o"  # 或 deepseek-chat, claude-3-opus 等
或启动前直接编辑 config.yaml 文件
登录系统 - 使用控制台显示的自动生成密码（或在 config.yaml 中设置 auth.password）。默认管理员账户为 Security Admin。
安装安全工具（可选） - 按需安装所需工具：
# macOS
brew install nmap sqlmap nuclei httpx gobuster feroxbuster subfinder amass
# Ubuntu/Debian
sudo apt-get install nmap sqlmap nuclei httpx gobuster feroxbuster
未安装的工具会自动跳过或改用替代方案。
其他启动方式：

# 直接运行（需手动配置环境）
go run cmd/server/main.go

# 手动编译
go build -o cyberstrike-ai cmd/server/main.go
./cyberstrike-ai
说明： Python 虚拟环境（venv/）由 run.sh 自动创建和管理。需要 Python 的工具（如 api-fuzzer、http-framework-test 等）会自动使用该环境。

版本更新（无兼容性问题）
（首次使用）启用脚本：chmod +x upgrade.sh
一键升级：./upgrade.sh（可选参数：--tag vX.Y.Z、--no-venv、--preserve-custom、--yes）
脚本会备份你的 config.yaml 和 data/，从 GitHub Release 升级代码，更新 config.yaml 的 version 字段后重启服务。
推荐的一键指令：
chmod +x upgrade.sh && ./upgrade.sh --yes

如果升级失败，可以从 .upgrade-backup/ 恢复，或按旧方式手动拷贝 /data 和 config.yaml 后再运行 ./run.sh。

依赖/提示：

需要 curl 或 wget 用于下载 GitHub Release 包。
建议/需要 rsync 用于安全同步代码。
如果遇到 GitHub API 限流，运行前设置 export GITHUB_TOKEN="..." 再执行 ./upgrade.sh。
⚠️ 注意： 仅适用于无兼容性变更的版本更新。若版本存在兼容性调整，此方法不适用。

举例： 无兼容性变更如 v1.3.1 → v1.3.2；有兼容性变更如 v1.3.1 → v1.4.0。项目采用语义化版本（SemVer）：仅第三位（补丁号）变更时通常可安全按上述步骤升级；次版本号或主版本号变更时可能涉及配置、数据或接口调整，需查阅 release notes 再决定是否适用本方法。

常用流程
对话测试：自然语言触发多步工具编排，SSE 实时输出。
单代理 / 多代理：配置 multi_agent.enabled: true 后，聊天界面可切换 单代理（原有 ReAct 循环）与 多代理（Eino DeepAgent + task 子代理）。多代理走 /api/multi-agent/stream，MCP 工具与单代理同源桥接。
角色化测试：从预设的安全测试角色（渗透测试、CTF、Web 应用扫描、API 安全测试等）中选择，自定义 AI 行为和可用工具。
工具监控：查看任务队列、执行日志、大文件附件。
会话历史：所有对话与工具调用保存在 SQLite，可随时重放。
对话分组：将对话按项目或主题组织到不同分组，支持置顶、重命名、删除等操作。
漏洞管理：在测试过程中创建、更新和跟踪发现的漏洞。支持按严重程度（严重/高危/中危/低危/信息）、状态（待确认/已确认/已修复/误报）和对话进行过滤，查看统计信息并导出发现。
批量任务管理：创建任务队列，批量添加多个任务，执行前可编辑或删除任务，然后依次顺序执行。
WebShell 管理：添加并管理 WebShell 连接（PHP/ASP/ASPX/JSP 或自定义类型），使用虚拟终端执行命令，使用文件管理浏览、读取、编辑、上传与删除目标文件。
可视化配置：在界面中切换模型、启停工具、设置迭代次数等。
默认安全措施
设置面板内置必填校验，防止漏配 API Key/Base URL/模型。
auth.password 为空时自动生成 24 位强口令并写回 config.yaml。
所有 API（除登录外）都需携带 Bearer Token，统一鉴权中间件拦截。
每个工具执行都带有超时、日志和错误隔离。
进阶使用
角色化测试
预设角色：系统内置 12+ 个预设的安全测试角色（渗透测试、CTF、Web 应用扫描、API 安全测试、二进制分析、云安全审计等），位于 roles/ 目录。
自定义提示词：每个角色可定义 user_prompt，会在用户消息前自动添加，引导 AI 采用特定的测试方法和关注重点。
工具限制：角色可指定 tools 列表，限制可用工具，实现聚焦的测试流程。
Skills 集成：角色可附加安全测试技能。技能名称会作为提示添加到系统提示词中，AI 智能体可通过 read_skill 工具按需获取技能内容。
轻松创建角色：通过在 roles/ 目录添加 YAML 文件即可创建自定义角色。
Web 界面集成：在聊天界面通过下拉菜单选择角色。
创建自定义角色示例：

在 roles/ 目录创建 YAML 文件（如 roles/custom-role.yaml）：
name: 自定义角色
description: 专用测试场景
user_prompt: 你是一个专注于 API 安全的专业安全测试人员...
icon: "\U0001F4E1"
tools:
  - api-fuzzer
  - arjun
  - graphql-scanner
skills:
  - api-security-testing
  - sql-injection-testing
enabled: true
重启服务或重新加载配置，角色会出现在角色选择下拉菜单中。
多代理模式（Eino DeepAgent）
能力说明：基于 CloudWeGo Eino adk/prebuilt/deep 的可选路径：协调主代理通过内置 task 工具启动短时子代理，各子代理独立推理，工具集来自当前聊天所选角色（与单代理一致来源）。
Markdown 定义：在 agents_dir（默认 agents/，相对 config.yaml 所在目录）维护：
主代理：固定文件名 orchestrator.md，或任意 .md 且在 front matter 写 kind: orchestrator（同一目录仅允许一个主代理）。
子代理：其余 *.md（YAML front matter + 正文作 instruction）。
界面管理：Agents → Agent 管理 对 Markdown 增删改查；HTTP API 前缀 /api/multi-agent/markdown-agents。
配置项：config.yaml 中 multi_agent：enabled、default_mode（single | multi）、robot_use_multi_agent、batch_use_multi_agent、max_iteration、orchestrator_instruction 等。
更多细节：流式事件、机器人与批量任务、排障等见 docs/MULTI_AGENT_EINO.md。
Skills 技能系统
预设技能：系统内置 20+ 个预设的安全测试技能（SQL 注入、XSS、API 安全、云安全、容器安全等），位于 skills/ 目录。
提示词中的技能提示：当选择某个角色时，该角色附加的技能名称会作为推荐添加到系统提示词中。
按需调用：AI 智能体可通过内置工具（list_skills、read_skill）按需访问技能。
结构化格式：每个技能是一个目录，包含一个 SKILL.md 文件。
自定义技能：通过在 skills/ 目录添加目录即可创建自定义技能。
创建自定义技能：

在 skills/ 目录创建目录（如 skills/my-skill/）
在该目录下创建 SKILL.md 文件，编写技能内容
在角色的 YAML 文件中，通过添加 skills 字段将该技能附加到角色
工具编排与扩展
tools/*.yaml 定义命令、参数、提示词与元数据，可热加载。
security.tools_dir 指向目录即可批量启用；仍支持在主配置里内联定义。
大结果分页：超过 200KB 的输出会保存为附件，可通过 query_execution_result 工具分页、过滤、正则检索。
结果压缩/摘要：多兆字节日志可先压缩或生成摘要再写入 SQLite，减小档案体积。
自定义工具的一般步骤

复制 tools/ 下现有示例（如 tools/sample.yaml）。
修改 name、command、args、short_description 等基础信息。
在 parameters[] 中声明位置参数或带 flag 的参数。
视需要补充 description 或 notes。
重启服务或在界面中重新加载配置，新工具即可在设置面板中启用/禁用。
攻击链分析
智能体解析每次对话，抽取目标、工具、漏洞与因果关系。
Web 端可交互式查看链路节点、风险级别及时间轴，支持导出报告。
WebShell 管理
连接管理：在 Web 界面进入 WebShell 管理，可添加、编辑或删除 WebShell 连接。
虚拟终端：选择连接后执行任意命令，支持命令历史与常用快捷命令。
文件管理：列出目录、读取/编辑文件、删除文件、新建文件/目录、上传文件、重命名路径以及下载勾选文件。
AI 助手：与智能体对话，由系统自动结合当前 WebShell 连接执行工具与命令。
连通性测试：通过一次 echo 1 调用校验 Shell 地址、密码与命令参数是否正确。
持久化：所有 WebShell 连接与相关 AI 会话均保存在 SQLite。
MCP 全场景
Web 模式：自带 HTTP MCP 服务供前端调用。
MCP stdio 模式：go run cmd/mcp-stdio/main.go 可接入 Cursor/命令行。
外部 MCP 联邦：在设置中注册第三方 MCP（HTTP/stdio/SSE），按需启停并实时查看调用统计与健康度。
可选 MCP 服务：项目中的 mcp-servers/ 目录提供独立 MCP（如反向 Shell）。
MCP stdio 快速集成
编译可执行文件（在项目根目录执行）：
go build -o cyberstrike-ai-mcp cmd/mcp-stdio/main.go
在 Cursor 中配置
打开 Settings → Tools & MCP → Add Custom MCP，选择 Command：
{
  "mcpServers": {
    "lnu-seclm": {
      "command": "/absolute/path/to/cyberstrike-ai-mcp",
      "args": [
        "--config",
        "/absolute/path/to/config.yaml"
      ]
    }
  }
}
MCP HTTP 快速集成（Cursor / Claude Code）
HTTP MCP 服务在独立端口（默认 8081）运行，支持 Header 鉴权。

在配置中启用 MCP – 在 config.yaml 中设置 mcp.enabled: true，并按需设置 mcp.host / mcp.port。鉴权可设置：
mcp.auth_header：鉴权用的 header 名（如 X-MCP-Token）；
mcp.auth_header_value：鉴权密钥。留空时，首次启动会自动生成随机密钥并写回配置文件。
启动服务 – 执行 ./run.sh 或 go run cmd/server/main.go。MCP 端点为 http://<host>:<port>/mcp。
从终端复制 JSON – 启用 MCP 后，启动时会在终端打印一段可直接复制的 JSON。
在 Cursor 或 Claude Code 中使用：粘贴到对应客户端的 mcpServers 配置中。
终端打印示例（开启鉴权时）：

{
  "mcpServers": {
    "lnu-seclm": {
      "url": "http://localhost:8081/mcp",
      "headers": {
        "X-MCP-Token": "<自动生成或你配置的值>"
      },
      "type": "http"
    }
  }
}
外部 MCP 联邦（HTTP/stdio/SSE）
支持通过三种传输模式连接外部 MCP 服务器：

HTTP 模式 – 通过 HTTP POST 进行传统的请求/响应通信
stdio 模式 – 通过标准输入/输出进行进程间通信
SSE 模式 – 通过 Server-Sent Events 实现实时流式通信
添加外部 MCP 服务器：

打开 Web 界面，进入 设置 → 外部MCP。
点击 添加外部MCP，以 JSON 格式提供配置。
点击 保存，然后点击 启动 连接服务器。
实时监控连接状态、工具数量和健康度。
知识库功能
向量检索：AI 智能体在对话过程中可自动调用 search_knowledge_base 工具搜索知识库中的安全知识。
混合检索：结合向量相似度搜索与关键词匹配，提升检索准确性。
自动索引：扫描 knowledge_base/ 目录下的 Markdown 文件，自动构建向量嵌入索引。
Web 管理：通过 Web 界面创建、更新、删除知识项，支持分类管理。
检索日志：记录所有知识检索操作，便于审计与调试。
知识库配置步骤：

启用功能：在 config.yaml 中设置 knowledge.enabled: true：
knowledge:
  enabled: true
  base_path: knowledge_base
  embedding:
    provider: openai
    model: text-embedding-v4
    base_url: "https://api.openai.com/v1"
    api_key: "sk-xxx"
  retrieval:
    top_k: 5
    similarity_threshold: 0.7
    hybrid_weight: 0.7
添加知识文件：将 Markdown 文件放入 knowledge_base/ 目录，按分类组织。
扫描索引：在 Web 界面中点击"扫描知识库"。
对话中使用：AI 智能体在需要安全知识时会自动调用知识检索工具。
自动化与安全
REST API：认证、会话、任务、监控、漏洞管理、角色管理等接口全部开放，可与 CI/CD 集成。
多代理 API：POST /api/multi-agent/stream（SSE，需启用多代理）、POST /api/multi-agent（非流式）。
角色管理 API：通过 /api/roles 端点管理安全测试角色。
漏洞管理 API：通过 /api/vulnerabilities 端点管理漏洞。
批量任务 API：通过 /api/batch-tasks 端点管理批量任务队列。
WebShell API：通过 /api/webshell/connections 及 /api/webshell/exec、/api/webshell/fileop 管理 WebShell 连接与执行操作。
任务控制：支持暂停/终止长任务、修改参数后重跑、流式获取日志。
安全管理：/api/auth/change-password 可即时轮换口令；建议在暴露 MCP 端口时配合网络层 ACL。
配置参考
auth:
  password: "change-me"
  session_duration_hours: 12
server:
  host: "0.0.0.0"
  port: 8080
log:
  level: "info"
  output: "stdout"
mcp:
  enabled: true
  host: "0.0.0.0"
  port: 8081
  auth_header: "X-MCP-Token"       # 可选；留空则不鉴权
  auth_header_value: ""            # 可选；留空则首次启动自动生成并写回
openai:
  api_key: "sk-xxx"
  base_url: "https://api.deepseek.com/v1"
  model: "deepseek-chat"
database:
  path: "data/conversations.db"
  knowledge_db_path: "data/knowledge.db"
security:
  tools_dir: "tools"
knowledge:
  enabled: false
  base_path: "knowledge_base"
  embedding:
    provider: "openai"
    model: "text-embedding-v4"
    base_url: ""
    api_key: ""
  retrieval:
    top_k: 5
    similarity_threshold: 0.7
    hybrid_weight: 0.7
roles_dir: "roles"
skills_dir: "skills"
agents_dir: "agents"
multi_agent:
  enabled: false
  default_mode: "single"
  robot_use_multi_agent: false
  batch_use_multi_agent: false
  orchestrator_instruction: ""
工具模版示例（tools/nmap.yaml）
name: "nmap"
command: "nmap"
args: ["-sT", "-sV", "-sC"]
enabled: true
short_description: "网络资产扫描与服务指纹识别"
parameters:
  - name: "target"
    type: "string"
    description: "IP 或域名"
    required: true
    position: 0
  - name: "ports"
    type: "string"
    flag: "-p"
    description: "端口范围，如 1-1000"
角色配置示例（roles/渗透测试.yaml）
name: 渗透测试
description: 专业渗透测试专家，全面深入的漏洞检测
user_prompt: 你是一个专业的网络安全渗透测试专家。请使用专业的渗透测试方法和工具，对目标进行全面的安全测试，包括但不限于SQL注入、XSS、CSRF、文件包含、命令执行等常见漏洞。
icon: "\U0001F3AF"
tools:
  - nmap
  - sqlmap
  - nuclei
  - burpsuite
  - metasploit
  - httpx
  - record_vulnerability
  - list_knowledge_risk_types
  - search_knowledge_base
enabled: true
相关文档
本地大模型替换指南：将项目当前使用的 OpenAI 兼容 API 替换为本地模型服务。
多代理模式（Eino）：DeepAgent 编排、agents/*.md、接口与流式说明。
机器人使用说明（钉钉 / 飞书）：在手机端通过钉钉、飞书与平台对话的完整配置步骤。
项目结构
LNU-SecLM/
├── cmd/                 # Web 服务、MCP stdio 入口及辅助工具
├── internal/            # Agent、MCP 核心、路由与执行器
├── web/                 # 前端静态资源与模板
├── tools/               # YAML 工具目录（含 100+ 示例）
├── roles/               # 角色配置文件目录（含 12+ 预设安全测试角色）
├── skills/              # Skills 目录（含 20+ 预设安全测试技能）
├── agents/              # 多代理 Markdown（orchestrator.md + 子代理 *.md）
├── docs/                # 说明文档
├── images/              # 文档配图
├── config.yaml          # 运行配置
├── run.sh               # 启动脚本
└── README*.md
基础体验示例
扫描 192.168.1.1 的开放端口
对 192.168.1.1 做 80/443/22 重点扫描
检查 https://example.com/page?id=1 是否存在 SQL 注入
枚举 https://example.com 的隐藏目录与组件漏洞
获取 example.com 的子域并批量执行 nuclei
进阶剧本示例
加载侦察剧本：先 amass/subfinder，再对存活主机进行目录爆破。
挂载基于 Burp 的外部 MCP，完成认证流量回放并回传到攻击链。
将 5MB nuclei 报告压缩并生成摘要，附加到对话记录。
构建最新一次测试的攻击链，只导出风险 >= 高的节点列表。
致谢
LNU-SecLM 智御安全社区基于开源项目 CyberStrikeAI 进行二次定制开发，感谢原作者及社区的贡献。

许可证
LNU-SecLM 采用 Apache License 2.0 开源许可。
完整条款见仓库根目录 LICENSE 文件。

⚠️ 免责声明
本工具仅供教育和授权测试使用！

LNU-SecLM 是一个面向校园教学与研究的安全测试平台，旨在帮助安全研究人员、师生和 IT 专业人员在获得明确授权的情况下进行安全评估和漏洞研究。

使用本工具即表示您同意：

仅在您拥有明确书面授权的系统上使用此工具
遵守所有适用的法律法规和道德准则
对任何未经授权的使用或滥用行为承担全部责任
不会将本工具用于任何非法或恶意目的
开发者不对任何滥用行为负责！ 请确保您的使用符合当地法律法规，并获得目标系统所有者的明确授权。

欢迎提交 Issue/PR 贡献新的工具模版或优化建议！

主要改动说明：

- 标题与品牌全部改为 LNU-SecLM 智御安全社区，加上 "AI 驱动安全，代码守护未来" 标语（来自图片顶部）
- 新增「平台定位」表格和「功能全景」四大区块，对齐图片左侧导航（数据看板/安全工作台/扩展模块/智能引擎）
- 仪表盘描述更新为图片中的实际内容（运行中任务、发现漏洞、工具调用次数、工具执行成功率、漏洞严重程度分布、运行概览、热门工具、快速操作）
- 漏洞严重程度统一为图片中的「严重/高危/中危/低危/信息」
- 默认管理员标注为 Security Admin
- 新增「致谢」段落，注明基于 CyberStrikeAI 二次开发，符合 Apache 2.0 合规要求

