// 仪表盘页面：拉取运行中任务、漏洞统计、批量任务、工具与 Skills 统计并渲染

async function refreshDashboard() {
    const runningEl = document.getElementById('dashboard-running-tasks');
    const vulnTotalEl = document.getElementById('dashboard-vuln-total');
    const severityIds = ['critical', 'high', 'medium', 'low', 'info'];

    if (runningEl) runningEl.textContent = '…';
    if (vulnTotalEl) vulnTotalEl.textContent = '…';
    severityIds.forEach(s => {
        const el = document.getElementById('dashboard-severity-' + s);
        if (el) el.textContent = '0';
        const barEl = document.getElementById('dashboard-bar-' + s);
        if (barEl) barEl.style.width = '0%';
    });
    setDashboardOverviewPlaceholder('…');
    setEl('dashboard-kpi-tools-calls', '…');
    setEl('dashboard-kpi-success-rate', '…');
    var chartPlaceholder = document.getElementById('dashboard-tools-pie-placeholder');
    if (chartPlaceholder) { chartPlaceholder.style.removeProperty('display'); chartPlaceholder.textContent = '加载中…'; }
    var barChartEl = document.getElementById('dashboard-tools-bar-chart');
    if (barChartEl) { barChartEl.style.display = 'none'; barChartEl.innerHTML = ''; }

    if (typeof apiFetch === 'undefined') {
        if (runningEl) runningEl.textContent = '-';
        if (vulnTotalEl) vulnTotalEl.textContent = '-';
        setDashboardOverviewPlaceholder('-');
        return;
    }

    try {
        const [tasksRes, vulnRes, batchRes, monitorRes, knowledgeRes, skillsRes, vulnListRes, monitorDetailRes, reportsRes] = await Promise.all([
            apiFetch('/api/agent-loop/tasks').then(r => r.ok ? r.json() : null).catch(() => null),
            apiFetch('/api/vulnerabilities/stats').then(r => r.ok ? r.json() : null).catch(() => null),
            apiFetch('/api/batch-tasks?limit=500&page=1').then(r => r.ok ? r.json() : null).catch(() => null),
            apiFetch('/api/monitor/stats').then(r => r.ok ? r.json() : null).catch(() => null),
            apiFetch('/api/knowledge/stats').then(r => r.ok ? r.json() : null).catch(() => null),
            apiFetch('/api/skills/stats').then(r => r.ok ? r.json() : null).catch(() => null),
            apiFetch('/api/vulnerabilities?limit=100&page=1').then(r => r.ok ? r.json() : null).catch(() => null),
            apiFetch('/api/monitor?page=1&page_size=20').then(r => r.ok ? r.json() : null).catch(() => null),
            apiFetch('/api/reports?limit=20').then(r => r.ok ? r.json() : null).catch(() => null)
        ]);

        if (tasksRes && Array.isArray(tasksRes.tasks)) {
            if (runningEl) runningEl.textContent = String(tasksRes.tasks.length);
        } else {
            if (runningEl) runningEl.textContent = '-';
        }

        if (vulnRes && typeof vulnRes.total === 'number') {
            if (vulnTotalEl) vulnTotalEl.textContent = String(vulnRes.total);
            const bySeverity = vulnRes.by_severity || {};
            const total = vulnRes.total || 0;
            severityIds.forEach(sev => {
                const count = bySeverity[sev] || 0;
                const el = document.getElementById('dashboard-severity-' + sev);
                if (el) el.textContent = String(count);
                const barEl = document.getElementById('dashboard-bar-' + sev);
                if (barEl) barEl.style.width = total > 0 ? (count / total * 100) + '%' : '0%';
            });
        } else {
            if (vulnTotalEl) vulnTotalEl.textContent = '-';
            severityIds.forEach(sev => {
                const barEl = document.getElementById('dashboard-bar-' + sev);
                if (barEl) barEl.style.width = '0%';
            });
        }

        // 批量任务队列：按状态统计（优化版）
        if (batchRes && Array.isArray(batchRes.queues)) {
            const queues = batchRes.queues;
            let pending = 0, running = 0, done = 0;
            queues.forEach(q => {
                const s = (q.status || '').toLowerCase();
                if (s === 'pending' || s === 'paused') pending++;
                else if (s === 'running') running++;
                else if (s === 'completed' || s === 'cancelled') done++;
            });
            const total = pending + running + done;
            setEl('dashboard-batch-pending', String(pending));
            setEl('dashboard-batch-running', String(running));
            setEl('dashboard-batch-done', String(done));
            setEl('dashboard-batch-total', total > 0 ? `共 ${total} 个` : '暂无任务');
            
            // 更新进度条
            if (total > 0) {
                const pendingPct = (pending / total * 100).toFixed(1);
                const runningPct = (running / total * 100).toFixed(1);
                const donePct = (done / total * 100).toFixed(1);
                updateProgressBar('dashboard-batch-progress-pending', pendingPct);
                updateProgressBar('dashboard-batch-progress-running', runningPct);
                updateProgressBar('dashboard-batch-progress-done', donePct);
            } else {
                updateProgressBar('dashboard-batch-progress-pending', '0');
                updateProgressBar('dashboard-batch-progress-running', '0');
                updateProgressBar('dashboard-batch-progress-done', '0');
            }
        } else {
            setEl('dashboard-batch-pending', '-');
            setEl('dashboard-batch-running', '-');
            setEl('dashboard-batch-done', '-');
            setEl('dashboard-batch-total', '-');
            updateProgressBar('dashboard-batch-progress-pending', '0');
            updateProgressBar('dashboard-batch-progress-running', '0');
            updateProgressBar('dashboard-batch-progress-done', '0');
        }

        // 工具调用：monitor/stats 为 { toolName: { totalCalls, successCalls, failedCalls, ... } }（优化版）
        if (monitorRes && typeof monitorRes === 'object') {
            const names = Object.keys(monitorRes);
            let totalCalls = 0, totalSuccess = 0, totalFailed = 0;
            names.forEach(k => {
                const v = monitorRes[k];
                const n = v && (v.totalCalls ?? v.TotalCalls);
                if (typeof n === 'number') totalCalls += n;
                const s = v && (v.successCalls ?? v.SuccessCalls);
                if (typeof s === 'number') totalSuccess += s;
                const f = v && (v.failedCalls ?? v.FailedCalls);
                if (typeof f === 'number') totalFailed += f;
            });
            setEl('dashboard-tools-count', String(names.length));
            setEl('dashboard-tools-calls', formatNumber(totalCalls));
            setEl('dashboard-kpi-tools-calls', String(totalCalls));
            var rateStr = totalCalls > 0 ? ((totalSuccess / totalCalls) * 100).toFixed(1) + '%' : '-';
            setEl('dashboard-kpi-success-rate', rateStr);
            setEl('dashboard-tools-success-rate', rateStr !== '-' ? `成功率 ${rateStr}` : '-');
            renderDashboardToolsBar(monitorRes);
        } else {
            setEl('dashboard-tools-count', '-');
            setEl('dashboard-tools-calls', '-');
            setEl('dashboard-kpi-tools-calls', '-');
            setEl('dashboard-kpi-success-rate', '-');
            setEl('dashboard-tools-success-rate', '-');
            renderDashboardToolsBar(null);
        }

        // 知识：{ enabled, total_categories, total_items, ... }（优化版）
        const knowledgeItemsEl = document.getElementById('dashboard-knowledge-items');
        const knowledgeCategoriesEl = document.getElementById('dashboard-knowledge-categories');
        const knowledgeStatusEl = document.getElementById('dashboard-knowledge-status');
        if (knowledgeRes && typeof knowledgeRes === 'object') {
            if (knowledgeRes.enabled === false) {
                // 功能未启用：用状态标签展示，数值保持为 "-"
                if (knowledgeStatusEl) knowledgeStatusEl.textContent = '未启用';
                if (knowledgeItemsEl) knowledgeItemsEl.textContent = '-';
                if (knowledgeCategoriesEl) knowledgeCategoriesEl.textContent = '-';
            } else {
                const categories = knowledgeRes.total_categories ?? 0;
                const items = knowledgeRes.total_items ?? 0;
                if (knowledgeItemsEl) knowledgeItemsEl.textContent = formatNumber(items);
                if (knowledgeCategoriesEl) knowledgeCategoriesEl.textContent = formatNumber(categories);
                // 根据数据量给个轻量状态文案
                if (knowledgeStatusEl) {
                    if (items > 0 || categories > 0) {
                        knowledgeStatusEl.textContent = '已启用';
                    } else {
                        knowledgeStatusEl.textContent = '待配置';
                    }
                }
            }
        } else {
            if (knowledgeItemsEl) knowledgeItemsEl.textContent = '-';
            if (knowledgeCategoriesEl) knowledgeCategoriesEl.textContent = '-';
            if (knowledgeStatusEl) knowledgeStatusEl.textContent = '-';
        }

        // Skills：{ total_skills, total_calls, ... }（优化版）
        if (skillsRes && typeof skillsRes === 'object') {
            const totalSkills = skillsRes.total_skills ?? 0;
            const totalCalls = skillsRes.total_calls ?? 0;
            setEl('dashboard-skills-count', formatNumber(totalSkills));
            setEl('dashboard-skills-calls', formatNumber(totalCalls));
            
            // 设置状态标签
            const statusEl = document.getElementById('dashboard-skills-status');
            if (statusEl) {
                if (totalCalls === 0) {
                    statusEl.textContent = '待使用';
                    statusEl.style.background = 'rgba(0, 0, 0, 0.05)';
                    statusEl.style.color = 'var(--text-secondary)';
                } else if (totalCalls < 10) {
                    statusEl.textContent = '活跃';
                    statusEl.style.background = 'rgba(16, 185, 129, 0.1)';
                    statusEl.style.color = '#10b981';
                } else {
                    statusEl.textContent = '高频';
                    statusEl.style.background = 'rgba(59, 130, 246, 0.1)';
                    statusEl.style.color = '#3b82f6';
                }
            }
        } else {
            setEl('dashboard-skills-count', '-');
            setEl('dashboard-skills-calls', '-');
            const statusEl = document.getElementById('dashboard-skills-status');
            if (statusEl) statusEl.textContent = '-';
        }

        const vulnerabilities = vulnListRes && Array.isArray(vulnListRes.vulnerabilities)
            ? vulnListRes.vulnerabilities
            : [];
        const executions = monitorDetailRes && Array.isArray(monitorDetailRes.executions)
            ? monitorDetailRes.executions
            : [];
        const reports = reportsRes && Array.isArray(reportsRes.reports)
            ? reportsRes.reports
            : [];
        renderDashboardSecurityInsights(vulnRes, vulnerabilities, executions, reports, batchRes);
    } catch (e) {
        console.warn('仪表盘拉取统计失败', e);
        if (runningEl) runningEl.textContent = '-';
        if (vulnTotalEl) vulnTotalEl.textContent = '-';
        setDashboardOverviewPlaceholder('-');
        setEl('dashboard-kpi-success-rate', '-');
        setEl('dashboard-kpi-tools-calls', '-');
        renderDashboardToolsBar(null);
        renderDashboardSecurityInsights(null, [], [], [], null);
        var ph = document.getElementById('dashboard-tools-pie-placeholder');
        if (ph) { ph.style.removeProperty('display'); ph.textContent = '暂无调用数据'; }
    }
}

