// API文档页面JavaScript

let apiSpec = null;
let currentToken = null;

// 初始化
document.addEventListener('DOMContentLoaded', async () => {
    await loadToken();
    await loadAPISpec();
    if (apiSpec) {
        renderAPIDocs();
    }
});

// 加载token
async function loadToken() {
    try {
        const authData = localStorage.getItem('cyberstrike-auth');
        if (authData) {
            const parsed = JSON.parse(authData);
            if (parsed && parsed.token) {
                const expiry = parsed.expiresAt ? new Date(parsed.expiresAt) : null;
                if (!expiry || expiry.getTime() > Date.now()) {
                    currentToken = parsed.token;
                    return;
                }
            }
        }
        currentToken = localStorage.getItem('swagger_auth_token');
    } catch (e) {
        console.error('加载token失败:', e);
    }
}

// 加载OpenAPI规范
async function loadAPISpec() {
    try {
        let url = '/api/openapi/spec';
        if (currentToken) {
            url += '?token=' + encodeURIComponent(currentToken);
        }
        
        const response = await fetch(url);
        if (!response.ok) {
            if (response.status === 401) {
                showError('需要登录才能查看API文档。请先在前端页面登录，然后刷新此页面。');
                return;
            }
            throw new Error('加载API规范失败: ' + response.status);
        }
        
        apiSpec = await response.json();
    } catch (error) {
        console.error('加载API规范失败:', error);
        showError('加载API文档失败: ' + error.message);
    }
}

// 显示错误
function showError(message) {
    const main = document.getElementById('api-docs-main');
    main.innerHTML = `
        <div class="empty-state">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <circle cx="12" cy="12" r="10"/>
                <line x1="15" y1="9" x2="9" y2="15"/>
                <line x1="9" y1="9" x2="15" y2="15"/>
            </svg>
            <h3>加载失败</h3>
            <p>${message}</p>
            <div style="margin-top: 16px;">
                <a href="/" style="color: var(--accent-color); text-decoration: none;">返回首页登录</a>
            </div>
        </div>
    `;
}

// 渲染API文档
function renderAPIDocs() {
    if (!apiSpec || !apiSpec.paths) {
        showError('API规范格式错误');
        return;
    }
    
    // 显示认证说明
    renderAuthInfo();
    
    // 渲染侧边栏分组
    renderSidebar();
    
    // 渲染API端点
    renderEndpoints();
}

// 渲染认证说明
function renderAuthInfo() {
    const authSection = document.getElementById('auth-info-section');
    if (!authSection) return;
    
    // 显示认证说明部分
    authSection.style.display = 'block';
    
    // 检查是否有token
    const tokenStatus = document.getElementById('token-status');
    if (currentToken && tokenStatus) {
        tokenStatus.style.display = 'block';
    } else if (tokenStatus) {
        // 如果没有token，显示提示
        tokenStatus.style.display = 'block';
        tokenStatus.style.background = 'rgba(255, 152, 0, 0.1)';
        tokenStatus.style.borderLeftColor = '#ff9800';
        tokenStatus.innerHTML = '<p style="margin: 0; font-size: 0.8125rem; color: #ff9800;"><strong>⚠ 未检测到 Token</strong> - 请先在前端页面登录，然后刷新此页面。测试接口时需要在请求头中添加 Authorization: Bearer token</p>';
    }
}

// 渲染侧边栏
function renderSidebar() {
    const groups = new Set();
    Object.keys(apiSpec.paths).forEach(path => {
        Object.keys(apiSpec.paths[path]).forEach(method => {
            const endpoint = apiSpec.paths[path][method];
            if (endpoint.tags && endpoint.tags.length > 0) {
                endpoint.tags.forEach(tag => groups.add(tag));
            }
        });
    });
    
    const groupList = document.getElementById('api-group-list');
    const allGroups = Array.from(groups).sort();
    
    allGroups.forEach(group => {
        const li = document.createElement('li');
        li.className = 'api-group-item';
        li.innerHTML = `<a href="#" class="api-group-link" data-group="${group}">${group}</a>`;
        groupList.appendChild(li);
    });
    
    // 绑定点击事件
    groupList.querySelectorAll('.api-group-link').forEach(link => {
        link.addEventListener('click', (e) => {
            e.preventDefault();
            groupList.querySelectorAll('.api-group-link').forEach(l => l.classList.remove('active'));
            link.classList.add('active');
            const group = link.dataset.group;
            renderEndpoints(group === 'all' ? null : group);
        });
    });
}

