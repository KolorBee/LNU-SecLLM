感谢你考虑为本项目做出贡献！

## 如何贡献

### 报告 Bug

1. 检查 [Issues](https://github.com/LNU-SecLM/项目名/issues) 确认问题未被报告
2. 创建新 Issue，包含：
   - 问题描述
   - 复现步骤
   - 预期行为 vs 实际行为
   - 环境信息（操作系统、版本号）
   - 截图或日志

### 提出新功能

1. 先在 [Discussions](https://github.com/LNU-SecLM/项目名/discussions) 讨论
2. 获得认可后创建 Feature Request
3. 等待审核通过

### 提交代码

#### 1. 准备环境

```bash
# Fork 并克隆
git clone https://github.com/你的用户名/项目名.git
cd 项目名

# 添加上游仓库
git remote add upstream https://github.com/LNU-SecLM/项目名.git

# 创建分支
git checkout -b feature/your-feature
2. 代码规范
命名规范：

变量/函数：camelCase
类名：PascalCase
常量：UPPER_SNAKE_CASE
文件名：kebab-case
注释规范：

def process_data(data: dict) -> dict:
    """
    处理数据
    
    Args:
        data: 输入数据
        
    Returns:
        处理结果
    """
    pass
3. 提交规范
使用 Conventional Commits：

<类型>(<范围>): <描述>

[可选的详细说明]
类型：

feat: 新功能
fix: Bug 修复
docs: 文档更新
style: 代码格式
refactor: 重构
test: 测试
chore: 构建/工具
示例：

feat(auth): 添加 OAuth2 登录

- 实现 GitHub 认证
- 添加用户缓存

Closes #123
4. 提交 PR
提交前检查：

# 运行测试
npm test

# 代码检查
npm run lint

# 格式化
npm run format
PR 要求：

清晰的标题和描述
关联相关 Issue
更新相关文档
添加测试用例
至少 1 人 Review
开发流程
# 1. 同步上游
git fetch upstream
git rebase upstream/main

# 2. 开发功能
# ... 编码 ...

# 3. 提交代码
git add .
git commit -m "feat: 添加新功能"

# 4. 推送分支
git push origin feature/your-feature

# 5. 创建 PR
# 在 GitHub 上创建 Pull Request
代码审查
所有 PR 需要至少 1 位核心成员 Review
解决所有审查意见
确保 CI 检查通过
由维护者合并
文档贡献
文档同样重要！你可以：

修正错误
改进清晰度
添加示例
翻译文档


行为准则
尊重他人
包容不同观点
专注于建设性讨论
禁止骚扰和攻击
需要帮助？
💬 讨论区
📧 邮箱：
📚 新手指南
再次感谢你的贡献！🎉