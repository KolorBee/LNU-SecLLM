# QuantMind 模拟交易模块全面重构设计

> 文档日期：2026-06-12
> 适用范围：`backend/services/trade/` 模拟交易链路
> 目标系统：企业级、多租户、可审计、可回放的仿真交易子系统

---

## 1. 背景与重构目标

当前模拟交易模块已经暴露出一组结构性问题，已不适合继续通过局部补丁维持：

- 非交易时间仍可直接成交
- 调仓调度依赖分钟级字符串匹配，存在漏执行
- Redis 账户 JSON 被当作事实源，缺少完整持久化账本
- Settler、手动下单、托管执行存在多条并行写账路径
- 除权除息、分红送转等公司行为缺少正式建模
- 资产估值口径不统一，Redis/DB/实时行情之间频繁漂移
- 融资融券路径与普通多头路径使用不同记账语义
- 多租户与策略隔离边界不稳固

本次重构目标不是“修复若干 bug”，而是把模拟交易重构为一套正式的仿真交易系统：

- 以 PostgreSQL 持久化账本为事实源
- 以 Redis 作为缓存、锁和运行态补充，而非唯一真相
- 统一订单、撮合、成交、持仓、现金流水、快照的领域模型
- 统一交易所规则、费用规则、交易时段、整手规则、涨跌停规则
- 正式支持公司行为处理与日终盯市
- 正式支持调度幂等、补偿执行、执行审计
- 支持从账本重建任意时点账户状态

---

## 2. 重构原则

### 2.1 单一事实源

- 所有订单、成交、持仓、现金流水、日终快照必须落 PostgreSQL
- Redis 中的账户快照只能视为“派生缓存”
- 任一时刻都必须可以从 DB 重新构建账户状态

### 2.2 单一撮合入口

- 所有模拟盘成交都必须经过统一撮合引擎
- 禁止 Settler、Scheduler、Order API 分别直接改账户余额
- 禁止“拿到信号就 update_balance”的旁路写账方式

### 2.3 事件驱动记账

- 账户状态由事件推导，不由调用方直接覆盖
- 关键事件包括：订单创建、订单接受、成交、撤单、费用计提、利息计提、公司行为调整、日终估值

### 2.4 交易规则与估值规则解耦

- 交易是否可成交，由撮合规则决定
- 资产如何估值，由盯市与公司行为处理决定
- 调度何时触发，由任务执行器决定

### 2.5 多租户强隔离

- 所有核心表必须包含 `tenant_id`、`user_id`
- 与策略绑定的数据额外包含 `strategy_id`
- 所有查询、聚合、重建、调度都必须显式带隔离条件

### 2.6 Prefix 股票代码统一

- 全链路只使用 Prefix 格式，如 `SH600519`
- 所有外部输入在进入领域层前统一转换
- 遗留后缀格式仅允许存在于适配层

---

## 3. 目标架构

### 3.1 分层结构

1. 接入层
- `routers/simulation*.py`
- 负责鉴权、参数校验、幂等键、响应封装

2. 应用服务层
- 负责用例编排，如“提交订单”“执行调仓计划”“日终结算”
- 不直接改账户 JSON

3. 领域层
- 订单、成交、持仓、现金账本、公司行为、估值、调度任务
- 定义领域规则和状态转移

4. 基础设施层
- PostgreSQL
- Redis
- 行情服务
- 交易日历
- 公司行为数据源

### 3.2 运行时组件

建议形成以下核心组件：

- `SimulationOrderServiceV2`
- `SimulationMatcher`
- `SimulationLedgerService`
- `SimulationPositionService`
- `SimulationValuationService`
- `SimulationCorporateActionService`
- `SimulationScheduleExecutor`
- `SimulationAccountProjectionService`

其中：

- `Matcher` 决定订单何时、以何价成交
- `LedgerService` 负责生成现金与仓位流水
- `ProjectionService` 负责把账本投影为账户快照并写 Redis

