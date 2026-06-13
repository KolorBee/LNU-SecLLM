function initReportsPage() {
    loadReports();
}

async function loadReports() {
    const list = document.getElementById('reports-list');
    if (!list) return;
    list.innerHTML = '<div class="loading-spinner">加载中…</div>';

    try {
        const response = await apiFetch('/api/reports?limit=100');
        if (!response.ok) throw new Error(await readReportError(response));
        const data = await response.json();
        const reports = Array.isArray(data.reports) ? data.reports : [];
        renderReports(reports);
        updateReportSummary(reports, data.total || reports.length);
    } catch (error) {
        list.innerHTML = `<div class="reports-empty reports-error">${escapeReportHtml(error.message)}</div>`;
    }
}

async function generateReport() {
    const button = document.getElementById('report-generate-btn');
    const titleInput = document.getElementById('report-title-input');
    const conversationInput = document.getElementById('report-conversation-input');
    const title = titleInput.value.trim();
    const conversationId = conversationInput.value.trim();

    button.disabled = true;
    const originalText = button.textContent;
    button.textContent = '生成中…';
    try {
        const response = await apiFetch('/api/reports', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title, conversation_id: conversationId })
        });
        if (!response.ok) throw new Error(await readReportError(response));
        const report = await response.json();
        titleInput.value = '';
        await loadReports();
        showReportPreview(report.id);
    } catch (error) {
        alert(`生成报告失败：${error.message}`);
    } finally {
        button.disabled = false;
        button.textContent = originalText;
    }
}

function renderReports(reports) {
    const list = document.getElementById('reports-list');
    if (reports.length === 0) {
        list.innerHTML = '<div class="reports-empty">暂无报告。输入报告范围后生成第一份安全测试报告。</div>';
        return;
    }

    list.innerHTML = reports.map(report => {
        const risk = report.risk_level || 'info';
        const createdAt = new Date(report.created_at).toLocaleString('zh-CN');
        const scope = report.conversation_id
            ? `会话：${escapeReportHtml(report.conversation_id)}`
            : '全部平台数据';
        return `
            <article class="report-card">
                <div class="report-card-main">
                    <div class="report-card-title-row">
                        <h4>${escapeReportHtml(report.title)}</h4>
                        <span class="report-risk report-risk-${risk}">${reportRiskName(risk)}</span>
                    </div>
                    <div class="report-card-meta">
                        <span>${scope}</span>
                        <span>${createdAt}</span>
                    </div>
                    <div class="report-card-stats">
                        <span>漏洞 <strong>${report.vulnerability_count || 0}</strong></span>
                        <span class="critical">严重 <strong>${report.critical_count || 0}</strong></span>
                        <span class="high">高危 <strong>${report.high_count || 0}</strong></span>
                        <span>攻击链节点 <strong>${report.attack_chain_nodes || 0}</strong></span>
                        <span>工具执行 <strong>${report.tool_execution_count || 0}</strong></span>
                    </div>
                </div>
                <div class="report-card-actions">
                    <button class="btn-secondary" onclick="showReportPreview('${report.id}')">预览</button>
                    <button class="btn-primary" onclick="downloadReportMarkdown('${report.id}')">Markdown</button>
                    <button class="btn-ghost reports-delete-btn" onclick="deleteReport('${report.id}')">删除</button>
                </div>
            </article>
        `;
    }).join('');
}

function updateReportSummary(reports, total) {
    document.getElementById('reports-total-count').textContent = total;
    document.getElementById('reports-critical-count').textContent =
        reports.reduce((sum, report) => sum + (report.critical_count || 0), 0);
    document.getElementById('reports-high-count').textContent =
        reports.reduce((sum, report) => sum + (report.high_count || 0), 0);
    document.getElementById('reports-tool-count').textContent =
        reports.reduce((sum, report) => sum + (report.tool_execution_count || 0), 0);
}

async function showReportPreview(id) {
    try {
        const response = await apiFetch(`/api/reports/${encodeURIComponent(id)}`);
        if (!response.ok) throw new Error(await readReportError(response));
        const report = await response.json();
        closeReportPreview();

        const modal = document.createElement('div');
        modal.id = 'report-preview-modal';
        modal.className = 'report-preview-modal';
        modal.innerHTML = `
            <div class="report-preview-dialog">
                <div class="report-preview-header">
                    <div>
                        <h3>${escapeReportHtml(report.title)}</h3>
                        <span>${new Date(report.created_at).toLocaleString('zh-CN')}</span>
                    </div>
                    <button class="report-preview-close" onclick="closeReportPreview()" aria-label="关闭">×</button>
                </div>
                <pre class="report-markdown-preview">${escapeReportHtml(report.content_markdown || '')}</pre>
                <div class="report-preview-footer">
                    <button class="btn-secondary" onclick="closeReportPreview()">关闭</button>
                    <button class="btn-primary" onclick="downloadReportMarkdown('${report.id}')">下载 Markdown</button>
                </div>
            </div>
        `;
        modal.addEventListener('click', event => {
            if (event.target === modal) closeReportPreview();
        });
        document.body.appendChild(modal);
    } catch (error) {
        alert(`加载报告失败：${error.message}`);
    }
}

function closeReportPreview() {
    const modal = document.getElementById('report-preview-modal');
    if (modal) modal.remove();
}

async function downloadReportMarkdown(id) {
    try {
        const response = await apiFetch(`/api/reports/${encodeURIComponent(id)}/markdown`);
        if (!response.ok) throw new Error(await readReportError(response));
        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = `security-report-${id.slice(0, 8)}.md`;
        document.body.appendChild(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(url);
    } catch (error) {
        alert(`下载报告失败：${error.message}`);
    }
}

async function deleteReport(id) {
    if (!confirm('确定删除这份报告吗？')) return;
    try {
        const response = await apiFetch(`/api/reports/${encodeURIComponent(id)}`, { method: 'DELETE' });
        if (!response.ok) throw new Error(await readReportError(response));
        await loadReports();
    } catch (error) {
        alert(`删除报告失败：${error.message}`);
    }
}

async function readReportError(response) {
    try {
        const data = await response.json();
        return data.error || `请求失败 (${response.status})`;
    } catch (_) {
        return `请求失败 (${response.status})`;
    }
}

function reportRiskName(level) {
    return ({ critical: '严重', high: '高危', medium: '中危', low: '低危', info: '信息' })[level] || level;
}

function escapeReportHtml(value) {
    return String(value == null ? '' : value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}
