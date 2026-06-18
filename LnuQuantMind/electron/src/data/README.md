# data

用途：静态数据与配置数据。

## 说明
- 归属路径：electron\src\data
- 修改本目录代码后请同步更新本 README
- 增强指数策略模板显式包含 `market` 参数以匹配基准权重字段
- 行业轮动、风险平价、止损止盈已改为兼容实现（仅依赖当前 Qlib 能力）
- 权重策略模板统一为标准字段（`id/category/difficulty/code`）
- 2026-03-29：TopK 系列模板默认调仓比例统一为 20%（`n_drop = topk * 20%`）。