function renderDashboardSecurityInsights(stats, vulnerabilities, executions, reports, batchRes) {
    const total = stats && typeof stats.total === 'number' ? stats.total : vulnerabilities.length;
    const openVulnerabilities = vulnerabilities.filter(function (item) {
        return item.status !== 'fixed' && item.status !== 'false_positive';
    });
    const openCount = openVulnerabilities.length;
    const activeSeverity = openVulnerabilities.reduce(function (counts, item) {
        counts[item.severity] = (counts[item.severity] || 0) + 1;
        return counts;
    }, {});
    const riskPoints = (activeSeverity.critical || 0) * 28
        + (activeSeverity.high || 0) * 18
        + (activeSeverity.medium || 0) * 8
        + (activeSeverity.low || 0) * 3
        + Math.min(12, openCount * 2);
    const score = Math.max(0, 100 - Math.min(100, riskPoints));
    const level = score >= 90 ? '安全' : score >= 75 ? '良好' : score >= 60 ? '关注' : score >= 40 ? '较高风险' : '高风险';
    const color = score >= 90 ? '#10b981' : score >= 75 ? '#22c55e' : score >= 60 ? '#f59e0b' : '#ef4444';

    setEl('dashboard-risk-score', String(score));
    setEl('dashboard-risk-level', level);
    setEl('dashboard-risk-description', total === 0 ? '当前没有已记录的漏洞' : `共 ${total} 个漏洞，${openCount} 个尚未闭环`);
    const ring = document.getElementById('dashboard-risk-ring');
    if (ring) {
        ring.style.setProperty('--risk-score', score * 3.6 + 'deg');
        ring.style.setProperty('--risk-color', color);
    }
    const levelEl = document.getElementById('dashboard-risk-level');
    if (levelEl) {
        levelEl.style.color = color;
        levelEl.style.background = hexToDashboardRgba(color, 0.1);
    }

    renderDashboardVulnerabilityTrend(vulnerabilities);
    renderDashboardRiskRanking(vulnerabilities);
    renderDashboardActivity(vulnerabilities, executions, reports, batchRes);
    renderDashboardAISummary(activeSeverity, openCount, executions, reports, score);
}

