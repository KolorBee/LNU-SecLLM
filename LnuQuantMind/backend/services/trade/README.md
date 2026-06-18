# quantmind-trade

交易核心服务（订单、成交、持仓、模拟盘、风控）。

## 重构设计文档

- 模拟交易模块全面重构设计：`docs/simulation_trading_rearchitecture_2026-06.md`

## 重构进展（2026-06-13，第三十四阶段代码债务清理）

- `/api/v1/real-trading/status` 新增 `next_scheduled_execution`：
  - 当运行中策略为 `SIMULATION` 且带有 `live_trade_config` 时，接口会直接返回下一次预计调度窗口的 `trade_date / phase / target_at / window_start_at / window_end_at`；
  - 用于直接判断“下一次是否会按设定时间执行”，不再需要人工结合 `rebalance_days + started_at + 交易日历` 反推。
- 模拟盘原生策略启动链路说明补齐：
  - `SIMULATION` 下若命中 `STRATEGY_CONFIG` 且没有 `on_tick`，`/api/v1/real-trading/start` 会在沙箱启动成功后尝试触发一次 `simulation_native_bootstrap` 托管任务；
  - 该 bootstrap 只负责“启动时立即引导一轮”，与 `SimulationHostedScheduler` 的定时调度是两条链路；若启动时已经错过配置时间窗，bootstrap 不会补跑当日定时窗口。
- `/api/v1/simulation/account` 与 `SimulationProjectionService.build_cache_payload()` 修复“持仓明细与账户聚合脱节”问题：
  - 当 `simulation_position_lots` 已能投影出持仓时，`market_value / long_market_value / short_market_value / total_asset` 统一按持仓明细实时重算；
  - 不再盲信 `simulation_accounts.long_market_value / short_market_value` 这类可能滞后的聚合字段，避免出现“持仓数量 > 0，但持仓市值为 0、浮盈亏非 0”的脏展示。

- `SimulationExecutionEngine` 方法签名中 `SimOrder` 类型统一改为 `Any`，消除旧类型在运行态方法上的硬依赖，保持向后兼容。
- `SimulationSettler.run_daily_settlement` 的 `user_id` 参数类型从 `int` 放宽为 `str | int`，与账本层统一口径。
- `margin_interest_scanner` 清理了重复的 `redis_client` import。
- `_build_realtime_positions_from_db` 函数标注为 `[DEPRECATED]`，明确仅用于审计兼容，常规读路径应使用 `simulation_position_lots` 投影。

## 重构进展（2026-06-13，第三十五阶段强制平仓与保证金监控）

- 新增 `SimulationMarginMonitorService`（`margin_monitor_service.py`），后台扫描融资融券账户：
  - `maintenance_margin_ratio < 1.3`（警戒线）：写入 `MARGIN_WARNING` 现金流水，24 小时内不重复告警
  - `maintenance_margin_ratio < 1.1`（平仓线）：按 FIFO 平仓空头仓位直到 ratio 恢复至 1.3 以上
  - 强制平仓通过 `SimulationOrderSubmissionService` 统一下单，不走旁路
  - 平仓后自动从账本投影重建 Redis 缓存
- 环境变量配置：`SIM_MARGIN_MONITOR_ENABLED`、`SIM_MARGIN_MONITOR_INTERVAL_SECONDS`、`SIM_MARGIN_WARNING_RATIO`、`SIM_MARGIN_LIQUIDATION_RATIO`

## 重构进展（2026-06-13，第三十六阶段日终结算流程）

- 新增 `SimulationEodService`（`eod_service.py`），交易日收盘后（默认 15:05 上海时间）统一执行日终结算：
  1. 按 `simulation_position_lots` + 最新收盘价重算所有账户 `long_market_value / short_market_value / total_asset / equity`
  2. 触发 `SimulationDailySnapshotService.replace_daily_snapshot()` 写入日快照
  3. 触发 `SimulationFundSnapshotService.capture_all()` 写入资金快照
  4. 检查是否有未结算 pending 订单，记录告警日志
  5. 从账本投影重建 Redis 缓存（确保盘后缓存一致）
- 环境变量配置：`SIM_EOD_ENABLED`、`SIM_EOD_TRIGGER_TIME`

## 重构进展（2026-06-13，第三十七阶段旧表退役标记）

- `SimOrder` / `SimTrade` ORM 模型已添加 `[DEPRECATED]` docstring，明确标注仅用于迁移回放与审计兼容，运行态必须使用 `SimulationOrderV2` / `SimulationFill`。
- `/api/v1/real-trading/preflight` 中模拟盘数据表检查已重构：
  - 必需表变更为 `simulation_orders / simulation_fills / simulation_accounts / simulation_fund_snapshots`
  - `sim_orders / sim_trades` 降级为 legacy 表，缺失时仅告警不阻断

## 重构进展（2026-06-12，第一阶段收口）

- `SimulationExecutionEngine` 新增交易时段门禁，模拟订单仅允许在 A 股交易时段内撮合成交，非交易时间会直接拒绝，避免“休市也能成交”。
- `SimulationHostedScheduler` 从“严格等于某一分钟”改为“触发窗口匹配”，默认允许在配置时点后的 `90` 秒窗口内触发，降低轮询抖动导致的漏执行概率。
- `SimulationSettler` 不再直接调用 `SimulationAccountManager.update_balance` 旁路改账户，而是统一改为 `SimOrderService + SimulationExecutionEngine` 下单并撮合，开始向“单一成交入口”收口。
- `SimulationSettler` 调仓股数新增按 100 股整手向下取整，避免生成无法被模拟撮合链路接受的非整手数量。

## 重构进展（2026-06-12，第二阶段账本化基础）

- 模拟盘 schema 新增账户账本基础表：
  - `simulation_accounts`
  - `simulation_cash_ledger`
  - `simulation_position_lots`
  - `simulation_account_daily`
  - `simulation_position_daily`
  - `simulation_corporate_actions`
  - `simulation_rebalance_jobs`
- `simulation_fund_snapshots` 已切回模拟盘统一 `SQLAlchemy Base`，避免模拟盘 schema 被拆成两套 metadata。
- 新增 `SimulationLedgerService`，模拟成交完成后会开始同步写入：
  - 账户主表投影
  - 现金流水（买入结算、卖出回款、佣金、印花税、过户费）
  - 持仓批次摘要（当前先覆盖多头买卖与空头开平的基础 lot 变化）
- 当前 `/api/v1/simulation/account` 读路径仍以现有 Redis + `sim_trades` 聚合为主；新账本表已开始积累可追溯数据，为后续切换到账本投影与日终快照奠定基础。

## 重构进展（2026-06-12，第三阶段投影与调度落库）

- `/api/v1/simulation/account` 已开始优先读取 `simulation_accounts` 账户投影；当历史 `sim_trades` 聚合为空时，会优先使用 `simulation_position_lots` 聚合持仓，再回退 Redis 历史持仓。
- 新账本 lot 投影回退路径已修复空头市值符号，回退估值时空头仓位按负市值计入总资产，不再无条件正向累加。
- `SimulationHostedScheduler` 现在会为每次调度触发写入 `simulation_rebalance_jobs`，并记录 `pending -> running -> succeeded/failed` 的任务状态，开始为后续调度审计、补偿执行和任务查询提供持久化基础。

## 重构进展（2026-06-12，第四阶段日快照与公司行为）

- `SimulationFundSnapshotService.capture_all()` 现在在写 `simulation_fund_snapshots` 的同时，也会同步回填：
  - `simulation_account_daily`
  - `simulation_position_daily`
- 新增 `SimulationDailySnapshotService`，按“同租户/同用户/同日替换”的方式生成账户与持仓日快照，为后续日级回放、收益分析与对账提供结构化落库。
- 新增 `SimulationCorporateActionService`，支持基础公司行为自动应用：
  - `dividend`：按持仓批次汇总现金分红，写入 `simulation_cash_ledger`，并同步增加账户现金/权益；
  - `bonus_share / split / reverse_split`：调整 `simulation_position_lots` 的持仓数量与成本单价；
  - 公司行为状态会从 `pending` 更新为 `applied`，并记录 `applied_at`。
- trade 服务启动后新增模拟盘公司行为后台 worker，开始周期性扫描并应用到期公司行为。

## 重构进展（2026-06-12，第五阶段接口层切流）

- `/api/v1/simulation/snapshots/daily` 现在会优先读取 `simulation_account_daily`，仅在新 daily 表无数据时回退到旧 `simulation_fund_snapshots`。
- 新增模拟盘调度任务查询接口：
  - `GET /api/v1/simulation/rebalance-jobs`
- 新增模拟盘公司行为管理接口：
  - `GET /api/v1/simulation/corporate-actions`
  - `POST /api/v1/simulation/corporate-actions`
  - `POST /api/v1/simulation/corporate-actions/apply`
- 至此，新账本里的日快照、调度任务、公司行为已经不再只是后台内部结构，而是可以通过正式接口被前端或运维工具直接消费。

## 重构进展（2026-06-12，第六阶段重建与回放能力）

- 新增模拟盘现金流水查询接口：
  - `GET /api/v1/simulation/cash-ledger`
- 新增模拟盘持仓日快照查询接口：
  - `GET /api/v1/simulation/positions/daily`
- 新增按交易日回放接口：
  - `GET /api/v1/simulation/replay/{snapshot_date}`
  - 基于 `simulation_account_daily + simulation_position_daily` 返回指定日期的账户快照与持仓快照
- 新增账户投影重建接口：
  - `POST /api/v1/simulation/admin/rebuild-account`
  - 通过 `simulation_accounts + simulation_position_lots` 重建当前模拟账户 Redis 投影，并同步回写 trade account cache
- 至此，重构后的模拟盘已经具备基础的“查流水、查日仓、按日回放、重建账户投影”能力，不再完全依赖旧 Redis 账户态进行排障。

## 重构进展（2026-06-12，第七阶段回放扩展与配股）

- `/api/v1/simulation/account` 进一步下压旧 `sim_trades` 口径：当 `simulation_position_lots` 已有投影数据时，当前账户查询会优先使用 lot 投影估值，而不是继续依赖旧成交聚合。
- 新增按交易日回放到当前账户缓存的接口：
  - `POST /api/v1/simulation/admin/replay-trade-date`
  - 支持从 `simulation_account_daily + simulation_position_daily` 直接重建并回写指定交易日的模拟账户缓存，便于对账、回滚与复现实验。
- 公司行为服务新增基础配股处理：
  - `rights_issue` 会在账户现金充足时自动扣减现金、写入 `RIGHTS_SUBSCRIPTION` 现金流水，并新增对应的 long lot；
  - 为后续更完整的公司行为规则扩展提供了基础执行框架。

## 重构进展（2026-06-12，第八阶段历史回迁工具）

- 新增历史成交回放到新账本的管理入口：
  - `POST /api/v1/simulation/admin/replay-legacy-trades`
- 该入口会按当前用户维度读取旧 `sim_trades`，并回放写入：
  - `simulation_accounts`
  - `simulation_cash_ledger`
  - `simulation_position_lots`
- 回放完成后会自动触发一次当前账户投影重建，减少“旧成交表存在、新账本为空”的迁移割裂。
- `/api/v1/simulation/account` 继续下压旧口径依赖：只要 `simulation_position_lots` 已可生成投影，就会优先采用新 lot 投影估值。

## 重构进展（2026-06-12，第九阶段计息与任务 API 完整化）

- `margin_interest_scanner` 已从“旧 Redis key 扫描 + 直接改缓存”切到“新账本账户 + 现金流水”模式：
  - 基于 `simulation_accounts` 计算融资/融券利息；
  - 写入 `simulation_cash_ledger(event_type=MARGIN_INTEREST)`；
  - 同步更新账户投影，并回写模拟账户/交易账户缓存。
- `rebalance-jobs` 补齐了完整接口能力：
  - `POST /api/v1/simulation/rebalance-jobs`
  - `GET /api/v1/simulation/rebalance-jobs/{job_id}`
- 至此，调度任务已经不仅能后台自动写入，也支持主动创建和按 ID 查询，进一步靠近文档中的“任务执行器”目标。

## 重构进展（2026-06-12，第十阶段 T+1 / 可卖数量）

- `simulation_position_lots` 现在不只用于成本追踪，也开始参与 `T+1` 可卖数量计算。
- `SimulationProjectionService` 新增按 lot 计算 `available_quantity` 的逻辑：
  - long 仓位当日买入数量默认不可卖；
  - short 仓位维持当前剩余数量可用。
- `SimulationExecutionEngine` 的卖出撮合前新增 `available_quantity` 校验：
  - 当日新开的 long 仓位不足以满足卖出数量时，会返回
    `Insufficient available holdings for sell order (T+1 restriction)`。
- 至此，新账本 lot 模型已经从“仅记录成本/批次”扩展到“直接参与真实交易规则约束”。

## 重构进展（2026-06-12，第十一阶段账户对账视图）

- 新增模拟盘账户对账接口：
  - `GET /api/v1/simulation/admin/account-audit`
- 该接口会并行输出三套账户视图，便于迁移核对与灰度切流：
  - `redis_cache`
  - `ledger_projection`
  - `trade_history_aggregate`
- 返回结果包含：
  - `cash / available_cash / market_value / total_asset / initial_equity` 差异
  - `positions_only_in_left / positions_only_in_right`
  - 同名仓位的 `volume / available_volume` 差异
- `/api/v1/simulation/account` 同步修正 `valuation_source`：
  - 当已使用 `simulation_position_lots` 投影估值时，返回 `simulation_position_lots_projection`
  - 仅在旧成交聚合口径生效时，才返回 `sim_trades_plus_realtime_quote`

## 重构进展（2026-06-12，第十二阶段订单/成交事实建模）

- 模拟盘新增账本原生订单/成交表：
  - `simulation_orders`
  - `simulation_fills`
- `SimOrderService.create_order()` 现在直接落 `simulation_orders`，保留：
  - `client_order_id`
  - `account_id`
  - `strategy_id`
  - `time_in_force`
  - `trigger_source`
  - `trading_session_date`
  - `expires_at`
- `SimulationExecutionEngine.apply_filled()` 现在直接落 `simulation_fills`，保留：
  - `order_id`
  - `gross_amount`
  - `commission / stamp_duty / transfer_fee`
  - `price_source`
  - `session_phase`
- `/api/v1/simulation/trades` 已开始优先读取 `simulation_fills`；旧 `sim_trades` 仅在迁移回放时作为历史来源使用。

## 重构进展（2026-06-12，第十三阶段外部持仓快照账本化）

- `/api/v1/simulation/sync/confirm` 不再通过 `init_account + update_balance` 只改 Redis 账户。
- 新增 `SimulationSeedService`，把 OCR/手工确认后的外部持仓快照直接落为种子账本：
  - 重建 `simulation_accounts`
  - 写入 `simulation_cash_ledger(MANUAL_ADJUSTMENT)`
  - 写入 `simulation_position_lots`
- 该路径会在落账本后自动执行一次 `/api/v1/simulation/admin/rebuild-account`，确保 Redis 账户快照重新由账本投影生成。
- 对于这类“外部账户接管”场景，会同时清理该用户旧的 `sim_orders/sim_trades/simulation_orders/simulation_fills`，把新账本快照作为新的接管基准，减少历史旧成交继续污染当前账户视图。

## 重构进展（2026-06-12，第十四阶段调度状态机与读路径去混源）

- `SimulationHostedScheduler` 现在在执行前会先清理过窗未执行任务：
  - `pending/ready -> expired`
  - `last_error` 会记录为执行窗口已过，便于排查“为什么没跑到”
- 调度任务状态流转补齐为：
  - `pending -> ready -> running -> succeeded/failed`
  - 当执行窗口内已存在幂等锁时，会写成 `skipped`