---

## 4. 领域模型设计

### 4.1 核心实体

#### A. simulation_accounts

账户主实体，只保存账户元信息，不保存可变持仓明细：

- `tenant_id`
- `user_id`
- `account_id`
- `base_currency`
- `account_type`：`cash | margin`
- `status`
- `created_at`

#### B. simulation_orders

订单意图：

- `tenant_id`
- `user_id`
- `strategy_id`
- `account_id`
- `order_id`
- `client_order_id`
- `symbol`
- `side`
- `position_side`
- `trade_action`
- `order_type`
- `time_in_force`
- `quantity`
- `price`
- `trigger_source`：`manual | hosted | rebalance | recovery`
- `status`
- `rejected_reason`
- `trading_session_date`
- `submitted_at`
- `expires_at`

#### C. simulation_fills

成交明细：

- `fill_id`
- `order_id`
- `tenant_id`
- `user_id`
- `symbol`
- `fill_price`
- `fill_quantity`
- `gross_amount`
- `commission`
- `stamp_duty`
- `transfer_fee`
- `borrow_fee`
- `executed_at`
- `price_source`
- `session_phase`

#### D. simulation_cash_ledger

现金流水，替代“直接改 cash”：

- `ledger_id`
- `account_id`
- `tenant_id`
- `user_id`
- `event_type`
- `ref_type`
- `ref_id`
- `amount`
- `currency`
- `balance_after`
- `trade_date`
- `occurred_at`

事件示例：

- `BUY_SETTLEMENT`
- `SELL_PROCEEDS`
- `COMMISSION`
- `STAMP_DUTY`
- `TRANSFER_FEE`
- `MARGIN_INTEREST`
- `SHORT_PROCEEDS_FREEZE`
- `SHORT_PROCEEDS_RELEASE`
- `DIVIDEND_CASH`
- `MANUAL_ADJUSTMENT`

#### E. simulation_position_lots

持仓批次表，支持成本追踪与公司行为调整：

- `lot_id`
- `account_id`
- `tenant_id`
- `user_id`
- `symbol`
- `position_side`
- `open_fill_id`
- `open_date`
- `quantity_open`
- `quantity_remaining`
- `cost_price`
- `cost_amount`
- `status`

建议采用 lot 级模型，而不是只维护 symbol 聚合仓位，这样后续处理：

- 成本核算
- 部分平仓
- T+1 可卖数量
- 分红送转
- 回放审计

都会更清晰。

#### F. simulation_position_daily

账户日终仓位快照：

- `tenant_id`
- `user_id`
- `account_id`
- `trade_date`
- `symbol`
- `position_side`
- `quantity`
- `available_quantity`
- `cost_price`
- `close_price`
- `market_value`
- `unrealized_pnl`

#### G. simulation_account_daily

账户日终快照：

- `tenant_id`
- `user_id`
- `account_id`
- `trade_date`
- `cash`
- `available_cash`
- `frozen_cash`
- `long_market_value`
- `short_market_value`
- `total_asset`
- `liabilities`
- `equity`
- `daily_pnl`
- `total_pnl`
- `maintenance_margin_ratio`

#### H. simulation_corporate_actions

公司行为表：

- `symbol`
- `action_type`：`dividend | split | reverse_split | rights_issue | bonus_share`
- `ex_date`
- `effective_date`
- `cash_dividend_per_share`
- `share_ratio`
- `rights_price`
- `source`

#### I. simulation_jobs

调度与执行任务表：

- `job_id`
- `tenant_id`
- `user_id`
- `strategy_id`
- `job_type`：`rebalance | snapshot | interest | corporate_action`
- `schedule_type`
- `planned_run_at`
- `window_start_at`
- `window_end_at`
- `status`
- `attempt_count`
- `last_error`
- `idempotency_key`
- `started_at`
- `finished_at`

---

## 5. 核心流程设计