function renderDashboardVulnerabilityTrend(vulnerabilities) {
    const container = document.getElementById('dashboard-vuln-trend');
    if (!container) return;
    const now = new Date();
    const days = [];
    for (let offset = 6; offset >= 0; offset--) {
        const date = new Date(now.getFullYear(), now.getMonth(), now.getDate() - offset);
        days.push({
            key: dashboardDateKey(date),
            label: `${date.getMonth() + 1}/${date.getDate()}`,
            count: 0
        });
    }
    vulnerabilities.forEach(function (item) {
        const date = new Date(item.created_at);
        if (isNaN(date.getTime())) return;
        const day = days.find(function (entry) { return entry.key === dashboardDateKey(date); });
        if (day) day.count++;
    });
    const max = Math.max(1, ...days.map(function (day) { return day.count; }));
    const total = days.reduce(function (sum, day) { return sum + day.count; }, 0);
    setEl('dashboard-trend-total', `${total} 个`);
    container.innerHTML = days.map(function (day) {
        const height = day.count === 0 ? 8 : Math.max(18, Math.round(day.count / max * 100));
        return `<div class="dashboard-trend-column" title="${day.label}：${day.count} 个">
            <span class="dashboard-trend-value">${day.count}</span>
            <div class="dashboard-trend-bar-wrap"><span class="dashboard-trend-bar" style="height:${height}%"></span></div>
            <small>${day.label}</small>
        </div>`;
    }).join('');
}