- `/api/v1/simulation/account` 继续去混源：
  - 只要 `simulation_accounts` 已存在，就不再读取旧 `sim_trades` 聚合当前持仓
  - 有 `simulation_position_lots` 时返回 `simulation_position_lots_projection`
  - 无持仓批次但已有账户投影时返回 `simulation_account_projection`
- 这样单次账户查询不再把“新账本账户 + 旧成交聚合 + Redis 仓位兜底”混成一份返回结果，进一步靠近单一事实源目标。

## 重构进展（2026-06-12，第十五阶段影子盘与 Paper Broker 收口）

- 新增 `SimulationOrderSubmissionService`，把“创建模拟订单 -> 标记 submitted -> 统一撮合 -> 写账本 -> 回写投影”抽成单一复用入口。
- `internal_strategy_dispatcher` 的 `SIMULATION/SHADOW` 分支已统一接入该服务：
  - `SHADOW` 不再直接 `SimulationAccountManager.update_balance`
  - 影子盘现在也会生成正式的模拟订单与成交账本记录
- `PaperTradingBroker.place_order()` 也已切到同一条提交链路，不再自己拉行情后直接改 Redis 账户。
- 当前代码库里，`SimulationAccountManager.update_balance()` 的业务调用已收敛到 `SimulationExecutionEngine` 内部单点，外围入口不再直接旁路改账。

## 重构进展（2026-06-12，第十六阶段执行引擎账本优先）

- `SimulationExecutionEngine.execute_order()` 不再在成交前调用 `SimulationAccountManager.update_balance()` 预先改 Redis。
- 新流程改为：
  - 先基于 `simulation_accounts` 投影账户做资金/持仓校验
  - 若投影账户不存在，再回退 Redis/`simulation.settings.initial_cash` 作为种子账户视图
  - 成交后统一写 `simulation_fills + simulation_cash_ledger + simulation_position_lots`
  - 最后从账本投影重建 Redis 模拟账户与 trade account cache
- `SimulationLedgerService.record_trade()` 现在会先基于成交事实推导成交后的现金快照，再同步到账户投影，而不是依赖外部先把缓存改好再回填账本。

## 重构进展（2026-06-12，第十七阶段订单读路径与重置补齐）

- `/api/v1/simulation/orders` 已开始优先读取 `simulation_orders`，并结合 `simulation_fills` 回填：
  - `filled_quantity`
  - `average_price`
  - `filled_value`
  - `commission`
- `simulation_orders` 已补齐 `portfolio_id` 字段，订单列表即使带 `portfolio_id` 过滤也可继续走新表。
- 当新订单/成交读模型暂时为空但旧 `sim_orders/sim_trades` 仍有历史时，服务会先自动回放旧历史到 `simulation_orders/simulation_fills`，再按新表返回。
- 旧 `sim_orders/sim_trades` 的接口级直接读取进一步收缩为迁移兼容兜底，而不是常规查询主路径。
- `SimOrderService` / `SimTradeService` 当前对外已经不再直接返回旧 `SimOrder` / `SimTrade` ORM 结果；旧表仅保留为回放素材与迁移兼容层。
- `/api/v1/simulation/reset` 对历史清理也已扩展到新账本表：
  - `simulation_orders`
  - `simulation_fills`
  - `simulation_cash_ledger`
  - `simulation_position_lots`
  - `simulation_accounts`
  - `simulation_account_daily`
  - `simulation_position_daily`

## 重构进展（2026-06-12，第十八阶段旧订单/成交表退役为迁移层）

- 模拟盘运行态已不再写入旧 `sim_orders/sim_trades`：
  - 下单仅写 `simulation_orders`
  - 成交仅写 `simulation_fills`，再驱动账本与投影更新
- 旧表当前只保留三类职责：
  - 历史回放素材
  - `/api/v1/simulation/admin/replay-legacy-trades` 迁移入口
  - `/api/v1/simulation/admin/account-audit` 的 legacy 回退来源（仅在 `simulation_fills` 为空时启用）
- 这意味着模拟盘当前的单一事实源已经进一步收敛到：
  - 订单事实：`simulation_orders`
  - 成交事实：`simulation_fills`
  - 账户状态：`simulation_accounts` + `simulation_position_lots` + `simulation_cash_ledger`
  - `simulation_rebalance_jobs`
- 这样“重置账户”与“切到新账本做读路径”不再互相打架，避免新旧两套历史表清理范围不一致。

## 重构进展（2026-06-12，第十九阶段模拟盘订单幂等与字段贯通）

- `SimOrderCreate` / `SimOrderResponse` 已补齐并贯通：
  - `client_order_id`
  - `time_in_force`
  - `expires_at`
- `SimTradeResponse` 已补齐 `session_phase`，成交会话段不再只停留在落库层。
- `SimulationOrderSubmissionService` 现在会在模拟/影子盘提交前按
  `tenant_id + user_id + client_order_id` 检查已有 `simulation_orders`：
  - 已存在已成交订单时直接返回已有成交结果
  - 避免内部策略重试或重复投递导致模拟盘重复成交
- `internal_strategy_dispatcher` 的模拟/影子盘分支已接入这条幂等链路，并把 `client_order_id` 回传到调用方。

## 重构进展（2026-06-13，第二十阶段投影缓存版本化）

- `SimulationProjectionService` 新增统一 cache payload builder，模拟账户投影现在会稳定输出：
  - `account_version`
  - `snapshot_at`
  - `cash / available_cash / frozen_cash`
  - `long_market_value / short_market_value / total_asset / equity / liabilities`
  - `positions`
- `/api/v1/simulation/account` 现在会校验 Redis 缓存结构：
  - 若缺少 `account_version` / `snapshot_at`
  - 或 `positions` 结构损坏
  - 或核心数值字段类型不合法
  - 则会自动从账本投影重建并回写 Redis/trade account cache
- `SimulationExecutionEngine` 与 `/api/v1/simulation/admin/rebuild-account` 已统一复用这套投影缓存结构，减少不同入口写出不同 Redis 口径的风险。

## 重构进展（2026-06-13，第二十一阶段订单时效规则生效）

- 模拟盘 `time_in_force` 现在不再只是存储字段：
  - `SimOrderCreate` 仅允许 `DAY / GTD / IOC`
  - `GTD` 强制要求提供 `expires_at`
- `SimulationExecutionEngine` 在撮合前会校验订单是否已过期：
  - 若 `expires_at <= now`，直接拒绝并返回 `Order expired before execution`
- 这样模拟盘订单意图层已经从“字段落库”推进到“字段驱动执行规则”，后续继续扩展午休排队/下一交易日排队时可以复用这套时效基础。

## 重构进展（2026-06-13，第二十二阶段交易会话相位建模）

- `TradingCalendarService.is_trading_time()` 现在除了 `is_trading_time + matched_session`，还会返回标准化 `market_phase`：
  - `PRE_OPEN`
  - `CONTINUOUS_AM`
  - `LUNCH_BREAK`
  - `CONTINUOUS_PM`
  - `AFTER_CLOSE`
  - `CLOSED`
- 当前执行链路仍保持“非交易会话直接拒绝成交”，但午休、盘前、收盘后的相位信息已经可以被统一识别，为下一步实现“接单但延迟到下一有效会话撮合”打下基础。

## 重构进展（2026-06-13，第二十三阶段订单过期状态正式化）

- 模拟盘订单状态新增 `expired`，不再把“已过期”混入 `rejected`：
  - `OrderStatus.EXPIRED` 已贯通模型、查询响应和提交链路
  - `SimulationExecutionEngine.mark_expired()` 会把过期原因落到 `simulation_orders.rejected_reason`
- `/api/v1/simulation/orders` 提交链路与统一提交服务现在都会在遇到
  `Order expired before execution` 时写入正式 `expired` 状态。
- `expired` 状态订单不允许再执行撤单，避免生命周期语义冲突。

## 重构进展（2026-06-13，第二十四阶段持仓冻结量补齐）

- `SimulationProjectionService` 现在会在持仓投影里同时给出：
  - `volume`
  - `available_volume`
  - `frozen_volume`
- long 仓位的 `frozen_volume` 会直接反映 T+1 冻结股数，不再只能由前端自己做 `volume - available_volume` 推导。
- `SimulationDailySnapshotService` 与 `/api/v1/simulation/replay/{snapshot_date}` 已补齐 `frozen_quantity / frozen_volume`：
  - `simulation_position_daily` 会持久化 `frozen_quantity`
  - 从日快照重建缓存时也会保留该字段
- 这样“总持仓 / 可卖 / 冻结”三元关系已经进入投影、快照和回放链路，后续审计与前端展示不再需要二次猜算。

## 重构进展（2026-06-13，第二十五阶段订单触发来源贯通）

- `simulation_orders.trigger_source` 不再固定写成 `manual`，现在会按真实入口贯通：
  - `/api/v1/simulation/orders` -> `manual`
  - `internal_strategy_dispatcher` -> `strategy_dispatch`
  - `PaperTradingBroker` -> `paper_broker`
  - `SandboxSignalConsumer` -> `sandbox_signal`
  - `SimulationSettler` -> `settlement_rebalance`
  - 历史迁移回放继续保留 `legacy_replay`
- `SimOrderResponse` 已补齐 `trigger_source`，订单查询和审计接口可以直接看到真实触发来源。
- 这样后续排查“是谁在非预期时间下了这笔单”“为什么同一账户会出现不同链路的资产漂移”时，不再需要靠备注或日志做反推。

## 重构进展（2026-06-13，第二十六阶段融资融券 Redis 路径收口）

- `SimulationAccountManager._update_balance_margin()` 已从“读 Redis -> Python 计算 -> 回写 Redis”的非原子流程改为 Redis Lua 原子脚本，避免融资融券路径继续存在 TOCTOU 覆盖风险。
- 空头市值不再依赖开平仓增量推算，而是按当前 `positions[*].side=short` 持仓统一重算：
  - 修复同标的连续 `sell_to_open` 时 `short_market_value` 重复累加
  - 修复 `buy_to_close` 部分平仓时按开仓成本扣减导致的剩余空头市值失真
- 这条旧缓存路径现在也会同步刷新新版账户字段：
  - `available_cash`
  - `frozen_cash`
  - `equity`
  - `account_version`
  - `snapshot_at`
  - `rebuild_source=simulation_margin_update`
- 同时顺手收掉 `SimulationExecutionEngine` 的逐实例 `httpx.AsyncClient` 泄漏，改为共享客户端，避免模拟下单高频调用时连接池持续堆积。

## 重构进展（2026-06-13，第二十七阶段非交易时段接单排队）

- 模拟盘统一提交链路不再把“非交易时段下单”直接写成 `rejected`：
  - `PRE_OPEN / LUNCH_BREAK / AFTER_CLOSE / CLOSED`
  - 非交易日
  - 这些场景现在会保留订单为 `pending`
  - `remarks/rejected_reason` 会写入 `Outside A-share trading session, order queued for next valid session`
- `SimulationOrderSubmissionService`、`/api/v1/simulation/orders` 和内部策略模拟/影子盘派发链路已经统一采用这套语义：
  - 可以接单
  - 不会在休市时伪成交
  - 也不会误记成正式拒单
- 新增 `simulation pending order worker`：
  - 后台轮询 `simulation_orders.status=pending`
  - 当进入有效交易会话后推进为 `submitted -> filled/rejected/expired`
  - 这样盘前、午休和收盘后积压的模拟订单不再永远停留在 `pending`
- 当前这一步先实现“会话就绪后自动继续撮合”；更细的产品策略（例如盘后单是否跨日保留、不同 `time_in_force` 的排队失效规则）后续还可以继续下沉到订单时效状态机。

## 重构进展（2026-06-13，第二十八阶段公司行为后账户投影重算）

- `SimulationCorporateActionService` 现在不再只修改 lot 或现金流水后就结束，而是会对受影响账户立即执行一次投影刷新：
  - 重算 `long_market_value`
  - 重算 `short_market_value`
  - 重算 `total_asset`
  - 同步刷新 `equity`
- 这样以下场景不再停留在“半更新状态”：
  - 现金分红后只加了现金、没按除息价重算持仓市值
  - 送股/拆股后 lot 数量已变，但账户仍保留旧市值
- 新增回归覆盖：
  - 分红后 `cash + market_value` 连续，不会凭空抬高总资产
  - 拆股后 stale `long_market_value` 会按最新价格和新股数重建

## 重构进展（2026-06-13，第二十九阶段订单时效状态机收口）

- 非交易时段接单不再只有“统一排队”这一种行为，而是开始真正按 `time_in_force` 区分生命周期：
  - `IOC`：只允许在有效交易会话内立即成交；若提交时处于盘前、午休、盘后或休市日，会直接写成 `expired`，不再进入待执行队列
  - `DAY`：会记录目标 `trading_session_date`
    - 盘前、午休提交：继续以当日为目标会话排队
    - 盘后、休市日提交：自动挂到下一交易日
    - 若目标交易日收盘后仍未执行：自动过期为 `expired`
  - `GTD`：继续允许跨日保留，直到 `expires_at` 命中
- `SimulationExecutionEngine.assess_execution_window()` 现在会统一返回：
  - 当前交易日
  - 目标交易日
  - 最终状态建议（`queued / expired / rejected`）
- `SimulationOrderSubmissionService`、`/api/v1/simulation/orders`、`SimulationPendingOrderWorker` 已统一使用这套状态机：
  - 排队时会把目标交易日写回 `simulation_orders.trading_session_date`
  - worker 不再只会“等待下一次重试”，而是能识别 `DAY` 单已跨过目标会话、`IOC` 单不应排队等正式时效语义
- 新增回归覆盖：
  - `IOC` 非交易时段提交直接过期
  - `DAY` 盘后排队会指向下一交易日
  - `DAY` 待执行订单在目标会话收盘后自动过期

## 重构进展（2026-06-13，第三十阶段旧成交聚合退回显式审计源）

- `_build_realtime_positions_from_trade_history()` 不再默认在 `simulation_fills` 为空时隐式回退到旧 `sim_trades`：
  - 默认空结果会明确返回 `trade_history_aggregate_empty`
  - 这样“成交历史聚合”这一口径正式只代表新账本 `simulation_fills`
- `/api/v1/simulation/admin/account-audit` 若需要对照旧历史聚合，会把它作为单独来源显式展示：
  - `trade_history_aggregate`：新账本成交聚合
  - `legacy_trade_aggregate`：旧 `sim_trades` 聚合，仅在新账本聚合为空时补充
- 这一步的目的不是删除 legacy 能力，而是避免旧 `sim_trades` 在接口语义上继续伪装成当前主链路，降低后续被误接回运行态的风险。
- 新增回归覆盖：
  - 默认成交聚合不再偷偷触发 legacy fallback
  - 审计接口会把 legacy 对照源单独标识出来

## 重构进展（2026-06-13，第三十一阶段迁移回放账号键一致性）

- `SimulationMigrationService.replay_legacy_trades()` 在回放旧 `sim_trades` 时，账本写入现在会统一使用规范化后的新账本 `user_id`，不再把旧表里的裸整型 `user_id` 直接传给 `SimulationLedgerService`。
- 这修复了一个实际风险：旧成交回放时可能把账户、流水、lot 投影写到 `sim:default:8030005`，而不是规范账号 `sim:default:08030005`，导致迁移后出现“回放成功但主账户仍为空”的分叉。
- 同时修复了迁移回放的重复记账问题：回放循环现在会把“成交前快照”传给 `record_trade()`，避免先手工 apply 再由账本服务再 apply 一次，导致 cash/total_asset 被每笔旧成交重复推进。
- 新增回归覆盖：
  - 旧成交回放后，现金账本、持仓 lot、账户主记录会落到规范化账户键
  - lot 剩余数量与现金流水可直接追溯到回放成交序列
  - `admin/replay-trade-date` 写回缓存时会保留 long/short 与冻结量结构

