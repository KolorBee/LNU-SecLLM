# Trading Components

## 组件说明

- `PositionOverview.tsx`：实盘交易页和策略状态页共享的持仓概览组件，统一渲染持仓分布饼图与持仓明细表，数据源来自标准化后的 `holdings + summary`。
- `LiveTradeConfigForm.tsx`：实盘交易执行参数表单。
- `LiveTradeConfigWizard.tsx`：实盘执行参数向导。
- `TopBar.tsx`：交易页顶部工具栏。

## 执行参数约定

- `LiveTradeConfigForm.tsx` 的交易时段与后端 `live_trade_config` 校验保持一致：上午 `09:30-11:30`、下午 `13:00-15:00`。
- 卖出时间与买入时间允许相同；相同时后端托管调度会将该轮识别为 `ALL` 阶段，一次性执行卖买流程。

## 设计约束

- 持仓相关展示优先复用 `PositionOverview.tsx`，避免不同页面各自维护一套图表和表格口径。
- 页面级组件负责数据拉取、权限控制和外层布局，组件级模块只负责展示与交互。
