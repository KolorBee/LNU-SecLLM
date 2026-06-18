/**
 * 策略模板库
 *
 * 提供常用的交易策略模板，方便用户快速开始
 */

export interface StrategyTemplate {
    id: string;
    name: string;
    category: string;
    description: string;
    difficulty: 'beginner' | 'intermediate' | 'advanced';
    tags: string[];
    code: string;
    author?: string;
    parameters?: {
        name: string;
        type: string;
        default: any;
        description: string;
    }[];
}

export const strategyTemplates: StrategyTemplate[] = [
    // --- Beginner (入门) ---
    {
        id: 'standard_topk',
        name: '默认 Top-K 选股策略',
        category: '选股策略',
        description: '最经典的量化选股逻辑。每日截面排名，精选最具潜力的 Top-K 标的，等权持仓。',
        difficulty: 'beginner',
        tags: ['选股', 'Top-K', '等权'],
        code: `"""\n默认 Top-K 选股策略 (Standard Top-K Strategy)\n[Native] 核心逻辑：Top-K 选股 + 零换手强制约束\n"""\nSTRATEGY_CONFIG = {\n    "class": "RedisTopkStrategy",\n    "kwargs": {\n        "signal": "<PRED>",\n        "topk": 50,\n        "n_drop": 10,\n    }\n}`,
        parameters: [
            { name: 'topk', type: 'int', default: 50, description: '持仓股票总数' },
        ],
    },
    {
        id: 'momentum',
        name: '趋势动量策略',
        category: '趋势跟踪',
        description: '基于"强者恒强"逻辑，自动筛选过去一段时间涨幅最高且波动稳健的行业或个股。',
        difficulty: 'beginner',
        tags: ['动量', '趋势', '强度'],
        code: `"""\n趋势动量策略 (Momentum Strategy)\n[Native] 核心逻辑：基于过去 20-60 天的累计收益率进行排名。\n"""\nSTRATEGY_CONFIG = {\n    "class": "RedisTopkStrategy",\n    "kwargs": {\n        "topk": 30,\n        "n_drop": 6,\n        "momentum_period": 20\n    }\n}`,
        parameters: [
            { name: 'topk', type: 'int', default: 30, description: '选股数量' },
            { name: 'momentum_period', type: 'int', default: 20, description: '动量回看周期 (天)' },
        ],
    },
    {
        id: 'StopLoss',
        name: '止损止盈策略',
        category: '风险控制',
        description: '在标准 TopK 选股基础上叠加硬性止损/止盈规则，一旦触发立即强制平仓，保护资金安全。',
        difficulty: 'beginner',
        tags: ['风控', '止损', '止盈'],
        code: `"""\n止损止盈策略 (Stop-Loss / Take-Profit Strategy)\n[Native] 核心逻辑：每日持仓浮亏超过 stop_loss 或浮盈超过 take_profit 时，强制平仓并从选股池剔除。\n"""\nSTRATEGY_CONFIG = {\n    "class": "RedisStopLossStrategy",\n    "kwargs": {\n        "signal": "<PRED>",\n        "topk": 30,\n        "n_drop": 6,\n        "stop_loss": -0.08,\n        "take_profit": 0.15,\n    }\n}`,
        parameters: [
            { name: 'topk', type: 'int', default: 30, description: '选股数量' },
            { name: 'stop_loss', type: 'float', default: -0.08, description: '止损触发阈值' },
            { name: 'take_profit', type: 'float', default: 0.15, description: '止盈触发阈值' },
        ],
    },
    {
        id: 'risk_guard_topk',
        name: '大盘风控 Top-K 选股策略',
        category: '风险控制',
        description: '在基础 Top-K 选股之上叠加基本面硬过滤、行业集中度约束与大盘下行降仓，适合盘后生成、次日开盘执行。',
        difficulty: 'intermediate',
        tags: ['风控', '大盘周期', 'Top-K'],
        code: `"""\n大盘风控 Top-K 选股策略 (Risk-Guarded Top-K)\n[Native] 核心逻辑：Top-K 选股 + 基本面硬过滤 + 大盘周期降仓\n适合收盘后计算、次日开盘前推理的盘后选股流程。\n"""\nSTRATEGY_CONFIG = {\n    "class": "RedisRiskGuardTopkStrategy",\n    "kwargs": {\n        "signal": "<PRED>",\n        "topk": 50,\n        "n_drop": 10,\n        "rebalance_days": 3,\n        "market_state_symbol": "SH000300",\n        "market_state_window": 20,\n        "industry_cap_ratio": 0.30,\n        "listed_days_min": 120,\n        "turnover_rate_min": 0.5,\n        "turnover_rate_max": 15.0,\n        "beta_20_max": 1.8,\n        "float_mv_min": 500000000,\n    }\n}`,
        parameters: [
            { name: 'topk', type: 'int', default: 50, description: '持仓股票总数' },
            { name: 'n_drop', type: 'int', default: 10, description: '每期替换数量' },
            { name: 'rebalance_days', type: 'int', default: 3, description: '调仓周期（交易日）' },
            { name: 'market_state_symbol', type: 'string', default: 'SH000300', description: '市场状态参考指数' },
            { name: 'market_state_window', type: 'int', default: 20, description: '大盘状态判定窗口（交易日）' },
            { name: 'industry_cap_ratio', type: 'float', default: 0.3, description: '单行业持仓上限占比' },
            { name: 'listed_days_min', type: 'int', default: 120, description: '上市天数下限' },
            { name: 'turnover_rate_min', type: 'float', default: 0.5, description: '换手率下限（%）' },
            { name: 'turnover_rate_max', type: 'float', default: 15.0, description: '换手率上限（%）' },
            { name: 'beta_20_max', type: 'float', default: 1.8, description: '20日 Beta 上限' },
            { name: 'float_mv_min', type: 'int', default: 500000000, description: '流通市值下限（元）' },
        ],
    },

    // --- Intermediate (中级) ---
    {
        id: 'alpha_cross_section',
        name: '截面 Alpha 预测策略',
        category: '机器学习',
        description: '旗舰级机器学习选股策略。根据预测分自动分配资金权重，分高者重仓。',
        difficulty: 'intermediate',
        tags: ['Alpha', '截面', '权重分配'],
        code: `"""\n截面 Alpha 预测策略 (Cross-sectional Alpha)\n[Native] 核心逻辑：按模型预测分比例进行权重分配。\n"""\nSTRATEGY_CONFIG = {\n    "class": "RedisWeightStrategy",\n    "kwargs": {\n        "signal": "<PRED>",\n        "topk": 50,\n        "min_score": 0.0,\n        "max_weight": 0.05,\n    }\n}`,
        parameters: [
            { name: 'topk', type: 'int', default: 50, description: '参与权重的标的数量' },
            { name: 'max_weight', type: 'float', default: 0.05, description: '单票持仓上限 (0~1)' },
        ],
    },
    {
        id: 'adaptive_drift',
        name: '自适应动态调仓策略',
        category: '风险控制',
        description: '集成环境建模，自动识别牛熊阶段。动态调整选股宽度与仓位，应对风格漂移。',
        difficulty: 'intermediate',
        tags: ['自适应', '牛熊识别', '动态仓位'],
        code: `"""\n自适应动态调仓策略 (Adaptive Concept Drift)\n[Native] 核心逻辑：集成 MarketStateService，自动触发动态仓位开关。\n"""\nSTRATEGY_CONFIG = {\n    "class": "RedisRecordingStrategy",\n    "kwargs": {\n        "signal": "<PRED>",\n        "topk": 50,\n        "n_drop": 10,\n        "dynamic_position": True\n    }\n}`,
        parameters: [
            { name: 'topk', type: 'int', default: 50, description: '基准选股数量' },
        ],
    },
    {
        id: 'score_weighted',
        name: '得分加权组合策略',
        category: '选股策略',
        description: '根据模型预测分自动分配资金权重，分高者重仓，支持单票上限与最低分过滤。',
        difficulty: 'intermediate',
        tags: ['加权', '预测分', '组合优化'],
        code: `"""\n得分加权组合策略 (Score-Weighted)\n[Native] 核心逻辑：权重 = Score / Sum(Scores)，且 Weight <= Max_Weight。\n"""\nSTRATEGY_CONFIG = {\n    "class": "RedisWeightStrategy",\n    "kwargs": {\n        "signal": "<PRED>",\n        "topk": 50,\n        "min_score": 0.0,\n        "max_weight": 0.05,\n    }\n}`,
        parameters: [
            { name: 'topk', type: 'int', default: 50, description: '参与分配的股票数' },
            { name: 'max_weight', type: 'float', default: 0.05, description: '单只股票持仓上限' },
        ],
    },

    // --- Advanced (高级) ---
    {
        id: 'long_short_topk',
        name: '多空 TopK 策略',
        category: '高级算法',
        description: '同时做多最高分 TopK 与做空最低分 TopK，支持固定调仓周期、双向敞口和单票权重上限。',
        difficulty: 'advanced',
        tags: ['多空', 'Top-K', '双向交易', '做空'],
        code: `"""\n多空 TopK 策略 (Long-Short TopK)\n[Native] 核心逻辑：做多最高分 TopK + 做空最低分 TopK。\n"""\nSTRATEGY_CONFIG = {\n    "class": "RedisLongShortTopkStrategy",\n    "kwargs": {\n        "signal": "<PRED>",\n        "topk": 50,\n        "short_topk": 50,\n        "min_score": 0.0,\n        "max_weight": 0.05,\n        "long_exposure": 1.0,\n        "short_exposure": 1.0,\n        "rebalance_days": 5,\n        "enable_short_selling": True\n    }\n}`,
        parameters: [
            { name: 'topk', type: 'int', default: 50, description: '多头持仓股票数' },
            { name: 'short_topk', type: 'int', default: 50, description: '空头持仓股票数' },
            { name: 'rebalance_days', type: 'int', default: 5, description: '调仓周期（交易日）' },
            { name: 'max_weight', type: 'float', default: 0.05, description: '单票绝对权重上限 (0~1)' },
            { name: 'short_exposure', type: 'float', default: 1.0, description: '空头总敞口' },
        ],
    },
    {
        id: 'deep_time_series',
        name: '深度学习时序策略',
        category: '高级算法',
        description: '利用深度学习模型捕捉市场的长短期记忆效应，原生支持 3D 时序信号加载。',
        difficulty: 'advanced',
        tags: ['深度学习', '时序', 'GRU', 'LSTM'],
        code: `"""\n深度学习时序预测策略 (Time-Series GRU/LSTM)\n[Native] 核心逻辑：原生加载 .pkl 时序信号，支持 TS 格式特征。\n"""\nSTRATEGY_CONFIG = {\n    "class": "RedisRecordingStrategy",\n    "kwargs": {\n        "signal": "<PRED>",\n        "topk": 30,\n        "n_drop": 6,\n    }\n}`,
        parameters: [
            { name: 'topk', type: 'int', default: 30, description: '选股数量' },
            { name: 'n_drop', type: 'int', default: 6, description: '最大调仓数（默认按 topk 的 20%）' },
        ],
    },
    {
        id: 'aggressive_topk_strategy',
        name: '激进版截面TopK策略',
        category: '高级算法',
        description: '基于机器学习预测分数的激进版TopK动量轮动策略，零容忍度每日极致换仓，捕捉高频势能。',
        difficulty: 'advanced',
        tags: ['激进', '高频换手', '动量轮动'],
        code: `"""\n激进版截面TopK策略 (Aggressive Top-K Strategy)\n[Native] 核心逻辑：Top-K 选股 + 零容忍跌出即卖。\n"""\nSTRATEGY_CONFIG = {\n    "class": "RedisTopkStrategy",\n    "kwargs": {\n        "signal": "<PRED>",\n        "topk": 50,\n        "n_drop": 10,\n    }\n}`,
        parameters: [
            { name: 'topk', type: 'int', default: 50, description: '持仓股票总数' },
            { name: 'n_drop', type: 'int', default: 10, description: '每次调仓最大替换数量（默认按 topk 的 20%）' },
        ],
    },
];

export const getTemplatesByCategory = (category?: string) => {
    if (!category) return strategyTemplates;
    return strategyTemplates.filter(t => t.category === category);
};

export const getTemplateById = (id: string) => {
    return strategyTemplates.find(t => t.id === id);
};

export const getCategories = () => {
    return [...new Set(strategyTemplates.map(t => t.category))];
};
