// 安全学苑 (Security Academy) - 框架与交互引擎
// 自包含模块：依赖 window.ACADEMY_LABS / ACADEMY_TUTORIALS / ACADEMY_TOOLCHAIN / ACADEMY_RESOURCES
// 复用已加载的 marked / DOMPurify，不引入新依赖；进度存 localStorage；零后端。
(function () {
    'use strict';

    var PROGRESS_KEY = 'lnu_academy_progress_v1';
    var activeTab = 'labs';
    var labState = null;     // 当前打开的实验运行态
    var fgCollapsed = false;  // 悬浮向导是否折叠

    var TABS = [
        { id: 'labs', icon: '🧪', name: '实战实验室' },
        { id: 'tutorials', icon: '📖', name: '进阶教程' },
        { id: 'toolchain', icon: '🛰️', name: '工具链图谱' },
        { id: 'resources', icon: '🔗', name: '安全资源库' }
    ];

    // ---------- 工具函数 ----------
    function esc(s) {
        return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
            return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
        });
    }
    function md(text) {
        if (typeof marked === 'undefined') return '<pre>' + esc(text) + '</pre>';
        var html = marked.parse(text || '');
        return (typeof DOMPurify !== 'undefined') ? DOMPurify.sanitize(html) : html;
    }
    function loadProgress() {
        try { return JSON.parse(localStorage.getItem(PROGRESS_KEY)) || { labs: {} }; }
        catch (e) { return { labs: {} }; }
    }
    function saveProgress(p) { localStorage.setItem(PROGRESS_KEY, JSON.stringify(p)); }
    function $(id) { return document.getElementById(id); }
    function diffClass(d) {
        return d === '进阶' ? 'adv' : (d === '中级' ? 'mid' : 'easy');
    }

    // ---------- 入口 ----------
    function initAcademy() {
        var root = $('academy-root');
        if (!root) return;
        hideFloatingGuide(); // 回到学苑页时收起悬浮向导(页内已有完整界面)
        root.innerHTML =
            '<div class="aca-hero">' +
            '<div class="aca-hero-tag">辽宁大学 · 安全学苑</div>' +
            '<h1 class="aca-hero-title">安全学苑 Security Academy</h1>' +
            '<p class="aca-hero-sub">从入门到进阶：动手实战、系统教程、工具链全景与精选学习资源。</p>' +
            '</div>' +
            '<div class="aca-tabs" id="aca-tabs">' +
            TABS.map(function (t) {
                return '<button class="aca-tab' + (t.id === activeTab ? ' on' : '') +
                    '" onclick="academySwitchTab(\'' + t.id + '\')">' + t.icon + ' ' + t.name + '</button>';
            }).join('') +
            '</div>' +
            '<div class="aca-body" id="aca-body"></div>';
        renderTab(activeTab);
    }

    function academySwitchTab(id) {
        activeTab = id; labState = null;
        var tabs = $('aca-tabs');
        if (tabs) tabs.querySelectorAll('.aca-tab').forEach(function (b, i) {
            b.classList.toggle('on', TABS[i].id === id);
        });
        renderTab(id);
    }

    function renderTab(id) {
        if (id === 'labs') return renderLabs();
        if (id === 'tutorials') return renderTutorials();
        if (id === 'toolchain') return renderToolchain();
        if (id === 'resources') return renderResources();
    }

    function emptyHint(text) {
        return '<div class="aca-empty">' + esc(text) + '</div>';
    }

    // ============================================================
    //  Tab 1：实战实验室
    // ============================================================
    function renderLabs() {
        var body = $('aca-body');
        var data = window.ACADEMY_LABS;
        if (!data || !data.categories) { body.innerHTML = emptyHint('实验内容加载中…'); return; }
        var p = loadProgress();

        var total = 0, done = 0;
        data.categories.forEach(function (c) {
            (c.labs || []).forEach(function (l) { total++; if (p.labs[l.id]) done++; });
        });

        var html = '<div class="aca-labs-head">' +
            '<div class="aca-progress-pill">已完成 <b>' + done + '</b> / ' + total + ' 个实验</div>' +
            '<div class="aca-progress-bar"><span style="width:' + (total ? Math.round(done / total * 100) : 0) + '%"></span></div>' +
            '</div>';

        data.categories.forEach(function (cat) {
            html += '<div class="aca-cat"><div class="aca-cat-title">' + (cat.icon || '') + ' ' + esc(cat.name) + '</div>' +
                '<div class="aca-lab-grid">';
            (cat.labs || []).forEach(function (lab) {
                var ok = !!p.labs[lab.id];
                html += '<div class="aca-lab-card' + (ok ? ' done' : '') + '" onclick="academyOpenLab(\'' + lab.id + '\')">' +
                    '<div class="aca-lab-top"><span class="aca-diff aca-diff-' + diffClass(lab.difficulty) + '">' + esc(lab.difficulty || '入门') + '</span>' +
                    '<span class="aca-lab-min">⏱ ' + (lab.minutes || 10) + ' 分钟</span></div>' +
                    '<div class="aca-lab-title">' + esc(lab.title) + (ok ? ' <span class="aca-lab-check">✓</span>' : '') + '</div>' +
                    '<div class="aca-lab-goal">' + esc(lab.goal || '') + '</div>' +
                    '</div>';
            });
            html += '</div></div>';
        });
        body.innerHTML = html;
    }

    function findLab(id) {
        var data = window.ACADEMY_LABS; if (!data) return null;
        var found = null;
        (data.categories || []).forEach(function (c) {
            (c.labs || []).forEach(function (l) { if (l.id === id) found = l; });
        });
        return found;
    }

    function academyOpenLab(id) {
        var lab = findLab(id); if (!lab) return;
        labState = { lab: lab, stepDone: {}, quizAnswered: false };
        renderLabDetail();
    }

    function renderLabDetail() {
        var body = $('aca-body'), lab = labState.lab;
        var steps = lab.steps || [];
        var html = '<div class="aca-lab-detail">' +
            '<button class="aca-back" onclick="academySwitchTab(\'labs\')">← 返回实验列表</button>' +
            '<div class="aca-lab-h"><span class="aca-diff aca-diff-' + diffClass(lab.difficulty) + '">' + esc(lab.difficulty || '入门') + '</span>' +
            '<h2>' + esc(lab.title) + '</h2></div>' +
            (lab.intro ? '<div class="aca-lab-intro">' + lab.intro + '</div>' : '');

        // 步骤清单
        html += '<div class="aca-steps">';
        steps.forEach(function (st, i) {
            var sdone = labState.stepDone[i];
            html += '<div class="aca-step' + (sdone ? ' done' : '') + '">' +
                '<div class="aca-step-no">' + (sdone ? '✓' : (i + 1)) + '</div>' +
                '<div class="aca-step-main">' +
                '<div class="aca-step-title">' + esc(st.title) + '</div>' +
                (st.desc ? '<div class="aca-step-desc">' + st.desc + '</div>' : '') +
                '<div class="aca-step-actions">';
            if (st.action) {
                var a = st.action;
                if (a.type === 'goto') {
                    html += '<button class="aca-btn" onclick="academyGoto(' + i + ',\'' + a.page + '\')">去操作 →</button>';
                } else if (a.type === 'highlight') {
                    html += '<button class="aca-btn" onclick="academyHighlight(' + i + ',\'' + (a.page || '') + '\',\'' + a.selector + '\')">带我去看 →</button>';
                }
            }
            html += '<button class="aca-btn-ghost" onclick="academyToggleStep(' + i + ')">' + (sdone ? '已完成 ✓' : '标记完成') + '</button>';
            html += '</div></div></div>';
        });
        html += '</div>';

        // 容错示例（没配 AI 也能看）
        if (lab.demo) {
            html += '<details class="aca-demo"><summary>🖼 还没配置 AI / 工具？点这里看示例结果</summary>' +
                '<div class="aca-demo-body">' + lab.demo + '</div></details>';
        }

        // 小测验（可选）
        if (lab.quiz) {
            html += renderLabQuiz(lab.quiz);
        } else {
            html += '<div class="aca-lab-foot">' + completeBtn() + '</div>';
        }

        body.innerHTML = html;
    }

    function completeBtn() {
        var ok = loadProgress().labs[labState.lab.id];
        return '<button class="aca-btn aca-btn-lg" onclick="academyCompleteLab()">' +
            (ok ? '已通关 ✓（点此重做）' : '✅ 完成本实验') + '</button>';
    }

    function renderLabQuiz(q) {
        var html = '<div class="aca-quiz"><div class="aca-quiz-h">📝 小测验：答对即可完成实验</div>' +
            '<div class="aca-q-title">' + esc(q.q) + '</div><div class="aca-q-opts">';
        q.options.forEach(function (opt, oi) {
            html += '<div class="aca-opt" data-o="' + oi + '" onclick="academyQuizPick(' + oi + ')">' +
                '<span class="aca-opt-mark">' + String.fromCharCode(65 + oi) + '</span>' + esc(opt) + '</div>';
        });
        html += '</div><div class="aca-q-explain" id="aca-q-explain"></div>' +
            '<div class="aca-lab-foot" id="aca-quiz-foot"></div></div>';
        return html;
    }

    function academyQuizPick(oi) {
        var q = labState.lab.quiz, right = q.answer;
        document.querySelectorAll('.aca-opt').forEach(function (el) {
            var o = parseInt(el.getAttribute('data-o'), 10);
            el.classList.remove('correct', 'wrong', 'sel');
            if (o === right) el.classList.add('correct');
            else if (o === oi) el.classList.add('wrong');
        });
        var exp = $('aca-q-explain');
        if (exp) { exp.style.display = 'block'; exp.innerHTML = (oi === right ? '✅ 正确！' : '❌ 再想想。') + esc(q.explain || ''); }
        var foot = $('aca-quiz-foot');
        if (oi === right && foot) foot.innerHTML = completeBtn();
        else if (foot) foot.innerHTML = '';
    }

    function academyToggleStep(i) {
        labState.stepDone[i] = !labState.stepDone[i];
        renderLabDetail();
    }

    function academyCompleteLab() {
        var p = loadProgress();
        p.labs[labState.lab.id] = true;
        saveProgress(p);
        academyToast('🎉 实验完成！已记录进度');
        academySwitchTab('labs');
    }

    // 跳到真实模块去操作（低耦合：只用现成的 switchPage + 预填输入框）
    function academyGoto(stepIdx, page) {
        if (!labState) return;
        var st = labState.lab.steps[stepIdx], a = st.action || {};
        if (typeof window.switchPage === 'function') window.switchPage(page);
        showFloatingGuide(); // 跳转后浮出常驻向导,跟随到目标页
        if (a.prefill && page === 'chat') {
            setTimeout(function () {
                var input = document.getElementById('chat-input');
                if (input) {
                    input.value = a.prefill;
                    input.dispatchEvent(new Event('input', { bubbles: true }));
                    input.focus();
                    academyToast('已为你填好指令，确认后点发送即可');
                }
            }, 300);
        } else if (a.hint) {
            academyToast(a.hint);
        }
    }

    function academyHighlight(stepIdx, page, selector) {
        if (page && typeof window.switchPage === 'function') window.switchPage(page);
        showFloatingGuide(); // 跳转后浮出常驻向导,跟随到目标页
        setTimeout(function () {
            var el = document.querySelector(selector);
            if (el) {
                el.scrollIntoView({ behavior: 'smooth', block: 'center' });
                el.classList.add('aca-pulse');
                setTimeout(function () { el.classList.remove('aca-pulse'); }, 2400);
            } else {
                academyToast('提示：请在当前页面找到对应位置');
            }
        }, 400);
    }

    // ============================================================
    //  Tab 2：进阶教程
    // ============================================================
    function renderTutorials(openId) {
        var body = $('aca-body');
        var data = window.ACADEMY_TUTORIALS;
        if (!data || !data.categories) { body.innerHTML = emptyHint('教程内容加载中…'); return; }

        var first = openId;
        if (!first) {
            outer: for (var i = 0; i < data.categories.length; i++) {
                var arts = data.categories[i].articles || [];
                if (arts.length) { first = arts[0].id; break outer; }
            }
        }
        var current = null;
        data.categories.forEach(function (c) {
            (c.articles || []).forEach(function (a) { if (a.id === first) current = a; });
        });

        var toc = '<div class="aca-toc">';
        data.categories.forEach(function (cat) {
            toc += '<div class="aca-toc-cat">' + esc(cat.name) + '</div>';
            (cat.articles || []).forEach(function (a) {
                toc += '<div class="aca-toc-item' + (current && a.id === current.id ? ' on' : '') +
                    '" onclick="academyOpenArticle(\'' + a.id + '\')">' +
                    '<span class="aca-diff aca-diff-' + diffClass(a.difficulty) + '">' + esc(a.difficulty || '入门') + '</span>' +
                    esc(a.title) + '</div>';
            });
        });
        toc += '</div>';

        var content = '<div class="aca-article">';
        if (current) {
            content += '<div class="aca-article-meta">难度 ' + esc(current.difficulty || '入门') +
                ' · 约 ' + (current.minutes || 5) + ' 分钟</div>' +
                '<div class="markdown-body aca-md">' + md(current.md || '') + '</div>';
        } else {
            content += emptyHint('暂无教程');
        }
        content += '</div>';

        body.innerHTML = '<div class="aca-tut-layout">' + toc + content + '</div>';
    }
    function academyOpenArticle(id) { renderTutorials(id); }

    // ============================================================
    //  Tab 3：工具链图谱
    // ============================================================
    function renderToolchain() {
        var body = $('aca-body');
        var data = window.ACADEMY_TOOLCHAIN;
        if (!data || !data.phases) { body.innerHTML = emptyHint('工具链内容加载中…'); return; }
        var html = '<div class="aca-toolchain-intro">按「网络杀伤链」阶段梳理平台工具，点击任一工具查看它在链条中的角色。</div>' +
            '<div class="aca-chain">';
        data.phases.forEach(function (ph, i) {
            html += '<div class="aca-phase">' +
                '<div class="aca-phase-head"><span class="aca-phase-ic">' + (ph.icon || '') + '</span>' +
                '<span class="aca-phase-name">' + esc(ph.name) + '</span></div>' +
                (ph.desc ? '<div class="aca-phase-desc">' + esc(ph.desc) + '</div>' : '') +
                '<div class="aca-tool-chips">';
            (ph.tools || []).forEach(function (t, ti) {
                html += '<span class="aca-tool-chip" onclick="academyShowTool(' + i + ',' + ti + ')">' + esc(t.name) + '</span>';
            });
            html += '</div></div>';
            if (i < data.phases.length - 1) html += '<div class="aca-phase-arrow">→</div>';
        });
        html += '</div><div class="aca-tool-detail" id="aca-tool-detail"></div>';
        body.innerHTML = html;
    }

    function academyShowTool(pi, ti) {
        var t = window.ACADEMY_TOOLCHAIN.phases[pi].tools[ti];
        var el = $('aca-tool-detail');
        if (!t || !el) return;
        el.innerHTML = '<div class="aca-tool-card">' +
            '<div class="aca-tool-name">🧰 ' + esc(t.name) + '</div>' +
            '<div class="aca-tool-role"><b>链条角色：</b>' + esc(t.role || '') + '</div>' +
            (t.desc ? '<div class="aca-tool-desc">' + esc(t.desc) + '</div>' : '') +
            (t.tip ? '<div class="aca-tool-tip">💡 ' + esc(t.tip) + '</div>' : '') +
            '</div>';
        el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }

    // ============================================================
    //  Tab 4：安全资源库
    // ============================================================
    var resourceKW = '';
    function renderResources() {
        var body = $('aca-body');
        var data = window.ACADEMY_RESOURCES;
        if (!data || !data.categories) { body.innerHTML = emptyHint('资源内容加载中…'); return; }
        body.innerHTML = '<div class="aca-res-search"><input id="aca-res-input" placeholder="🔍 搜索资源（名称/描述）..." ' +
            'oninput="academyResSearch(this.value)" value="' + esc(resourceKW) + '"></div>' +
            '<div id="aca-res-list">' + resourceListHTML(data, resourceKW) + '</div>';
        var inp = $('aca-res-input');
        if (inp && resourceKW) { inp.focus(); inp.setSelectionRange(inp.value.length, inp.value.length); }
    }
    function resourceListHTML(data, kw) {
        kw = (kw || '').toLowerCase();
        var html = '', any = false;
        data.categories.forEach(function (cat) {
            var links = (cat.links || []).filter(function (l) {
                return !kw || (l.title + ' ' + (l.desc || '')).toLowerCase().indexOf(kw) >= 0;
            });
            if (!links.length) return;
            any = true;
            html += '<div class="aca-res-cat"><div class="aca-res-cat-title">' + (cat.icon || '') + ' ' + esc(cat.name) + '</div>' +
                '<div class="aca-res-grid">';
            links.forEach(function (l) {
                html += '<a class="aca-res-card" href="' + esc(l.url) + '" target="_blank" rel="noopener noreferrer">' +
                    '<div class="aca-res-title">' + esc(l.title) + ' <span class="aca-res-ext">↗</span></div>' +
                    '<div class="aca-res-desc">' + esc(l.desc || '') + '</div></a>';
            });
            html += '</div></div>';
        });
        return any ? html : emptyHint('没有匹配的资源');
    }
    function academyResSearch(v) {
        resourceKW = v;
        var list = $('aca-res-list');
        if (list) list.innerHTML = resourceListHTML(window.ACADEMY_RESOURCES, v);
    }

    // ============================================================
    //  常驻悬浮实验向导（跳转到真实模块后仍可继续做下一步）
    // ============================================================
    function showFloatingGuide() { if (labState) renderFloatingGuide(); }

    function hideFloatingGuide() {
        var el = $('aca-fg'); if (el) el.remove();
    }

    function fgCurrentStep() {
        var steps = labState.lab.steps || [];
        for (var i = 0; i < steps.length; i++) if (!labState.stepDone[i]) return i;
        return steps.length;
    }

    function renderFloatingGuide() {
        if (!labState) { hideFloatingGuide(); return; }
        var lab = labState.lab, steps = lab.steps || [];
        var el = $('aca-fg');
        if (!el) { el = document.createElement('div'); el.id = 'aca-fg'; el.className = 'aca-fg'; document.body.appendChild(el); }
        el.classList.toggle('collapsed', fgCollapsed);

        var head = '<div class="aca-fg-head" onclick="academyFloatToggleCollapse()">' +
            '<span class="aca-fg-title">🧪 ' + esc(lab.title) + '</span>' +
            '<span class="aca-fg-ops">' +
            '<span class="aca-fg-icon">' + (fgCollapsed ? '▢' : '—') + '</span>' +
            '<span class="aca-fg-icon" onclick="event.stopPropagation();academyFloatClose()">✕</span>' +
            '</span></div>';

        if (fgCollapsed) { el.innerHTML = head; return; }

        var cur = fgCurrentStep(), allDone = cur >= steps.length;
        var body = '<div class="aca-fg-body"><div class="aca-fg-steps">';
        steps.forEach(function (st, i) {
            var done = labState.stepDone[i], isCur = (i === cur);
            body += '<div class="aca-fg-step' + (done ? ' done' : '') + (isCur ? ' cur' : '') +
                '" onclick="academyFloatToggle(' + i + ')">' +
                '<span class="aca-fg-dot">' + (done ? '✓' : (i + 1)) + '</span>' +
                '<span class="aca-fg-step-t">' + esc(st.title) + '</span></div>';
        });
        body += '</div>';

        if (!allDone) {
            var st = steps[cur], a = st.action;
            if (st.desc) body += '<div class="aca-fg-desc">' + st.desc + '</div>';
            body += '<div class="aca-fg-actions">';
            if (a && a.type === 'goto') body += '<button class="aca-btn" onclick="academyGoto(' + cur + ',\'' + a.page + '\')">去做这步 →</button>';
            else if (a && a.type === 'highlight') body += '<button class="aca-btn" onclick="academyHighlight(' + cur + ',\'' + (a.page || '') + '\',\'' + a.selector + '\')">带我去看 →</button>';
            body += '<button class="aca-btn-ghost" onclick="academyFloatToggle(' + cur + ')">完成这步 ✓</button></div>';
        } else {
            body += '<div class="aca-fg-desc">🎉 全部步骤已完成！</div>' +
                '<div class="aca-fg-actions"><button class="aca-btn" onclick="academyFloatComplete()">✅ 完成实验</button></div>';
        }
        body += '<div class="aca-fg-foot"><span class="aca-fg-link" onclick="academyFloatReturn()">↩ 返回学苑看详情</span></div></div>';
        el.innerHTML = head + body;
    }

    function academyFloatToggleCollapse() { fgCollapsed = !fgCollapsed; renderFloatingGuide(); }
    function academyFloatClose() { hideFloatingGuide(); }
    function academyFloatToggle(i) {
        if (!labState) return;
        labState.stepDone[i] = !labState.stepDone[i];
        renderFloatingGuide();
    }
    function academyFloatComplete() {
        if (!labState) return;
        var p = loadProgress(); p.labs[labState.lab.id] = true; saveProgress(p);
        academyToast('🎉 实验完成！已记录进度');
        hideFloatingGuide();
        if (typeof window.switchPage === 'function') window.switchPage('academy');
        labState = null;
    }
    function academyFloatReturn() {
        if (typeof window.switchPage === 'function') window.switchPage('academy');
        hideFloatingGuide();
        if (labState) renderLabDetail(); // 用现有 labState,保留已勾选的步骤进度
    }

    // ---------- 轻量 toast ----------
    function academyToast(msg) {
        var t = document.createElement('div');
        t.className = 'aca-toast';
        t.textContent = msg;
        document.body.appendChild(t);
        setTimeout(function () { t.classList.add('show'); }, 10);
        setTimeout(function () { t.classList.remove('show'); setTimeout(function () { t.remove(); }, 300); }, 2600);
    }

    // ---------- 导出全局 ----------
    window.initAcademy = initAcademy;
    window.academySwitchTab = academySwitchTab;
    window.academyOpenLab = academyOpenLab;
    window.academyToggleStep = academyToggleStep;
    window.academyCompleteLab = academyCompleteLab;
    window.academyGoto = academyGoto;
    window.academyHighlight = academyHighlight;
    window.academyQuizPick = academyQuizPick;
    window.academyOpenArticle = academyOpenArticle;
    window.academyShowTool = academyShowTool;
    window.academyResSearch = academyResSearch;
    window.academyFloatToggleCollapse = academyFloatToggleCollapse;
    window.academyFloatClose = academyFloatClose;
    window.academyFloatToggle = academyFloatToggle;
    window.academyFloatComplete = academyFloatComplete;
    window.academyFloatReturn = academyFloatReturn;
})();
