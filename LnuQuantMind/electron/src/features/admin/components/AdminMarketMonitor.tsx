import React, { useEffect, useState } from 'react';
import { Card, Row, Col, Typography, Spin, Alert, Badge, Button, Divider, Tag } from 'antd';
import { DatabaseOutlined, CloudServerOutlined, ReloadOutlined, CheckCircleOutlined, CloseCircleOutlined } from '@ant-design/icons';
import { adminService } from '../services/adminService';

const { Title, Text } = Typography;

interface PostgresqlStatus {
    status: string;
    error?: string;
}

interface RedisStatus {
    status: string;
    error?: string;
}

interface FeatureSnapshotsStatus {
    status: string;
    latest_date: string | null;
    row_count: number;
}

interface OnlineSourceStatus {
    server_ip: string;
    status: string;
    postgresql: PostgresqlStatus;
    redis: RedisStatus;
    latest_date: string | null;
    row_count: number;
    error: string | null;
}

interface OfflineSourceStatus {
    server_ip: string;
    status: string;
    postgresql: PostgresqlStatus;
    feature_snapshots: FeatureSnapshotsStatus;
    error: string | null;
}

interface MarketSourcesStatus {
    online_source: OnlineSourceStatus;
    offline_source: OfflineSourceStatus;
}