## 重构进展（2026-06-13，第三十二阶段配股资产连续性与代码规范化）

- 公司行为入口与执行链路现在统一把 `symbol` 规范成 Prefix 口径：
  - `/api/v1/simulation/corporate-actions` 创建时就会写入 `SH600519` 这类标准格式
  - `SimulationCorporateActionService` 执行时也会再次规范化，避免历史后缀代码导致 lot 匹配失败
- 为 `rights_issue` 补齐了资产连续性回归：
  - 配股自动参与时会扣减现金、写入 `RIGHTS_SUBSCRIPTION` 现金流水、增加新 long lot
  - 在使用除权后价格重算投影时，`cash + market_value` 保持连续，不会因配股动作凭空抬高或压低总资产
- 同时补上了“自动参与失败”的显式审计痕迹：
  - 当账户现金不足无法参与配股时，不再静默跳过
  - 会写入 `RIGHTS_SUBSCRIPTION_SKIPPED` 的零金额现金流水，并在公司行为 `note` 中记录 `applied/skipped` 账户摘要，便于后续排障与审计

## 重构进展（2026-06-13，第三十三阶段快照审计追溯接口）

- 新增 `GET /api/v1/simulation/replay/{snapshot_date}/audit`：
  - 在按交易日回放快照结果之外，额外返回该快照时点前的
    - `simulation_fills`
    - `simulation_cash_ledger`
    - `simulation_position_lots`
  - 这样“某日快照为什么是这个资产值、这笔持仓来自哪些批次、对应过哪些成交和流水”已经可以直接通过正式接口追出来
- 这一步主要对应设计文档里的审计要求：
  - 任意账户可按交易日回放
  - 任意快照可追溯到成交与流水
  - 任一持仓数量可追溯到 lot 变化

## 修复记录（2026-06-09，模拟盘 user_id 统一 8 位）

- 模拟盘 Redis 主键与设置键统一为 `simulation:account:{tenant}:{8位user_id}` / `simulation:settings:{tenant}:{8位user_id}`。
- `SimulationAccountManager` 增加旧键兼容迁移：检测到 `8030005` 与 `08030005` 并存时自动归并到 8 位键，避免账户分叉。
- `SimulationFundSnapshotService.capture_all` 对扫描结果按归一化 `user_id` 去重并回写规范键，防止 `simulation_fund_snapshots` 同日重复记录。
- `/api/v1/simulation/reset` 清理历史快照时同时覆盖旧 7 位与新 8 位 `user_id`，避免重置后残留历史脏数据。

## 修复记录（2026-06-10，模拟盘托管严格绑定策略最新信号）

- `manual_execution_service.create_hosted_task()` 在 `REAL/SHADOW` 下仍强制使用“当前策略 `strategy_id` 对应的最新完成推理批次”作为托管执行来源；若找不到该策略最新信号、命中兜底批次或超过执行窗口，直接返回 `409` 阻断执行。
- 对 TopK 风格策略，若最新信号批次里没有显式 `BUY/SELL` 方向且策略参数缺少有效 `topk`，系统会直接拒绝执行，不再静默回退成 `topk=50`。
- 目标是让“前端当前启动的策略”和“后端实际托管执行的信号源”保持一一对应，宁可不执行，也不再做默认模型或默认 TopK 的降级替代。
- 模拟盘定时托管严格按 `live_trade_config.sell_time/buy_time` 的配置分钟触发：配置 `14:50` 时 `09:30` 不会触发；配置 `09:30` 时 `10:40` 也不会补触发，防止启动引导或后台调度绕过用户设置。

## 修复记录（2026-06-11，模拟盘启动默认模型兜底）

- 模拟盘启动的 bootstrap 托管在找不到“当前策略最新完成推理”时，会回退消费“当前用户默认模型最新完成推理”，避免所有用户因策略级推理未落库而统一被 409 拦截。
- 该兜底仅对 `SIMULATION` 生效，`REAL/SHADOW` 仍保留策略级强绑定校验，避免影响实盘与影子盘的既有门禁。

## 修复记录（2026-06-02，模拟盘定时托管与收益字段）

- 新增 `SimulationHostedScheduler` 后台任务，扫描 `trade:active_strategy:*` 中运行中的 `SIMULATION` 策略，按 `live_trade_config.sell_time/buy_time/schedule_type` 创建自动托管执行任务。
- 新增 `SimulationRuntimeRestorer`：`quantmind-trade` 容器重启后会从 `trade:active_strategy:*` 恢复模拟盘沙箱进程，避免每日更新代码/重启容器后模拟盘状态丢失。
- 模拟盘启动状态新增 `started_at`，`interval` 调仓日以策略启动日为锚点计算，避免使用交易所全局序号导致“设置每 N 天”与用户预期错位。
- `SimulationHostedScheduler` 新增交易日判断：优先使用 `exchange_calendars` 的 XSHG 日历，依赖不可用时回退工作日，避免周末/非交易日按设置时间误触发模拟盘交易。
- 当 `sell_time == buy_time` 时调度 phase 统一为 `ALL`，支持同一时刻卖买一次性触发；调度锁 `qm:hosted:simulation:*` 防止同一交易日重复排队。
- `/api/v1/simulation/account` 与 `/api/v1/simulation/snapshots/daily` 补充 `daily_return_pct/daily_return_ratio/total_return_pct/total_return_ratio`，前端每日收益率不再从金额字段猜测。
- `/api/v1/simulation/batch/step` 增加租户校验并显式传递 `tenant_id` 给结算器，避免多租户环境落到 `default`。
- `/api/v1/real-trading/status?trading_mode=...` 现在严格按请求模式返回状态；查询实盘时不会串入模拟盘 active strategy，查询模拟盘时也不会被实盘 K8s 状态误判为运行中。
- `/api/v1/simulation/reset` 现在会按当前 `tenant_id + user_id` 清理 `sim_trades/sim_orders/simulation_fund_snapshots` 后再重建 100 万模拟账户，避免重置后交易记录与智能图表继续显示旧数据。

## 修复记录（2026-06-02，模拟盘成交安全与接口收敛）

- 模拟盘前端调用收敛到 `/api/v1/simulation/orders`、`/api/v1/simulation/trades` 与 `/api/v1/simulation/trades/stats/summary`，避免与实盘通用 `/orders`、`/trades` 表混用。
- `SimulationExecutionEngine` 移除行情/数据库均失败后的随机价格兜底，改为拒单，避免伪成交污染账户。
- 模拟盘限价单新增可成交性校验：买入限价低于市价、卖出限价高于市价时拒单；成交价按市价滑点并受限价约束。
- 模拟盘成交补齐 A 股整手校验与卖出印花税/过户费字段，费率可通过 `SIMULATION_STAMP_DUTY_RATE`、`SIMULATION_TRANSFER_FEE_RATE` 配置。
- 修复 `SimulationSettler.run_daily_settlement` 持久化成交时未定义 `tenant_id` 的运行期错误，并在结算更新账户时显式传递租户。

## 路由拆分（2026-04-08）

- `routers/real_trading.py`：聚合入口
- `routers/real_trading_utils.py`：身份、账户快照、预检写回、配置归一等工具
- `routers/real_trading_preflight.py`：`/preflight`、`/trading-precheck`、`/preflight/snapshots/daily`、`/account`
- `routers/real_trading_lifecycle.py`：`/start`、`/stop`、`/status`、`/logs`、`/orders`、`/history`
- `routers/manual_executions.py`：实盘页“手动执行调试”任务入口，支持创建任务、按任务类型查询任务、查询任务级日志
- `routers/internal_strategy.py`：聚合入口
- `routers/internal_strategy_utils.py`：内部网关共享 helper、模型、会话上下文
- `routers/internal_strategy_bridge.py`：`/dispatch/item-status` 与 `/bridge/*`
- `routers/internal_strategy_lifecycle.py`：`/heartbeat`、`/sync-account`、`/order`、`/hosted-executions`
- 拆分后补齐了 `internal_strategy_bridge.py` 对 `internal_strategy_utils.py` 的显式私有符号导入（`_bridge_ws_url`、`_agent_template_root`、`_qmt_agent_release_manifest_key`、`_qmt_agent_release_asset_ttl`、`_qmt_agent_release_local_manifest_path`、`_load_qmt_agent_release_manifest`、`_build_qmt_agent_release_asset`、`_iso_or_none`、`_to_float`、`_compute_account_metrics`、`_get_bridge_session_context`），避免 `import *` 跳过前导下划线名称导致的启动期/运行期 `NameError`。
- `_sync_qmt_account_to_db` 保持为 `internal_strategy_bridge.py` 本文件内的局部实现，用于账户快照入库，不从 utils 重复导入。

## 修复记录（2026-05-21，实盘交易中心 QMT Agent 异常状态提示修复）

- 修复了 `routers/internal_strategy_bridge.py` 中 `get_qmt_binding_status` 接口计算 `stale_reason` 时，因直接使用 `float()` 强转 Redis 缓存中的 `timestamp` 字符串而发生 `ValueError` 的 Bug（`could not convert string to float: '2026-05-18T14:15:50.223414'`）。
- 增加了 `_parse_timestamp` 内部辅助函数，健壮地兼容 numeric 时间戳与 ISO-8601 datetime 格式。
- 优化了前端 `SettingsCenter.tsx` 中对未通过门禁原因 `stale_reason` 的展示逻辑，若其为未知异常或 `error` 时不进行警告块渲染。

## 修复记录（2026-05-18，预检门禁、对账与账本路由异常修复）

- 修复了实盘/模拟盘核心单元测试与预置探针阻断的一系列关键问题：
  - **QMT Agent 对账校验**：`test_qmt_agent_async_reconcile.py` 中的对账 Mock 数据与最新的 UUID 强制过滤规则对齐，将 mock `order_remark` 升级为合规的标准 UUID，并增加了 `.get("exchange_trade_id")` 鲁棒性保护以防止 KeyError。
  - **日账本路由字段鲁棒性**：`routers/real_trading_ledger.py` 中属性读取改为使用 `getattr(row, "payload_json", None)`，解决了单元测试及特殊历史环境下由于 ORM/Mock 行结构字段缺失导致查询日账本抛出 `AttributeError: type object 'Row' has no attribute 'payload_json'` 的阻断性 Bug。
  - **订阅预检模式兼容性**：`test_trade_trading_precheck.py` 中 `test_trading_precheck_blocks_non_pro_subscription` 的订阅级别预检由 `mode="SIMULATION"` 修正为 `mode="SHADOW"`，以兼容最新的“模拟盘免除 Pro 订阅门禁”业务逻辑。
  - **行情探针提示匹配**：修正了 `test_trading_precheck_blocks_when_realtime_market_not_ready` 测试中的断言错误，将行情不新鲜匹配内容调整为 `"行情数据不新鲜"`，符合实际的报警字样拼装。

## 修复记录（2026-05-18，模拟盘“假运行中”与沙箱互相误杀）

- `sandbox/manager.py` 调整了模拟盘 worker 调度策略：
  - `submit_strategy` 改为优先分配“空闲 worker”，不再按 `hash(user_id)` 直接复用 PID；
  - 当所有 worker 都忙时直接返回 `No idle sandbox worker available`，避免把新策略排队到正在运行无限循环的 worker 队列中；
  - 新增 worker 存活清理与池容量自愈逻辑：异常退出的 worker 会被剔除并补齐，失效策略映射会同步清理；
  - `stop_strategy` 增加“共享 PID 保护”：检测到历史脏映射（多个策略共用同一 PID）时拒绝直接 kill，避免一次停止误杀其他策略。
- 新增 `sandbox_manager.is_strategy_running()`，统一给上层状态接口做“策略真实存活”判断。
- `/api/v1/real-trading/status` 在 `SIMULATION` 模式下改为双重判定：
  - 只有 Redis 的 active strategy 标记存在且对应沙箱进程仍存活，才返回 `running`；
  - 若仅有 Redis 标记但进程已退出，返回 `not_running` 并提示“沙箱运行进程未存活，请重新启动模拟盘”。

## 修复记录（2026-05-18，默认模型读取口径对齐）

- `trade` 自动托管链路读取“用户默认模型”时，已去除对 `metadata_json.system_default=true` 的排除条件。
- 修复前：用户在模型管理页面把系统模型（如 `model_qlib`）设为默认后，`trade` 侧会误判为 `missing_default_model`，导致模拟盘到点无信号、无委托、账本不更新。
- 修复后：系统默认模型与用户训练模型在自动托管判定中一视同仁，后续再由最新推理批次和执行窗口规则决定是否可执行。

## 修复记录（2026-05-18，原生策略模拟盘无 on_tick 时无产出）

- 现象：`STRATEGY_CONFIG` 风格的原生策略（如“多空 TopK 策略”）在 `SIMULATION` 启动后会显示运行中，但由于代码本身不定义 `on_tick`，沙箱循环不会产生委托信号，导致账本不更新。
- 修复：`/api/v1/real-trading/start` 在 `SIMULATION` 分支检测到“原生策略配置且无 `on_tick`”后，会在沙箱启动成功后立即触发一次 `create_hosted_task` 自动托管引导任务，确保本轮可进入真实执行链路。
- 说明：该修复不改变 `REAL/SHADOW` 的 K8s runner 行为，仅补齐模拟盘与原生策略的兼容入口。

## 修复记录（2026-05-18，模拟盘任务不再依赖实盘账户快照）

- 问题：自动托管任务在 `SIMULATION` 模式下仍复用“实盘账户快照等待”逻辑，导致在实盘快照断更时卡在 `portfolio_lookup`（`等待下一次账户上报超时`）。
- 修复：
  - `manual_execution_service` 的账户快照读取按 `trading_mode` 分流：
    - `REAL/SHADOW`：继续读取 PostgreSQL 实盘快照；
    - `SIMULATION`：改为读取 Redis `simulation:account:{tenant}:{user}`。
  - 买单前“等待下一次账户上报”仅在 `REAL` 且存在卖单时触发；
  - `SIMULATION` 直接基于当前模拟账户可用资金重算买单预算，不再等待实盘链路上报。

## 修复记录（2026-05-25，模拟盘启动引导任务误读实盘快照）

- 现象：`SIMULATION` 启动前自检全部通过后，点击“确认并启动模拟盘”仍弹出
  `未检测到最新实盘账户快照，请先确认 QMT Agent 已上报账户数据`。
- 根因：`real_trading_lifecycle.py` 在 `SIMULATION` 原生策略分支触发 `manual_execution_service.create_hosted_task(...)` 时，后者读取账户快照调用 `_load_latest_account_snapshot(...)` 漏传 `trading_mode`，默认值回落到 `REAL`，从而错误读取实盘快照。
- 修复：`create_hosted_task` 内部调用 `_load_latest_account_snapshot` 时显式传入 `trading_mode=mode`，确保 `SIMULATION` 走 `simulation:account:{tenant}:{user}` Redis 模拟账户快照，不再依赖 QMT Agent 实盘上报。

## 修复记录（2026-06-03，首次实盘手动执行自动初始化组合）

- 现象：首次确认实盘调仓预案后，任务进入 `validating` 阶段时报错
  `当前未发现可用的实盘组合，请先启动实盘策略或完成组合初始化`。
- 根因：预览/提交阶段只依赖 QMT 最新账户快照，但后台执行 worker 仍强制要求当前租户、用户、策略已有 `active` 实盘组合；首次实盘执行尚未创建组合时链路被阻断。
- 修复：`manual_execution_service` 在 `REAL` 手动任务校验阶段优先复用已存在的实盘组合；若不存在，则基于最新 QMT 账户快照自动初始化 `REAL + active + running` 组合后继续执行。
- 约束：没有最新 QMT 账户快照或快照总资产无效时仍会阻断，避免在资金状态未知时创建空组合。