// 渲染API端点
function renderEndpoints(filterGroup = null) {
    const main = document.getElementById('api-docs-main');
    main.innerHTML = '';
    
    const endpoints = [];
    Object.keys(apiSpec.paths).forEach(path => {
        Object.keys(apiSpec.paths[path]).forEach(method => {
            const endpoint = apiSpec.paths[path][method];
            const tags = endpoint.tags || [];
            if (!filterGroup || filterGroup === 'all' || tags.includes(filterGroup)) {
                endpoints.push({
                    path,
                    method,
                    ...endpoint
                });
            }
        });
    });
    
    // 按分组排序
    endpoints.sort((a, b) => {
        const tagA = a.tags && a.tags.length > 0 ? a.tags[0] : '';
        const tagB = b.tags && b.tags.length > 0 ? b.tags[0] : '';
        if (tagA !== tagB) return tagA.localeCompare(tagB);
        return a.path.localeCompare(b.path);
    });
    
    if (endpoints.length === 0) {
        main.innerHTML = '<div class="empty-state"><h3>暂无API</h3><p>该分组下没有API端点</p></div>';
        return;
    }
    
    endpoints.forEach(endpoint => {
        main.appendChild(createEndpointCard(endpoint));
    });
}

// 创建API端点卡片
function createEndpointCard(endpoint) {
    const card = document.createElement('div');
    card.className = 'api-endpoint';
    
    const methodClass = endpoint.method.toLowerCase();
    const tags = endpoint.tags || [];
    const tagHtml = tags.map(tag => `<span class="api-tag">${tag}</span>`).join('');
    
    card.innerHTML = `
        <div class="api-endpoint-header">
            <div class="api-endpoint-title">
                <span class="api-method ${methodClass}">${endpoint.method.toUpperCase()}</span>
                <span class="api-path">${endpoint.path}</span>
                ${tagHtml}
            </div>
        </div>
        <div class="api-endpoint-body">
            <div class="api-section">
                <div class="api-section-title">描述</div>
                ${endpoint.summary ? `<div class="api-description" style="font-weight: 500; margin-bottom: 8px; color: var(--text-primary);">${escapeHtml(endpoint.summary)}</div>` : ''}
                ${endpoint.description ? `
                    <div class="api-description-toggle">
                        <button class="description-toggle-btn" onclick="toggleDescription(this)">
                            <svg class="description-toggle-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <polyline points="6 9 12 15 18 9"/>
                            </svg>
                            <span>查看详细说明</span>
                        </button>
                        <div class="api-description-detail" style="display: none;">
                            ${formatDescription(endpoint.description)}
                        </div>
                    </div>
                ` : endpoint.summary ? '' : '<div class="api-description">无描述</div>'}
            </div>
            
            ${renderParameters(endpoint)}
            ${renderRequestBody(endpoint)}
            ${renderResponses(endpoint)}
            ${renderTestSection(endpoint)}
        </div>
    `;
    
    return card;
}

// 渲染参数
function renderParameters(endpoint) {
    const params = endpoint.parameters || [];
    if (params.length === 0) return '';
    
    const rows = params.map(param => {
            const required = param.required ? '<span class="api-param-required">必需</span>' : '<span class="api-param-optional">可选</span>';
        // 处理描述文本，将换行符转换为<br>
        let descriptionHtml = '-';
        if (param.description) {
            const escapedDesc = escapeHtml(param.description);
            descriptionHtml = escapedDesc.replace(/\n/g, '<br>');
        }
        
        return `
            <tr>
                <td><span class="api-param-name">${param.name}</span></td>
                <td><span class="api-param-type">${param.schema?.type || 'string'}</span></td>
                <td>${descriptionHtml}</td>
                <td>${required}</td>
            </tr>
        `;
    }).join('');
    
    return `
        <div class="api-section">
            <div class="api-section-title">参数</div>
            <div class="api-table-wrapper">
                <table class="api-params-table">
                    <thead>
                        <tr>
                            <th>参数名</th>
                            <th>类型</th>
                            <th>描述</th>
                            <th>必需</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${rows}
                    </tbody>
                </table>
            </div>
        </div>
    `;
}

