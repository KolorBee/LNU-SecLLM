/**
 * 交易统计面板
 */

import React, { useEffect, useState } from 'react';
import { AlertTriangle, BarChart3, Info, RefreshCw, Target, TrendingDown, TrendingUp } from 'lucide-react';
import ReactECharts from 'echarts-for-react';
import {
  advancedAnalysisService,
  type TradeStatsResponse,
} from '../../../services/advancedAnalysisService';

interface TradeStatsPanelProps {
  backtestId: string;
}

export const TradeStatsPanel: React.FC<TradeStatsPanelProps> = ({ backtestId }) => {
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<TradeStatsResponse | null>(null);
  const [error, setError] = useState<string>('');

  useEffect(() => {
    if (backtestId) {
      void loadData();
    }
  }, [backtestId]);

  const loadData = async () => {
    setLoading(true);
    setError('');
    try {
      const tradeStatsResult = await advancedAnalysisService.analyzeTradeStats(backtestId);
      setData(tradeStatsResult);
    } catch (err: unknown) {
      setError(extractErrorMessage(err));
      console.error('加载交易统计失败:', err);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-center">
          <RefreshCw className="w-8 h-8 text-blue-500 animate-spin mx-auto mb-2" />
          <p className="text-sm text-gray-600">正在分析...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-2xl p-4">
        <div className="flex items-start gap-2">
          <AlertTriangle className="w-5 h-5 text-red-600 mt-0.5" />
          <div>
            <div className="font-medium text-red-800">分析失败</div>
            <div className="text-sm text-red-700 mt-1">{error}</div>
            <button
              onClick={() => void loadData()}
              className="mt-2 text-sm text-red-600 hover:text-red-700 underline"
            >
              重试
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="text-center text-gray-500 py-12">
        <Info className="w-12 h-12 mx-auto mb-2 opacity-50" />
        <p>选择回测结果后开始分析</p>
      </div>
    );
  }

  const isFallback = data.metrics.metric_basis !== 'closed_trade_fifo';

  const topMetrics = [
    {
      label: '交易胜率',
      value: data.metrics.real_win_rate,
      displayValue: isFallback ? '--' : undefined,
      format: 'percent' as const,
      icon: Target,
      color: 'red' as const,
    },
    {
      label: '平均盈亏',
      value: data.metrics.avg_trade_return,
      displayValue: isFallback ? '--' : undefined,
      format: 'percent' as const,
      icon: TrendingUp,
      color: data.metrics.avg_trade_return >= 0 ? 'red' as const : 'green' as const,
    },
    {
      label: '盈亏比',
      value: data.metrics.profit_loss_ratio,
      displayValue: isFallback ? '--' : undefined,
      format: 'number' as const,
      icon: BarChart3,
      color: 'purple' as const,
      decimals: 2,
    },
    {
      label: '利润因子',
      value: data.metrics.profit_factor,
      displayValue: isFallback ? '--' : undefined,
      format: 'number' as const,
      icon: TrendingUp,
      color: 'purple' as const,
      decimals: 2,
    },
    {
      label: '已完成交易笔数',
      value: data.metrics.closed_trades,
      displayValue: isFallback ? '--' : undefined,
      format: 'number' as const,
      icon: BarChart3,
      color: 'gray' as const,
      decimals: 0,
      suffix: '笔',
    },
  ];

  const detailMetrics = [
    {
      label: '月均交易次数',
      value: data.metrics.trade_frequency,
      displayValue: isFallback ? '--' : undefined,
      format: 'number' as const,
      icon: TrendingUp,
      color: 'gray' as const,
      decimals: 0,
      suffix: '笔',
    },
    {
      label: '未闭环买入批次',
      value: data.metrics.open_buy_trades,
      displayValue: isFallback ? '--' : undefined,
      format: 'number' as const,
      icon: TrendingDown,
      color: 'orange' as const,
      decimals: 0,
      suffix: '笔',
    },
    {
      label: '盈利交易',
      value: data.metrics.winning_trades,
      displayValue: isFallback ? '--' : undefined,
      format: 'number' as const,
      icon: TrendingUp,
      color: 'red' as const,
      decimals: 0,
      suffix: '笔',
    },
    {
      label: '亏损交易',
      value: data.metrics.losing_trades,
      displayValue: isFallback ? '--' : undefined,
      format: 'number' as const,
      icon: TrendingDown,
      color: 'green' as const,
      decimals: 0,
      suffix: '笔',
    },
    {
      label: '最大盈利',
      value: data.metrics.max_win_return,
      displayValue: isFallback ? '--' : undefined,
      format: 'percent' as const,
      icon: TrendingUp,
      color: 'red' as const,
    },
    {
      label: '最大亏损',
      value: data.metrics.max_loss_return,
      displayValue: isFallback ? '--' : undefined,
      format: 'percent' as const,
      icon: TrendingDown,
      color: 'green' as const,
    },
    {
      label: '盈利交易平均盈利',
      value: data.metrics.avg_win_return,
      displayValue: isFallback ? '--' : undefined,
      format: 'percent' as const,
      icon: TrendingUp,
      color: 'red' as const,
    },
    {
      label: '亏损交易平均亏损',
      value: -Math.abs(data.metrics.avg_loss_return),
      displayValue: isFallback ? '--' : undefined,
      format: 'percent' as const,
      icon: TrendingDown,
      color: 'green' as const,
    },
    {
      label: '平均持仓天数',
      value: data.metrics.avg_holding_days,
      displayValue: isFallback ? '--' : undefined,
      format: 'number' as const,
      icon: BarChart3,
      color: 'gray' as const,
      decimals: 2,
      suffix: '天',
    },
    {
      label: '总成交次数',
      value: data.metrics.total_trades,
      displayValue: isFallback ? '--' : undefined,
      format: 'number' as const,
      icon: BarChart3,
      color: 'gray' as const,
      decimals: 0,
      suffix: '笔',
    },
  ];

  return (
    <div className="space-y-6">
      <div className={`${isFallback ? 'bg-amber-50 border-amber-200' : 'bg-green-50 border-green-200'} border rounded-2xl p-4`}>
        <div className="flex items-start gap-2">
          <Info className={`w-4 h-4 mt-0.5 flex-shrink-0 ${isFallback ? 'text-amber-600' : 'text-green-600'}`} />
          <div className={`text-xs ${isFallback ? 'text-amber-700' : 'text-green-700'}`}>
            <div className="font-semibold mb-1 text-[11px]">真实交易能力</div>
            <div>
              {isFallback
                ? '该回测缺少完整成交闭环，当前部分指标为兼容口径；建议优先查看已完成且成交明细完整的回测结果。'
                : '当前指标按已平仓单笔交易 FIFO 配对计算，手续费已计入，未平仓仓位不纳入真实胜率。'}
            </div>
          </div>
        </div>
      </div>

      <div>
        <div className="text-xs font-semibold text-gray-700 mb-3">单笔交易核心指标</div>
        <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
          {topMetrics.map((metric) => (
            <MetricCard key={metric.label} {...metric} size="lg" />
          ))}
        </div>
      </div>

      <div>
        <div className="text-xs font-semibold text-gray-700 mb-3">交易明细</div>
        <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-3">
          {detailMetrics.map((metric) => (
            <MetricCard key={metric.label} {...metric} />
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <ChartCard title="单笔盈亏分布">
          {hasHistogramData(data.pnl_distribution) ? (
            <ReactECharts
              option={getPnlDistributionOption(data.pnl_distribution)}
              style={{ height: '320px' }}
              opts={{ renderer: 'canvas' }}
            />
          ) : (
            <EmptyChart />
          )}
        </ChartCard>

        <ChartCard title="持仓天数分布">
          {hasHistogramData(data.holding_days_distribution) ? (
            <ReactECharts
              option={getHoldingDaysOption(data.holding_days_distribution)}
              style={{ height: '320px' }}
              opts={{ renderer: 'canvas' }}
            />
          ) : (
            <EmptyChart />
          )}
        </ChartCard>
      </div>

      <ChartCard title="月度交易次数">
        {hasSeriesData(data.trade_frequency_series) ? (
          <ReactECharts
            option={getTradeFrequencyOption(data.trade_frequency_series)}
            style={{ height: '320px' }}
            opts={{ renderer: 'canvas' }}
          />
        ) : (
          <EmptyChart />
        )}
      </ChartCard>
    </div>
  );
};

const hasHistogramData = (series: { bins: number[]; counts: number[] }) =>
  Array.isArray(series?.bins) && Array.isArray(series?.counts) && series.bins.length > 1 && series.counts.length > 0;

const hasSeriesData = (series: { dates: string[]; values: number[] }) =>
  Array.isArray(series?.dates) && Array.isArray(series?.values) && series.dates.length > 0 && series.values.length > 0;

const ChartCard: React.FC<{ title: string; children: React.ReactNode }> = ({ title, children }) => {
  return (
    <div className="bg-white rounded-2xl border border-gray-200 p-4">
      <h3 className="text-sm font-medium text-gray-700 mb-4">{title}</h3>
      {children}
    </div>
  );
};

function getPnlDistributionOption(data: { bins: number[]; counts: number[] }) {
  const labels = buildHistogramLabels(data.bins, (value) => `${(value * 100).toFixed(1)}%`);
  return {
    tooltip: {
      trigger: 'axis',
      formatter: (params: Array<{ axisValue: string; value: number }>) => `${params[0].axisValue}<br/>频次: ${params[0].value}`,
    },
    grid: { left: '6%', right: '6%', bottom: '14%', top: '10%', containLabel: true },
    xAxis: { type: 'category', data: labels, axisLabel: { interval: 'auto' } },
    yAxis: { type: 'value', name: '频次' },
    series: [
      {
        name: '单笔收益率分布',
        type: 'bar',
        data: data.counts,
        itemStyle: { color: '#10b981' },
        barMaxWidth: 24,
      },
    ],
  };
}

function getHoldingDaysOption(data: { bins: number[]; counts: number[] }) {
  const normalized = normalizeHoldingDistribution(data);
  const labels = buildHoldingPeriodLabels();
  return {
    tooltip: {
      trigger: 'axis',
      formatter: (params: Array<{ axisValue: string; value: number }>) => `${params[0].axisValue}<br/>频次: ${params[0].value}`,
    },
    grid: { left: '6%', right: '6%', bottom: '14%', top: '10%', containLabel: true },
    xAxis: { type: 'category', data: labels, axisLabel: { interval: 0, rotate: 20 } },
    yAxis: { type: 'value', name: '频次' },
    series: [
      {
        name: '持仓天数',
        type: 'bar',
        data: normalized,
        itemStyle: { color: '#60a5fa' },
        barMaxWidth: 24,
      },
    ],
  };
}

function getTradeFrequencyOption(series: { dates: string[]; values: number[] }) {
  return {
    tooltip: {
      trigger: 'axis',
      formatter: (params: Array<{ axisValue: string; value: number }>) => `${params[0].axisValue}<br/>平仓交易数: ${params[0].value}`,
    },
    dataZoom: [
      { type: 'inside', start: 0, end: 100 },
      { start: 0, end: 100, height: 16 },
    ],
    grid: { left: '6%', right: '6%', bottom: '16%', top: '10%', containLabel: true },
    xAxis: {
      type: 'category',
      data: series.dates,
      axisLabel: {
        formatter: (value: string) => value.slice(2, 7),
      },
    },
    yAxis: { type: 'value', name: '笔数' },
    series: [
      {
        name: '月度交易次数',
        type: 'line',
        data: series.values,
        smooth: true,
        symbol: 'none',
        lineStyle: { color: '#f97316', width: 2 },
        areaStyle: { color: 'rgba(249, 115, 22, 0.2)' },
      },
    ],
  };
}

function buildHistogramLabels(bins: number[], formatter: (value: number) => string) {
  const labels: string[] = [];
  for (let i = 0; i < bins.length - 1; i += 1) {
    const mid = (bins[i] + bins[i + 1]) / 2;
    labels.push(formatter(mid));
  }
  return labels;
}

function buildHoldingPeriodLabels() {
  return ['1-7天', '7-30天', '30-90天', '90-180天', '180-365天'];
}

function normalizeHoldingDistribution(data: { bins: number[]; counts: number[] }) {
  const target = [0, 0, 0, 0, 0];
  const bins = Array.isArray(data?.bins) ? data.bins : [];
  const counts = Array.isArray(data?.counts) ? data.counts : [];
  if (!counts.length) return target;
  if (counts.length === 5) {
    return counts.map((value) => Number(value) || 0);
  }
  for (let i = 0; i < counts.length; i += 1) {
    const count = Number(counts[i]) || 0;
    const left = Number(bins[i]);
    const right = Number(bins[i + 1]);
    const mid = Number.isFinite(left) && Number.isFinite(right) ? (left + right) / 2 : Number.isFinite(left) ? left : i + 1;
    const idx = holdingBucketIndex(mid);
    if (idx >= 0) target[idx] += count;
  }
  return target;
}

function holdingBucketIndex(days: number) {
  if (days <= 1) return -1;
  if (days <= 7) return 0;
  if (days <= 30) return 1;
  if (days <= 90) return 2;
  if (days <= 180) return 3;
  return 4;
}

function extractErrorMessage(error: unknown): string {
  const err = error as {
    message?: string;
    response?: { data?: { detail?: string } };
  };
  return err?.response?.data?.detail || err?.message || '分析失败';
}

interface MetricCardProps {
  label: string;
  value: number;
  displayValue?: string;
  format: 'percent' | 'number';
  icon?: React.ComponentType<{ className?: string }>;
  color?: 'blue' | 'green' | 'red' | 'orange' | 'purple' | 'gray';
  decimals?: number;
  suffix?: string;
  size?: 'lg' | 'sm';
}

const MetricCard: React.FC<MetricCardProps> = ({
  label,
  value,
  displayValue,
  format,
  icon: Icon,
  color: _color = 'gray',
  decimals = 2,
  suffix = '',
  size = 'sm',
}) => {
  const formattedValue = displayValue ?? (format === 'percent'
    ? `${(value * 100).toFixed(decimals)}%`
    : value.toFixed(decimals));

  const palette: Record<string, { shell: string; icon: string; value: string }> = {
    red: { shell: 'bg-red-50/70 border-red-100', icon: 'bg-red-50 text-red-600', value: 'text-red-600' },
    green: { shell: 'bg-emerald-50/70 border-emerald-100', icon: 'bg-emerald-50 text-emerald-600', value: 'text-emerald-600' },
    orange: { shell: 'bg-orange-50/70 border-orange-100', icon: 'bg-orange-50 text-orange-600', value: 'text-orange-600' },
    purple: { shell: 'bg-violet-50/70 border-violet-100', icon: 'bg-violet-50 text-violet-600', value: 'text-violet-600' },
    blue: { shell: 'bg-sky-50/70 border-sky-100', icon: 'bg-sky-50 text-sky-600', value: 'text-sky-600' },
    gray: { shell: 'bg-slate-50/70 border-slate-200', icon: 'bg-slate-50 text-slate-600', value: 'text-slate-800' },
  };
  const resolvedPalette = palette[_color] || palette.gray;

  return (
    <div className={`rounded-2xl border p-4 hover:shadow-md transition-shadow flex flex-col items-center text-center relative overflow-hidden ${resolvedPalette.shell}`}>
      {Icon && (
        <div className={`absolute top-3 right-3 w-6 h-6 rounded-lg flex items-center justify-center ${resolvedPalette.icon}`}>
          <Icon className="w-3 h-3" />
        </div>
      )}
      <span className={size === 'lg' ? 'text-xs font-semibold text-gray-700 mb-1' : 'text-[10px] font-semibold text-gray-700 mb-1'}>{label}</span>
      <div className={`${size === 'lg' ? 'text-lg' : 'text-base'} font-bold ${resolvedPalette.value}`}>
        {formattedValue}{suffix}
      </div>
    </div>
  );
};

const EmptyChart: React.FC = () => {
  return (
    <div className="h-[320px] rounded-2xl border border-dashed border-gray-200 flex items-center justify-center text-sm text-gray-400">
      暂无数据
    </div>
  );
};