### 5.1 提交订单流程

`Signal / Manual Request -> Order Intent -> PreCheck -> Accepted/Rejected`

执行步骤：

1. 统一标准化股票代码
2. 读取交易日历与市场时段
3. 校验是否在允许接单窗口
4. 校验停牌、涨跌停、整手、持仓可卖数、购买力
5. 生成订单
6. 写 `simulation_orders`
7. 投递给 `SimulationMatcher`

注意：

- 非交易时间默认不直接成交
- 可配置为：
  - 拒单
  - 进入下一交易时段等待撮合

### 5.2 撮合成交流程

`Accepted Order -> Matcher -> Fill -> Ledger -> Projection`

统一撮合规则：

- 仅在有效交易时段内成交
- A 股午休不可成交
- 非交易日不可成交
- 市价单按最新可用价格成交
- 限价单需要满足可成交性
- 涨停不可买、跌停不可卖
- 停牌不可成交
- 数量必须满足最小交易单位

撮合完成后：

1. 写 `simulation_fills`
2. 写现金流水
3. 写持仓批次变化
4. 更新订单状态
5. 重建账户投影
6. 刷新 Redis 实时快照

### 5.3 调仓任务流程

`Hosted Schedule -> Rebalance Plan -> Orders -> Matcher -> Ledger`

重构后调仓不再直接修改账户，而是：

1. 调度器生成调仓任务
2. 读取指定 `strategy_id` 最新有效信号
3. 基于账户当前持仓生成目标权重差异
4. 生成卖单与买单计划
5. 分阶段下单
6. 由统一撮合引擎处理成交

这样可避免当前 Settler 路径与手动下单路径分裂。

### 5.4 日终结算流程

`Close -> Valuation -> Interest -> Snapshot`

建议固定拆成 4 个任务：

1. 收盘持仓盯市
2. 费用与融资融券利息计提
3. 公司行为应用
4. 生成账户与持仓日快照

### 5.5 账户查询流程

查询优先级：

1. 优先读 Redis 投影快照
2. Redis miss 或版本落后时，从 DB 重建
3. 重建后回写 Redis

禁止：

- 现金从 Redis 取，仓位从 DB 聚合，价格再从另一路行情补
- 单次请求内拼接多个口径的半成品结果

---

## 6. 交易规则设计

### 6.1 交易时间规则

必须显式建模以下会话：

- `PRE_OPEN`
- `CONTINUOUS_AM`
- `LUNCH_BREAK`
- `CONTINUOUS_PM`
- `AFTER_CLOSE`
- `CLOSED`

基础规则：

- 非交易日不可成交
- 开盘前提交的订单，进入待撮合队列
- 午休期间订单可接受但不可成交
- 收盘后订单保留到下一交易日或按配置失效

### 6.2 价格规则

- 行情价格必须统一口径
- 成交价与估值价分离
- 成交价优先使用实时成交参考价
- 若实时行情缺失，可降级到最近可用交易价，但必须打标 `price_source`
- 禁止随机价格兜底

### 6.3 整手与最小价位

- 主板/创业板/北交所默认 100 股
- 科创板按规则配置
- 卖出可支持零股清仓，但需显式规则化
- 价格必须按最小价位单位对齐

### 6.4 T+1 与可卖数量

建议新增：

- `quantity_total`
- `quantity_available`
- `quantity_frozen`

买入成交当日：

- `quantity_total` 增加
- `quantity_available` 不增加或按规则增加

次一交易日：

- 由结算任务释放为可卖数量

### 6.5 融资融券规则

融资融券单独建模，不与普通多头共用简化字段：

- 多头持仓
- 空头持仓
- 负现金融资
- 融券卖出所得冻结
- 维保比例
- 强平线与预警线

建议为 `margin` 账户单独维护：

- `cash_balance`
- `financing_debt`
- `short_proceeds_frozen`
- `short_market_value`
- `equity`

---

