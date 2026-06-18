# LNU-SecLLM API 接口文档

> Base URL：`/api`

## 1. 通用说明

- 请求格式：`application/json`
- 登录后所有受保护接口需携带：

```http
Authorization: Bearer <token>
```

通用返回：

```json
{"message":"success"}
```

错误：

```json
{"error":"error message"}
```

---

## 2. 认证

| 方法 | 接口 | 说明 |
|---|---|---|
|POST|/auth/login|登录|
|POST|/auth/logout|退出|
|POST|/auth/change-password|修改密码|
|GET|/auth/validate|验证 Token|

登录：

```json
{"password":"******"}
```

---

## 3. AI 对话

| 方法 | 接口 |
|---|---|
|POST|/agent-loop|
|POST|/agent-loop/stream|
|POST|/agent-loop/cancel|
|GET|/agent-loop/tasks|
|POST|/multi-agent|
|POST|/multi-agent/stream|

示例：

```json
{
  "message":"扫描目标",
  "conversationId":"xxx",
  "role":"默认"
}
```

---

## 4. 会话管理

- 创建：POST `/conversations`
- 查询：GET `/conversations`
- 详情：GET `/conversations/:id`
- 修改：PUT `/conversations/:id`
- 删除：DELETE `/conversations/:id`
- 置顶：PUT `/conversations/:id/pinned`
- 消息过程：GET `/messages/:id/process-details`

分组：

- `/groups`
- `/groups/:id`
- `/groups/conversations`

---

## 5. 漏洞与报告

### 漏洞

GET/POST/PUT/DELETE：

```
/vulnerabilities
/vulnerabilities/:id
/vulnerabilities/stats
```

主要字段：

- title
- severity
- status
- target
- proof
- recommendation

### 报告

```
GET  /reports
POST /reports
GET  /reports/:id
GET  /reports/:id/markdown
DELETE /reports/:id
```

---

## 6. 攻击链与监控

```
GET  /attack-chain/:conversationId
POST /attack-chain/:conversationId/regenerate

GET  /monitor
GET  /monitor/stats
GET  /monitor/execution/:id
DELETE /monitor/execution/:id
```

---

## 7. 知识库

```
GET    /knowledge/categories
GET    /knowledge/items
POST   /knowledge/items
PUT    /knowledge/items/:id
DELETE /knowledge/items/:id
POST   /knowledge/search
POST   /knowledge/index
GET    /knowledge/stats
```

---

## 8. 角色与技能

角色：

```
/roles
/roles/:name
```

技能：

```
/skills
/skills/:name
/skills/stats
```

---

## 9. WebShell

```
GET    /webshell/connections
POST   /webshell/connections
PUT    /webshell/connections/:id
DELETE /webshell/connections/:id

POST   /webshell/exec
POST   /webshell/file
```

---

## 10. 文件管理

```
GET    /chat-uploads
POST   /chat-uploads
DELETE /chat-uploads
PUT    /chat-uploads/content
GET    /chat-uploads/download
```

---

## 11. 系统配置

```
GET  /config
PUT  /config
POST /config/apply
GET  /config/tools
```

---

## 12. MCP

```
GET    /external-mcp
PUT    /external-mcp/:name
POST   /external-mcp/:name/start
POST   /external-mcp/:name/stop
DELETE /external-mcp/:name

POST /mcp
```

---

## 13. 机器人

```
POST /robot/test
GET  /robot/wecom
POST /robot/wecom
POST /robot/dingtalk
POST /robot/lark
```

---

## 14. OpenAPI

```
GET /openapi/spec
GET /conversations/:id/results
GET /api-docs
```

---

## 15. 开发建议

1. 登录后统一注入 Token。
2. 长任务优先使用 Stream 接口。
3. 大会话按需加载消息详情。
4. WebShell、终端等接口仅用于授权环境。
5. 新增接口同步更新 OpenAPI 与文档。