function renderDashboardRiskRanking(vulnerabilities) {
    const container = document.getElementById('dashboard-risk-list');
    if (!container) return;
    const weights = { critical: 5, high: 4, medium: 3, low: 2, info: 1 };
    const labels = { critical: '严重', high: '高危', medium: '中危', low: '低危', info: '信息' };
    const list = vulnerabilities
        .filter(function (item) { return item.status !== 'fixed' && item.status !== 'false_positive'; })
        .sort(function (a, b) {
            return (weights[b.severity] || 0) - (weights[a.severity] || 0)
                || new Date(b.created_at) - new Date(a.created_at);
        })
        .slice(0, 5);
    if (list.length === 0) {
        container.innerHTML = '<div class="dashboard-empty-compact">暂无待处置的高风险漏洞</div>';
        return;
    }
    container.innerHTML = list.map(function (item, index) {
        const target = item.target || item.type || '未填写影响目标';
        return `<button type="button" class="dashboard-risk-item" onclick="switchPage('vulnerabilities')">
            <span class="dashboard-risk-rank">${index + 1}</span>
            <span class="dashboard-risk-item-main">
                <strong>${esc(item.title || '未命名漏洞')}</strong>
                <small>${esc(target)} · ${formatDashboardTime(item.created_at)}</small>
            </span>
            <span class="dashboard-severity-badge severity-${esc(item.severity || 'info')}">${labels[item.severity] || esc(item.severity || '信息')}</span>
        </button>`;
    }).join('');
}

