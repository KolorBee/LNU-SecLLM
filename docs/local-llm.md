# 本地大模型替换指南

本文档说明如何把 CyberStrikeAI 当前依赖的云端模型 API 替换为本地大模型服务。

结论先说：这个项目本身并不绑定 OpenAI 官方服务，它依赖的是 OpenAI 兼容接口。因此只要你的本地服务能正确提供以下接口，就可以在不改代码的前提下完成替换：

- /chat/completions
- /embeddings（仅在启用知识库时需要）

## 适用范围

本指南适用于以下场景：

- 你想把 openai.base_url 从公网 API 切换到本地推理服务
- 你想继续使用单代理、多代理、流式输出和工具调用能力
- 你想保留知识库功能，并将嵌入模型也切到本地

不适用于以下场景：

- 你的本地服务只提供私有协议，不兼容 OpenAI 接口
- 你的本地服务只有纯文本对话，不支持工具调用
- 你希望直接对接 Ollama 原生的 /api/chat 或 /api/embed 接口而不加兼容层

## 项目当前的模型接入方式

项目里虽然配置块名叫 openai，但实际含义是“OpenAI 兼容接口配置”。

当前代码路径有两个核心约束：

- 对话能力固定请求 /chat/completions
- 知识库嵌入固定请求 /embeddings
- api_key 不能为空，否则后端会直接报错
- 代理模式依赖 tool_calls，模型若不支持函数调用，能力会明显退化

这意味着本地替换的关键不是“模型品牌”，而是“接口兼容度”。

## 推荐接入方式

优先选择以下几类本地服务：

- vLLM：原生支持 OpenAI 兼容接口，适合服务化部署
- LM Studio：本地桌面部署简单，适合单机验证
- Ollama + OpenAI 兼容层：适合已有 Ollama 环境但需要 /v1 接口的场景
- 其他 OpenAI 兼容网关：如自建代理层、统一网关、模型服务聚合层

如果你直接使用本地服务，请先确认它至少满足下面几点：

- 有稳定的 /v1/chat/completions
- 流式输出兼容 SSE
- 支持 tool_calls 或 function calling
- 如果要启用知识库，还需要 /v1/embeddings

## 最小改动方案

### 1. 替换主对话模型

编辑 config.yaml，把 openai 段改为你的本地服务地址。

示例一：LM Studio

```yaml
openai:
  base_url: http://127.0.0.1:1234/v1
  api_key: local-token
  model: your-local-chat-model
  max_total_tokens: 120000
```

示例二：vLLM

```yaml
openai:
  base_url: http://127.0.0.1:8000/v1
  api_key: local-token
  model: Qwen/Qwen2.5-14B-Instruct
  max_total_tokens: 120000
```

示例三：Ollama 经兼容层暴露 /v1

```yaml
openai:
  base_url: http://127.0.0.1:11434/v1
  api_key: local-token
  model: qwen3:14b
  max_total_tokens: 120000
```

说明：

- api_key 目前必须填，哪怕本地服务不校验鉴权，也请填一个非空占位值，例如 local-token
- model 必须与本地服务实际暴露的模型名一致，不能照抄示例
- base_url 不要写到 /chat/completions，项目会自动拼接接口路径

### 2. 如果不使用知识库

如果你暂时不需要知识检索，建议保持：

```yaml
knowledge:
  enabled: false
```

这样你只需要保证聊天模型可用即可。

### 3. 如果要启用知识库

知识库索引和检索依赖嵌入模型。当前实现虽然配置项里有 provider，但实际仍按 OpenAI 兼容接口请求 /embeddings。

如果你的本地服务同时支持聊天和嵌入，可以这样配置：

```yaml
knowledge:
  enabled: true
  base_path: knowledge_base
  embedding:
    provider: openai
    model: your-local-embedding-model
    base_url: http://127.0.0.1:8000/v1
    api_key: local-token
  retrieval:
    top_k: 5
    similarity_threshold: 0.7
    hybrid_weight: 0.7
```

如果聊天模型和嵌入模型不在同一服务，也可以分别指定：

```yaml
openai:
  base_url: http://127.0.0.1:8000/v1
  api_key: local-token
  model: your-local-chat-model

knowledge:
  enabled: true
  embedding:
    provider: openai
    model: your-local-embedding-model
    base_url: http://127.0.0.1:9997/v1
    api_key: local-token
```

## 推荐模型选择原则

这个项目不是普通聊天页面，而是安全测试代理平台。模型除了“能回答”之外，还要尽量满足下面几点：