## 7. 公司行为与除权除息处理

这是当前系统最需要补齐的核心能力之一。

### 7.1 设计原则

- 交易成交记录永远保留原始成交事实
- 公司行为不修改历史成交
- 公司行为通过“调整事件”影响持仓批次、成本和现金流水

### 7.2 支持的公司行为

- 现金分红
- 送股
- 转增
- 拆股
- 合股
- 配股

### 7.3 处理方式

#### 现金分红

- 以 `ex_date` 持仓为基准
- 生成 `DIVIDEND_CASH` 现金流水
- 除息后估值使用除权价

#### 送股/转增/拆股

- 调整 `quantity_remaining`
- 按比例摊薄 `cost_price`
- 不改历史 fill

#### 配股

- 若仿真规则选择自动参与，则生成买入型调整事件
- 若不自动参与，则只记录权利但不执行

### 7.4 数据要求

必须有正式公司行为数据表或统一数据接入，不允许仅靠复权因子推测所有权益变化。

复权因子只能用于价格换算，不能代替：

- 分红现金入账
- 股数增加
- 成本重置

### 7.5 处理时点

建议由日终任务或开盘前任务执行：

- `corporate_action_apply(ex_date)`
- 写审计日志
- 生成账户/仓位变更事件

---

## 8. 调度系统重构

### 8.1 当前问题

- 依赖分钟字符串匹配
- 轮询抖动即可能漏执行
- 无正式任务状态
- 无补偿逻辑
- 无统一幂等键

### 8.2 目标设计

调度系统要从“时间判断函数”升级为“任务执行器”。

任务状态建议：

- `PENDING`
- `READY`
- `RUNNING`
- `SUCCEEDED`
- `FAILED`
- `SKIPPED`
- `EXPIRED`

### 8.3 执行机制

每个调仓计划至少包含：

- 计划时间
- 允许执行窗口
- 账户
- 策略
- 交易日
- 幂等键

执行时：

1. 扫描 `window_start_at <= now <= window_end_at`
2. 获取分布式锁
3. 原子更新任务状态到 `RUNNING`
4. 执行调仓逻辑
5. 写结果与审计

### 8.4 补偿策略

若在窗口内因依赖异常未执行：

- 保持 `FAILED`
- 若仍在窗口内允许重试
- 超过窗口改 `EXPIRED`
- 可配置“是否允许补跑”

### 8.5 交易日历

必须统一使用交易日历服务：

- 判断是否交易日
- 下一交易日
- 盘中 session
- 特殊半日市

---

## 9. 账户投影与缓存设计

### 9.1 原则

Redis 只存投影，不存唯一事实。

建议保留：

- `simulation:account:{tenant}:{user}`
- `simulation:positions:{tenant}:{user}`
- `simulation:job-lock:*`

### 9.2 投影内容

Redis 账户快照建议只保存：

- `account_version`
- `snapshot_at`
- `cash`
- `available_cash`
- `frozen_cash`
- `long_market_value`
- `short_market_value`
- `total_asset`
- `equity`
- `liabilities`
- `positions`

### 9.3 重建机制

投影由 `ProjectionService` 统一生成：

- 来自最新账本版本
- 带版本号
- 带来源时间

API 查询时若发现：

- key 不存在
- 版本落后
- 结构不合法

则自动从 DB 重建。

---

## 10. 数据迁移方案

### 10.1 迁移原则

- 不直接丢弃旧链路
- 新旧双轨运行一段时间
- 先建账本，再切写路径，再切读路径

### 10.2 迁移阶段

#### Phase 1：补表与建模

- 新增账本表、持仓批次表、调度任务表、公司行为表
- 保留旧 Redis 账户逻辑

#### Phase 2：新成交写双份

- 新撮合链路写：
  - 旧 `sim_orders/sim_trades`
  - 新 `simulation_orders/simulation_fills/cash_ledger/position_lots`