function renderDashboardActivity(vulnerabilities, executions, reports, batchRes) {
    const container = document.getElementById('dashboard-activity-list');
    if (!container) return;
    const activities = [];
    vulnerabilities.slice(0, 10).forEach(function (item) {
        activities.push({
            time: item.created_at,
            type: 'vulnerability',
            title: `发现${dashboardSeverityLabel(item.severity)}漏洞`,
            detail: item.title || '未命名漏洞'
        });
    });
    executions.slice(0, 10).forEach(function (item) {
        activities.push({
            time: item.endTime || item.startTime,
            type: item.status === 'failed' ? 'failed' : 'tool',
            title: item.status === 'failed' ? '工具执行失败' : '工具执行完成',
            detail: item.toolName || '未知工具'
        });
    });
    reports.slice(0, 8).forEach(function (item) {
        activities.push({
            time: item.created_at,
            type: 'report',
            title: '安全报告已生成',
            detail: item.title || '未命名报告'
        });
    });
    const queues = batchRes && Array.isArray(batchRes.queues) ? batchRes.queues : [];
    queues.slice(0, 5).forEach(function (item) {
        if (!item.updated_at && !item.created_at && !item.createdAt) return;
        activities.push({
            time: item.updated_at || item.created_at || item.createdAt,
            type: 'task',
            title: item.status === 'completed' ? '批量任务已完成' : '批量任务状态更新',
            detail: item.title || '未命名任务'
        });
    });
    activities.sort(function (a, b) { return new Date(b.time) - new Date(a.time); });
    const visible = activities.slice(0, 6);
    setEl('dashboard-activity-count', `${visible.length} 条`);
    if (visible.length === 0) {
        container.innerHTML = '<div class="dashboard-empty-compact">暂无安全动态</div>';
        return;
    }
    container.innerHTML = visible.map(function (item) {
        return `<div class="dashboard-activity-item">
            <span class="dashboard-activity-dot ${item.type}"></span>
            <span class="dashboard-activity-main">
                <strong>${esc(item.title)}</strong>
                <small>${esc(item.detail)}</small>
            </span>
            <time>${formatDashboardTime(item.time)}</time>
        </div>`;
    }).join('');
}

function renderDashboardAISummary(activeSeverity, openCount, executions, reports, score) {
    const container = document.getElementById('dashboard-ai-summary');
    if (!container) return;
    const criticalHigh = (activeSeverity.critical || 0) + (activeSeverity.high || 0);
    const failedTools = executions.filter(function (item) { return item.status === 'failed'; }).length;
    const messages = [];
    if (criticalHigh > 0) {
        messages.push(`当前存在 ${criticalHigh} 个严重或高危漏洞，建议优先确认影响范围并安排修复复测。`);
    } else if (openCount > 0) {
        messages.push(`当前没有严重或高危漏洞，但仍有 ${openCount} 个漏洞尚未闭环，建议持续跟踪处置状态。`);
    } else {
        messages.push('当前未发现待处置的高风险漏洞，整体安全态势稳定。');
    }
    if (failedTools > 0) {
        messages.push(`最近执行记录中有 ${failedTools} 次工具失败，可前往 MCP 监控检查参数或运行环境。`);
    } else if (executions.length > 0) {
        messages.push(`最近 ${executions.length} 次工具执行未发现失败记录，自动化能力运行正常。`);
    } else {
        messages.push('暂无近期工具执行记录，建议运行一次基线扫描以补充态势数据。');
    }
    messages.push(reports.length > 0
        ? `系统已有 ${reports.length} 份近期安全报告，可结合最新漏洞变化重新生成报告。`
        : '尚未生成安全报告，完成漏洞确认后可创建首份安全评估报告。');
    container.innerHTML = `<div class="dashboard-ai-score-line">
        <span>综合研判</span><strong>${score} 分</strong>
    </div><ul>${messages.map(function (message) { return `<li>${esc(message)}</li>`; }).join('')}</ul>`;
}