## 修复记录（2026-06-09，模拟盘启动误报 QMT Agent）

- 现象：`SIMULATION` 原生策略启动后，如果自动托管引导任务读取不到模拟账户快照，页面会报
  `未检测到最新实盘账户快照，请先确认 QMT Agent 已上报账户数据`，误导为仍依赖 QMT Agent。
- 根因：`manual_execution_service.create_hosted_task()` 虽已按 `trading_mode=SIMULATION` 读取 Redis 模拟账户，但缺快照时仍沿用实盘固定报错文案。
- 修复：缺少账户快照时改为按模式返回文案：
  - `SIMULATION`：提示“未检测到最新模拟账户快照，请先确认模拟账户已初始化并有最新资金快照”；
  - `REAL/SHADOW`：继续提示 QMT Agent 实盘快照未上报。

## 修复记录（2026-06-03，QMT 异步回报与保护限价）

- 现象：实盘手动任务显示 50 笔委托已提交，但 QMT 端没有真实委托；Agent 日志只有 `async order accepted by qmt, seq=...`，后续回调携带 `exchange_order_id=-1`。
- 根因：`seq` 只代表 QMT SDK 异步请求受理，不代表柜台已生成真实委托；云端曾把 `-1` 当作交易所委托号落库，导致前端看起来“已提交”但柜台无单。
- 修复：
  - bridge execution 过滤 `-1/0/空/none/null/nan` 等无效委托号，不再覆盖 `orders.exchange_order_id`；
  - 实盘桥接市价单自动下发 `agent_price_mode=protect_limit`，由 Agent 取盘口生成保护限价，避免 QMT 市价语义不落真实委托；
  - 真实成交/委托状态仍以 Agent 后续 `on_stock_order/on_stock_trade` 回调为准。

## 修复记录（2026-06-04，手动实盘任务防重复提交）

- 现象：同一账户连续确认相同调仓预案时，会创建多笔 `queued` 任务；单 worker 串行处理导致页面只显示创建日志，前序任务完成后还可能重复报单。
- 修复：
  - 同一账户存在活跃手动任务时，相同 `run_id + strategy_id` 直接返回已有任务，不再创建重复任务；
  - 不同批次/策略提交时返回 `409`，明确提示当前活跃任务 ID 与状态；
  - worker 领取历史积压任务时，若发现该任务创建后已有更早同批次任务完成，则自动取消积压任务，避免重复报单；
  - 修复历史任务清理时字符串 `user_id` 传入整数订单字段导致事务回滚的问题。

## 修复记录（2026-06-04，手动任务重复保护时间参数类型）

- 现象：用户重发手动实盘任务后，前端只看到“已确认并创建执行任务”，后续没有进入验证、派单或 QMT 回报阶段。
- 根因：`trade_manual_execution_tasks` 读取后会把 `created_at` 序列化成 ISO 字符串；worker 在执行“已完成前序任务抑制”查询时直接把该字符串传给 PostgreSQL `timestamptz` 参数，`asyncpg` 抛出 `expected a datetime.date or datetime.datetime instance`，任务在 `validating` 前异常退出。
- 修复：`manual_execution_persistence.has_completed_predecessor()` 在入参层统一兼容 `datetime` 与 ISO-8601 字符串，查询前强制转换为 `datetime`，避免 worker 因时间类型不匹配中断。

## 修复记录（2026-06-04，手动任务原生市价与 QMT 价位单位）

- 现象：手动任务虽然在云端按 `MARKET` 生成，但桥接层会把所有 `MARKET/price=0` 订单改写成 `agent_price_mode=protect_limit`；QMT Agent 计算出的保护限价又未按最小价位单位对齐，导致柜台批量返回 `120161 校验最小价差失败`。
- 修复：
  - 手动任务 `client_order_id=manual-*` 现在保留原生 `MARKET` 语义，桥接层不再强制改写为 `protect_limit`；
  - 非手动任务若仍使用 `protect_limit`，QMT Agent 会按证券最小价位单位对齐价格后再下单，避免因价格步长不合法被柜台拒单。

## 修复记录（2026-05-25，模拟盘结算拉行情容器地址与内部鉴权）

- 现象：模拟盘结算器在容器内调用行情接口时，默认地址回退到 `http://127.0.0.1:8003`，会命中本容器而非 `quantmind-stream`；即使请求到 stream，未携带内部鉴权头也会被 `data_access` 拦截为 `403`。
- 修复：
  - `simulation_settler.py` 的 `STREAM_SERVICE_URL` 默认值改为 `http://quantmind-stream:8003/api/v1/quotes`（容器内服务名可达）；
  - 请求 `GET /api/v1/quotes/{symbol}` 时补充 `X-Internal-Call: INTERNAL_CALL_SECRET`，走 stream 内部调用放行分支；
  - 新增非 200 响应的告警日志，便于定位行情链路异常。

## 修复记录（2026-05-18，模拟盘虚拟成交价格兜底）

- 问题：`internal_strategy_dispatcher` 在 `SIMULATION/SHADOW` 分支中，直接使用请求中的 `price` 记账；当上游传入 `price=0`（市价语义）时，会把持仓 `price/market_value` 写成 `0`，导致账本看起来“不更新”。
- 修复：
  - 新增 `_resolve_virtual_fill_price`，优先使用信号价；当信号价 `<=0` 时，复用 `SimulationExecutionEngine` 的行情/数据库兜底链路获取有效成交价；
  - 虚拟成交记账改为使用 `fill_price`，并在返回体增加 `fill_price` 与 `price_source`，便于排障与审计。

## 修复记录（2026-05-18，模拟盘执行链路简化到“信号→行情→成交→写库→实时估值”）

- 背景：托管模拟盘此前存在“预案预算与执行时资金口径错位”与“仅更新 Redis、未落 `sim_orders/sim_trades`”的问题，容易出现总资产异常放大、交易记录不完整。
- 修复：
  - `internal_strategy_dispatcher` 在 `SIMULATION` 模式下改为统一走 `SimOrderService + SimulationExecutionEngine`：
    - 从托管任务生成的信号下单；
    - 成交价由行情服务（失败时数据库兜底）确定，并执行涨跌停/停牌约束；
    - 成交后同时写入 `sim_orders`、`sim_trades`，并同步模拟账户缓存。
  - `manual_execution_service` 在 `SIMULATION` 买单阶段改为“按当前可用资金等额重算”，不再沿用旧预案预算，避免因历史预案资金口径导致超额下单。
  - `/api/v1/simulation/account` 改为优先基于 `sim_trades` 聚合当前持仓，并按最新行情重算 `market_value/total_asset`（无成交历史时再回退 Redis 仓位），前端可直接用该数据实时展示市值。
  - 2026-06-08 继续补强基线一致性：若账户来自 OCR/手工同步持仓且暂时没有 `sim_trades` 成交历史，接口会优先使用 Redis 账户里显式记录的 `initial_equity/baseline.initial_equity`；对于历史老账户缺少这些字段的情况，则按 `cash + 持仓成本` 推导种子权益，避免“资产正常、初始权益回退默认 100 万”导致启动即显示大额盈利。
  - 2026-06-08 新增 native bootstrap 防重：原生 `STRATEGY_CONFIG` 模拟策略在启动时若已命中当日调度窗口，会与 `simulation_hosted_scheduler` 共用同一 `task_id + Redis lock`，避免“启动立即托管一轮，调度器随后再补一轮”导致同日重复买入、账户资产被双份持仓抬高。

## 手动执行任务（2026-04-12，引导式预案版）

- 手动任务已从“一页式直接执行”重构为“预览 -> 确认提交”两阶段：
  - `POST /api/v1/real-trading/manual-executions/preview`：只做调仓预案计算，不落库、不发单；
  - `POST /api/v1/real-trading/manual-executions`：基于 `preview_hash` 二次校验后创建正式任务；
  - `GET /api/v1/real-trading/manual-executions`
  - `GET /api/v1/real-trading/manual-executions/{task_id}`
  - `GET /api/v1/real-trading/manual-executions/{task_id}/logs`
- 首版引导式执行仅支持 `REAL`，且只允许同租户/同用户的已完成推理批次 + 已验证策略。
- `preview` 会固定读取 `engine_signal_scores` 与最新实盘账户快照，生成结构化调仓预案：
  - `account_snapshot`
  - `strategy_context`
  - `sell_orders / buy_orders / skipped_items`
  - `summary`
  - `preview_hash`
- 预案计算语义：
  - 根据策略参数与当前持仓生成“先卖后买”的委托草案；
  - 对无持仓卖出、缺参考价、预算不足等情况，不生成委托，改记入 `skipped_items`；
  - 买入数量按板块最小手数（主板/创业板/北交所默认 100，科创板默认 200）与可用现金预算计算。
- 正式提交后，任务仍写入 `trade_manual_execution_tasks`，并由 `manual_execution_worker.py` 后台轮询消费，继续复用现有日志流 `qm:real-trading:manual-execution:*`。
- 当前 `completed` 仍表示“派单完成/已完成提交尝试”，不等价于柜台最终成交；最终成交仍以后续订单状态和执行回报流为准。
- 启动阶段会通过 `manual_execution_persistence.ensure_tables()` 自动补齐 `trade_manual_execution_tasks.progress` 列，兼容旧环境中缺少该列但运行期已读写进度值的历史表结构。
- 手动任务正式执行阶段默认使用市价单：
  - trade 服务下发 `order_type=MARKET`、`price=0`，由交易链路按市价单语义执行；
  - 调仓执行顺序固定为“先卖后买”，卖单全部提交后轮询等待“下一次账户快照上报”，再进入买单阶段；
  - 买单预算以“下一次快照”的 `available_cash` 为准重算，不再使用“初始现金 + 预估卖出金额”；
  - 买单重算口径（2026-05-13）：
    - 预案阶段先为每个买入标的生成等额 `planned_budget`（例如 30 只买单，每只约 40 万）；
    - 卖单提交完成并收到下一次账户快照后，按 `available_cash` 仅放行可覆盖 `planned_budget` 的前 N 笔买单；
    - 不再采用“第一笔买单吃满全部可用资金”的顺序重算方式，避免出现 `buy=29` 但实际只发 1 笔的偏差。
  - `REAL` 模式购买力风控会优先读取最新账户快照 `available_cash`，与手动任务买单预算口径一致；
  - 买单全部提交后进入观察窗，超时会对未完全成交买单发起撤单（最终状态仍以 QMT 回报为准）；
  - `MANUAL_TASK_SELL_BUY_INTERVAL_SECONDS` 仅做历史兼容保留，新链路不再使用；
  - 新增配置：
    - `MANUAL_TASK_WAIT_NEXT_ACCOUNT_TIMEOUT_SECONDS`：默认 `120`，等待下一次账户上报超时阈值；
    - `MANUAL_TASK_ACCOUNT_POLL_INTERVAL_SECONDS`：默认 `3`，账户快照轮询间隔；
    - `MANUAL_TASK_BUY_CANCEL_TIMEOUT_SECONDS`：默认 `300`，买单观察窗（超时触发撤单）；
  - trade 风控估值不再依赖 preview 阶段的 Redis 参考价，而是通过 `QMTBridgeBroker.query_quote()` 实时调用 stream `GET /api/v1/quotes/{symbol}` 获取最新价做市值估算
- 修复记录（2026-04-20，手动预案 Hash 稳定性）：
  - `preview_hash` 口径已收敛为“稳定执行意图”：`model_id/run_id/prediction_trade_date/strategy_id/trading_mode + 订单(symbol/side/trade_action/order_type/quantity) + 买卖单数量`。
  - 不再将 `note`、`reference_price`、`estimated_notional` 等易抖动字段纳入 hash，避免 preview→submit 间隔内行情波动导致 `POST /api/v1/real-trading/manual-executions` 误报 `409 预览结果已失效`。
- 修复记录（2026-04-20，模拟盘沙箱池生命周期接入）：
  - `quantmind-trade` 启动阶段已接入 `sandbox_manager.start_pool()`，停止阶段接入 `sandbox_manager.stop_pool()`。
  - 修复前 `SIMULATION` preflight 的 `simulation_sandbox_pool` 会因 `_workers` 为空持续失败（`Sandbox Worker Pool is empty`），导致模拟盘链路无法形成完整闭环。
- 修复记录（2026-04-20，模拟盘后台链路生命周期接入）：
  - `quantmind-trade` 生命周期已接入 `vectorized_matcher.start()/stop()`，避免模拟盘信号消费链路只在手工调用时生效。
  - 同步接入 `SimulationFundSnapshotWorker` 后台任务，按 `SIM_FUND_SNAPSHOT_ENABLED` 与 `SIM_FUND_SNAPSHOT_INTERVAL_SECONDS` 周期采集 `simulation:account:*` 到 `simulation_fund_snapshots`。

## 自动托管任务化收口（2026-04-13）

- 自动托管已不再由 `runner/main.py` 逐笔调用 `/api/v1/internal/strategy/order`，而是统一改为：
  - runner 仅保留时间窗、触发检测、幂等锁与任务上报；
  - 命中条件后一次性调用 `POST /api/v1/internal/strategy/hosted-executions`；
  - trade 服务直接查询当前用户的默认模型最新完成推理结果，不再依赖 signal stream、fallback matcher 或外部信号作为数据源；
  - trade 服务按 `data_trade_date` + 默认模型 `target_horizon_days` 计算可执行窗口，超过窗口直接拒绝；
  - trade 服务基于默认模型最新推理结果、当前账户快照与策略参数生成 `execution_plan`，写入 `trade_manual_execution_tasks`；
  - 当策略参数包含 `f_` 前缀（如 `f_pe_ttm_max`、`f_total_mv_min`）时，托管执行会在生成 `execution_plan` 前按 `prediction_trade_date` 调用 `FundamentalAligner` 对候选信号做一致性过滤（显式卖出信号保留），并在 `summary` 中回写 `raw_signal_count/fundamental_filtered_count` 便于审计；
  - 后续仍由 `manual_execution_worker.py` 异步消费，并复用手动任务执行器、日志流、QMT Agent 保护限价能力。
- `trade_manual_execution_tasks` 已扩展并兼容以下字段：
  - `task_type`：`manual | hosted`
  - `task_source`：如 `manual_page | hosted_runner`
  - `trigger_mode`：`manual | schedule`
  - `trigger_context_json`
  - `strategy_snapshot_json`
  - `parent_runtime_id`
- 策略启动链路已修正为显式透传真实 `strategy_id`：
  - 运行容器不再从 `run_id.py` 文件名或固定字符串推断策略身份；
  - `runner/main.py` 现在优先读取启动参数/环境变量中的真实 `strategy_id`，确保自动托管任务回写与前端选中的策略一致；
  - 该修复同时覆盖 Docker 与 K8s 启动路径。
- `GET /api/v1/real-trading/manual-executions` 已支持按 `task_type/task_source/active_runtime_id` 过滤。
- `GET /api/v1/real-trading/status` 已新增：
  - `latest_hosted_task`
  - `latest_signal_run_id`
  - `signal_source_status`
- `signal_source_status` 现在会区分默认模型状态来源：
  - `missing`：没有默认模型或没有最新完成推理
  - `window_pending`：已找到最新完成推理，但尚未进入可执行窗口
  - `expired`：已超过可执行窗口
  - `fallback` / `mismatch`：兜底或来源不匹配，自动托管拒绝
  - `user_default`：可用于自动托管
- 启动前 readiness 已增加自动托管上游检查：
  - `signal_pipeline_enabled`：当前用户默认模型最新完成推理是否可用于自动托管
  - `latest_signal_run`：当前用户默认模型最新完成推理批次号