#### Phase 3：投影改由新账本生成

- `/simulation/account`
- `/simulation/trades`
- `/simulation/snapshots`

全部优先读新账本投影

#### Phase 4：下线旧路径

- 下线 `SimulationSettler.update_balance` 直写
- 下线 `_update_balance_margin` 账户覆写逻辑
- 下线“只写 Redis 不写账本”的链路

### 10.3 旧账户迁移

可按以下方式初始化新账本：

1. 从 `sim_trades` 回放生成多头成交历史
2. 从 Redis 当前账户读取补充基线现金与持仓
3. 对无法可靠回放的历史空头账户，做一次“迁移基准快照”入库
4. 从迁移日开始完全由新账本接管

对无法精确还原的历史数据，必须记录：

- `migration_source`
- `migration_batch_tag`
- `is_seeded_snapshot`

---

## 11. API 收敛建议

### 11.1 保留的外部语义

- `POST /api/v1/simulation/orders`
- `GET /api/v1/simulation/orders`
- `GET /api/v1/simulation/trades`
- `GET /api/v1/simulation/account`
- `POST /api/v1/simulation/reset`

### 11.2 内部改造方向

- 订单接口只负责提交订单
- 不再直接执行账户写账
- 调仓接口只生成 rebalance job
- 日快照接口只读取持久化快照

### 11.3 新增建议接口

- `POST /api/v1/simulation/rebalance-jobs`
- `GET /api/v1/simulation/rebalance-jobs/{job_id}`
- `POST /api/v1/simulation/admin/rebuild-account`
- `POST /api/v1/simulation/admin/replay-trade-date`
- `GET /api/v1/simulation/corporate-actions`

---

## 12. 实施计划

### 阶段一：止血与收口

目标：在不全面切换的情况下先消除高风险写账分叉。

- 禁止 Settler 直接 `update_balance`
- 托管调仓统一走订单创建与撮合链路
- 修复非交易时段成交
- 修复调度严格等值匹配
- 修复多租户/策略隔离缺失

### 阶段二：建立账本内核

- 落 `simulation_orders_v2`
- 落 `simulation_fills`
- 落 `simulation_cash_ledger`
- 落 `simulation_position_lots`
- 新增账户投影服务

### 阶段三：建立估值与公司行为引擎

- 日终盯市
- 分红送转处理
- 融资融券计息入账
- 日快照生成

### 阶段四：切读与切写

- 账户查询切到新投影
- 持仓查询切到新账本
- 下线旧 Redis 直写逻辑

### 阶段五：审计与回放

- 增加 replay 工具
- 增加账本对账工具
- 增加任务执行审计与报警

---

## 13. 测试策略

### 13.1 单元测试

- 交易时段校验
- 整手与最小价位
- 限价单撮合
- 涨跌停约束
- T+1 可卖
- 融资融券开平仓
- 公司行为应用

### 13.2 集成测试

- 调仓任务从信号到成交全链路
- Redis 投影与 DB 重建一致性
- 日终快照生成
- 多租户隔离

### 13.3 回归测试

重点覆盖当前已知痛点：

- 非交易时间不能成交
- 午休不成交
- 除权后总资产不突变
- 分红后现金正确增加
- 调度不漏触发
- 重试不重复下单
- 手动下单与托管调仓口径一致

### 13.4 审计测试

- 任意账户可按交易日回放
- 任意快照可追溯到成交与流水
- 任一持仓数量可追溯到 lot 变化

---

## 14. 需要明确的产品决策

在正式开发前，建议先统一以下策略口径：

1. 非交易时间提交的订单是拒单，还是排队到下一交易时段？
2. 午休时间是否允许接受订单但延迟成交？
3. 模拟盘默认采用 T+1 还是允许当日回转？
4. 市价单在无实时行情时是否允许使用上一笔可用价成交？
5. 配股在模拟盘中默认自动参与还是默认忽略？
6. 融资融券账户是与普通账户共存，还是单独开户模型？
7. 历史旧账户无法完全回放时，是否接受“迁移基准快照”方案？