// 渲染请求体
function renderRequestBody(endpoint) {
    if (!endpoint.requestBody) return '';
    
    const content = endpoint.requestBody.content || {};
    let schema = content['application/json']?.schema || {};
    
    // 处理 $ref 引用
    if (schema.$ref) {
        const refPath = schema.$ref.split('/');
        const refName = refPath[refPath.length - 1];
        if (apiSpec.components && apiSpec.components.schemas && apiSpec.components.schemas[refName]) {
            schema = apiSpec.components.schemas[refName];
        }
    }
    
    // 渲染参数表格
    let paramsTable = '';
    if (schema.properties) {
        const requiredFields = schema.required || [];
        const rows = Object.keys(schema.properties).map(key => {
            const prop = schema.properties[key];
            const required = requiredFields.includes(key) 
                ? '<span class="api-param-required">必需</span>' 
                : '<span class="api-param-optional">可选</span>';
            
            // 处理嵌套类型
            let typeDisplay = prop.type || 'object';
            if (prop.type === 'array' && prop.items) {
                typeDisplay = `array[${prop.items.type || 'object'}]`;
            } else if (prop.$ref) {
                const refPath = prop.$ref.split('/');
                typeDisplay = refPath[refPath.length - 1];
            }
            
            // 处理枚举
            if (prop.enum) {
                typeDisplay += ` (${prop.enum.join(', ')})`;
            }
            
            // 处理描述文本，将换行符转换为<br>，但保持其他格式
            let descriptionHtml = '-';
            if (prop.description) {
                // 转义HTML，然后处理换行
                const escapedDesc = escapeHtml(prop.description);
                // 将 \n 转换为 <br>，但不要转换已经转义的换行
                descriptionHtml = escapedDesc.replace(/\n/g, '<br>');
            }
            
            return `
                <tr>
                    <td><span class="api-param-name">${escapeHtml(key)}</span></td>
                    <td><span class="api-param-type">${escapeHtml(typeDisplay)}</span></td>
                    <td>${descriptionHtml}</td>
                    <td>${required}</td>
                    <td>${prop.example !== undefined ? `<code>${escapeHtml(String(prop.example))}</code>` : '-'}</td>
                </tr>
            `;
        }).join('');
        
        if (rows) {
            paramsTable = `
                <div class="api-table-wrapper" style="margin-top: 12px;">
                    <table class="api-params-table">
                        <thead>
                            <tr>
                                <th>参数名</th>
                                <th>类型</th>
                                <th>描述</th>
                                <th>必需</th>
                                <th>示例</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${rows}
                        </tbody>
                    </table>
                </div>
            `;
        }
    }
    
    // 生成示例JSON
    let example = '';
    if (schema.example) {
        example = JSON.stringify(schema.example, null, 2);
    } else if (schema.properties) {
        const exampleObj = {};
        Object.keys(schema.properties).forEach(key => {
            const prop = schema.properties[key];
            if (prop.example !== undefined) {
                exampleObj[key] = prop.example;
            } else {
                // 根据类型生成默认示例
                if (prop.type === 'string') {
                    exampleObj[key] = prop.description || 'string';
                } else if (prop.type === 'number') {
                    exampleObj[key] = 0;
                } else if (prop.type === 'boolean') {
                    exampleObj[key] = false;
                } else if (prop.type === 'array') {
                    exampleObj[key] = [];
                } else {
                    exampleObj[key] = null;
                }
            }
        });
        example = JSON.stringify(exampleObj, null, 2);
    }
    
    return `
        <div class="api-section">
            <div class="api-section-title">请求体</div>
            ${endpoint.requestBody.description ? `<div class="api-description">${endpoint.requestBody.description}</div>` : ''}
            ${paramsTable}
            ${example ? `
                <div style="margin-top: 16px;">
                    <div style="font-weight: 500; margin-bottom: 8px; color: var(--text-primary);">示例JSON:</div>
                    <div class="api-response-example">
                        <pre>${escapeHtml(example)}</pre>
                    </div>
                </div>
            ` : ''}
        </div>
    `;
}

