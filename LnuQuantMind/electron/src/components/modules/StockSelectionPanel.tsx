import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Search, Loader2, CheckCircle, AlertCircle, Download, TrendingUp, DollarSign } from 'lucide-react';
import axios from 'axios';
import { SERVICE_ENDPOINTS } from '../../config/services';

interface StockResult {
    symbol: string;
    name: string;
    pe_ratio?: number;
    pb_ratio?: number;
    market_cap?: number;
    roe?: number;
    turnover?: number;
    close?: number;
}

interface StockSelectionPanelProps {
    onStockPoolSelected?: (symbols: string[]) => void;
}

export const StockSelectionPanel: React.FC<StockSelectionPanelProps> = ({
    onStockPoolSelected
}) => {
    const [query, setQuery] = useState('');
    const [isSelecting, setIsSelecting] = useState(false);
    const [results, setResults] = useState<StockResult[]>([]);
    const [selectedStocks, setSelectedStocks] = useState<Set<string>>(new Set());
    const [error, setError] = useState<string | null>(null);

    const handleSelect = async () => {
        if (!query.trim()) {
            setError('请输入选股条件');
            return;
        }

        setIsSelecting(true);
        setError(null);
        setResults([]);
        setSelectedStocks(new Set());

        try {
            const response = await axios.post(
                `${SERVICE_ENDPOINTS.AI_STRATEGY}/stocks/select`,
                {
                    query: query.trim(),
                    limit: 200
                }
            );

            const data = response.data?.data || response.data;
            const stockList = data?.data || data?.stocks || [];

            if (Array.isArray(stockList) && stockList.length > 0) {
                setResults(stockList);
            } else {
                setError('未找到符合条件的股票');
            }
        } catch (err) {
            console.error('Stock selection error:', err);
            if (axios.isAxiosError(err)) {
                const message = err.response?.data?.message || err.response?.data?.detail || err.message;
                setError(`选股失败: ${message}`);
            } else {
                setError('选股失败，请稍后重试');
            }
        } finally {
            setIsSelecting(false);
        }
    };

    const toggleStock = (symbol: string) => {
        const newSelected = new Set(selectedStocks);
        if (newSelected.has(symbol)) {
            newSelected.delete(symbol);
        } else {
            newSelected.add(symbol);
        }
        setSelectedStocks(newSelected);
    };

    const toggleAll = () => {
        if (selectedStocks.size === results.length) {
            setSelectedStocks(new Set());
        } else {
            setSelectedStocks(new Set(results.map(s => s.symbol)));
        }
    };

    const handleApply = () => {
        if (onStockPoolSelected && selectedStocks.size > 0) {
            onStockPoolSelected(Array.from(selectedStocks));
        }
    };

    const handleExport = () => {
        const selectedData = results.filter(s => selectedStocks.has(s.symbol));
        const csv = [
            ['股票代码', '股票名称', '市盈率', '市净率', '市值(万)', 'ROE(%)', '成交额(万)', '收盘价'].join(','),
            ...selectedData.map(s => [
                s.symbol,
                s.name,
                s.pe_ratio?.toFixed(2) || '-',
                s.pb_ratio?.toFixed(2) || '-',
                s.market_cap?.toFixed(0) || '-',
                s.roe?.toFixed(2) || '-',
                s.turnover?.toFixed(0) || '-',
                s.close?.toFixed(2) || '-'
            ].join(','))
        ].join('\n');

        const blob = new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8;' });
        const link = document.createElement('a');
        link.href = URL.createObjectURL(blob);
        link.download = `选股结果_${new Date().toISOString().split('T')[0]}.csv`;
        link.click();
    };

    const formatNumber = (num: number | undefined, decimals = 2): string => {
        if (num === undefined || num === null) return '-';
        return num.toFixed(decimals);
    };

    const formatLargeNumber = (num: number | undefined): string => {
        if (num === undefined || num === null) return '-';
        if (num >= 10000) {
            return `${(num / 10000).toFixed(2)}亿`;
        }
        return `${num.toFixed(0)}万`;
    };

    return (
        <div className="h-full flex flex-col gap-4 p-6 bg-gray-50">
            {/* 头部 */}
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-green-500 to-teal-500 flex items-center justify-center">
                        <TrendingUp className="w-5 h-5 text-white" />
                    </div>
                    <div>
                        <h2 className="text-xl font-bold text-gray-800">智能选股</h2>
                        <p className="text-sm text-gray-500">使用自然语言描述选股条件</p>
                    </div>
                </div>
            </div>

            <div className="flex-1 overflow-y-auto">
                <div className="max-w-6xl mx-auto space-y-6">
                    {/* 搜索区域 */}
                    <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm">
                        <label className="block text-sm font-medium text-gray-700 mb-3">
                            选股条件 <span className="text-red-500">*</span>
                        </label>
                        <div className="flex gap-3">
                            <input
                                type="text"
                                value={query}
                                onChange={(e) => setQuery(e.target.value)}
                                onKeyPress={(e) => e.key === 'Enter' && handleSelect()}
                                placeholder="例如: 低市盈率的白马股、ROE大于15%的成长股、市值超过100亿的蓝筹股..."
                                className="flex-1 px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-green-500 focus:border-transparent text-gray-800 placeholder-gray-400"
                                disabled={isSelecting}
                            />
                            <button
                                onClick={handleSelect}
                                disabled={isSelecting || !query.trim()}
                                className="px-6 py-3 bg-gradient-to-r from-green-600 to-teal-600 text-white rounded-lg font-medium hover:from-green-700 hover:to-teal-700 disabled:opacity-50 disabled:cursor-not-allowed transition-all shadow-lg shadow-green-200 flex items-center gap-2"
                            >
                                {isSelecting ? (
                                    <>
                                        <Loader2 className="w-5 h-5 animate-spin" />
                                        选股中...
                                    </>
                                ) : (
                                    <>
                                        <Search className="w-5 h-5" />
                                        开始选股
                                    </>
                                )}
                            </button>
                        </div>

                        {/* 示例提示 */}
                        <div className="mt-3 p-3 bg-blue-50 border border-blue-100 rounded-lg">
                            <p className="text-xs text-blue-700">
                                <span className="font-medium">提示:</span> 支持多种条件组合，如"市盈率小于20且ROE大于15%的股票"、"沪深300成分股中市值前50名"等
                            </p>
                        </div>
                    </div>

                    {/* 错误提示 */}
                    {error && (
                        <motion.div
                            initial={{ opacity: 0, y: -10 }}
                            animate={{ opacity: 1, y: 0 }}
                            className="bg-red-50 border border-red-200 rounded-lg p-4 flex items-start gap-3"
                        >
                            <AlertCircle className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" />
                            <div>
                                <p className="text-sm font-medium text-red-800">选股失败</p>
                                <p className="text-sm text-red-600 mt-1">{error}</p>
                            </div>
                        </motion.div>
                    )}

                    {/* 结果区域 */}
                    {results.length > 0 && (
                        <motion.div
                            initial={{ opacity: 0, y: 20 }}
                            animate={{ opacity: 1, y: 0 }}
                            className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden"
                        >
                            {/* 结果头部 */}
                            <div className="bg-gradient-to-r from-green-50 to-teal-50 border-b border-gray-200 px-6 py-4">
                                <div className="flex items-center justify-between">
                                    <div className="flex items-center gap-3">
                                        <CheckCircle className="w-6 h-6 text-green-500" />
                                        <div>
                                            <h3 className="font-bold text-gray-800">选股结果</h3>
                                            <p className="text-sm text-gray-600 mt-1">
                                                共找到 {results.length} 只股票，已选择 {selectedStocks.size} 只
                                            </p>
                                        </div>
                                    </div>

                                    <div className="flex gap-2">
                                        <button
                                            onClick={toggleAll}
                                            className="px-4 py-2 bg-white border border-gray-300 text-gray-700 rounded-lg text-sm font-medium hover:bg-gray-50 transition-colors"
                                        >
                                            {selectedStocks.size === results.length ? '取消全选' : '全选'}
                                        </button>
                                        <button
                                            onClick={handleExport}
                                            disabled={selectedStocks.size === 0}
                                            className="px-4 py-2 bg-white border border-gray-300 text-gray-700 rounded-lg text-sm font-medium hover:bg-gray-50 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                                        >
                                            <Download className="w-4 h-4" />
                                            导出CSV
                                        </button>
                                        {onStockPoolSelected && (
                                            <button
                                                onClick={handleApply}
                                                disabled={selectedStocks.size === 0}
                                                className="px-4 py-2 bg-gradient-to-r from-green-600 to-teal-600 text-white rounded-lg text-sm font-medium hover:from-green-700 hover:to-teal-700 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                                            >
                                                应用到策略 ({selectedStocks.size})
                                            </button>
                                        )}
                                    </div>
                                </div>
                            </div>

                            {/* 结果表格 */}
                            <div className="overflow-x-auto">
                                <table className="w-full">
                                    <thead className="bg-gray-50 border-b border-gray-200">
                                        <tr>
                                            <th className="px-4 py-3 text-left">
                                                <input
                                                    type="checkbox"
                                                    checked={selectedStocks.size === results.length && results.length > 0}
                                                    onChange={toggleAll}
                                                    className="rounded border-gray-300 text-green-600 focus:ring-green-500"
                                                />
                                            </th>
                                            <th className="px-4 py-3 text-left text-xs font-medium text-gray-600 uppercase">股票代码</th>
                                            <th className="px-4 py-3 text-left text-xs font-medium text-gray-600 uppercase">股票名称</th>
                                            <th className="px-4 py-3 text-right text-xs font-medium text-gray-600 uppercase">市盈率</th>
                                            <th className="px-4 py-3 text-right text-xs font-medium text-gray-600 uppercase">市净率</th>
                                            <th className="px-4 py-3 text-right text-xs font-medium text-gray-600 uppercase">市值</th>
                                            <th className="px-4 py-3 text-right text-xs font-medium text-gray-600 uppercase">ROE(%)</th>
                                            <th className="px-4 py-3 text-right text-xs font-medium text-gray-600 uppercase">成交额</th>
                                            <th className="px-4 py-3 text-right text-xs font-medium text-gray-600 uppercase">收盘价</th>
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y divide-gray-200">
                                        {results.map((stock, idx) => (
                                            <tr
                                                key={stock.symbol}
                                                className={`hover:bg-gray-50 transition-colors ${selectedStocks.has(stock.symbol) ? 'bg-green-50' : ''
                                                    }`}
                                            >
                                                <td className="px-4 py-3">
                                                    <input
                                                        type="checkbox"
                                                        checked={selectedStocks.has(stock.symbol)}
                                                        onChange={() => toggleStock(stock.symbol)}
                                                        className="rounded border-gray-300 text-green-600 focus:ring-green-500"
                                                    />
                                                </td>
                                                <td className="px-4 py-3 text-sm font-mono text-gray-800">{stock.symbol}</td>
                                                <td className="px-4 py-3 text-sm font-medium text-gray-800">{stock.name}</td>
                                                <td className="px-4 py-3 text-sm text-right text-gray-600">{formatNumber(stock.pe_ratio)}</td>
                                                <td className="px-4 py-3 text-sm text-right text-gray-600">{formatNumber(stock.pb_ratio)}</td>
                                                <td className="px-4 py-3 text-sm text-right text-gray-600">{formatLargeNumber(stock.market_cap)}</td>
                                                <td className="px-4 py-3 text-sm text-right text-gray-600">{formatNumber(stock.roe)}</td>
                                                <td className="px-4 py-3 text-sm text-right text-gray-600">{formatLargeNumber(stock.turnover)}</td>
                                                <td className="px-4 py-3 text-sm text-right font-medium text-gray-800">
                                                    {stock.close ? `¥${formatNumber(stock.close)}` : '-'}
                                                </td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        </motion.div>
                    )}
                </div>
            </div>
        </div>
    );
};