> 注：自动托管链路当前接受“用户默认模型的最新 `completed` 推理结果”，其中 `model_source` 允许为 `user_default` 或 `explicit_system_model`；且要求该结果未使用兜底模型。T+5 之类的执行有效期由模型元数据中的 `target_horizon_days` 决定。

## 仪表盘口径收敛（2026-04-09）

- `GET /api/v1/real-trading/account` 现在只读 PostgreSQL 视图 `real_account_snapshot_overview_v`，会一并返回 `payload_json.positions`、`position_count`，并基于 PostgreSQL 的 `day_open_equity` 视图口径补齐 `today_pnl`；账户未持久化时返回 `404`，不再回退缓存快照。若视图尚未创建，服务会先回滚当前会话再降级到表查询，避免事务被错误状态污染。
- 实盘账户基线已拆分为独立表 `real_account_baselines`：新账户会在第一条 `qmt_bridge` 落库记录时自动写入初始资金，若存在人工修正则以基线表为准。`79311845 / 8886664999` 已被手动修正为 `21000000.00`。
- 新增实盘账户日账本 `real_account_ledger_daily_snapshots`：由 `qmt_bridge` 每次上报落库，保存 `initial_equity/day_open_equity/month_open_equity/today_pnl_raw/monthly_pnl_raw/total_return_pct` 等按日快照字段；`GET /api/v1/real-trading/account/ledger/daily` 默认按当前账户读取最近 N 天游标，并优先锁定当前活跃账户，避免多账户混读。
- 日账本规范化补层（2026-04-11）：
  - 持久化层继续保留兼容字段，但 `today_pnl_raw` 已回归为桥接层原始当日盈亏上报值，不再写入派生日盈亏；
  - `/api/v1/real-trading/account/ledger/daily` 现补充规范化字段：`snapshot_kind/broker_today_pnl_raw/daily_pnl/monthly_pnl/total_pnl/floating_pnl/daily_return_ratio/total_return_ratio/baseline`；
  - `GET /api/v1/real-trading/account` 与 `GET /api/v1/real-trading/account/ledger/daily` 已统一语义：
    - `broker_today_pnl_raw`：桥接层原始当日盈亏上报值，仅用于审计/排障；
    - `daily_pnl/monthly_pnl/total_pnl/floating_pnl`：规范化展示字段；
    - `daily_return_pct/total_return_pct`：百分数字面值（例如 `1.23` 表示 `1.23%`）；
    - `daily_return_ratio/total_return_ratio`：比例值（例如 `0.0123`）；
    - `baseline.initial_equity/day_open_equity/month_open_equity`：统一基线口径；
  - 前端图表与后续上层逻辑应优先消费规范化字段或 `*_return_pct/*_return_ratio`，避免直接依赖 `*_raw` 字段做展示。
  - 新增异常快照保护：若 QMT Agent 在退出/重连过程中上报 `total_asset/cash/market_value` 全为 `0` 且无持仓的空快照，而库内已存在历史有效快照，则 trade 服务会拒绝该次快照写入 `real_account_snapshots` 与 `real_account_ledger_daily_snapshots`，避免把资金概览和当日账本覆盖成 `0 / -100%`。
  - 异常快照保护已扩展到“资产跳变”场景：若相较最近有效快照出现整张资产负债表断崖式下跌，或仍声明存在持仓但 `market_value` 丢失，则视为桥接层不完整上报并拒绝落库。
  - `GET /api/v1/real-trading/account` 读取最新快照时会自动跳过最近的“空尾快照”，优先回退到最近一条有效 PostgreSQL 快照；同时 `is_online` 改为基于 `snapshot_at` 时效判断，不再固定返回 `true`。
  - `POST /api/v1/internal/strategy/bridge/account` 在快照被 guard 拒绝时，不再继续把原始坏 payload 同步进 `portfolio/positions`；若存在最近有效快照，则改用该快照回填组合资金与持仓，否则直接跳过本次 portfolio 同步。
  - 新增“零总资产但持仓/市值非空”的异常快照保护：这类桥接上报会被视为不完整 payload，`/account` 读取和 `bridge/account` 写缓存都会统一拒绝，避免前端把坏快照展示成真实实盘口径。
  - guard 触发时会在 `metrics_meta.snapshot_guard` 中回写结构化审计信息，并输出服务端告警日志，便于线上复盘被拒绝的上报内容与回退来源。
  - `real_account_ledger_daily_snapshots` 现在只接受“时间上更新”的快照覆盖；迟到旧包不会再倒灌覆盖当天账本。
  - 新增后台任务 `real_account_ledger_settlement_task`：每个交易日 `15:05`（上海时间）对当日日账本做一次“无迁移版日终结算”，在原有日账本行上补写 `settlement_finalized/settlement_finalized_at/settlement_snapshot_count` 等审计元数据，并将来源标记为 `daily_settlement`。
  - `GET /api/v1/real-trading/account/ledger/daily` 已透出 `settlement_finalized/settlement_finalized_at/settlement_snapshot_count`，上层可以据此区分“盘中实时账本”和“收盘后已结算账本”。
- `QMT Agent 在线预检` 会把 PostgreSQL 中无时区的 `snapshot_at` 按 UTC 解释，避免把最新快照误判为过期。
- `GET /api/v1/real-trading/preflight` 中的 `QMT Agent 在线状态` 检查已补 JSON 解析容错，避免脏快照把启动前自检直接打断。
- `GET /api/v1/real-trading/status` 的 `sys_` 模板回查改为懒加载并捕获异常，避免模板缺失导致状态轮询直接 500。
- `SandboxSignalConsumer` 已补 Redis 传输层退避重连与降噪日志：
  - 遇到 `Timeout reading from socket` / 连接断开时会先指数退避，再重建 Redis 连接；
  - 连续异常只按节奏输出 warning，避免同一故障刷屏掩盖真正的 HTTP 请求问题；
  - 重连成功后会输出一次恢复日志，便于快速确认问题是否自愈。
- `SandboxSignalConsumer` 监听链路已与共享 Redis 客户端解耦：
  - 模拟盘信号消费改为使用专用阻塞监听连接，不再复用全局共享 Redis client；
  - 专用连接的 `socket_timeout` 会显式高于 `BLPOP` 超时时间，避免空轮询被误判为 `Timeout reading from socket`；
  - 监听重连仅重建专用连接，不再关闭 trade 进程内供 HTTP/其他后台任务复用的共享 Redis 连接。
- `SimulationRuntimeRestorer` 已修复协程误用：
  - 恢复模拟盘运行态时，用户策略读取改为正确 await `StrategyStorageService.get(...)`；
  - 避免容器重启阶段出现 `coroutine 'StrategyStorageService.get' was never awaited` 告警，并防止恢复链路把策略代码误判为空。

## 修复记录（2026-03-28，Runner 镜像预检与默认回退对齐）
- 修复 `/api/v1/real-trading/preflight` 与 `/api/v1/real-trading/trading-precheck` 在 `STRATEGY_RUNNER_IMAGE` 未显式配置时的误拦截问题。
- `/api/v1/real-trading/start` 会按模式恢复真实启动链路：`REAL/SHADOW` 通过 `k8s_manager` 拉起运行容器，`SIMULATION` 通过沙箱执行器提交任务；`/api/v1/real-trading/stop` 对应执行删除/停止。
- 预检输出会新增 `image_source=configured|default`，便于区分“显式配置”与“默认回退”。

## 修复记录（2026-04-02，健康检查降级语义对齐）
- `main.py` 启动阶段新增关键依赖状态跟踪：`startup_healthy`、`db_connected`、`redis_connected`。
- `/health` 现按综合状态返回：
  - `healthy`：启动与关键依赖均正常
  - `degraded`：任一关键依赖初始化失败
- `/health` 新增 `components.database/components.redis`，用于快速定位降级来源。
- 恢复并统一暴露：
  - `GET /` 根路由（`QuantMind Trade Core V2 is running`）
  - `GET /metrics`（Prometheus 服务健康指标）

## 修复记录（2026-04-13，bridge/account 日账本落库 KeyError）
- 修复 `real_account_ledger_service.upsert_real_account_daily_ledger()` 构造 upsert 行数据时遗漏关键字段的问题：
  - 补齐 `account_id`
  - 补齐 `snapshot_date`
  - 补齐 `last_snapshot_at`
- 修复后 `on_conflict_do_update` 不再触发 `KeyError: 'last_snapshot_at'`，`POST /api/v1/internal/strategy/bridge/account` 可继续完成账户快照与日账本落库闭环。

## 修复记录（2026-04-13，日收益率图表账本回填与查询增强）
- `GET /api/v1/real-trading/account/ledger/daily` 新增 `account_id` 参数，支持前端按实盘账户精确读取日账本，避免多账户/切换场景误读。
- 当账本表无数据但 `real_account_snapshots` 已有历史快照时，后端会自动执行一次按日回填（`qmt_bridge_backfill`），补齐 `daily_return_pct`/`total_return_pct` 等核心字段后再返回结果。
- 该回填能力可修复历史用户缺失日账本导致“智能图表无法读取每日收益率”的问题，同时保持后续桥接上报继续走实时持久化链路。

## 修复记录（2026-03-27，preflight 快照落库）
- 修复 `PreflightSnapshot` ORM 模型字段缺失问题（此前仅保留 `id/run_count`），与表 `real_trading_preflight_snapshots` 结构重新对齐。
- 修复后 `/api/v1/real-trading/preflight` 的日级快照 upsert 不再触发
  `Unconsumed column names`，可持续写入 `tenant_id/user_id/trading_mode/snapshot_date` 等留痕字段。
- 本次变更不需要新增迁移脚本：线上表结构已存在，属于代码侧模型定义回补。

## 实盘状态映射与最小申报股数修复（2026-03-23）
- QMT 执行回写状态码口径统一（Agent 与 Trade 服务一致）：
  - `50 -> SUBMITTED`
  - `56 -> FILLED`
  - `57 -> REJECTED`
- `POST /api/v1/internal/strategy/bridge/execution` 的 raw code 兜底映射同步更新：
  - `56` 按已成处理，`57` 按拒单处理。
- `POST /api/v1/internal/strategy/bridge/execution` 的成交入账口径已收口：
  - 仅带 `exchange_trade_id` 的 trade callback 会新增 `trades` 并累计 `orders.filled_quantity/filled_value`；
  - 不带 `exchange_trade_id` 的 order callback 只更新订单状态与 `exchange_order_id`，避免与后续 trade callback 双计成交。
- 风控新增 A 股买入整手校验（`RiskService`）：
  - 主板：`MIN_LOT_MAIN_BOARD`（默认 100）
  - 创业板：`MIN_LOT_GEM_BOARD`（默认 100）
  - 科创板：`MIN_LOT_STAR_BOARD`（默认 200）
  - 北交所：`MIN_LOT_BJ_BOARD`（默认 100）
- 校验不通过会直接返回风险阻断，避免无效委托进入柜台。

## 双向交易后端支持（2026-03-15）
- 新增固定融资融券股票池能力：默认读取项目根目录 `data/融资融券.xlsx`，通过 `backend.shared.margin_stock_pool` 提供只读判定。
- 订单/成交模型新增双向语义字段：
  - `trade_action`：`buy_to_open / sell_to_close / sell_to_open / buy_to_close`
  - `position_side`：`long / short`
  - `is_margin_trade`
- 组合/持仓模型新增信用口径字段：
  - `portfolios.liabilities / short_market_value / maintenance_margin_ratio / warning_level`
  - `positions.side / borrow_fee / financing_fee / margin_occupied / maintenance_margin_ratio`
- 风控新增最小双向规则：
  - `sell_to_open` 仅允许融资融券股票池内标的；
  - 校验保证金占用与 feature flag `ENABLE_MARGIN_TRADING`。
- Runner 与内部下单链路已支持透传 `trade_action / position_side / is_margin_trade`，前端暂不新增切换入口。
- `GET /api/v1/real-trading/preflight` 已补充双向交易专项检查：
  - `双向交易功能开关`
  - `融资融券股票池`
  - `信用交易动作支持`
  - `信用账户状态`

## QMT 多空实盘灰度（2026-03-19）
- 不新增外部下单契约字段，沿用：
  - `trade_action`
  - `position_side`
  - `is_margin_trade`
- Bridge 下单已透传三字段到 QMT Agent（含异步链路）。
- 新增服务端开关：
  - `ENABLE_LONG_SHORT_REAL=false`（默认关闭）
  - `LONG_SHORT_WHITELIST_USERS=`（逗号分隔）
  - `SHORT_ADMISSION_STRICT=true`（默认开启）
- REAL 模式 `sell_to_open` 风控新增标准错误码：
  - `LONG_SHORT_NOT_ENABLED`
  - `SHORT_POOL_FORBIDDEN`
  - `CREDIT_ACCOUNT_UNAVAILABLE`
  - `SHORT_QUOTA_INSUFFICIENT`
- `bridge/account` 快照结构已向后兼容扩展信用字段：
  - `liabilities`
  - `short_market_value`
  - `credit_limit`
  - `maintenance_margin_ratio`
  - `credit_enabled`
  - `shortable_symbols_count`
  - `last_short_check_at`
- CI 门禁已纳入以下必跑测试集（`scripts/ops/ci/p2_ci_quality_gate.py`）：
  - `backend/services/tests/test_qmt_agent_async_reconcile.py`
  - `backend/services/tests/test_trade_long_short_risk_and_bridge.py`
  - `backend/services/tests/test_trade_long_short_integration_chain.py`
  - `backend/services/tests/test_trade_trading_precheck.py`

### 迁移脚本
```bash
psql "$DATABASE_URL" -f backend/migrations/add_margin_trading_fields.sql
```

## 入口
- 应用入口：`/Users/qusong/git/quantmind/backend/services/trade/main.py`
- 默认端口：`8002`
- Kubernetes 命名空间：默认读取 `K8S_NAMESPACE`，未配置时使用 `quantmind`；`k8s_manager` 不再默认写死 `default`。
- 数据库配置来源：仅项目根目录 `.env`（服务目录 `.env` 不再维护 `DATABASE_URL`）。
- 生产 Redis 约定：实盘交易链路默认连接 `quantmind-trade-redis`，回测/通用链路连接 `quantmind-backtest-redis`，二者端口和数据独立。
- CORS 策略：开发/测试环境默认允许本机前端源；生产/预发环境必须通过 `CORS_ALLOWED_ORIGINS`（或兼容变量 `CORS_ORIGINS`）显式配置白名单，禁止 `*`。
- 镜像依赖策略：`trade` Docker 镜像改用 [requirements/trade.txt](/Users/qusong/git/quantmind/requirements/trade.txt)，不再安装 `requirements/ai.txt`，以降低镜像体积、冷启动时长和首启内存峰值。

## 模块边界（P1）
- `trade` 负责交易执行域：订单、成交、持仓、组合、模拟盘、实盘。
- 路由归属：`/api/v1/orders/*`、`/api/v1/trades/*`、`/api/v1/portfolios/*`、`/api/v1/simulation/*`、`/api/v1/real-trading/*`。
- 模拟盘账户管理统一实现位于 `backend/services/trade/services/simulation_manager.py`；
  `backend/services/trade/simulation/services/simulation_manager.py` 为兼容导出层，不再维护重复实现。
- 单条订单/成交读取与更新链路强制使用 `tenant_id + user_id + 业务ID` 约束，
  避免仅按主键读取导致的跨租户越权风险。
- `portfolios/positions` 单条查询与写操作强制绑定当前 `user_id` 作用域，
  禁止跨用户访问其他组合、持仓及快照数据。
- `real_trading` 相关接口改为以 JWT 身份为准，外部传入 `user_id/tenant_id`
  仅作一致性校验，禁止参数覆盖身份上下文。