export const AdminMarketMonitor: React.FC = () => {
    const [loading, setLoading] = useState(true);
    const [data, setData] = useState<MarketSourcesStatus | null>(null);
    const [error, setError] = useState<string | null>(null);

    const fetchData = async () => {
        setLoading(true);
        setError(null);
        try {
            // Note: Add this API method to adminService.ts if it doesn't exist.
            // For now, we'll use a direct fetch to the backend if needed, but assuming adminService will handle it.
            const response = await adminService.getMarketSourcesStatus();
            if (response.success && response.data) {
                setData(response.data as MarketSourcesStatus);
            } else {
                setError(response.message || '获取监控数据失败');
            }
        } catch (err: any) {
            setError(err.message || '请求监控接口失败');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchData();
        const interval = setInterval(fetchData, 30000); // 自动刷新，每30秒
        return () => clearInterval(interval);
    }, []);

    const renderStatusBadge = (status: string) => {
        if (status === 'unreachable' || status === 'error') {
            return <Badge status="error" text="异常" className="text-red-500 font-medium" />;
        }
        if (status === 'degraded' || status === 'empty') {
            return <Badge status="warning" text="降级" className="text-orange-500 font-medium" />;
        }
        if (status === 'checking' || status === 'unknown') {
            return <Badge status="processing" text="检测中" className="text-blue-500 font-medium" />;
        }
        return <Badge status="success" text="正常" className="text-emerald-500 font-medium" />;
    };

    const renderServiceTag = (status: string) => {
        if (status === 'healthy') {
            return <Tag color="success" icon={<CheckCircleOutlined />}>正常</Tag>;
        }
        if (status === 'unreachable' || status === 'error') {
            return <Tag color="error" icon={<CloseCircleOutlined />}>异常</Tag>;
        }
        return <Tag color="default">未知</Tag>;
    };

    if (loading && !data) {
        return (
            <div className="flex items-center justify-center h-64">
                <Spin size="large" tip="加载行情源监控数据...">
                    <div style={{ height: 100, width: 100 }} />
                </Spin>
            </div>
        );
    }

    if (error && !data) {
        return <Alert type="error" message="监控加载失败" description={error} showIcon />;
    }

    const online = data?.online_source;
    const offline = data?.offline_source;

    return (
        <div className="p-8 max-w-7xl mx-auto">
            <div className="flex justify-between items-center mb-8">
                <div>
                    <Title level={2} className="!mb-1 !text-slate-800">行情源监控</Title>
                    <Text className="text-slate-500">实时监控在线与离线数据源的健康状况与覆盖范围</Text>
                </div>
                <Button 
                    type="primary" 
                    icon={<ReloadOutlined />} 
                    onClick={fetchData} 
                    loading={loading}
                    className="bg-indigo-600 rounded-lg shadow-sm"
                >
                    手动刷新
                </Button>
            </div>

            <Row gutter={[24, 24]}>
                {/* 106 Online Source */}
                <Col xs={24} lg={12}>
                    <Card
                        variant="borderless"
                        className="h-full rounded-2xl shadow-sm border border-slate-100 hover:shadow-md transition-shadow"
                        styles={{ body: { padding: '24px' } }}
                    >
                        <div className="flex items-start justify-between mb-4">
                            <div className="flex items-center space-x-3">
                                <div className="w-12 h-12 rounded-xl bg-blue-50 flex items-center justify-center">
                                    <CloudServerOutlined className="text-blue-600 text-2xl" />
                                </div>
                                <div>
                                    <Title level={4} className="!mb-0 !text-slate-800">在线行情源</Title>
                                    <Text className="text-xs text-slate-400 font-mono">{online?.server_ip || '106.53.100.144'}</Text>
                                    <Text className="text-xs text-slate-400 block mt-0.5">投研平台数据查询</Text>
                                </div>
                            </div>
                            <div className="px-3 py-1 bg-slate-50 rounded-lg border border-slate-100">
                                {renderStatusBadge(online?.status || 'error')}
                            </div>
                        </div>

                        {/* 核心指标 — 日期信息置顶 */}
                        <div className="bg-indigo-50 p-4 rounded-xl mb-4">
                            <div className="flex items-baseline space-x-2">
                                <Text className="text-sm text-indigo-600">最新行情日期:</Text>
                                <Text className="text-xl font-bold text-indigo-700 font-mono">
                                    {online?.latest_date || '--'}
                                </Text>
                            </div>
                            <div className="flex items-baseline space-x-2 mt-1">
                                <Text className="text-sm text-indigo-600">数据量:</Text>
                                <Text className="text-lg font-bold text-indigo-700 font-mono">
                                    {online?.row_count?.toLocaleString() || 0}
                                </Text>
                                <Text className="text-xs text-indigo-400">条</Text>
                                {online?.row_count && online.row_count < 4000 ? (
                                    <Text className="text-xs text-orange-500">(偏少)</Text>
                                ) : null}
                            </div>
                        </div>

                        <Divider className="my-4" />

                        <div className="space-y-4">
                            <div className="bg-slate-50 p-4 rounded-xl">
                                <div className="flex items-center justify-between">
                                    <Text className="text-xs font-bold text-slate-500 uppercase tracking-wider">PostgreSQL</Text>
                                    {renderServiceTag(online?.postgresql?.status || 'unknown')}
                                </div>
                                {online?.postgresql?.error && (
                                    <Text className="text-xs text-red-500 mt-1 block">{online.postgresql.error}</Text>
                                )}
                            </div>

                            <div className="bg-slate-50 p-4 rounded-xl">
                                <div className="flex items-center justify-between">
                                    <Text className="text-xs font-bold text-slate-500 uppercase tracking-wider">Redis (DB 3)</Text>
                                    {renderServiceTag(online?.redis?.status || 'unknown')}
                                </div>
                                {online?.redis?.error && (
                                    <Text className="text-xs text-red-500 mt-1 block">{online.redis.error}</Text>
                                )}
                            </div>
                        </div>

                        {online?.error && (
                            <Alert
                                type="error"
                                message="连接异常"
                                description={online.error}
                                showIcon
                                className="mt-4 rounded-xl"
                            />
                        )}
                    </Card>
                </Col>

                {/* 139 Offline Source */}
                <Col xs={24} lg={12}>
                    <Card
                        variant="borderless"
                        className="h-full rounded-2xl shadow-sm border border-slate-100 hover:shadow-md transition-shadow"
                        styles={{ body: { padding: '24px' } }}
                    >
                        <div className="flex items-start justify-between mb-4">
                            <div className="flex items-center space-x-3">
                                <div className="w-12 h-12 rounded-xl bg-purple-50 flex items-center justify-center">
                                    <DatabaseOutlined className="text-purple-600 text-2xl" />
                                </div>
                                <div>
                                    <Title level={4} className="!mb-0 !text-slate-800">离线数据源</Title>
                                    <Text className="text-xs text-slate-400 font-mono">{offline?.server_ip || '139.199.75.121'}</Text>
                                    <Text className="text-xs text-slate-400 block mt-0.5">Parquet 数据更新</Text>
                                </div>
                            </div>
                            <div className="px-3 py-1 bg-slate-50 rounded-lg border border-slate-100">
                                {renderStatusBadge(offline?.status || 'error')}
                            </div>
                        </div>

                        {/* 核心指标 — 日期信息置顶 */}
                        <div className="bg-purple-50 p-4 rounded-xl mb-4">
                            <div className="flex items-baseline space-x-2">
                                <Text className="text-sm text-purple-600">最新快照日期:</Text>
                                <Text className="text-xl font-bold text-purple-700 font-mono">
                                    {offline?.feature_snapshots?.latest_date || '--'}
                                </Text>
                            </div>
                            <div className="flex items-baseline space-x-2 mt-1">
                                <Text className="text-sm text-purple-600">数据量:</Text>
                                <Text className="text-lg font-bold text-purple-700 font-mono">
                                    {offline?.feature_snapshots?.row_count?.toLocaleString() || 0}
                                </Text>
                                <Text className="text-xs text-purple-400">条</Text>
                            </div>
                        </div>

                        <Divider className="my-4" />

                        <div className="space-y-4">
                            <div className="bg-slate-50 p-4 rounded-xl">
                                <div className="flex items-center justify-between">
                                    <Text className="text-xs font-bold text-slate-500 uppercase tracking-wider">PostgreSQL</Text>
                                    {renderServiceTag(offline?.postgresql?.status || 'unknown')}
                                </div>
                            </div>

                            <div className="bg-slate-50 p-4 rounded-xl">
                                <div className="flex items-center justify-between">
                                    <Text className="text-xs font-bold text-slate-500 uppercase tracking-wider">Feature Snapshots</Text>
                                    {renderServiceTag(offline?.feature_snapshots?.status || 'unknown')}
                                </div>
                            </div>
                        </div>

                        {offline?.error && (
                            <Alert
                                type="error"
                                message="连接异常"
                                description={offline.error}
                                showIcon
                                className="mt-4 rounded-xl"
                            />
                        )}
                    </Card>
                </Col>
            </Row>
        </div>
    );
};
