# 角色配置文件说明

本目录包含所有角色配置文件，每个角色定义了AI的行为模式、可用工具和技能。

## 创建新角色

创建新角色时，请在 `roles/` 目录下创建 YAML 文件，格式如下：

**方式1：显式指定工具列表（推荐）**
```yaml
name: 角色名称
description: 角色描述
user_prompt: 用户提示词（追加到用户消息前，用于引导AI行为）
icon: "图标（可选）"
tools:
    # 添加你需要的工具...
    # ⚠️ 重要：建议包含以下5个内置MCP工具
    - record_vulnerability
    - list_knowledge_risk_types
    - search_knowledge_base
    - list_skills
    - read_skill
enabled: true
```

**方式2：不设置tools字段（使用所有已开启的工具）**
```yaml
name: 角色名称
description: 角色描述
user_prompt: 用户提示词（追加到用户消息前，用于引导AI行为）
icon: "图标（可选）"
# 不设置tools字段，将默认使用所有MCP管理中已开启的工具
enabled: true
```

## ⚠️ 重要提醒：内置MCP工具

**如果设置了 `tools` 字段，请务必在列表中添加以下5个内置MCP工具：**

1. **`record_vulnerability`** - 漏洞管理工具，用于记录发现的漏洞
2. **`list_knowledge_risk_types`** - 知识库工具，列出可用的风险类型
3. **`search_knowledge_base`** - 知识库工具，搜索知识库内容
4. **`list_skills`** - Skills工具，列出可用的技能
5. **`read_skill`** - Skills工具，读取技能详情

这些内置工具是系统核心功能，建议所有角色都包含它们，以确保：
- 能够记录和管理发现的漏洞
- 能够访问知识库获取安全测试知识
- 能够查看和使用可用的安全测试技能

**注意**：如果不设置 `tools` 字段，系统会默认使用所有MCP管理中已开启的工具（包括这5个内置工具），但为了明确控制角色可用的工具范围，建议显式设置 `tools` 字段。

## 角色配置字段说明

- **name**: 角色名称（必填）
- **description**: 角色描述（必填）
- **user_prompt**: 用户提示词，会追加到用户消息前，用于引导AI采用特定的测试方法和关注点（可选）
- **icon**: 角色图标，支持Unicode emoji（可选）
- **tools**: 工具列表，指定该角色可用的工具（可选）
  - **如果不设置 `tools` 字段**：默认会选中**全部MCP管理中已开启的工具**
  - **如果设置了 `tools` 字段**：只使用列表中指定的工具（建议至少包含5个内置工具）
- **skills**: 技能列表，指定该角色关联的技能（可选）
- **enabled**: 是否启用该角色（必填，true/false）

## 示例

参考本目录下的其他角色文件，如 `渗透测试.yaml`、`Web应用扫描.yaml` 等。