- `/api/v1/real-trading/account` 错误语义收敛为标准 HTTP：账户未上报返回 `404`，服务异常返回 `500`，不再返回 `200 + {"error": ...}`。
- `portfolio` 模块已引入 `tenant_id` 字段并在查询/写入链路启用
  `tenant_id + user_id` 联合约束；迁移脚本见
  `backend/migrations/add_trade_portfolio_tenant_id.sql`。
- P3 可观测性基线：统一注入并透传 `X-Request-ID` 响应头，便于跨服务链路追踪。
- P3 错误契约：统一错误结构 `error.code/error.message/error.request_id`，并兼容保留 `detail` 字段。
- P3 日志基线：统一访问日志字段 `service/request_id/tenant_id/user_id/method/path/status/duration_ms`。
- P3 指标基线：新增 `/metrics`（Prometheus），统一暴露 `quantmind_service_health_status{service="quantmind-trade"}` 与 `quantmind_service_degraded{service="quantmind-trade"}`。
- P3 健康语义：`/health` 在数据库/Redis 等关键依赖初始化失败时返回 `status=degraded`，并同步到服务健康指标。
- P6 深度 E2E 修复：`simulation` 订单/成交模型与线上 PostgreSQL enum 口径对齐：
  `orderside/ordertype/orderstatus` 继续使用小写值，
  `tradingmode` 统一使用大写值（`SIMULATION`），并保留接口层大小写兼容（`simulation/SIMULATION` 均可）。
- 禁止范围：`trade` 不负责策略生成/推理/回测，不承担行情采集与推送职责。

## 成交统计接口扩展（2026-03-09）
- 接口：`GET /api/v1/trades/stats/summary`（路径不变，字段扩展）。
- 返回新增：`daily_counts`（按 `executed_at` 日级聚合，升序输出，元素结构：`timestamp/value/label`）。
- 兼容保留：原汇总字段 `total_trades/total_value/total_commission/buy_trades/sell_trades` 继续返回。
- 聚合口径：严格按 `tenant_id + user_id + 可选 portfolio_id` 过滤，确保多租户与用户隔离。

## 实时交易记录接口兼容（2026-03-09）
- `GET /api/v1/trades` 已补充 `trading_mode` 大小写兼容：
  - 支持前端传入 `real/simulation` 或 `REAL/SIMULATION`；
  - 服务层统一归一化后过滤，非法值返回 `422 Invalid trading_mode`。
- 保持租户与用户隔离口径不变（鉴权上下文 `tenant_id + user_id`）。
- `GET /api/v1/orders` 与 `GET /api/v1/simulation/orders` 现已支持 `start_date/end_date/limit/offset`，前端交易记录页会按 `tradingMode` 自动切换到对应订单源，并将时间范围直接透传到后端查询。
- `GET /api/v1/orders` 与 `GET /api/v1/trades` 的时间查询参数新增时区兼容：当请求携带带时区的 ISO 时间（如 `...Z`）时，服务层会先统一转换为 UTC naive 时间，再与库内 `timestamp without time zone` 字段比较，避免 `asyncpg DataError: can't subtract offset-naive and offset-aware datetimes` 导致 500。
- `GET /api/v1/orders` 与 `GET /api/v1/trades` 的响应时间字段已统一序列化为带时区的 UTC ISO 字符串；即使旧客户端仍按浏览器默认方式解析，也能正确显示上海本地时间，避免仪表盘交易记录出现 `05:12` 这类偏移值。

## 模拟盘资金日快照（新增）
- 新增表：`simulation_fund_snapshots`（`tenant_id + user_id + snapshot_date` 唯一键）。
- 用途：按“天”永久保存用户资金概览，支持仪表盘资金历史追溯，不再仅依赖 Redis 当前态。
- 数据来源：`simulation:account:{tenant}:{user}`（Redis），按天 upsert 当日记录，保留历史天数据。
- 启动行为：`quantmind-trade` 启动后自动拉起后台任务周期采集（默认每 300 秒执行一次）。
- `/api/v1/simulation/account` 与 `SimulationAccountManager.update_balance()` 在账户不存在时会优先读取 `simulation/settings.initial_cash` 自动初始化，并把 `initial_equity/day_open_equity/month_open_equity/baseline.*` 一并写入 Redis 账户，避免账户回退到默认 100 万导致设置与账户口径不一致。
- `/api/v1/simulation/reset` 与首次自动初始化都会立即触发一次当日资金快照采集，确保“保存/重置后”的历史资金口径及时落库。
- `/api/v1/simulation/reset` 现固定重置为 100 万，不再依赖请求体中的 `initial_cash`，并会同步写回 `simulation/settings.initial_cash=1000000`，确保 `simulation/account.initial_equity` 与默认重置口径一致。
- 新增接口：
  - `GET /api/v1/simulation/snapshots/daily?days=30`：查询当前用户日快照历史。
  - `POST /api/v1/simulation/snapshots/capture`：手动触发一次采集（按天 upsert）。
- 运行参数（根 `.env`）：
  - `SIM_FUND_SNAPSHOT_ENABLED=true|false`（默认 `true`）
  - `SIM_FUND_SNAPSHOT_INTERVAL_SECONDS=300`（默认 300 秒）
  - `SIM_FUND_SNAPSHOT_TZ=Asia/Shanghai`（默认上海时区）

## 实盘闭环执行链路（2026-02-25）
- 控制面：`/api/v1/real-trading/start|stop|status|logs` 负责启动/停止/观测实盘容器。
- 控制面新增：`/api/v1/real-trading/preflight` 启动前自检（K8s/Redis/DB/Runner 镜像/内部密钥），供前端做启动门禁。
- 控制面新增：`/api/v1/real-trading/preflight` 已补充 `QMT Agent 在线状态` 检测（基于 PostgreSQL 实盘账户快照 + `trade:agent:heartbeat:{tenant}:{user}` 心跳判定），`REAL` 模式下默认作为必需项。
- `RedisBroker.query_account` 已改为读取 PostgreSQL 视图 `real_account_snapshot_overview_v`，不再把 Redis 账户快照当作查询来源。
- 控制面新增：`/api/v1/real-trading/preflight` 已补充 Stream 闭环探针：
  `stream_series_freshness`（series 新鲜度）、
  `stream_quote_persist_rate`（quote 落库速率），并通过 `checks[].details` 回传诊断明细。
- 控制面新增：`/api/v1/real-trading/preflight` 已补充 `SIMULATION` 专用探针：
  `inference_database_ready`（模型推理数据库是否已具备前一交易日 48 维完整数据）、
  `simulation_sandbox_pool`（沙箱进程池存活）、
  `simulation_tables`（`sim_orders/sim_trades/simulation_fund_snapshots` 关键表）、
  `simulation_snapshot_worker_config`（资金快照任务配置，非阻断）。
- 模式收敛：`SIMULATION` 模式下 `preflight` 不执行 K 线接口可用性探针，仅保留 `stream_series_freshness/stream_quote_persist_rate` 等核心行情检查与模拟盘必要检查项。
- `stream_series_freshness` 数据源对齐：优先直连 `REMOTE_QUOTE_REDIS_*`（与 `quantmind-stream` 的 quote->series 写入端一致），远端探测异常时降级到交易 Redis 并在 `checks[].details.remote_probe_error` 回显原因。
- P3 兼容清理：`trade` 与 `portfolio/simulation` 的响应 schema 已切到 `ConfigDict(from_attributes=True)`，配置类切到 `SettingsConfigDict`，ORM 基类切到 `sqlalchemy.orm.declarative_base()`，避免 Pydantic V2 / SQLAlchemy 2.x 弃用告警污染 smoke/CI。
- 控制面新增：`/api/v1/real-trading/preflight` 调用后会自动写入
  `real_trading_preflight_snapshots`（按 `tenant_id+user_id+trading_mode+snapshot_date` 日级 upsert），用于长期留痕与问题追踪。
- 控制面新增：`GET /api/v1/real-trading/preflight/snapshots/daily?days=30&trading_mode=REAL`
  可查询当前用户的自检历史快照（含 `failed_required_keys/checks/last_checked_at`）。
- 控制面新增：`GET /api/v1/real-trading/trading-precheck?trading_mode=REAL|SHADOW|SIMULATION`
  用于检查“交易准备度”是否满足启动条件，返回 `{ passed, checked_at, items[] }`。
- `REAL/SHADOW` 仅保留 4 类核心项：
  生产模型存在、模型推理数据库已准备就绪（按前一交易日且 48 维完整判定）、Kubernetes 服务与执行镜像已就绪、实时行情服务已就绪；
  其中 `REAL` 额外要求 `QMT Agent` 心跳与 PostgreSQL 账户快照已上报，`SHADOW` 不阻断该项。
- 交易准备度检测前部固定追加 4 个基础必需项：
  `Redis`、`PostgreSQL`、`内部密钥`、`用户权限`（仅 Pro 可托管），保持与商业化门禁一致。
- `MODELS_PRODUCTION` 未显式配置时，`trade` 默认按生产路径 `/app/models/production/model_qlib` 检测模型，
  避免误回退到历史相对路径 `model_qlib`。
- `SIMULATION` 的交易准备度会保留 4 个基础必需项（`Redis`、`PostgreSQL`、`内部密钥`、`用户权限`），并额外校验 `模型推理数据库已准备就绪`、`模拟盘进程池`、`实时行情服务已就绪`；其中模型数据库项也会出现在 `/api/v1/real-trading/preflight` 的模拟盘自检列表中，避免前端切换阶段后丢失模型相关结果。
- `trading-precheck` 已移除“最新推理信号版本可见”检查项；该项仅用于诊断不再作为启动门禁。
- `trading-precheck` 的 `实时行情服务已就绪` 已升级为硬门禁：行情探针失败会直接导致 `passed=false`。
- `/api/v1/real-trading/preflight` 的商业化门禁已对齐：`用户标识` 改为 `用户权限`（仅 Pro 可托管），并移除 `latest_signal_run` 展示项，避免与交易准备度弹窗口径不一致。
- `trading-precheck` 的 `生产模型存在` 与 `推理模型已就绪` 已升级为按真实模型文件识别：
  默认识别 `model.lgb/model.pkl/model.joblib/model.bin/model.txt`（以及同目录 `*.lgb/*.pkl/*.joblib/*.bin`），
  检查明细会回显命中的真实文件路径（`matched`），不再仅展示固定 `model.txt` 候选文案。
- `trading-precheck` 的模型目录解析口径已与回测/推理一致：优先按当前用户 `model_registry` 解析到的默认模型
  `storage_path` 做检测（千人千面），解析失败时才回退 `MODELS_PRODUCTION` 默认目录。
- 模拟盘控制台误报修复（2026-06-05）：
  - `SIMULATION` 的“推理模型已就绪”现优先按当前用户默认模型解析目录；若本地目录未挂载但默认模型最新推理批次已可被自动托管消费，则改判为就绪，避免“生产批次摘要已完成但环境监控仍报 `/app/models/production/model_qlib` 不存在”的误报。
  - `stream_series_freshness` 在午休、收盘后等非交易时段不再因上一笔行情时间戳陈旧而直接报红；只要 Redis 可连通，就返回“非交易时段”状态，避免把休市误判成行情异常。
- 控制面增强：`POST /api/v1/real-trading/start` 在 `REAL/SHADOW/SIMULATION` 全模式下
  会按模式执行启动门禁：
  `REAL/SHADOW` 先跑完整交易准备度检测，`SIMULATION` 先跑“基础 4 项 + 模型推理数据库 + 模拟盘进程池 + 实时行情”的最小准备度检测；
  未通过时返回 `409`，并在 `detail` 中附带 `precheck_failed/items/first_failed_reason`，供前端直接回显。
- 控制面新增：`/api/v1/real-trading/start` 支持前端传入 `execution_config`（JSON），会与策略默认风控合并后注入 runner `EXECUTION_CONFIG`。
- 控制面新增：`/api/v1/real-trading/start` 支持前端传入 `live_trade_config`（JSON），与策略模板默认实盘配置合并后注入 runner `LIVE_TRADE_CONFIG`。
- 控制面新增：`/api/v1/real-trading/start` 响应 `effective_execution_config/effective_live_trade_config`，`/api/v1/real-trading/status` 回传 `execution_config/live_trade_config` 用于前端持续回显。
- `GET /api/v1/real-trading/status` 在 `REAL/SHADOW` 场景也会稳定回传 `mode`（与 `SIMULATION` 分支对齐），避免前端顶部运行模式/部署通道落入“未识别”。
- `GET /api/v1/real-trading/status` 新增 `orchestration_mode`（`docker`/`k8s`），供前端准确展示部署通道，避免将 Docker 场景误标为 K8s。
- QMT Agent 接入收敛（2026-03-14）：
  - 仅保留 QMT Agent，PTrade 模板与入口已下线；
  - 新增 `POST /api/v1/internal/strategy/bridge/session` 与 `POST /api/v1/internal/strategy/bridge/session/refresh`，使用 `access_key + secret_key` 换取短期 `bridge_session_token`；
  - `/ws/bridge` 与 Agent 上报接口只接受短期 `bridge_session_token`，`qm_live_*` 不再直接用于 WebSocket 握手；
  - 新增 `POST /api/v1/internal/strategy/bridge/account`、`/heartbeat`、`/execution`，分别负责账户快照、心跳、执行回报闭环；
  - `POST /api/v1/internal/strategy/bridge/execution` 回写订单默认按 `tenant_id + user_id + client_order_id` 精确匹配；并新增兼容匹配链路（`client_order_id` 误传为 `order_id(UUID)` 或可用 `exchange_order_id` 时可回填），同时输出结构化日志便于排查回写键不一致；