---

## 15. 推荐落地顺序

如果目标是“先稳定线上，再逐步重构”，建议顺序如下：

1. 先收口成交入口
2. 再改调度执行模型
3. 再建现金流水与持仓批次账本
4. 再切账户查询到新投影
5. 最后补公司行为与完整回放能力

这个顺序的好处是：

- 可以先解决“非交易时间成交、未按设定时间执行”这类线上痛点
- 可以避免一上来就做全量数据迁移
- 可以把最难的“除权与账本回放”放到内核稳定后完成

---

## 16. 结论

模拟交易模块已经不适合继续围绕 `Redis account JSON + 多路径 update_balance` 迭代。建议正式转向：

- PostgreSQL 账本为核心
- 统一撮合引擎为唯一成交入口
- Redis 投影为实时缓存
- 公司行为与日终估值为正式子系统
- 调度器升级为有状态任务执行器

该方案能直接对应当前最关键的使用问题：

- 非交易时间成交
- 除权导致权益计算错误
- 无持久化可回放账本
- 未按设定时间执行
- 多条执行链路口径不一致

后续实施时，应优先完成“成交入口收口 + 调度收口 + 账本建模”三件事，再进入持仓快照、公司行为和全面切流阶段。

---

## 17. 当前实施状态（2026-06-12）

截至 2026-06-12，本方案的主干改造已进入“新账本运行、旧表迁移兼容”的阶段，状态如下：

### 17.1 已完成

- 非交易时段成交拦截已落地，模拟成交仅允许发生在 A 股交易时段
- 托管调度已从“分钟字符串严格相等”改为“执行窗口”模型，并补齐 `pending/ready/running/skipped/expired/succeeded/failed` 状态流转
- 手动下单、托管调仓、影子盘、Paper Broker 已统一收口到单一模拟下单与撮合链路
- 模拟/影子盘订单已补齐 `client_order_id / time_in_force / expires_at` 订单意图字段，并开始使用 `client_order_id` 做提交幂等
- 新账本核心表已落地并接入运行：
  - `simulation_orders`
  - `simulation_fills`
  - `simulation_cash_ledger`
  - `simulation_position_lots`
  - `simulation_accounts`
  - `simulation_account_daily`
  - `simulation_position_daily`
  - `simulation_corporate_actions`
  - `simulation_rebalance_jobs`
- 账户读取已优先基于账本投影，不再把 Redis 账户 JSON 作为唯一事实源
- 已支持旧 `sim_trades` 回放到账本投影，降低历史账户迁移成本
- 已支持公司行为入账与日终快照生成
- 已支持账户重建、历史回放、任务审计、账户审计等管理能力

### 17.2 当前运行口径

- 订单事实源：`simulation_orders`
- 成交事实源：`simulation_fills`
- 账户与持仓事实源：
  - `simulation_accounts`
  - `simulation_cash_ledger`
  - `simulation_position_lots`
- Redis 当前仅作为：
  - 运行态缓存
  - 账户投影视图缓存
  - 锁与幂等辅助
- 模拟账户缓存已补齐 `account_version` 与 `snapshot_at` 元数据，并在读路径发现结构损坏时自动从账本重建

### 17.3 旧链路现状

- 运行态已不再继续写入旧 `sim_orders/sim_trades`
- 旧表仅保留以下用途：
  - 历史回放素材
  - 迁移兼容入口
  - 对账审计辅助视图

### 17.4 剩余建议收口项

- 继续缩减仅用于审计的旧 `sim_trades` 聚合辅助逻辑，避免后续被误接回主链路
- 将 README 中更早期的历史描述逐步整理为“演进记录”与“当前事实”两层，减少口径混淆
- 在更大范围补齐公司行为、调度窗口、迁移回放的端到端回归用例