// 渲染响应
function renderResponses(endpoint) {
    const responses = endpoint.responses || {};
    const responseItems = Object.keys(responses).map(status => {
        const response = responses[status];
        const schema = response.content?.['application/json']?.schema || {};
        let example = '';
        if (schema.example) {
            example = JSON.stringify(schema.example, null, 2);
        }
        
        return `
            <div style="margin-bottom: 16px;">
                <strong style="color: ${status.startsWith('2') ? 'var(--success-color)' : status.startsWith('4') ? 'var(--error-color)' : 'var(--warning-color)'}">${status}</strong>
                ${response.description ? `<span style="color: var(--text-secondary); margin-left: 8px;">${response.description}</span>` : ''}
                ${example ? `
                    <div class="api-response-example" style="margin-top: 8px;">
                        <pre>${escapeHtml(example)}</pre>
                    </div>
                ` : ''}
            </div>
        `;
    }).join('');
    
    if (!responseItems) return '';
    
    return `
        <div class="api-section">
            <div class="api-section-title">响应</div>
            ${responseItems}
        </div>
    `;
}

// 渲染测试区域
function renderTestSection(endpoint) {
    const method = endpoint.method.toUpperCase();
    const path = endpoint.path;
    const hasBody = endpoint.requestBody && ['POST', 'PUT', 'PATCH'].includes(method);
    
    let bodyInput = '';
    if (hasBody) {
        const schema = endpoint.requestBody.content?.['application/json']?.schema || {};
        let defaultBody = '';
        if (schema.example) {
            defaultBody = JSON.stringify(schema.example, null, 2);
        } else if (schema.properties) {
            const exampleObj = {};
            Object.keys(schema.properties).forEach(key => {
                const prop = schema.properties[key];
                exampleObj[key] = prop.example || (prop.type === 'string' ? '' : prop.type === 'number' ? 0 : prop.type === 'boolean' ? false : null);
            });
            defaultBody = JSON.stringify(exampleObj, null, 2);
        }
        
        const bodyInputId = `test-body-${escapeId(path)}-${method}`;
        bodyInput = `
            <div class="api-test-input-group">
                <label>请求体 (JSON)</label>
                <textarea id="${bodyInputId}" class="test-body-input" placeholder='请输入JSON格式的请求体'>${defaultBody}</textarea>
            </div>
        `;
    }
    
    // 处理路径参数
    const pathParams = (endpoint.parameters || []).filter(p => p.in === 'path');
    let pathParamsInput = '';
    if (pathParams.length > 0) {
        pathParamsInput = pathParams.map(param => {
            const inputId = `test-param-${param.name}-${escapeId(path)}-${method}`;
            return `
                <div class="api-test-input-group">
                    <label>${param.name} <span style="color: var(--error-color);">*</span></label>
                    <input type="text" id="${inputId}" placeholder="${param.description || param.name}" required>
                </div>
            `;
        }).join('');
    }
    
    // 处理查询参数
    const queryParams = (endpoint.parameters || []).filter(p => p.in === 'query');
    let queryParamsInput = '';
    if (queryParams.length > 0) {
        queryParamsInput = queryParams.map(param => {
            const inputId = `test-query-${param.name}-${escapeId(path)}-${method}`;
            const defaultValue = param.schema?.default !== undefined ? param.schema.default : '';
            const placeholder = param.description || param.name;
            const required = param.required ? '<span style="color: var(--error-color);">*</span>' : '<span style="color: var(--text-muted);">可选</span>';
            return `
                <div class="api-test-input-group">
                    <label>${param.name} ${required}</label>
                    <input type="${param.schema?.type === 'number' || param.schema?.type === 'integer' ? 'number' : 'text'}" 
                           id="${inputId}" 
                           placeholder="${placeholder}" 
                           value="${defaultValue}"
                           ${param.required ? 'required' : ''}>
                </div>
            `;
        }).join('');
    }
    
    return `
        <div class="api-test-section">
            <div class="api-section-title">测试接口</div>
            <div class="api-test-form">
                ${pathParamsInput}
                ${queryParamsInput ? `<div style="margin-top: 16px;"><div style="font-weight: 500; margin-bottom: 8px; color: var(--text-primary);">查询参数:</div>${queryParamsInput}</div>` : ''}
                ${bodyInput}
                <div class="api-test-buttons">
                    <button class="api-test-btn primary" onclick="testAPI('${method}', '${escapeHtml(path)}', '${endpoint.operationId || ''}')">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <polygon points="5 3 19 12 5 21 5 3"/>
                        </svg>
                        发送请求
                    </button>
                    <button class="api-test-btn copy-curl" onclick="copyCurlCommand(event, '${method}', '${escapeHtml(path)}')" title="复制curl命令">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <rect x="9" y="9" width="13" height="13" rx="2" ry="2" stroke="currentColor" stroke-width="2"/>
                            <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" stroke="currentColor" stroke-width="2"/>
                        </svg>
                        复制curl
                    </button>
                    <button class="api-test-btn clear-result" onclick="clearTestResult('${escapeId(path)}-${method}')" title="清除测试结果">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <polyline points="3 6 5 6 21 6"/>
                            <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                        </svg>
                        清除结果
                    </button>
                </div>
                <div id="test-result-${escapeId(path)}-${method}" class="api-test-result" style="display: none;"></div>
            </div>
        </div>
    `;
}