- `QMTBridgeBroker` 下单派发成功后不再预填伪 `exchange_order_id`（不再回填 `client_order_id` 冒充柜台单号），真实柜台单号仅由 Agent 回报驱动更新；
- `TradingEngine.cancel_order_execution` 不再在发送撤单请求后直接写 `CANCELLED`，改为保留当前状态并写备注，最终状态由 QMT 回报落库；
- `tools/qmt_agent/qmt_agent.py` 已支持同步/异步下单撤单（`order_stock/order_stock_async`、`cancel_order_stock/cancel_order_stock_async`）与对应异步回报；
- Agent 启动后会执行一次 `query_stock_orders + query_stock_trades` 补偿查询并回写执行事件，降低断线窗口的状态缺口；
- `tools/qmt_agent` 侧已对 `access_key/secret_key/account_id/tenant_id/user_id` 等关键配置做统一 `strip()`，`download/agent` 生成的 `qmt_agent_config.json` 也会写入清洗后的值，避免复制粘贴带入换行或尾随空格导致 `401`；
- 新增 `GET /api/v1/internal/strategy/bridge/binding/status`，供前端设置中心展示 QMT Agent 在线状态；
  - `/api/v1/internal/strategy/bridge/download/agent` 继续要求登录态 JWT，返回 `qmt_agent_client.zip`，其中包含 `qmt_agent.py`、`desktop_app.py`、`requirements.txt`、`README.md`、`qmt_agent_config.json`、Windows 打包脚本（`build_windows_agent.py`/`qmt_agent_desktop.spec`/`qmt_agent_setup.iss`/`version.json`）和参考脚本；下载请求中的 `user_id` 若与登录用户不一致会返回 `403`。
  - 下载包完整性修复（2026-03-23）：`qmt_agent_client.zip` 现额外包含运行必需子模块 `agent.py/auth.py/client.py/config.py/reporter.py/_callback.py`，避免仅更新入口脚本时子模块仍停留旧版本。
  - `qmt_agent_client.zip` 的定位已收敛为“独立部署包源代码”，用于在客户服务端或专用 Windows 主机单独安装/打包 QMT Agent；Electron 只提供下载入口，不直接控制该 Agent 的本地生命周期。
  - 新增 `/api/v1/internal/strategy/bridge/download/agent/release`：后端优先读取 COS 上的 `qmt-agent/windows/release/latest.json`，返回 Windows 安装器的预签名下载地址，前端下载按钮改走该接口，不再直连 COS。
  - 推荐 COS 目录结构：
    - `qmt-agent/windows/release/latest.json`
    - `qmt-agent/windows/release/v{version}/QuantMindQMTAgent-Setup-{version}.exe`
    - `qmt-agent/windows/release/v{version}/QuantMindQMTAgent-{version}-win64.zip`
    - `qmt-agent/windows/release/v{version}/sha256.txt`
  - 相关环境变量：
    - `QMT_AGENT_RELEASE_MANIFEST_KEY`：发布清单 key，默认 `qmt-agent/windows/release/latest.json`
    - `QMT_AGENT_RELEASE_URL_TTL`：安装器签名 URL 有效期，默认 `1800` 秒
    - `QMT_AGENT_RELEASE_MANIFEST_LOCAL_PATH`：本地 manifest 兜底路径，便于开发联调
  - `tools/qmt_agent/build_windows_agent.py` 现在会在本地 `dist/qmt_agent/latest.json` 生成发布清单，包含版本、构建时间、COS key 和 SHA256，便于同步上传到 COS。
  - `tools/qmt_agent/qmt_agent.py` 已合并旧 `local_agent` 的关键执行能力：`xtquant` 实盘下单、QMT 自动重连、周期账户查询与心跳上报；旧 Redis Stream 终端直连方案不再作为正式交付面维护。
  - Redis 键规范（2026-04-09）：
    - 数字型 `user_id` 统一归一化为 8 位补零后再拼接 `trade:account` / `trade:agent:heartbeat`；
    - 账户快照、心跳、preflight、交易准备度、bridge broker、信用风控均已统一复用共享 key helper，避免出现“Agent 明明在线但某条读路径判离线”的假阴性。
  - 在线门禁统一收敛为 `qmt_agent_online`，依赖 PostgreSQL 实盘账户快照与 `trade:agent:heartbeat:{tenant}:{user}` 心跳判定；
  - Bridge 派发唯一连接（2026-04-09）：
    - `/ws/bridge` 握手元数据现显式带 `session_id`；
    - 同一 `binding_id` 建立新连接后，`stream` 会主动清理旧 bridge 连接；
    - `/api/v1/internal/bridge/order` 与 `/api/v1/internal/bridge/cancel` 仅向最新活动 bridge 连接派发，避免同账户多连接重复下单。
  - 在线联调已验证：旧的 `qm_live_*` 直连 `ws/bridge` 会被拒绝，新会话链路可以成功写入账户快照与心跳；
  - `bridge/account` 快照字段补齐：支持上报并透传 `today_pnl` / `total_pnl` / `floating_pnl`，用于前端优先展示柜台盈亏口径；
  - 持仓快照价格口径增强：`cost_price` / `last_price` 支持多字段兜底，缓解柜台回包缺字段导致前端盈亏恒为 0 的问题；
- 注意：当前交易服务读取的是交易 Redis **DB 2**，排查“无数据上报”时不要误查默认库 `0`。
- 内部下单热修（2026-03-14）：
  - 修复 `/api/v1/internal/strategy/order` 对 `TradingMode.SHADOW` 的硬引用问题。
  - 当前枚举不包含 `SHADOW` 成员时，旧逻辑会抛 `AttributeError: SHADOW` 并导致下单请求返回 `500`；
    已改为按 `trading_mode.value` 字符串判断，避免枚举成员缺失引发运行时异常。
  - 修复 `except IntegrityError` 未导入问题（`NameError: IntegrityError`），避免重复 `client_order_id` 或唯一键冲突时误报 `500`。
  - 交易枚举与线上 PostgreSQL enum 口径对齐：`orderside/ordertype/orderstatus` 统一使用库中小写值，并为接口输入保留大小写兼容解析（如 `BUY/buy`、`LIMIT/limit` 均可）。
  - 风控资金读取改为优先查询本地 `portfolios` 表（`tenant_id + user_id + portfolio_id`），远程 `/api/v1/portfolios/{id}` 仅做兜底，避免内部无 JWT 调用导致 `403` 后误判可用资金为 `0`。
  - Broker 适配兼容：`TradingEngine` 下单时按 Broker 类型转换 `side/order_type`（QMT 用大写，模拟盘用小写），并在 Broker 不支持 `client_order_id` 参数时自动跳过，避免 `unexpected keyword argument` 导致执行失败。
  - REAL 下单默认 Broker 已切换为 `bridge`：通过 `quantmind-stream` 内部接口将订单派发到在线 QMT Agent（`/ws/bridge`），不再默认依赖 `QMT_HOST:QMT_PORT` 本地 HTTP 直连。
  - 新增配置：`REAL_BROKER_TYPE`（默认 `bridge`，可选 `qmt`/`redis`）；`REAL` 下单若未传 `client_order_id`，会自动生成 `auto-<uuid>` 以保证 Agent 回报可关联订单。
  - 修复 `TradingEngine` 在 `begin_nested()` 中调用会 `commit` 的 service 导致事务关闭异常（`Can't operate on closed transaction...`）；Bridge 派发场景下改为仅提交“已派发”状态，真实成交统一由 `/bridge/execution` 回写落库。
  - `TradingEngine` 的 `asyncio.TimeoutError` 分支现在统一保留当前订单状态，并追加 `[AWAITING_BRIDGE_ACK]` / `[BRIDGE_ACK_TIMEOUT_PENDING_REVIEW]` 标记，避免把“派发后状态未知”的订单误写成终态失败。
- `/api/v1/real-trading/status` 容错增强：当 Redis 中 `trade:active_strategy:{tenant}:{user}` 为历史脏数据、非 JSON 或非对象结构时，不再直接返回 `500`，改为记录告警并按空状态继续返回。
- 同一接口在实盘运行时会额外返回当前组合快照 `portfolio`，并透出 `daily_pnl` / `daily_return`，供上层策略监控直接显示真实“今日收益”。
- 执行面：`runner` 通过内部网关 `/api/v1/internal/strategy/order` 上报信号。
- 执行回写新增：`POST /api/v1/internal/strategy/dispatch/item-status`（内部密钥保护）用于按 `client_order_id` 回写 `engine_dispatch_items` 与 `orders` 状态，支撑实盘 E2E 状态机闭环。
- 交易面：内部网关直接落单并调用 `TradingEngine` 执行（风控检查 -> Broker 下单 -> 订单/成交落库 -> Redis 账户回写）。
- 影子模式：`trading_mode=SHADOW` 在 `SimulationAccountManager` 做虚拟成交，不触发真实 Broker。
- 模拟结算器：`SimulationSettler` 已补齐目标权重到调仓股数（`delta_volume`）换算逻辑，避免结算阶段未定义变量导致中断。
- 身份与租户：内部网关统一从 `X-User-Id`/`X-Tenant-Id` 识别执行主体，缓存键统一带 `tenant_id`。
  - 旧链路下线：`dispatcher`（`trade:internal:order_queue`）与 `order_stream_consumer`（`trade:orders:*`）已移除，不再作为交易执行入口。
  - 账户盈亏口径增强（2026-03-23）：
- `POST /api/v1/internal/strategy/bridge/account` 会先将账户快照持久化到 PostgreSQL，再更新 Redis 缓存；`POST /api/v1/real-trading/account` 现在只读 PostgreSQL 视图 `real_account_snapshot_overview_v`，不再在 API 层拼接 Redis 补字段；
- 当券商未上报或上报为 0 时，服务端会基于数据库快照基线自动推导 `today_pnl/total_pnl/monthly_pnl/total_return`，并按持仓 `cost_price/last_price/volume` 推导 `floating_pnl`；
- 新增表 `real_account_snapshots`（ORM 定义位于 `backend/services/trade/models/real_account_snapshot.py`，按 `tenant_id/user_id/account_id/snapshot_at` 维度持久化），同时新增视图 `real_account_snapshot_overview_v`，统一输出最新快照与日/月/累计基线，避免 Redis 重启或覆盖导致口径漂移；
    - 首次启用时支持“上一交易日收盘权益”自动回填：当历史缺少前一日快照且券商上报 `today_pnl` 可用时，会自动写入 `source=auto_backfill_prev_close` 的回填快照，并作为今日基线；
    - `trade:account:{tenant}:{user}` 仅保留短期缓存与推送用途，不再参与账户概览页面展示决策；
    - `real_account_snapshot_overview_v` 负责提供 `today_pnl/total_pnl/floating_pnl` 以及 `initial_equity/day_open_equity/month_open_equity` 等展示口径，前端只消费 PostgreSQL 派生结果。
    - `payload_json` 会把桥接上报的柜台扩展字段（含 `positions` / `credit` / `metrics_meta`）一并落库，供风险校验、审计与 broker 兼容查询使用。
    - 口径一致性修复：`total_return` 与最终 `total_pnl` 同源计算（`broker_raw` 或 `db_snapshot`），避免“总盈亏为负但收益率显示 0.00%”。
    - 新增 `win_rate`（基于持仓盈利只数占比）随账户快照一并上报，供资金卡片“投资胜率”展示。
  - REAL 成交回写防覆盖（2026-03-23）：
    - `TradingEngine._sync_account_to_redis` 在 `recent_mode=REAL` 时不再覆盖 `trade:account`；
    - REAL 账户快照统一以 QMT Agent 的 `bridge/account` 为准，避免丢失扩展字段（如 `metrics/metrics_meta`）。
- **股票名称自动补全 (2026-03-23)**:
  - 新增 `backend/services/trade/utils/stock_lookup.py`：基于本地 `stocks_index.json` 的通用股票名称查询工具，支持 Docker 路径自适应。
  - `OrderService` 与 `InternalStrategyRouter` 已全链路接入该工具，确保报单、成交及持仓快照中的 `symbol_name` 字段在缺失时能自动补全。
  - `QMTPositionPayload` 协议已扩展 `symbol_name` 字段，支持持仓明细中的名称显示。
- Runner 地址规范：
  - 可直接设置完整地址 `TRADE_SERVICE_HEARTBEAT_URL` / `TRADE_SERVICE_ORDER_URL`
  - 或设置基地址 `TRADE_SERVICE_INTERNAL_URL`（自动拼接 `/heartbeat` 与 `/order`）

## 实盘发布端三层信号改造（2026-02-26）
- `runner` 执行端已切换为消费 `signal stream`（`qm:signal:stream:{tenant}`），不再在执行端主动调用 pipeline。
- runner 启动阶段云端模型下载默认后缀已切换为 `.txt`（`/app/model.txt`），与 `model_qlib/model.txt` 生产模型格式保持一致。
- 信号生产由 `engine` 侧发布（`ENABLE_SIGNAL_STREAM_PUBLISH=true`），执行端只做消费、风控和下单。
- 动态 runner 运行时地址统一：
  - `TRADE_SERVICE_INTERNAL_URL` 默认 `http://quantmind-trade:8002/api/v1/internal/strategy`
  - `ENGINE_SERVICE_INTERNAL_URL` 默认 `http://quantmind-engine:8001/api/v1`
  - 避免容器内误用 `127.0.0.1` 或遗留 `trade-core/engine-compute` 域名导致回写/查询失败。
- 发布行为：按融合得分排序生成订单，写入 `/api/v1/internal/strategy/order`；`remarks` 附带 `fusion_score` 便于审计。
- 调度方式：runner 在交易时段持续消费 Redis Stream（`XREADGROUP` 阻塞读取），不再按日触发“执行端再平衡”，循环内按 `heartbeat_interval_seconds` 持续心跳上报。
- 幂等防重：对每轮订单信号计算指纹并写入 Redis `SETNX` 锁（`idempotency_ttl_seconds`），重复信号自动跳过下单。
- 服务端幂等：runner 为每笔订单注入 `client_order_id`，`/api/v1/internal/strategy/order` 对重复 `client_order_id` 返回 `duplicate_skipped`，不重复创建订单。
- 信号归属隔离：runner 默认使用 `signal-runners-{tenant}-{user}-{strategy}` 独立 consumer group，避免多 runner 共享组导致串单；消费时按 `event.user_id` 二次校验。
- 执行回报入库消费：`ExecutionStreamConsumer` 订阅 `EXEC_STREAM_PREFIX:{tenant}`，处理 `order_submitted/order_rejected/order_filled`；
  - 订单匹配优先级：`order_id(UUID)` -> `tenant_id + user_id + client_order_id` -> `tenant_id + user_id + exchange_order_id` -> 兼容将 `broker_order_id` 解释为本地 `order_id(UUID)`；
  - `order_filled` 幂等键优先使用 `exchange_trade_id`；若上游未提供，再回退到 `broker_order_id + exec_id`，避免把 `broker_order_id` 错当本地 UUID 才能入账。
- 信号最新性闸门：runner 会读取 `qm:signal:latest:{tenant_id}:{user_id}`，仅接受当前最新 `run_id` 的 `qm:signal:stream:{tenant}` 消息；旧 run 或重放消息会被直接 ACK 丢弃，避免消费过期推理结果。
- 为避免“最新推理刚完成、runner 已读到旧快照”的短窗口，runner 在真正发单前会再次读取 `qm:signal:latest:{tenant_id}:{user_id}` 并做二次比对；若版本已变化，信号会在下单前被跳过，不会继续送往交易服务。
- `quantmind-trade` 服务启动时会自动拉起 `ExecutionStreamConsumer`（受 `ENABLE_EXEC_STREAM_CONSUMER` 开关控制），服务停止时自动优雅下线并完成已拉取批次的 ACK。
- 组合级风控闸门：下单前调用 `/api/v1/internal/strategy/sync-account` 获取真实资金/持仓，并执行
  `max_turnover_ratio_per_cycle`、`buy_cash_utilization`、`max_single_order_notional`、持仓卖出上限等约束。
- 执行风控补充：runner 支持 `max_buy_drop`（日内大跌买入拦截）与 `stop_loss`（达到阈值后仅允许卖出减仓）。
- 执行时机调度增强（2026-03-13）：
  - runner 读取 `LIVE_TRADE_CONFIG`，按 `rebalance_days/schedule_type/trade_weekdays` 判断是否为调仓日；
  - 按 `enabled_sessions + sell_time + buy_time + sell_first` 划分 `IDLE/SELL/BUY` 阶段，`SELL` 窗口仅允许卖单、`BUY` 窗口仅允许买单；
  - 模拟盘与自动托管执行支持同一时间买卖：支持 `sell_time == buy_time` 配置，此时任务将在触发时间点一次性唤醒并按“先卖后买”逻辑自动串行完成所有订单，从而简化模拟盘及托管任务的记账式交易；
  - 每轮下单数量受 `max_orders_per_cycle` 限制，并在结构化日志中输出 `phase/is_rebalance_day/live_trade_config`。
  - 时区口径固定为 `RUNNER_TIMEZONE`（默认 `Asia/Shanghai`），避免容器默认 UTC 导致交易时段门禁误判为 `IDLE`。
- 临时联调开关（仅测试）：
  - 设置 `RUNNER_TEST_MODE=true` 后，runner 会绕过交易日/交易时段门禁，直接消费 Stream 并执行下单流程；
  - 验证结束后需立即关闭该开关并重启 runner，避免非交易时段误执行。
- 执行参数对齐补齐（2026-03-13）：
  - `execution_config.stop_loss` 已直接映射 runner 全局止损，不再依赖历史键 `global_stop_loss_drawdown`；
  - `execution_config.max_buy_drop` 已接入买入拦截逻辑，当行情跌幅低于阈值时跳过买单；
  - `live_trade_config.max_price_deviation` 已接入 runner 价格偏离校验，按前端设置限制信号价与实时价偏差。