function dashboardDateKey(date) {
    return `${date.getFullYear()}-${date.getMonth() + 1}-${date.getDate()}`;
}

function dashboardSeverityLabel(severity) {
    return ({ critical: '严重', high: '高危', medium: '中危', low: '低危', info: '信息' })[severity] || '';
}

function formatDashboardTime(value) {
    const date = new Date(value);
    if (isNaN(date.getTime())) return '时间未知';
    const diff = Date.now() - date.getTime();
    if (diff >= 0 && diff < 60000) return '刚刚';
    if (diff >= 0 && diff < 3600000) return `${Math.floor(diff / 60000)} 分钟前`;
    if (diff >= 0 && diff < 86400000) return `${Math.floor(diff / 3600000)} 小时前`;
    return `${date.getMonth() + 1}/${date.getDate()}`;
}

function hexToDashboardRgba(hex, alpha) {
    const value = hex.replace('#', '');
    const number = parseInt(value, 16);
    return `rgba(${number >> 16}, ${(number >> 8) & 255}, ${number & 255}, ${alpha})`;
}

function setEl(id, text) {
    const el = document.getElementById(id);
    if (el) el.textContent = text;
}

function setDashboardOverviewPlaceholder(t) {
    ['dashboard-batch-pending', 'dashboard-batch-running', 'dashboard-batch-done', 'dashboard-batch-total',
     'dashboard-tools-count', 'dashboard-tools-calls', 'dashboard-tools-success-rate',
     'dashboard-skills-count', 'dashboard-skills-calls', 'dashboard-skills-status',
     'dashboard-knowledge-items', 'dashboard-knowledge-categories', 'dashboard-knowledge-status'].forEach(id => setEl(id, t));
    updateProgressBar('dashboard-batch-progress-pending', '0');
    updateProgressBar('dashboard-batch-progress-running', '0');
    updateProgressBar('dashboard-batch-progress-done', '0');
}

// 格式化数字，添加千位分隔符
function formatNumber(num) {
    if (typeof num !== 'number' || isNaN(num)) return '-';
    if (num === 0) return '0';
    return num.toLocaleString('zh-CN');
}

// 更新进度条宽度
function updateProgressBar(id, percentage) {
    const el = document.getElementById(id);
    if (el) {
        const pct = parseFloat(percentage) || 0;
        el.style.width = Math.max(0, Math.min(100, pct)) + '%';
    }
}

// 热门工具执行次数柱状图颜色
var DASHBOARD_BAR_COLORS = [
    '#93c5fd', '#a78bfa', '#6ee7b7', '#fde047', '#fda4af',
    '#7dd3fc', '#a5b4fc', '#5eead4', '#fdba74', '#e9d5ff',
    '#67e8f9', '#c4b5fd', '#86efac', '#fcd34d', '#f9a8d4',
    '#bae6fd', '#c7d2fe', '#99f6e4', '#fed7aa', '#ddd6fe',
    '#22d3ee', '#8b5cf6', '#4ade80', '#fbbf24', '#fb7185',
    '#38bdf8', '#818cf8', '#2dd4bf', '#fb923c', '#e0e7ff'
];

function esc(s) {
    if (typeof s !== 'string') return '';
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;');
}