// 测试API
async function testAPI(method, path, operationId) {
    const resultId = `test-result-${escapeId(path)}-${method}`;
    const resultDiv = document.getElementById(resultId);
    if (!resultDiv) return;
    
    resultDiv.style.display = 'block';
    resultDiv.className = 'api-test-result loading';
    resultDiv.textContent = '发送请求中...';
    
    try {
        // 替换路径参数
        let actualPath = path;
        const pathParams = path.match(/\{([^}]+)\}/g) || [];
        pathParams.forEach(param => {
            const paramName = param.slice(1, -1);
            const inputId = `test-param-${paramName}-${escapeId(path)}-${method}`;
            const input = document.getElementById(inputId);
            if (input && input.value) {
                actualPath = actualPath.replace(param, encodeURIComponent(input.value));
            } else {
                throw new Error(`路径参数 ${paramName} 不能为空`);
            }
        });
        
        // 确保路径以/api开头（如果OpenAPI规范中的路径不包含/api）
        if (!actualPath.startsWith('/api') && !actualPath.startsWith('http')) {
            actualPath = '/api' + actualPath;
        }
        
        // 构建查询参数
        const queryParams = [];
        const endpointSpec = apiSpec.paths[path]?.[method.toLowerCase()];
        if (endpointSpec && endpointSpec.parameters) {
            endpointSpec.parameters.filter(p => p.in === 'query').forEach(param => {
                const inputId = `test-query-${param.name}-${escapeId(path)}-${method}`;
                const input = document.getElementById(inputId);
                if (input && input.value !== '' && input.value !== null && input.value !== undefined) {
                    queryParams.push(`${encodeURIComponent(param.name)}=${encodeURIComponent(input.value)}`);
                } else if (param.required) {
                    throw new Error(`查询参数 ${param.name} 不能为空`);
                }
            });
        }
        
        // 添加查询字符串
        if (queryParams.length > 0) {
            actualPath += (actualPath.includes('?') ? '&' : '?') + queryParams.join('&');
        }
        
        // 构建请求选项
        const options = {
            method: method,
            headers: {
                'Content-Type': 'application/json',
            }
        };
        
        // 添加token
        if (currentToken) {
            options.headers['Authorization'] = 'Bearer ' + currentToken;
        } else {
            // 如果没有token，提示用户
            throw new Error('未检测到 Token。请先在前端页面登录，然后刷新此页面。或者手动在请求头中添加 Authorization: Bearer your_token');
        }
        
        // 添加请求体
        if (['POST', 'PUT', 'PATCH'].includes(method)) {
            const bodyInputId = `test-body-${escapeId(path)}-${method}`;
            const bodyInput = document.getElementById(bodyInputId);
            if (bodyInput && bodyInput.value.trim()) {
                try {
                    options.body = JSON.stringify(JSON.parse(bodyInput.value.trim()));
                } catch (e) {
                    throw new Error('请求体JSON格式错误: ' + e.message);
                }
            }
        }
        
        // 发送请求
        const response = await fetch(actualPath, options);
        const responseText = await response.text();
        
        let responseData;
        try {
            responseData = JSON.parse(responseText);
        } catch {
            responseData = responseText;
        }
        
        // 显示结果
        resultDiv.className = response.ok ? 'api-test-result success' : 'api-test-result error';
        resultDiv.textContent = `状态码: ${response.status} ${response.statusText}\n\n${typeof responseData === 'string' ? responseData : JSON.stringify(responseData, null, 2)}`;
        
    } catch (error) {
        resultDiv.className = 'api-test-result error';
        resultDiv.textContent = '请求失败: ' + error.message;
    }
}