- 交易时段调度：默认仅在工作日的 A 股连续竞价时段（09:30-11:30, 13:00-15:00）执行信号消费与下单；可通过 `ignore_trading_calendar=true` 覆盖。
- 日历引擎：默认启用 `use_exchange_calendar=true`，优先使用 `exchange_calendars` 的 `XSHG` 交易所日历做精确交易日/时段判断（节假日与盘中休市）；不可用时自动回退到工作日+固定时段规则。
- 容器环境新增：
  - `TENANT_ID`：由控制面注入，内部调用统一带 `X-Tenant-Id`
  - `EXECUTION_CONFIG` 支持：
    `max_orders/notional_per_order/lot_size/idempotency_ttl_seconds/`
    `max_turnover_ratio_per_cycle/buy_cash_utilization/max_single_order_notional`
    `heartbeat_interval_seconds/off_market_sleep_seconds`
  - `RUNNER_ENABLE_EXEC_STREAM_PUBLISH`：默认 `true`，将下单执行回报写入 Redis Stream。
  - `LIVE_TRADE_CONFIG`：控制调仓周期、执行时段、买卖时间点、委托方式与单轮最大委托数。
  - `EXEC_STREAM_PREFIX`：默认 `qm:exec:stream`。
  - `SIGNAL_STREAM_PREFIX`：默认 `qm:signal:stream`。
  - `SIGNAL_STREAM_GROUP`：可选；不填时默认 `signal-runners-{tenant}-{user}-{strategy}`。
  - `SIGNAL_STREAM_CONSUMER_NAME`：可选；不填时默认 `runner-{tenant}-{user}-{strategy}`。
  - `SIGNAL_STREAM_BATCH_SIZE`：默认 `100`。
  - `SIGNAL_STREAM_BLOCK_MS`：默认 `1000`。
- 安全回退：若三层闭环调用失败，runner 将停止本轮下单并保留心跳，不再发旧静态假信号。
- Deployment 命名规则：
  - runner Deployment 统一按 `strategy-{tenant}-{user}` 命名，并对超长名称做截断 + hash；
  - `start/stop/status/logs` 全链路统一使用 `tenant_id + user_id` 寻址，避免多租户下命名冲突或查错命名空间对象。
- 消费器开关与参数：
  - `ENABLE_EXEC_STREAM_CONSUMER`：默认 `false`（建议灰度开启）
  - `EXEC_STREAM_PREFIX`：默认 `qm:exec:stream`
  - `EXEC_STREAM_GROUP`：默认 `exec-trade`
  - `EXEC_STREAM_CONSUMER_NAME`：默认 `trade-consumer-1`
  - `EXEC_STREAM_BATCH_SIZE`：默认 `100`
  - `EXEC_STREAM_BLOCK_MS`：默认 `3000`
  - `EXEC_STREAM_TENANTS`：默认 `default`（多租户可逗号分隔）
  - `EXEC_STREAM_REDIS_DB`：默认 `0`（用于执行回报流消费，独立于 `trade` 主 Redis DB）
  - `EXEC_STREAM_MAX_RETRY`：默认 `3`（处理失败后重试次数）
  - `EXEC_STREAM_DLQ_PREFIX`：默认 `qm:exec:dlq`（重试耗尽/非法事件入死信）
- 订单超时扫描（防“submitted 假成功”）：
  - `ORDER_TIMEOUT_MINUTES`：默认 `30`，兜底将长时间无回报的 `REAL+SUBMITTED` 订单标记为 `EXPIRED`。
  - `ORDER_SCAN_INTERVAL_SEC`：默认 `300`，长超时扫描周期。
  - `BRIDGE_ACK_TIMEOUT_SECONDS`：默认 `20`，仅针对含 `[AWAITING_BRIDGE_ACK]` 且无 `exchange_order_id` 的桥接订单，超时追加 `[BRIDGE_ACK_TIMEOUT_PENDING_REVIEW]` 标记并推送“待核查”通知，不直接改写为 `REJECTED`。
  - `BRIDGE_ACK_SCAN_INTERVAL_SEC`：默认 `5`，桥接 ACK 短超时扫描周期。
  - `TradingEngine` 直接下单请求超时同样会走“待核查”语义，不会改写为 `REJECTED`，并保留桥接等待标记供扫描器兜底。

### DLQ 回放工具
```bash
# 1) 先 dry-run 看候选事件
python backend/services/trade/scripts/dlq_replay.py \
  --tenant default \
  --event-type order_filled \
  --reason-contains processing_error \
  --max-count 50 \
  --dry-run

# 2) 执行回放并删除已回放的 DLQ 消息
python backend/services/trade/scripts/dlq_replay.py \
  --tenant default \
  --event-type order_filled \
  --max-count 50 \
  --delete-after-replay
```

### P2-2 数据迁移/验收/回滚
```bash
# 迁移
psql "$PSQL_URL" -v ON_ERROR_STOP=1 -f backend/migrations/add_trade_portfolio_tenant_id.sql

# 验收
psql "$PSQL_URL" -v ON_ERROR_STOP=1 -f backend/migrations/verify_trade_portfolio_tenant_id.sql

# 回滚（仅当 tenant_id 全部为 default 时允许）
psql "$PSQL_URL" -v ON_ERROR_STOP=1 -f backend/migrations/rollback_trade_portfolio_tenant_id.sql
```

## 实盘 Runner 镜像构建（基于 Qlib 回测环境）
- 统一镜像 Dockerfile：`/Users/qusong/git/quantmind/docker/Dockerfile.ml-runtime`
- 默认镜像名：`quantmind-ml-runtime:latest`（与 `STRATEGY_RUNNER_IMAGE` 默认值语义一致）
- 实盘状态接口 `real_trading_lifecycle.py` 依赖 `real_trading_utils.py` 的 `_fetch_active_portfolio_snapshot` 等内部 helper；拆分后若新增状态字段，必须同步导入清单。

```bash
# 本地构建（默认安装 pyqlib）
docker build -f docker/Dockerfile.ml-runtime \
  -t quantmind-ml-runtime:latest \
  .

# 不安装 pyqlib（仅执行端消费信号/下单场景，可加快构建）
docker build -f docker/Dockerfile.ml-runtime \
  --build-arg SKIP_PYQLIB=1 \
  -t quantmind-ml-runtime:latest \
  .

# 面向 x86_64 服务器构建（推荐）
docker build --platform linux/amd64 -f docker/Dockerfile.ml-runtime \
  -t quantmind-ml-runtime:latest \
  .

# 构建并推送到镜像仓库
docker build --platform linux/amd64 -f docker/Dockerfile.ml-runtime \
  -t asia-east1-docker.pkg.dev/<project>/<repo>/quantmind-ml-runtime \
  .
```

### 构建参数
- `PIP_INDEX_URL`：默认 `https://mirrors.cloud.tencent.com/pypi/simple/`，可切换为企业镜像源。
- `SKIP_PYQLIB`：默认 `auto`；设为 `1` 跳过 `pyqlib` 安装，设为 `0` 强制安装。

### 运行时关键说明
- 镜像已包含 `backend/shared`，保证 runner 可正常导入 `backend.shared.event_bus.schemas`。
- 旧 runner 入口 `/app/main.py` 已退役，仅保留兼容性警告；新的实盘执行必须通过手动任务或托管任务链路完成。
- runner 会优先直接读取 `INTERNAL_CALL_SECRET/SECRET_KEY`，避免镜像因认证模块额外依赖导致启动失败。
- 生产环境通过 `STRATEGY_RUNNER_IMAGE` 指向目标镜像 tag，当前主标签为 `quantmind-ml-runtime:latest`。
- 当前统一镜像 `docker/Dockerfile.ml-runtime` 未定义通用 `HEALTHCHECK`；健康检查应由具体服务进程或编排层按入口职责单独配置。

## 本次重构更新（2026-02-18）
- 移除 `main.py` 中历史 portfolio 服务的 `sys.path` 注入。
- 将 portfolio 相关实现本地化到 `backend/services/trade/portfolio/`：
  - `models/`
  - `schemas/`
  - `services/`
  - `utils/`
  - `config.py`
- `trade` 服务不再直接依赖历史 portfolio 模块。
- 修复 `deps.get_redis` 依赖注入，统一返回 `trade.redis_client.RedisClient`，
  避免模拟盘/订单链路出现 Redis 客户端类型不一致。
- 修复模拟盘与组合路由中的 `user_id` 类型对齐（JWT 字符串 -> 整型），
  避免写库/查询时出现 PostgreSQL 类型不匹配。
- 新增 `PositionService.sync_trade_update`，支持“成交同步持仓”内部链路。
- 数据库初始化 `init_db()` 已接入统一 Schema 注册中心
  `backend/shared/schema_registry.py`，一次性建表覆盖：
  - `trade.core`
  - `trade.simulation`
  - `trade.portfolio`

## Schema 归口巡检
```bash
source .venv/bin/activate
python backend/scripts/schema_registry_audit.py --schema trade.core --schema trade.simulation --schema trade.portfolio
```

## 测试
```bash
source .venv/bin/activate
pytest -q backend/services/tests/test_trade_service.py
pytest -q backend/services/tests/test_e2e_deep_real_infra.py
pytest -q backend/services/tests
```

## 修复记录（2026-03-09，实盘启停状态回写）

- 通知中心联动（交易/实盘优先）：
- `real_trading/start|stop` 会按模式真正拉起/停止运行容器或沙箱任务，但仍会异步发布用户通知（`type=strategy`）；
- `TradingEngine` 在 Broker 拒单、执行异常、成交确认时发布通知；
- `ExecutionStreamConsumer` 在 `order_rejected` 与 `order_filled(最终成交)` 时发布通知。
- 发布方式：
  - 统一通过 `backend.shared.notification_publisher.publish_notification_async`；
  - best-effort，失败仅告警，不阻塞交易主流程。

- `real_trading/start` 与 `real_trading/stop` 成功后，新增“非阻塞异步回写”策略生命周期状态：
  - `start` -> best-effort 回写策略为 `live_trading`；
  - `stop` -> best-effort 回写策略为 `repository`。
- 回写实现特性：
  - 不阻塞主接口返回；
  - 轻量重试 + 告警日志；
  - 回写失败不影响启停主流程成功响应。
- 异常口径：
  - 运行态 `error` 不自动降级生命周期，策略仍保持 `live_trading`，由前端基于 `runtime_state=error` 展示异常。

## 修复记录（2026-05-25，模拟盘资金分配与资金快照刷新）

- 模拟盘手动任务买单重算（`manual_execution_service.py`）增强：
  - `_rebuild_buy_orders_for_simulation_cash` 改为“实时价优先”重算，不再盲目沿用预览阶段的 `reference_price`。
  - 新增 `SIM_BUY_REBUDGET_PRICE_DRIFT_THRESHOLD`（默认 `0.2`）偏差阈值，预览价与实时价偏差过大时强制采用实时价，降低“前几笔成交吃满资金、后续批量拒单”的概率。

- 模拟盘账户实时估值（`routers/simulation.py`）增强：
  - `_build_realtime_positions_from_db` 改为并发拉取各持仓行情，避免逐只串行请求导致 `/simulation/account` 响应变慢、前端刷新滞后。
  - `_get_latest_price` 增加代码格式自适应（Prefix/Suffix 双格式尝试）并完善数据库兜底查询，减少代码格式不一致导致的估值缺失。

## 修复记录（2026-05-25，模拟盘成交价回退到 100 的根因修复）

- 现象：部分模拟盘成交均价异常接近 `100`，与真实行情偏离明显。
- 根因：
  - `simulation/execution_engine.py` 拉取行情时携带了 `X-Internal-Call: true`，被 stream 侧按匿名请求处理并返回 `403`；
  - 失败后查库仅按单一 symbol 格式查询 `stock_daily_latest`，后缀/前缀不一致时命中失败；
  - 旧版本两级都失败后会触发随机价格兜底，导致成交价异常接近 `100`。
- 修复：
  - 行情请求统一携带 `X-Internal-Call: INTERNAL_CALL_SECRET`（并透传 `X-User-Id/X-Tenant-Id`）；
  - 行情查询与数据库兜底均支持 Prefix/Suffix 双格式尝试；
  - 同步修复 `routers/simulation.py` 账户估值链路的内部鉴权头，避免资产页估值也被 403 降级。

## 修复记录（2026-05-25，模拟盘30秒刷新链路对齐）

- 将模拟盘资金快照后台任务默认周期从 `300s` 调整为 `30s`：
  - `SIM_FUND_SNAPSHOT_INTERVAL_SECONDS` 默认值改为 `30`；
  - `SimulationFundSnapshotWorker` 最小间隔从 `60s` 放宽到 `5s`，便于环境按需配置。
- 在 `SimulationFundSnapshotService.capture_all` 中，行情重算后立即回写：
  - `simulation:account:{tenant}:{user}`（模拟账户 Redis 实时态）；
  - `trade:account:{tenant}:{user}`（交易账户缓存，供前端/交易链路读取）。
- 收盘结算口径保持不变：实盘日账本仍由 `real_account_ledger_settlement_task` 在收盘后窗口触发。

## 修复记录（2026-05-25，模拟盘今日盈亏/浮动盈亏口径补齐）

- `GET /api/v1/simulation/account` 现在会返回并维护：
  - `today_pnl / daily_pnl`：优先以“上一交易日资金快照 total_asset”为日开盘基线计算；
  - `floating_pnl`：基于持仓 `cost_price` 与最新价逐仓计算（支持 long/short）；
  - `total_pnl`：`total_asset - initial_equity`。
- 当实时仓位来自 `sim_trades` 聚合时，会尝试从 Redis 持仓对象回填 `cost_price`（含 Prefix/Suffix + `::long` 兼容），避免浮盈长期为 0。
- 当实时仓位回退到 Redis 且无成交历史时，若发现 `initial_equity` 缺失或与 `cash + 持仓成本` 明显偏离，接口会自动按种子持仓成本纠正基线，使 `total_pnl` 与 `floating_pnl` 保持同一口径。

## 公司行为 CSV 维护格式（2026-06-17）

- 默认维护文件：
  - `backend/services/trade/data/corporate_actions.csv`
- 原始公司行为 CSV 导入预览：
  - `python backend/services/trade/scripts/import_simulation_corporate_actions.py --dry-run`
- 确认预览结果后可正式写入：
  - `python backend/services/trade/scripts/import_simulation_corporate_actions.py --replace-existing`
- 服务器宿主机日常更新建议直接使用一条同步脚本：
  - `bash backend/services/trade/scripts/run_corporate_actions_sync.sh`
  - 该脚本会自动：
    - 加载项目根目录 `.env`
    - 把宿主机不可解析的 `quantmind-postgresql` 自动改连 `127.0.0.1:5432`
    - 执行公司行为导入（`--replace-existing`）
    - 执行到期公司行为应用
    - 输出 `applied/pending` 状态汇总
- 当前已确认支持的一类上游原始格式为：
  - 表头：`symbol,code,date,type,bonus,allotment`
  - 示例：`sh600857.SH,600857.SH,2026-06-01,1,0.45,0.0`
- 当前已确认的映射规则：
  - `type=1` 且 `bonus>0`：映射为模拟盘 `dividend`
  - `date`：映射到 `ex_date`
  - `bonus`：语义为“每 10 股派现金额”，导入时必须转换为 `cash_dividend_per_share = bonus / 10`
  - `symbol/code`：统一通过 `StockCodeUtil` 转成 Prefix 口径（如 `SH600857`）
- 当前明确跳过的记录：
  - `type!=1`
  - `bonus<=0`
  - `allotment>0`（尚未确认上游配股字段口径前，不直接映射到 `rights_issue`）
- 这样做的原因是模拟盘内部公司行为服务按“每股现金分红”计算：
  - 若把上游 `bonus` 直接当 `cash_dividend_per_share`，会把分红放大 10 倍，导致 `cash/equity/total_asset` 全部失真