function renderDashboardToolsBar(monitorRes) {
    const placeholder = document.getElementById('dashboard-tools-pie-placeholder');
    const barChartEl = document.getElementById('dashboard-tools-bar-chart');
    if (!placeholder || !barChartEl) return;

    if (!monitorRes || typeof monitorRes !== 'object') {
        placeholder.style.removeProperty('display');
        placeholder.textContent = '暂无调用数据';
        barChartEl.style.display = 'none';
        barChartEl.innerHTML = '';
        return;
    }

    const entries = Object.keys(monitorRes).map(function (k) {
        const v = monitorRes[k];
        const totalCalls = v && (v.totalCalls ?? v.TotalCalls);
        return { name: k, totalCalls: typeof totalCalls === 'number' ? totalCalls : 0 };
    }).filter(function (e) { return e.totalCalls > 0; })
        .sort(function (a, b) { return b.totalCalls - a.totalCalls; })
        .slice(0, 10);

    if (entries.length === 0) {
        placeholder.style.removeProperty('display');
        placeholder.textContent = '暂无调用数据';
        barChartEl.style.display = 'none';
        barChartEl.innerHTML = '';
        return;
    }

    placeholder.style.display = 'none';
    barChartEl.style.display = 'block';

    const maxCalls = Math.max.apply(null, entries.map(function (e) { return e.totalCalls; }));
    var html = '';
    entries.forEach(function (e, i) {
        var pct = maxCalls > 0 ? (e.totalCalls / maxCalls) * 100 : 0;
        var label = e.name.length > 12 ? e.name.slice(0, 10) + '…' : e.name;
        var color = DASHBOARD_BAR_COLORS[i % DASHBOARD_BAR_COLORS.length];
        var fullName = esc(e.name);
        html += '<div class="dashboard-tools-bar-item" data-tooltip="' + fullName + '">';
        html += '<span class="dashboard-tools-bar-label">' + esc(label) + '</span>';
        html += '<div class="dashboard-tools-bar-track"><div class="dashboard-tools-bar-fill" style="width:' + pct + '%;background:' + color + '"></div></div>';
        html += '<span class="dashboard-tools-bar-value">' + e.totalCalls + '</span>';
        html += '</div>';
    });
    barChartEl.innerHTML = html;
    attachDashboardBarTooltips(barChartEl);
}

var dashboardBarTooltipEl = null;
var dashboardBarTooltipTimer = null;

function attachDashboardBarTooltips(barChartEl) {
    if (!barChartEl) return;
    if (!dashboardBarTooltipEl) {
        dashboardBarTooltipEl = document.createElement('div');
        dashboardBarTooltipEl.className = 'dashboard-tools-bar-tooltip';
        dashboardBarTooltipEl.setAttribute('role', 'tooltip');
        document.body.appendChild(dashboardBarTooltipEl);
    }
    barChartEl.removeEventListener('mouseover', dashboardBarTooltipOnOver);
    barChartEl.removeEventListener('mouseout', dashboardBarTooltipOnOut);
    barChartEl.addEventListener('mouseover', dashboardBarTooltipOnOver);
    barChartEl.addEventListener('mouseout', dashboardBarTooltipOnOut);
}

function dashboardBarTooltipOnOver(ev) {
    var item = ev.target && ev.target.closest && ev.target.closest('.dashboard-tools-bar-item');
    if (!item || !dashboardBarTooltipEl) return;
    var text = item.getAttribute('data-tooltip');
    if (!text) return;
    clearTimeout(dashboardBarTooltipTimer);
    dashboardBarTooltipTimer = setTimeout(function () {
        dashboardBarTooltipEl.textContent = text;
        dashboardBarTooltipEl.style.display = 'block';
        requestAnimationFrame(function () {
            var rect = item.getBoundingClientRect();
            var ttRect = dashboardBarTooltipEl.getBoundingClientRect();
            var x = rect.left + (rect.width / 2) - (ttRect.width / 2);
            var y = rect.top - ttRect.height - 6;
            if (y < 8) y = rect.bottom + 6;
            var pad = 8;
            if (x < pad) x = pad;
            if (x + ttRect.width > window.innerWidth - pad) x = window.innerWidth - ttRect.width - pad;
            dashboardBarTooltipEl.style.left = x + 'px';
            dashboardBarTooltipEl.style.top = y + 'px';
        });
    }, 180);
}

function dashboardBarTooltipOnOut(ev) {
    var item = ev.target && ev.target.closest && ev.target.closest('.dashboard-tools-bar-item');
    var related = ev.relatedTarget && ev.relatedTarget.closest && ev.relatedTarget.closest('.dashboard-tools-bar-item');
    if (item && item === related) return;
    clearTimeout(dashboardBarTooltipTimer);
    dashboardBarTooltipTimer = null;
    if (dashboardBarTooltipEl) dashboardBarTooltipEl.style.display = 'none';
}