// 清除测试结果
function clearTestResult(id) {
    const resultDiv = document.getElementById(`test-result-${id}`);
    if (resultDiv) {
        resultDiv.style.display = 'none';
        resultDiv.textContent = '';
    }
}

// 复制curl命令
function copyCurlCommand(event, method, path) {
    try {
        // 替换路径参数
        let actualPath = path;
        const pathParams = path.match(/\{([^}]+)\}/g) || [];
        pathParams.forEach(param => {
            const paramName = param.slice(1, -1);
            const inputId = `test-param-${paramName}-${escapeId(path)}-${method}`;
            const input = document.getElementById(inputId);
            if (input && input.value) {
                actualPath = actualPath.replace(param, encodeURIComponent(input.value));
            }
        });
        
        // 确保路径以/api开头
        if (!actualPath.startsWith('/api') && !actualPath.startsWith('http')) {
            actualPath = '/api' + actualPath;
        }
        
        // 构建查询参数
        const queryParams = [];
        const endpointSpec = apiSpec.paths[path]?.[method.toLowerCase()];
        if (endpointSpec && endpointSpec.parameters) {
            endpointSpec.parameters.filter(p => p.in === 'query').forEach(param => {
                const inputId = `test-query-${param.name}-${escapeId(path)}-${method}`;
                const input = document.getElementById(inputId);
                if (input && input.value !== '' && input.value !== null && input.value !== undefined) {
                    queryParams.push(`${encodeURIComponent(param.name)}=${encodeURIComponent(input.value)}`);
                }
            });
        }
        
        // 添加查询字符串
        if (queryParams.length > 0) {
            actualPath += (actualPath.includes('?') ? '&' : '?') + queryParams.join('&');
        }
        
        // 构建完整的URL
        const baseUrl = window.location.origin;
        const fullUrl = baseUrl + actualPath;
        
        // 构建curl命令
        let curlCommand = `curl -X ${method.toUpperCase()} "${fullUrl}"`;
        
        // 添加请求头
        curlCommand += ` \\\n  -H "Content-Type: application/json"`;
        
        // 添加Authorization头
        if (currentToken) {
            curlCommand += ` \\\n  -H "Authorization: Bearer ${currentToken}"`;
        } else {
            curlCommand += ` \\\n  -H "Authorization: Bearer YOUR_TOKEN_HERE"`;
        }
        
        // 添加请求体（如果有）
        if (['POST', 'PUT', 'PATCH'].includes(method.toUpperCase())) {
            const bodyInputId = `test-body-${escapeId(path)}-${method}`;
            const bodyInput = document.getElementById(bodyInputId);
            if (bodyInput && bodyInput.value.trim()) {
                try {
                    // 验证JSON格式并格式化
                    const jsonBody = JSON.parse(bodyInput.value.trim());
                    const jsonString = JSON.stringify(jsonBody);
                    // 在单引号内，只需要转义单引号本身
                    const escapedJson = jsonString.replace(/'/g, "'\\''");
                    curlCommand += ` \\\n  -d '${escapedJson}'`;
                } catch (e) {
                    // 如果不是有效JSON，直接使用原始值
                    const escapedBody = bodyInput.value.trim().replace(/'/g, "'\\''");
                    curlCommand += ` \\\n  -d '${escapedBody}'`;
                }
            }
        }
        
        // 复制到剪贴板
        const button = event ? event.target.closest('button') : null;
        navigator.clipboard.writeText(curlCommand).then(() => {
            // 显示成功提示
            if (button) {
                const originalText = button.innerHTML;
                button.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>已复制';
                button.style.color = 'var(--success-color)';
                setTimeout(() => {
                    button.innerHTML = originalText;
                    button.style.color = '';
                }, 2000);
            } else {
                alert('curl命令已复制到剪贴板！');
            }
        }).catch(err => {
            console.error('复制失败:', err);
            // 如果clipboard API失败，使用fallback方法
            const textarea = document.createElement('textarea');
            textarea.value = curlCommand;
            textarea.style.position = 'fixed';
            textarea.style.opacity = '0';
            document.body.appendChild(textarea);
            textarea.select();
            try {
                document.execCommand('copy');
                if (button) {
                    const originalText = button.innerHTML;
                    button.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>已复制';
                    button.style.color = 'var(--success-color)';
                    setTimeout(() => {
                        button.innerHTML = originalText;
                        button.style.color = '';
                    }, 2000);
                } else {
                    alert('curl命令已复制到剪贴板！');
                }
            } catch (e) {
                alert('复制失败，请手动复制:\n\n' + curlCommand);
            }
            document.body.removeChild(textarea);
        });
        
    } catch (error) {
        console.error('生成curl命令失败:', error);
        alert('生成curl命令失败: ' + error.message);
    }
}

// 格式化描述文本（处理markdown格式）
function formatDescription(text) {
    if (!text) return '';
    
    // 先提取代码块（避免代码块内的markdown被处理）
    let formatted = text;
    const codeBlocks = [];
    let codeBlockIndex = 0;
    
    // 提取代码块（支持语言标识符，如 ```json 或 ```javascript）
    formatted = formatted.replace(/```(\w+)?\s*\n?([\s\S]*?)```/g, (match, lang, code) => {
        const placeholder = `__CODE_BLOCK_${codeBlockIndex}__`;
        codeBlocks[codeBlockIndex] = {
            lang: (lang && lang.trim()) || '',
            code: code.trim()
        };
        codeBlockIndex++;
        return placeholder;
    });
    
    // 提取行内代码（避免行内代码内的markdown被处理）
    const inlineCodes = [];
    let inlineCodeIndex = 0;
    formatted = formatted.replace(/`([^`\n]+)`/g, (match, code) => {
        const placeholder = `__INLINE_CODE_${inlineCodeIndex}__`;
        inlineCodes[inlineCodeIndex] = code;
        inlineCodeIndex++;
        return placeholder;
    });
    
    // 转义HTML（但保留占位符）
    formatted = escapeHtml(formatted);
    
    // 恢复行内代码（需要转义，因为占位符已经被转义了）
    inlineCodes.forEach((code, index) => {
        formatted = formatted.replace(
            `__INLINE_CODE_${index}__`,
            `<code class="inline-code">${escapeHtml(code)}</code>`
        );
    });
    
    // 恢复代码块（代码块内容已经转义过，直接使用）
    codeBlocks.forEach((block, index) => {
        const langLabel = block.lang ? `<span class="code-lang">${escapeHtml(block.lang)}</span>` : '';
        // 代码块内容已经在提取时保存，不需要再次转义
        formatted = formatted.replace(
            `__CODE_BLOCK_${index}__`,
            `<pre class="code-block">${langLabel}<code>${escapeHtml(block.code)}</code></pre>`
        );
    });
    
    // 处理标题（### 标题）
    formatted = formatted.replace(/^###\s+(.+)$/gm, '<h3 class="md-h3">$1</h3>');
    formatted = formatted.replace(/^##\s+(.+)$/gm, '<h2 class="md-h2">$1</h2>');
    formatted = formatted.replace(/^#\s+(.+)$/gm, '<h1 class="md-h1">$1</h1>');
    
    // 处理加粗文本（**text** 或 __text__）
    formatted = formatted.replace(/\*\*([^*]+?)\*\*/g, '<strong>$1</strong>');
    formatted = formatted.replace(/__([^_]+?)__/g, '<strong>$1</strong>');
    
    // 处理斜体（*text* 或 _text_，但不与加粗冲突）
    formatted = formatted.replace(/(?<!\*)\*([^*\n]+?)\*(?!\*)/g, '<em>$1</em>');
    formatted = formatted.replace(/(?<!_)_([^_\n]+?)_(?!_)/g, '<em>$1</em>');
    
    // 处理链接 [text](url)
    formatted = formatted.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer" class="md-link">$1</a>');
    
    // 处理列表项（有序和无序）
    const lines = formatted.split('\n');
    const result = [];
    let inUnorderedList = false;
    let inOrderedList = false;
    let orderedListStart = 1;
    
    for (let i = 0; i < lines.length; i++) {
        const line = lines[i];
        const unorderedMatch = line.match(/^[-*]\s+(.+)$/);
        const orderedMatch = line.match(/^\d+\.\s+(.+)$/);
        
        if (unorderedMatch) {
            if (inOrderedList) {
                result.push('</ol>');
                inOrderedList = false;
            }
            if (!inUnorderedList) {
                result.push('<ul class="md-list">');
                inUnorderedList = true;
            }
            result.push(`<li class="md-list-item">${unorderedMatch[1]}</li>`);
        } else if (orderedMatch) {
            if (inUnorderedList) {
                result.push('</ul>');
                inUnorderedList = false;
            }
            if (!inOrderedList) {
                result.push('<ol class="md-list">');
                inOrderedList = true;
                orderedListStart = parseInt(line.match(/^(\d+)\./)[1]) || 1;
            }
            result.push(`<li class="md-list-item">${orderedMatch[1]}</li>`);
        } else {
            if (inUnorderedList) {
                result.push('</ul>');
                inUnorderedList = false;
            }
            if (inOrderedList) {
                result.push('</ol>');
                inOrderedList = false;
            }
            if (line.trim()) {
                result.push(line);
            } else if (i < lines.length - 1) {
                // 只在非最后一行时添加换行
                result.push('<br>');
            }
        }
    }
    
    if (inUnorderedList) {
        result.push('</ul>');
    }
    if (inOrderedList) {
        result.push('</ol>');
    }
    
    formatted = result.join('\n');
    
    // 处理段落（连续的空行分隔段落）
    formatted = formatted.replace(/(<br>\s*){2,}/g, '</p><p class="md-paragraph">');
    formatted = '<p class="md-paragraph">' + formatted + '</p>';
    
    // 清理多余的<br>标签（在块级元素前后）
    formatted = formatted.replace(/(<\/?(h[1-6]|ul|ol|li|pre|p)[^>]*>)\s*<br>/gi, '$1');
    formatted = formatted.replace(/<br>\s*(<\/?(h[1-6]|ul|ol|li|pre|p)[^>]*>)/gi, '$1');
    
    // 将剩余的单个换行符转换为<br>（但避免在块级元素内）
    formatted = formatted.replace(/\n(?!<\/?(h[1-6]|ul|ol|li|pre|p|code))/g, '<br>');
    
    return formatted;
}

// HTML转义
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ID转义（用于HTML ID属性）
function escapeId(text) {
    return text.replace(/[{}]/g, '').replace(/\//g, '-');
}

// 切换描述显示/隐藏
function toggleDescription(button) {
    const icon = button.querySelector('.description-toggle-icon');
    const detail = button.parentElement.querySelector('.api-description-detail');
    const span = button.querySelector('span');
    
    if (detail.style.display === 'none') {
        detail.style.display = 'block';
        icon.style.transform = 'rotate(180deg)';
        span.textContent = '隐藏详细说明';
    } else {
        detail.style.display = 'none';
        icon.style.transform = 'rotate(0deg)';
        span.textContent = '查看详细说明';
    }
}