- 支持工具调用
- 指令遵循稳定
- 长上下文表现可靠
- 流式输出兼容较好
- 对 JSON 参数生成更稳定

如果你主要使用单代理、多代理、MCP 工具编排，优先选择偏 Instruct、Tool Calling 能力更稳定的模型，而不是只擅长自由对话的模型。

## 启动前自检

在修改 config.yaml 后，建议先确认本地接口是通的。

聊天接口自检示例：

```bash
curl http://127.0.0.1:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer local-token' \
  -d '{
    "model": "your-local-chat-model",
    "messages": [
      {"role": "user", "content": "hello"}
    ]
  }'
```

嵌入接口自检示例：

```bash
curl http://127.0.0.1:8000/v1/embeddings \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer local-token' \
  -d '{
    "model": "your-local-embedding-model",
    "input": ["test embedding"]
  }'
```

只要这两个请求能返回标准 OpenAI 兼容 JSON，CyberStrikeAI 基本就能接上。

## 常见替换路径

### 路径一：只替换聊天模型

适合先验证系统能跑起来。

- 修改 openai.base_url
- 修改 openai.api_key
- 修改 openai.model
- 保持 knowledge.enabled: false

这是最稳妥的第一步。

### 路径二：聊天和知识库都本地化

适合对数据不出网有明确要求的环境。

- 替换 openai 段为本地聊天模型
- 替换 knowledge.embedding 为本地嵌入服务
- 重新扫描知识库索引

注意：如果旧的 knowledge.db 是用另一套嵌入模型生成的，切换嵌入模型后建议重新构建索引，否则检索效果会不稳定。

### 路径三：本地聊天 + 远程嵌入

适合先把主对话迁到本地，但暂时没有本地 embedding 服务的情况。

- openai 使用本地服务
- knowledge.embedding 单独指向远程兼容接口

这种方式可以过渡，但严格来说不属于“完全本地化”。

## 常见问题

### 1. 报错 openai api key is empty

原因：当前实现要求 api_key 非空。

处理：

- 在 openai.api_key 填任意非空值
- 在 knowledge.embedding.api_key 也填非空值，或留空继承 openai.api_key

### 2. 报 404 或接口不存在

原因通常有三种：

- base_url 写错了
- 本地服务没有暴露 /v1 路径
- 你连的是原生接口，不是 OpenAI 兼容接口

处理：

- 确认 base_url 形如 http://127.0.0.1:8000/v1
- 不要把完整路径写成 http://127.0.0.1:8000/v1/chat/completions
- 如果服务只提供 /api/chat，需要额外加兼容层

### 3. 模型能聊天，但代理不会调用工具

原因：模型不支持 tool_calls，或者兼容层没有正确返回工具调用结构。

处理：

- 更换支持工具调用的模型
- 检查兼容层是否返回标准 tool_calls 字段
- 优先使用对函数调用支持更成熟的服务端实现

### 4. 扫描知识库时报 embeddings 错误

原因：

- 嵌入服务没有 /embeddings
- embedding.model 不存在
- api_key/base_url 没单独配置好

处理：

- 先用 curl 单独验证 /v1/embeddings
- 不需要知识库时，直接关闭 knowledge.enabled
- 更换支持 embedding 的本地服务

### 5. 流式输出异常或卡住

原因通常是兼容层 SSE 实现不完整。

处理：

- 先关闭复杂场景，做一个最小聊天请求验证
- 换用更成熟的 OpenAI 兼容服务
- 若非必要，可先验证非流式能力

## 推荐落地顺序

建议按下面顺序替换，排障成本最低：

1. 先只替换 openai 段，验证基础聊天
2. 再验证工具调用是否正常
3. 最后再接 knowledge.embedding 并重建知识库索引

如果你一次性同时替换聊天、流式、工具调用和嵌入，出现问题时会很难定位是哪一层不兼容。

## 一份可直接参考的本地化配置

```yaml
openai:
  base_url: http://127.0.0.1:8000/v1
  api_key: local-token
  model: your-local-chat-model
  max_total_tokens: 120000

knowledge:
  enabled: false
  base_path: knowledge_base
  embedding:
    provider: openai
    model: your-local-embedding-model
    base_url: http://127.0.0.1:8000/v1
    api_key: local-token
  retrieval:
    top_k: 5
    similarity_threshold: 0.7
    hybrid_weight: 0.7
```

如果后续确认本地 embedding 也稳定，再把 knowledge.enabled 改成 true 并重新扫描知识库即可。