const API_BASE = '/api';

let currentTaskId = null;
let currentTaskStatus = null;
let currentSnapshots = [];
let selectedVersionA = null;
let selectedVersionB = null;

const snapTypeLabels = {
    'generate': '生成方案',
    'import': '导入方案',
    'copy': '复制任务',
    'pre_approve': '批准前',
    'manual': '手动创建'
};

const snapStatusLabels = {
    'draft': '草稿',
    'pending_review': '待复核',
    'approved': '已批准',
    'rejected': '已驳回',
    'revoked': '已撤销'
};

document.addEventListener('DOMContentLoaded', function() {
    setupTabs();
    setupFileInputs();
    loadStats();
    loadSamples();
    loadPrimers();
    loadReagents();
    loadTemplates();
    loadTasks();
    loadHistory();
});

function setupTabs() {
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', function() {
            const tab = this.dataset.tab;
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            this.classList.add('active');
            document.getElementById('tab-' + tab).classList.add('active');
        });
    });
}

function setupFileInputs() {
    document.getElementById('sample-file').addEventListener('change', function(e) {
        importFile('samples', e.target.files[0]);
        this.value = '';
    });
    
    document.getElementById('primer-file').addEventListener('change', function(e) {
        importFile('primers', e.target.files[0]);
        this.value = '';
    });
    
    document.getElementById('reagent-file').addEventListener('change', function(e) {
        importFile('reagents', e.target.files[0]);
        this.value = '';
    });
    
    document.getElementById('template-file').addEventListener('change', function(e) {
        importTemplate(e.target.files[0]);
        this.value = '';
    });
}

async function importFile(type, file) {
    const formData = new FormData();
    formData.append('file', file);
    
    try {
        const response = await fetch(`${API_BASE}/${type}/import`, {
            method: 'POST',
            body: formData
        });
        const data = await response.json();
        
        if (response.ok) {
            showToast(`导入成功: ${data.imported} 条记录`, 'success');
            loadStats();
            if (type === 'samples') loadSamples();
            if (type === 'primers') loadPrimers();
            if (type === 'reagents') loadReagents();
        } else {
            showToast('导入失败: ' + data.error, 'error');
        }
    } catch (e) {
        showToast('导入失败: ' + e.message, 'error');
    }
}

async function importTemplate(file) {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('name', file.name.replace('.csv', ''));
    
    try {
        const response = await fetch(`${API_BASE}/templates/import`, {
            method: 'POST',
            body: formData
        });
        const data = await response.json();
        
        if (response.ok) {
            showToast('模板导入成功', 'success');
            loadTemplates();
            loadStats();
        } else {
            showToast('导入失败: ' + data.error, 'error');
        }
    } catch (e) {
        showToast('导入失败: ' + e.message, 'error');
    }
}

async function loadStats() {
    try {
        const response = await fetch(`${API_BASE}/stats`);
        const data = await response.json();
        document.getElementById('stats-info').textContent = 
            `样本: ${data.samples} | 引物: ${data.primers} | 试剂: ${data.reagents} | 模板: ${data.templates} | 任务: ${data.tasks} | 已批准: ${data.approved_tasks}`;
    } catch (e) {
        console.error('加载统计失败', e);
    }
}

async function loadSamples() {
    try {
        const response = await fetch(`${API_BASE}/samples`);
        const data = await response.json();
        const listEl = document.getElementById('sample-list');
        
        if (data.length === 0) {
            listEl.innerHTML = '<p class="empty">暂无样本</p>';
            return;
        }
        
        listEl.innerHTML = data.map(s => `
            <div class="item-row">
                <div class="item-name">${s.name}</div>
                <div class="item-info">浓度: ${s.concentration} ${s.concentration_unit} | 体积: ${s.volume} ${s.volume_unit}</div>
            </div>
        `).join('');
    } catch (e) {
        console.error(e);
    }
}

async function loadPrimers() {
    try {
        const response = await fetch(`${API_BASE}/primers`);
        const data = await response.json();
        const listEl = document.getElementById('primer-list');
        
        if (data.length === 0) {
            listEl.innerHTML = '<p class="empty">暂无引物</p>';
            return;
        }
        
        listEl.innerHTML = data.map(p => `
            <div class="item-row">
                <div class="item-name">${p.name}</div>
                <div class="item-info">浓度: ${p.concentration} ${p.concentration_unit} | 体积: ${p.volume} ${p.volume_unit}</div>
            </div>
        `).join('');
    } catch (e) {
        console.error(e);
    }
}

async function loadReagents() {
    try {
        const response = await fetch(`${API_BASE}/reagents`);
        const data = await response.json();
        const listEl = document.getElementById('reagent-list');
        
        if (data.length === 0) {
            listEl.innerHTML = '<p class="empty">暂无试剂</p>';
            return;
        }
        
        listEl.innerHTML = data.map(r => `
            <div class="item-row">
                <div class="item-name">${r.name}</div>
                <div class="item-info">类型: ${r.type} | 库存: ${r.volume} ${r.volume_unit}</div>
            </div>
        `).join('');
    } catch (e) {
        console.error(e);
    }
}

async function loadTemplates() {
    try {
        const response = await fetch(`${API_BASE}/templates`);
        const data = await response.json();
        
        const listEl = document.getElementById('template-list');
        const selectEl = document.getElementById('plate-template-select');
        
        if (data.length === 0) {
            listEl.innerHTML = '<p class="empty">暂无模板</p>';
            selectEl.innerHTML = '<option value="">请选择模板</option>';
            return;
        }
        
        listEl.innerHTML = data.map(t => `
            <div class="item-row">
                <div class="item-name">${t.name}</div>
                <div class="item-info">${t.rows}行 × ${t.cols}列 | ${t.rows * t.cols} 孔</div>
            </div>
        `).join('');
        
        selectEl.innerHTML = '<option value="">请选择模板</option>' + 
            data.map(t => `<option value="${t.id}">${t.name} (${t.rows}×${t.cols})</option>`).join('');
    } catch (e) {
        console.error(e);
    }
}

async function renderPlateView() {
    const templateId = document.getElementById('plate-template-select').value;
    const plateEl = document.getElementById('plate-view');
    
    if (!templateId) {
        plateEl.innerHTML = '<p class="empty">请选择模板查看板位布局</p>';
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE}/templates/${templateId}`);
        const data = await response.json();
        
        const wells = data.wells;
        const cols = data.cols;
        const rows = data.rows;
        
        let html = '<div class="legend">';
        html += '<div class="legend-item"><div class="legend-color legend-sample"></div>样本孔</div>';
        html += '<div class="legend-item"><div class="legend-color legend-positive"></div>阳性对照</div>';
        html += '<div class="legend-item"><div class="legend-color legend-negative"></div>阴性对照</div>';
        html += '<div class="legend-item"><div class="legend-color legend-empty"></div>空孔</div>';
        html += '</div>';
        
        html += `<div class="well-grid" style="grid-template-columns: repeat(${cols + 1}, 1fr);">`;
        
        html += '<div class="well-cell" style="background:transparent;border:none;"></div>';
        for (let c = 1; c <= cols; c++) {
            html += `<div class="well-cell" style="background:#f0f0f0;border:none;font-weight:bold;">${c}</div>`;
        }
        
        for (let r = 1; r <= rows; r++) {
            html += `<div class="well-cell" style="background:#f0f0f0;border:none;font-weight:bold;">${String.fromCharCode(64 + r)}</div>`;
            for (let c = 1; c <= cols; c++) {
                const well = wells.find(w => w.well_row === r && w.well_col === c);
                if (well) {
                    let wellClass = 'well-sample';
                    let wellText = well.sample_name || '';
                    
                    if (well.well_type === 'positive_control') {
                        wellClass = 'well-positive';
                        wellText = 'PC';
                    } else if (well.well_type === 'negative_control') {
                        wellClass = 'well-negative';
                        wellText = 'NC';
                    } else if (well.well_type === 'empty') {
                        wellClass = 'well-empty';
                        wellText = '';
                    }
                    
                    if (wellText && wellText.length > 8) {
                        wellText = wellText.substring(0, 7) + '...';
                    }
                    
                    html += `<div class="well-cell ${wellClass}" title="${well.sample_name || well.well_type}">${wellText}</div>`;
                } else {
                    html += '<div class="well-cell well-empty"></div>';
                }
            }
        }
        
        html += '</div>';
        plateEl.innerHTML = html;
    } catch (e) {
        console.error(e);
        plateEl.innerHTML = '<p class="empty">加载失败</p>';
    }
}

async function loadTasks() {
    const status = document.getElementById('task-status-filter').value;
    let url = `${API_BASE}/tasks`;
    if (status) url += `?status=${status}`;
    
    try {
        const response = await fetch(url);
        const data = await response.json();
        const listEl = document.getElementById('task-list');
        
        if (data.length === 0) {
            listEl.innerHTML = '<p class="empty">暂无任务</p>';
            return;
        }
        
        const statusLabels = {
            'draft': '草稿',
            'pending_review': '待复核',
            'approved': '已批准',
            'rejected': '已驳回',
            'revoked': '已撤销'
        };
        
        listEl.innerHTML = data.map(t => `
            <div class="task-card status-${t.status}">
                <div onclick="showTaskDetail(${t.id})">
                    <h3>${t.name}</h3>
                    <div class="task-meta">
                        <span class="task-status status-${t.status}">${statusLabels[t.status] || t.status}</span>
                        <span>总体系: ${t.total_volume} ${t.volume_unit}</span>
                        <span>创建时间: ${t.created_at}</span>
                    </div>
                    ${t.deviation_note ? `<div style="margin-top:8px;color:#ffc107;font-size:13px;">📝 有偏差备注</div>` : ''}
                </div>
                <div class="task-card-actions">
                    <button class="btn-small" onclick="event.stopPropagation(); copyTask(${t.id})" title="复制为新草稿">📋 复制</button>
                    <button class="btn-small" onclick="event.stopPropagation(); exportTaskPlan(${t.id})" title="导出方案 JSON">📤 导出</button>
                </div>
            </div>
        `).join('');
    } catch (e) {
        console.error(e);
    }
}

async function showTaskDetail(taskId) {
    currentTaskId = taskId;
    
    try {
        const response = await fetch(`${API_BASE}/tasks/${taskId}`);
        const data = await response.json();
        
        const detailEl = document.getElementById('task-detail');
        const contentEl = document.getElementById('task-detail-content');
        
        const statusLabels = {
            'draft': '草稿',
            'pending_review': '待复核',
            'approved': '已批准',
            'rejected': '已驳回',
            'revoked': '已撤销'
        };
        
        let html = '';
        
        html += '<div class="well-detail-actions">';
        if (data.task.status === 'pending_review') {
            html += '<button class="btn-approve" onclick="approveTask()">✓ 批准</button>';
            html += '<button class="btn-reject" onclick="rejectTask()">✗ 驳回</button>';
            html += '<button class="btn-deviation" onclick="addDeviationNote()">📝 偏差备注</button>';
        }
        if (data.task.status === 'approved') {
            html += '<button class="btn-revoke" onclick="revokeTask()">↶ 撤销确认</button>';
        }
        if (data.task.status === 'draft' || data.task.status === 'rejected') {
            html += '<button onclick="generatePlan()">🔬 生成方案</button>';
        }
        html += '<button onclick="copyCurrentTask()">📋 复制任务</button>';
        html += '<button onclick="exportTaskPlan(currentTaskId)">📤 导出方案</button>';
        html += '<button onclick="exportReport()">📊 导出报告</button>';
        html += '</div>';
        
        html += '<div class="detail-section">';
        html += '<h4>基本信息</h4>';
        html += `<div class="info-row"><span class="info-label">任务名称</span><span class="info-value">${data.task.name}</span></div>`;
        html += `<div class="info-row"><span class="info-label">状态</span><span class="info-value">${statusLabels[data.task.status] || data.task.status}</span></div>`;
        html += `<div class="info-row"><span class="info-label">总体系</span><span class="info-value">${data.task.total_volume} ${data.task.volume_unit}</span></div>`;
        html += `<div class="info-row"><span class="info-label">创建时间</span><span class="info-value">${data.task.created_at}</span></div>`;
        html += '</div>';
        
        html += '<div class="detail-section">';
        html += '<h4>版本快照</h4>';
        html += '<div id="snapshot-section"><p style="color:#999;font-size:13px;">加载中...</p></div>';
        html += '</div>';
        
        if (data.task.deviation_note) {
            html += '<div class="detail-section">';
            html += '<h4>偏差备注</h4>';
            html += `<p style="color:#ffc107;font-size:14px;">${data.task.deviation_note}</p>`;
            html += '</div>';
        }
        
        if (data.task.rejected_reason) {
            html += '<div class="detail-section">';
            html += '<h4>驳回原因</h4>';
            html += `<p style="color:#dc3545;font-size:14px;">${data.task.rejected_reason}</p>`;
            html += '</div>';
        }
        
        if (data.wells && data.wells.length > 0) {
            html += '<div class="detail-section">';
            html += '<h4>孔位用量明细</h4>';
            
            const sampleWells = data.wells.filter(w => w.well_type === 'sample');
            const positiveWells = data.wells.filter(w => w.well_type === 'positive_control');
            const negativeWells = data.wells.filter(w => w.well_type === 'negative_control');
            
            html += `<p style="font-size:13px;color:#666;margin-bottom:10px;">样本孔: ${sampleWells.length} | 阳性对照: ${positiveWells.length} | 阴性对照: ${negativeWells.length}</p>`;
            
            html += '<div style="overflow-x:auto;">';
            html += '<table style="width:100%;font-size:12px;border-collapse:collapse;">';
            html += '<thead><tr style="background:#f8f9fa;">';
            html += '<th style="padding:8px;text-align:left;border-bottom:2px solid #ddd;">孔位</th>';
            html += '<th style="padding:8px;text-align:left;border-bottom:2px solid #ddd;">类型</th>';
            html += '<th style="padding:8px;text-align:left;border-bottom:2px solid #ddd;">样本</th>';
            html += '<th style="padding:8px;text-align:right;border-bottom:2px solid #ddd;">样本(µL)</th>';
            html += '<th style="padding:8px;text-align:right;border-bottom:2px solid #ddd;">引物(µL)</th>';
            html += '<th style="padding:8px;text-align:right;border-bottom:2px solid #ddd;">MM(µL)</th>';
            html += '<th style="padding:8px;text-align:right;border-bottom:2px solid #ddd;">水(µL)</th>';
            html += '<th style="padding:8px;text-align:right;border-bottom:2px solid #ddd;">总计(µL)</th>';
            html += '</tr></thead>';
            html += '<tbody>';
            
            const typeLabels = {
                'sample': '样本',
                'positive_control': '阳性对照',
                'negative_control': '阴性对照',
                'empty': '空孔'
            };
            
            data.wells.forEach(w => {
                const wellName = `${String.fromCharCode(64 + w.well_row)}${w.well_col}`;
                html += '<tr style="border-bottom:1px solid #eee;">';
                html += `<td style="padding:6px;font-weight:bold;">${wellName}</td>`;
                html += `<td style="padding:6px;">${typeLabels[w.well_type] || w.well_type}</td>`;
                html += `<td style="padding:6px;font-size:11px;">${w.sample_name || '-'}</td>`;
                html += `<td style="padding:6px;text-align:right;">${w.sample_volume ? w.sample_volume.toFixed(2) : '-'}</td>`;
                html += `<td style="padding:6px;text-align:right;">${w.primer_volume ? w.primer_volume.toFixed(2) : '-'}</td>`;
                html += `<td style="padding:6px;text-align:right;">${w.master_mix_volume ? w.master_mix_volume.toFixed(2) : '-'}</td>`;
                html += `<td style="padding:6px;text-align:right;">${w.water_volume ? w.water_volume.toFixed(2) : '-'}</td>`;
                html += `<td style="padding:6px;text-align:right;font-weight:bold;">${w.total_volume ? w.total_volume.toFixed(2) : '-'}</td>`;
                html += '</tr>';
            });
            
            html += '</tbody></table></div>';
            html += '</div>';
            
            if (data.reagent_usage && data.reagent_usage.length > 0) {
                html += '<div class="detail-section">';
                html += '<h4>试剂使用 & 库存扣减</h4>';
                data.reagent_usage.forEach(r => {
                    html += `<div class="info-row">`;
                    html += `<span class="info-label">${r.reagent_name} (${r.source})</span>`;
                    html += `<span class="info-value">${r.used_volume.toFixed(2)} ${r.used_volume_unit}</span>`;
                    html += '</div>';
                });
                html += '</div>';
            }
            
            if (data.primer_usage && data.primer_usage.length > 0) {
                html += '<div class="detail-section">';
                html += '<h4>引物使用</h4>';
                data.primer_usage.forEach(p => {
                    html += `<div class="info-row">`;
                    html += `<span class="info-label">${p.primer_name}</span>`;
                    html += `<span class="info-value">${p.used_volume.toFixed(2)} ${p.used_volume_unit}</span>`;
                    html += '</div>';
                });
                html += '</div>';
            }
        } else {
            html += '<div class="detail-section">';
            html += '<p style="color:#999;text-align:center;padding:30px;">尚未生成方案，请点击"生成方案"按钮</p>';
            html += '</div>';
        }
        
        contentEl.innerHTML = html;
        detailEl.classList.remove('hidden');
        setTimeout(() => detailEl.classList.add('active'), 10);
        
        currentTaskStatus = data.task.status;
        loadTaskSnapshots(taskId, data.task.status);
        
    } catch (e) {
        showToast('加载任务详情失败', 'error');
        console.error(e);
    }
}

function closeTaskDetail() {
    const detailEl = document.getElementById('task-detail');
    detailEl.classList.remove('active');
    setTimeout(() => {
        detailEl.classList.add('hidden');
        currentTaskId = null;
    }, 300);
}

async function loadTaskSnapshots(taskId, taskStatus) {
    try {
        const response = await fetch(`${API_BASE}/tasks/${taskId}/snapshots`);
        if (!response.ok) {
            throw new Error('加载快照列表失败');
        }
        const snapshots = await response.json();
        currentSnapshots = snapshots;
        
        renderSnapshotSection(snapshots, taskStatus);
    } catch (e) {
        const sectionEl = document.getElementById('snapshot-section');
        if (sectionEl) {
            sectionEl.innerHTML = '<p style="color:#dc3545;font-size:13px;">加载快照列表失败</p>';
        }
        console.error(e);
    }
}

function renderSnapshotSection(snapshots, taskStatus) {
    const sectionEl = document.getElementById('snapshot-section');
    if (!sectionEl) return;
    
    if (!snapshots || snapshots.length === 0) {
        sectionEl.innerHTML = `
            <p style="color:#999;font-size:13px;">暂无版本快照</p>
            <button onclick="createManualSnapshot()" style="margin-top:8px;font-size:12px;padding:4px 10px;">📷 手动创建快照</button>
        `;
        return;
    }
    
    const canRollback = taskStatus !== 'approved' && taskStatus !== 'revoked';
    const rollbackHint = !canRollback ? 
        `<p style="font-size:11px;color:#999;margin-top:4px;">⚠️ 已${taskStatus === 'approved' ? '批准' : '撤销'}的任务不能回滚</p>` : '';
    
    const options = snapshots.map(s => 
        `<option value="${s.version}">v${s.version} - ${snapTypeLabels[s.snapshot_type] || s.snapshot_type} (${snapStatusLabels[s.status] || s.status}) - ${s.created_at}</option>`
    ).join('');
    
    let html = '';
    html += `<p style="font-size:13px;color:#666;margin-bottom:8px;">共 ${snapshots.length} 个历史版本</p>`;
    
    html += '<div style="display:flex;gap:10px;align-items:flex-start;margin-bottom:10px;flex-wrap:wrap;">';
    html += '<div style="flex:1;min-width:180px;">';
    html += '<label style="font-size:12px;color:#666;">版本 A</label>';
    html += `<select id="compare-version-a" onchange="onVersionSelectChange()" style="width:100%;padding:6px;font-size:12px;">${options}</select>`;
    html += '</div>';
    html += '<div style="display:flex;align-items:flex-end;padding-bottom:6px;"><span style="font-size:16px;">↔</span></div>';
    html += '<div style="flex:1;min-width:180px;">';
    html += '<label style="font-size:12px;color:#666;">版本 B</label>';
    html += `<select id="compare-version-b" onchange="onVersionSelectChange()" style="width:100%;padding:6px;font-size:12px;">${options}</select>`;
    html += '</div>';
    html += '</div>';
    
    html += '<div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px;">';
    html += '<button onclick="compareCurrentVersions()" style="font-size:12px;padding:5px 12px;">🔍 对比差异</button>';
    if (canRollback) {
        html += '<button onclick="rollbackFromSelect()" class="btn-reject" style="font-size:12px;padding:5px 12px;">⏪ 回滚到版本 A</button>';
    }
    html += '<button onclick="createManualSnapshot()" style="font-size:12px;padding:5px 12px;">📷 保存快照</button>';
    html += '</div>';
    
    html += rollbackHint;
    
    html += '<div id="compare-result" style="margin-top:10px;"></div>';
    
    sectionEl.innerHTML = html;
    
    if (snapshots.length >= 2) {
        document.getElementById('compare-version-a').value = snapshots[1].version;
        document.getElementById('compare-version-b').value = snapshots[0].version;
    }
}

function onVersionSelectChange() {
    const resultEl = document.getElementById('compare-result');
    if (resultEl) {
        resultEl.innerHTML = '';
    }
}

async function compareCurrentVersions() {
    const selA = document.getElementById('compare-version-a');
    const selB = document.getElementById('compare-version-b');
    if (!selA || !selB) return;
    
    const versionA = parseInt(selA.value);
    const versionB = parseInt(selB.value);
    
    if (versionA === versionB) {
        showToast('请选择两个不同的版本进行对比', 'warning');
        return;
    }
    
    const resultEl = document.getElementById('compare-result');
    if (resultEl) {
        resultEl.innerHTML = '<p style="font-size:13px;color:#999;">对比中...</p>';
    }
    
    try {
        const response = await fetch(
            `${API_BASE}/tasks/${currentTaskId}/snapshots/compare?version_a=${versionA}&version_b=${versionB}`
        );
        if (!response.ok) {
            throw new Error('对比失败');
        }
        const diff = await response.json();
        renderComparisonResult(diff);
    } catch (e) {
        if (resultEl) {
            resultEl.innerHTML = `<p style="color:#dc3545;font-size:13px;">对比失败: ${e.message}</p>`;
        }
        console.error(e);
    }
}

function renderComparisonResult(diff) {
    const resultEl = document.getElementById('compare-result');
    if (!resultEl) return;
    
    const summary = diff.summary;
    let html = '';
    
    html += '<div style="background:#f0f7ff;padding:10px;border-radius:6px;border-left:3px solid #007bff;margin-bottom:12px;">';
    html += `<strong style="font-size:13px;">版本对比 v${diff.version_a} ↔ v${diff.version_b}</strong>`;
    html += '<div style="font-size:12px;color:#555;margin-top:4px;">';
    html += `孔位: +${summary.wells_added} / -${summary.wells_removed} / ~${summary.wells_modified} &nbsp;|&nbsp; `;
    html += `试剂: +${summary.reagents_added} / -${summary.reagents_removed} / ~${summary.reagents_modified} &nbsp;|&nbsp; `;
    html += `引物: +${summary.primers_added} / -${summary.primers_removed} / ~${summary.primers_modified}`;
    html += '</div></div>';
    
    const taskDiffs = diff.task_differences || {};
    const templateDiffs = diff.template_differences || {};
    if (Object.keys(taskDiffs).length > 0 || Object.keys(templateDiffs).length > 0) {
        html += '<div style="margin-bottom:10px;">';
        html += '<h5 style="font-size:13px;margin:0 0 6px 0;color:#333;">📋 基本信息差异</h5>';
        html += '<table style="width:100%;font-size:12px;border-collapse:collapse;">';
        html += '<thead><tr style="background:#f8f9fa;">';
        html += '<th style="padding:6px;text-align:left;border-bottom:1px solid #ddd;">项目</th>';
        html += `<th style="padding:6px;text-align:left;border-bottom:1px solid #ddd;">v${diff.version_a}</th>`;
        html += `<th style="padding:6px;text-align:left;border-bottom:1px solid #ddd;">v${diff.version_b}</th>`;
        html += '</tr></thead><tbody>';
        
        for (const [key, val] of Object.entries(taskDiffs)) {
            const labelMap = {
                'status': '状态',
                'total_volume': '总体积',
                'volume_unit': '体积单位',
                'deviation_note': '偏差备注'
            };
            const label = labelMap[key] || key;
            const oldVal = val.old !== null && val.old !== undefined ? val.old : '-';
            const newVal = val.new !== null && val.new !== undefined ? val.new : '-';
            const statusLabel = (v) => v && snapStatusLabels[v] ? snapStatusLabels[v] : v;
            html += '<tr>';
            html += `<td style="padding:5px;border-bottom:1px solid #eee;font-weight:500;">${label}</td>`;
            html += `<td style="padding:5px;border-bottom:1px solid #eee;color:#dc3545;">${statusLabel(oldVal)}</td>`;
            html += `<td style="padding:5px;border-bottom:1px solid #eee;color:#28a745;">${statusLabel(newVal)}</td>`;
            html += '</tr>';
        }
        
        for (const [key, val] of Object.entries(templateDiffs)) {
            const labelMap = { 'template_name': '模板名称' };
            const label = labelMap[key] || key;
            html += '<tr>';
            html += `<td style="padding:5px;border-bottom:1px solid #eee;font-weight:500;">${label}</td>`;
            html += `<td style="padding:5px;border-bottom:1px solid #eee;color:#dc3545;">${val.old || '-'}</td>`;
            html += `<td style="padding:5px;border-bottom:1px solid #eee;color:#28a745;">${val.new || '-'}</td>`;
            html += '</tr>';
        }
        
        html += '</tbody></table>';
        html += '</div>';
    }
    
    const wellDiffObj = diff.well_differences || {};
    const wellsAdded = [];
    const wellsRemoved = [];
    const wellsModified = [];
    for (const [name, d] of Object.entries(wellDiffObj)) {
        if (d.change === 'added') wellsAdded.push({ name, ...d });
        else if (d.change === 'removed') wellsRemoved.push({ name, ...d });
        else if (d.change === 'modified') wellsModified.push({ name, ...d });
    }
    
    function renderWellTable(wells, showVersion) {
        let h = '<div style="overflow-x:auto;"><table style="width:100%;font-size:11px;border-collapse:collapse;">';
        h += '<thead><tr style="background:#f8f9fa;">';
        h += '<th style="padding:5px;text-align:left;border-bottom:1px solid #ddd;">孔位</th>';
        h += '<th style="padding:5px;text-align:left;border-bottom:1px solid #ddd;">类型</th>';
        h += '<th style="padding:5px;text-align:left;border-bottom:1px solid #ddd;">样本</th>';
        h += '<th style="padding:5px;text-align:right;border-bottom:1px solid #ddd;">样本(µL)</th>';
        h += '<th style="padding:5px;text-align:right;border-bottom:1px solid #ddd;">引物(µL)</th>';
        h += '<th style="padding:5px;text-align:right;border-bottom:1px solid #ddd;">MM(µL)</th>';
        h += '<th style="padding:5px;text-align:right;border-bottom:1px solid #ddd;">水(µL)</th>';
        h += '<th style="padding:5px;text-align:right;border-bottom:1px solid #ddd;">总计(µL)</th>';
        h += '</tr></thead><tbody>';
        const typeLabels = { 'sample': '样本', 'positive_control': '阳性对照', 'negative_control': '阴性对照', 'empty': '空孔' };
        wells.forEach(w => {
            const well = w.well || {};
            const wellName = w.name || `${String.fromCharCode(64 + well.well_row)}${well.well_col}`;
            const type = typeLabels[well.well_type] || well.well_type || '-';
            h += '<tr style="border-bottom:1px solid #eee;">';
            h += `<td style="padding:4px;font-weight:bold;">${wellName}</td>`;
            h += `<td style="padding:4px;">${type}</td>`;
            h += `<td style="padding:4px;">${well.sample_name || '-'}</td>`;
            h += `<td style="padding:4px;text-align:right;">${well.sample_volume !== undefined ? well.sample_volume : '-'}</td>`;
            h += `<td style="padding:4px;text-align:right;">${well.primer_volume !== undefined ? well.primer_volume : '-'}</td>`;
            h += `<td style="padding:4px;text-align:right;">${well.master_mix_volume !== undefined ? well.master_mix_volume : '-'}</td>`;
            h += `<td style="padding:4px;text-align:right;">${well.water_volume !== undefined ? well.water_volume : '-'}</td>`;
            h += `<td style="padding:4px;text-align:right;">${well.total_volume !== undefined ? well.total_volume : '-'}</td>`;
            h += '</tr>';
        });
        h += '</tbody></table></div>';
        return h;
    }
    
    if (wellsAdded.length > 0) {
        html += '<div style="margin-bottom:12px;">';
        html += `<h5 style="font-size:13px;margin:0 0 6px 0;color:#28a745;">➕ 新增孔位 (${wellsAdded.length})</h5>`;
        html += renderWellTable(wellsAdded);
        html += '</div>';
    }
    if (wellsRemoved.length > 0) {
        html += '<div style="margin-bottom:12px;">';
        html += `<h5 style="font-size:13px;margin:0 0 6px 0;color:#dc3545;">➖ 删除孔位 (${wellsRemoved.length})</h5>`;
        html += renderWellTable(wellsRemoved);
        html += '</div>';
    }
    if (wellsModified.length > 0) {
        html += '<div style="margin-bottom:12px;">';
        html += `<h5 style="font-size:13px;margin:0 0 6px 0;color:#ffc107;">✏️ 修改孔位 (${wellsModified.length})</h5>`;
        html += '<div style="overflow-x:auto;"><table style="width:100%;font-size:11px;border-collapse:collapse;">';
        html += '<thead><tr style="background:#f8f9fa;">';
        html += '<th style="padding:5px;text-align:left;border-bottom:1px solid #ddd;">孔位</th>';
        html += '<th style="padding:5px;text-align:left;border-bottom:1px solid #ddd;">字段</th>';
        html += `<th style="padding:5px;text-align:right;border-bottom:1px solid #ddd;">v${diff.version_a}</th>`;
        html += `<th style="padding:5px;text-align:right;border-bottom:1px solid #ddd;">v${diff.version_b}</th>`;
        html += '</tr></thead><tbody>';
        const fieldLabels = {
            'well_type': '类型', 'sample_name': '样本', 'sample_volume': '样本(µL)',
            'primer_name': '引物', 'primer_volume': '引物(µL)', 'master_mix_volume': 'MM(µL)',
            'water_volume': '水(µL)', 'total_volume': '总计(µL)'
        };
        const typeLabels = { 'sample': '样本', 'positive_control': '阳性对照', 'negative_control': '阴性对照', 'empty': '空孔' };
        wellsModified.forEach(w => {
            const fields = w.fields || {};
            let first = true;
            for (const [fkey, fval] of Object.entries(fields)) {
                const label = fieldLabels[fkey] || fkey;
                const oldV = fval.old !== null && fval.old !== undefined ? fval.old : '-';
                const newV = fval.new !== null && fval.new !== undefined ? fval.new : '-';
                const formatV = (v, k) => {
                    if (k === 'well_type') return typeLabels[v] || v;
                    return v;
                };
                html += '<tr style="border-bottom:1px solid #eee;">';
                if (first) {
                    html += `<td style="padding:4px;font-weight:bold;" rowspan="${Object.keys(fields).length}">${w.name}</td>`;
                    first = false;
                }
                html += `<td style="padding:4px;">${label}</td>`;
                html += `<td style="padding:4px;text-align:right;color:#dc3545;">${formatV(oldV, fkey)}</td>`;
                html += `<td style="padding:4px;text-align:right;color:#28a745;">${formatV(newV, fkey)}</td>`;
                html += '</tr>';
            }
        });
        html += '</tbody></table></div>';
        html += '</div>';
    }
    
    const reagentDiffObj = diff.reagent_differences || {};
    const reagentsAdded = [];
    const reagentsRemoved = [];
    const reagentsModified = [];
    for (const [name, d] of Object.entries(reagentDiffObj)) {
        if (d.change === 'added') reagentsAdded.push({ name, ...d });
        else if (d.change === 'removed') reagentsRemoved.push({ name, ...d });
        else if (d.change === 'modified') reagentsModified.push({ name, ...d });
    }
    
    function renderReagentTable(reagents, showVersion) {
        let h = '<table style="width:100%;font-size:11px;border-collapse:collapse;">';
        h += '<thead><tr style="background:#f8f9fa;">';
        h += '<th style="padding:5px;text-align:left;border-bottom:1px solid #ddd;">试剂</th>';
        h += '<th style="padding:5px;text-align:left;border-bottom:1px solid #ddd;">来源</th>';
        h += '<th style="padding:5px;text-align:right;border-bottom:1px solid #ddd;">用量(µL)</th>';
        h += '</tr></thead><tbody>';
        reagents.forEach(r => {
            const data = r.data || {};
            h += '<tr style="border-bottom:1px solid #eee;">';
            h += `<td style="padding:4px;font-weight:500;">${data.reagent_name || r.name}</td>`;
            h += `<td style="padding:4px;">${data.source || '-'}</td>`;
            h += `<td style="padding:4px;text-align:right;">${data.used_volume !== undefined ? data.used_volume : '-'} ${data.used_volume_unit || ''}</td>`;
            h += '</tr>';
        });
        h += '</tbody></table>';
        return h;
    }
    
    if (reagentsAdded.length > 0) {
        html += '<div style="margin-bottom:10px;">';
        html += `<h5 style="font-size:13px;margin:0 0 6px 0;color:#28a745;">💧 新增试剂 (${reagentsAdded.length})</h5>`;
        html += renderReagentTable(reagentsAdded);
        html += '</div>';
    }
    if (reagentsRemoved.length > 0) {
        html += '<div style="margin-bottom:10px;">';
        html += `<h5 style="font-size:13px;margin:0 0 6px 0;color:#dc3545;">💧 删除试剂 (${reagentsRemoved.length})</h5>`;
        html += renderReagentTable(reagentsRemoved);
        html += '</div>';
    }
    if (reagentsModified.length > 0) {
        html += '<div style="margin-bottom:10px;">';
        html += `<h5 style="font-size:13px;margin:0 0 6px 0;color:#ffc107;">💧 试剂用量变化 (${reagentsModified.length})</h5>`;
        html += '<table style="width:100%;font-size:11px;border-collapse:collapse;">';
        html += '<thead><tr style="background:#f8f9fa;">';
        html += '<th style="padding:5px;text-align:left;">试剂</th>';
        html += '<th style="padding:5px;text-align:left;">字段</th>';
        html += `<th style="padding:5px;text-align:right;">v${diff.version_a}</th>`;
        html += `<th style="padding:5px;text-align:right;">v${diff.version_b}</th>`;
        html += '</tr></thead><tbody>';
        const fieldLabels = { 'used_volume': '用量(µL)', 'used_volume_unit': '单位', 'source': '来源' };
        reagentsModified.forEach(r => {
            const fields = r.fields || {};
            let first = true;
            for (const [fkey, fval] of Object.entries(fields)) {
                const label = fieldLabels[fkey] || fkey;
                html += '<tr style="border-bottom:1px solid #eee;">';
                if (first) {
                    html += `<td style="padding:4px;font-weight:500;" rowspan="${Object.keys(fields).length}">${r.name}</td>`;
                    first = false;
                }
                html += `<td style="padding:4px;">${label}</td>`;
                html += `<td style="padding:4px;text-align:right;color:#dc3545;">${fval.old !== null && fval.old !== undefined ? fval.old : '-'}</td>`;
                html += `<td style="padding:4px;text-align:right;color:#28a745;">${fval.new !== null && fval.new !== undefined ? fval.new : '-'}</td>`;
                html += '</tr>';
            }
        });
        html += '</tbody></table>';
        html += '</div>';
    }
    
    const primerDiffObj = diff.primer_differences || {};
    const primersAdded = [];
    const primersRemoved = [];
    const primersModified = [];
    for (const [name, d] of Object.entries(primerDiffObj)) {
        if (d.change === 'added') primersAdded.push({ name, ...d });
        else if (d.change === 'removed') primersRemoved.push({ name, ...d });
        else if (d.change === 'modified') primersModified.push({ name, ...d });
    }
    
    function renderPrimerTable(primers) {
        let h = '<table style="width:100%;font-size:11px;border-collapse:collapse;">';
        h += '<thead><tr style="background:#f8f9fa;">';
        h += '<th style="padding:5px;text-align:left;border-bottom:1px solid #ddd;">引物</th>';
        h += '<th style="padding:5px;text-align:left;border-bottom:1px solid #ddd;">来源</th>';
        h += '<th style="padding:5px;text-align:right;border-bottom:1px solid #ddd;">用量(µL)</th>';
        h += '</tr></thead><tbody>';
        primers.forEach(p => {
            const data = p.data || {};
            h += '<tr style="border-bottom:1px solid #eee;">';
            h += `<td style="padding:4px;font-weight:500;">${data.primer_name || p.name}</td>`;
            h += `<td style="padding:4px;">${data.source || '-'}</td>`;
            h += `<td style="padding:4px;text-align:right;">${data.used_volume !== undefined ? data.used_volume : '-'} ${data.used_volume_unit || ''}</td>`;
            h += '</tr>';
        });
        h += '</tbody></table>';
        return h;
    }
    
    if (primersAdded.length > 0) {
        html += '<div style="margin-bottom:10px;">';
        html += `<h5 style="font-size:13px;margin:0 0 6px 0;color:#28a745;">🧪 新增引物 (${primersAdded.length})</h5>`;
        html += renderPrimerTable(primersAdded);
        html += '</div>';
    }
    if (primersRemoved.length > 0) {
        html += '<div style="margin-bottom:10px;">';
        html += `<h5 style="font-size:13px;margin:0 0 6px 0;color:#dc3545;">🧪 删除引物 (${primersRemoved.length})</h5>`;
        html += renderPrimerTable(primersRemoved);
        html += '</div>';
    }
    if (primersModified.length > 0) {
        html += '<div style="margin-bottom:10px;">';
        html += `<h5 style="font-size:13px;margin:0 0 6px 0;color:#ffc107;">🧪 引物用量变化 (${primersModified.length})</h5>`;
        html += '<table style="width:100%;font-size:11px;border-collapse:collapse;">';
        html += '<thead><tr style="background:#f8f9fa;">';
        html += '<th style="padding:5px;text-align:left;">引物</th>';
        html += '<th style="padding:5px;text-align:left;">字段</th>';
        html += `<th style="padding:5px;text-align:right;">v${diff.version_a}</th>`;
        html += `<th style="padding:5px;text-align:right;">v${diff.version_b}</th>`;
        html += '</tr></thead><tbody>';
        const fieldLabels = { 'used_volume': '用量(µL)', 'used_volume_unit': '单位', 'source': '来源' };
        primersModified.forEach(p => {
            const fields = p.fields || {};
            let first = true;
            for (const [fkey, fval] of Object.entries(fields)) {
                const label = fieldLabels[fkey] || fkey;
                html += '<tr style="border-bottom:1px solid #eee;">';
                if (first) {
                    html += `<td style="padding:4px;font-weight:500;" rowspan="${Object.keys(fields).length}">${p.name}</td>`;
                    first = false;
                }
                html += `<td style="padding:4px;">${label}</td>`;
                html += `<td style="padding:4px;text-align:right;color:#dc3545;">${fval.old !== null && fval.old !== undefined ? fval.old : '-'}</td>`;
                html += `<td style="padding:4px;text-align:right;color:#28a745;">${fval.new !== null && fval.new !== undefined ? fval.new : '-'}</td>`;
                html += '</tr>';
            }
        });
        html += '</tbody></table>';
        html += '</div>';
    }
    
    if (summary.wells_added === 0 && summary.wells_removed === 0 && summary.wells_modified === 0 &&
        summary.reagents_added === 0 && summary.reagents_removed === 0 && summary.reagents_modified === 0 &&
        summary.primers_added === 0 && summary.primers_removed === 0 && summary.primers_modified === 0 &&
        Object.keys(taskDiffs).length === 0 && Object.keys(templateDiffs).length === 0) {
        html += '<p style="color:#28a745;font-size:13px;text-align:center;padding:15px;background:#f0fff4;border-radius:6px;">✅ 两个版本完全相同，无差异</p>';
    }
    
    resultEl.innerHTML = html;
}

async function rollbackFromSelect() {
    const selA = document.getElementById('compare-version-a');
    if (!selA) return;
    
    const version = parseInt(selA.value);
    if (!confirm(`确定要回滚到版本 v${version} 吗？\n回滚后当前状态会保存为新快照，不会丢失。`)) {
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE}/tasks/${currentTaskId}/snapshots/rollback`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ version, operator: 'user' })
        });
        
        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.error || '回滚失败');
        }
        
        const result = await response.json();
        showToast(`已回滚到版本 v${version}`, 'success');
        
        showTaskDetail(currentTaskId);
        loadTasks();
    } catch (e) {
        showToast(`回滚失败: ${e.message}`, 'error');
        console.error(e);
    }
}

async function createManualSnapshot() {
    const note = prompt('请输入快照备注（可选）:', '');
    if (note === null) return;
    
    try {
        const response = await fetch(`${API_BASE}/tasks/${currentTaskId}/snapshots`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ note: note || '' })
        });
        
        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.error || '创建快照失败');
        }
        
        const result = await response.json();
        showToast(`已创建快照 v${result.version}`, 'success');
        
        loadTaskSnapshots(currentTaskId, currentTaskStatus ? currentTaskStatus : 'draft');
    } catch (e) {
        showToast(`创建快照失败: ${e.message}`, 'error');
        console.error(e);
    }
}

function showCreateTaskModal() {
    fetch(`${API_BASE}/templates`)
        .then(r => r.json())
        .then(templates => {
            const modalBody = document.getElementById('modal-body');
            modalBody.innerHTML = `
                <h3>新建任务</h3>
                <div class="form-group">
                    <label>任务名称</label>
                    <input type="text" id="new-task-name" placeholder="请输入任务名称">
                </div>
                <div class="form-group">
                    <label>选择板位模板</label>
                    <select id="new-task-template">
                        <option value="">请选择模板</option>
                        ${templates.map(t => `<option value="${t.id}">${t.name} (${t.rows}×${t.cols})</option>`).join('')}
                    </select>
                </div>
                <div class="form-group">
                    <label>总体系 (µL)</label>
                    <input type="number" id="new-task-volume" value="20" step="0.5">
                </div>
                <div class="form-actions">
                    <button class="btn-cancel" onclick="closeModal()">取消</button>
                    <button class="btn-submit" onclick="createTask()">创建</button>
                </div>
            `;
            document.getElementById('modal').classList.remove('hidden');
        });
}

async function createTask() {
    const name = document.getElementById('new-task-name').value;
    const templateId = document.getElementById('new-task-template').value;
    const volume = parseFloat(document.getElementById('new-task-volume').value);
    
    if (!name || !templateId || !volume) {
        showToast('请填写完整信息', 'error');
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE}/tasks`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                name,
                template_id: parseInt(templateId),
                total_volume: volume,
                volume_unit: 'ul'
            })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            showToast('任务创建成功', 'success');
            closeModal();
            loadTasks();
            loadStats();
        } else {
            showToast('创建失败: ' + data.error, 'error');
        }
    } catch (e) {
        showToast('创建失败: ' + e.message, 'error');
    }
}

async function generatePlan() {
    if (!currentTaskId) return;
    
    try {
        const response = await fetch(`${API_BASE}/tasks/${currentTaskId}/generate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({})
        });
        
        const data = await response.json();
        
        if (response.ok) {
            if (data.below_min_pipette) {
                showToast('方案已生成，注意：存在低于最小移液体积的孔', 'warning');
            } else {
                showToast('方案生成成功', 'success');
            }
            showTaskDetail(currentTaskId);
            loadTasks();
            loadStats();
        } else {
            showToast('生成失败: ' + data.error, 'error');
        }
    } catch (e) {
        showToast('生成失败: ' + e.message, 'error');
    }
}

async function approveTask() {
    if (!currentTaskId) return;
    
    const ignoreConfirm = confirm('确认批准该任务？批准后将扣减库存。');
    if (!ignoreConfirm) return;
    
    try {
        const response = await fetch(`${API_BASE}/tasks/${currentTaskId}/approve`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ignore_min_pipette: false })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            showToast('任务已批准，库存已扣减', 'success');
            showTaskDetail(currentTaskId);
            loadTasks();
            loadStats();
            loadSamples();
            loadReagents();
            loadPrimers();
            loadHistory();
        } else {
            if (data.error && data.error.indexOf('低于最小移液体积') > -1) {
                const forceApprove = confirm(data.error + '\n\n是否添加偏差备注后强制批准？');
                if (forceApprove) {
                    const note = prompt('请输入偏差备注说明：');
                    if (note) {
                        await addDeviationNoteWithText(note);
                        const response2 = await fetch(`${API_BASE}/tasks/${currentTaskId}/approve`, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ ignore_min_pipette: true })
                        });
                        const data2 = await response2.json();
                        if (response2.ok) {
                            showToast('任务已批准（带偏差）', 'success');
                            showTaskDetail(currentTaskId);
                            loadTasks();
                            loadStats();
                            loadSamples();
                            loadReagents();
                            loadPrimers();
                            loadHistory();
                        } else {
                            showToast('批准失败: ' + data2.error, 'error');
                        }
                    }
                    return;
                }
            }
            showToast('批准失败: ' + data.error, 'error');
        }
    } catch (e) {
        showToast('批准失败: ' + e.message, 'error');
    }
}

async function addDeviationNoteWithText(note) {
    try {
        const response = await fetch(`${API_BASE}/tasks/${currentTaskId}/deviation`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ note })
        });
        return response.ok;
    } catch (e) {
        return false;
    }
}

function addDeviationNote() {
    const note = prompt('请输入偏差备注：');
    if (!note) return;
    
    fetch(`${API_BASE}/tasks/${currentTaskId}/deviation`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ note })
    })
    .then(r => r.json())
    .then(data => {
        if (data.success) {
            showToast('偏差备注已添加', 'success');
            showTaskDetail(currentTaskId);
            loadTasks();
            loadHistory();
        } else {
            showToast('添加失败: ' + data.error, 'error');
        }
    })
    .catch(e => showToast('添加失败: ' + e.message, 'error'));
}

function rejectTask() {
    const reason = prompt('请输入驳回原因：');
    if (!reason) return;
    
    fetch(`${API_BASE}/tasks/${currentTaskId}/reject`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason })
    })
    .then(r => r.json())
    .then(data => {
        if (data.success) {
            showToast('任务已驳回', 'success');
            showTaskDetail(currentTaskId);
            loadTasks();
            loadHistory();
        } else {
            showToast('驳回失败: ' + data.error, 'error');
        }
    })
    .catch(e => showToast('驳回失败: ' + e.message, 'error'));
}

async function revokeTask() {
    if (!confirm('确认撤销批准？撤销后库存将退回。')) return;
    
    try {
        const response = await fetch(`${API_BASE}/tasks/${currentTaskId}/revoke`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({})
        });
        
        const data = await response.json();
        
        if (response.ok) {
            showToast('已撤销，库存已退回', 'success');
            showTaskDetail(currentTaskId);
            loadTasks();
            loadStats();
            loadSamples();
            loadReagents();
            loadPrimers();
            loadHistory();
        } else {
            showToast('撤销失败: ' + data.error, 'error');
        }
    } catch (e) {
        showToast('撤销失败: ' + e.message, 'error');
    }
}

function exportReport() {
    if (!currentTaskId) return;
    
    const modalBody = document.getElementById('modal-body');
    modalBody.innerHTML = `
        <h3>导出报告</h3>
        <p>选择导出格式：</p>
        <div class="form-actions">
            <button class="btn-cancel" onclick="closeModal()">取消</button>
            <button class="btn-submit" onclick="downloadReportCsv()">CSV 格式</button>
            <button class="btn-submit" onclick="downloadReportJson()">JSON 格式</button>
        </div>
    `;
    document.getElementById('modal').classList.remove('hidden');
}

function downloadReportCsv() {
    window.open(`${API_BASE}/reports/task/${currentTaskId}/csv`);
    closeModal();
}

function downloadReportJson() {
    window.open(`${API_BASE}/reports/task/${currentTaskId}/json`);
    closeModal();
}

async function loadHistory() {
    try {
        const response = await fetch(`${API_BASE}/history?limit=50`);
        const data = await response.json();
        
        const listEl = document.getElementById('history-list');
        
        if (data.length === 0) {
            listEl.innerHTML = '<p class="empty">暂无历史记录</p>';
            return;
        }
        
        const typeLabels = {
            'create': '创建',
            'generate': '生成方案',
            'approve': '批准',
            'reject': '驳回',
            'revoke': '撤销',
            'deviation': '偏差备注'
        };
        
        listEl.innerHTML = data.map(h => `
            <div class="history-item">
                <div class="history-time">${h.created_at}</div>
                <div class="history-action">${typeLabels[h.action] || h.action}${h.task_id ? ` - 任务 #${h.task_id}` : ''}</div>
                <div class="history-detail">${h.detail}</div>
            </div>
        `).join('');
    } catch (e) {
        console.error(e);
    }
}

function exportHistoryJson() {
    window.open(`${API_BASE}/history/export/json`);
}

function exportHistoryCsv() {
    window.open(`${API_BASE}/history/export/csv`);
}

async function quickSetup() {
    try {
        showToast('正在导入样例数据...', 'success');
        
        const [samples, primers, reagents] = await Promise.all([
            fetch('/data/samples/sample_samples.csv').then(r => r.text()),
            fetch('/data/primers/sample_primers.csv').then(r => r.text()),
            fetch('/data/reagents/sample_reagents.csv').then(r => r.text())
        ]);
        
        let formData = new FormData();
        formData.append('file', new File([samples], 'samples.csv'));
        await fetch(`${API_BASE}/samples/import`, { method: 'POST', body: formData });
        
        formData = new FormData();
        formData.append('file', new File([primers], 'primers.csv'));
        await fetch(`${API_BASE}/primers/import`, { method: 'POST', body: formData });
        
        formData = new FormData();
        formData.append('file', new File([reagents], 'reagents.csv'));
        await fetch(`${API_BASE}/reagents/import`, { method: 'POST', body: formData });
        
        const templateCsv = await fetch('/data/templates/96well_template.csv').then(r => r.text());
        formData = new FormData();
        formData.append('file', new File([templateCsv], 'template.csv'));
        formData.append('name', '96孔板标准模板');
        await fetch(`${API_BASE}/templates/import`, { method: 'POST', body: formData });
        
        loadStats();
        loadSamples();
        loadPrimers();
        loadReagents();
        loadTemplates();
        loadHistory();
        
        showToast('样例数据导入完成！', 'success');
        
    } catch (e) {
        showToast('导入失败: ' + e.message, 'error');
        console.error(e);
    }
}

function closeModal() {
    document.getElementById('modal').classList.add('hidden');
}

function showToast(message, type = 'success') {
    const toast = document.getElementById('toast');
    toast.textContent = message;
    toast.className = `toast ${type}`;
    
    setTimeout(() => {
        toast.classList.add('hidden');
    }, 3000);
}

window.onclick = function(event) {
    const modal = document.getElementById('modal');
    if (event.target === modal) {
        closeModal();
    }
};

async function copyTask(taskId) {
    try {
        const response = await fetch(`${API_BASE}/tasks/${taskId}/copy`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({})
        });
        
        const data = await response.json();
        
        if (response.ok) {
            showToast('任务复制成功，已创建新草稿', 'success');
            loadTasks();
            loadStats();
            loadHistory();
        } else {
            showToast('复制失败: ' + data.error, 'error');
        }
    } catch (e) {
        showToast('复制失败: ' + e.message, 'error');
    }
}

function copyCurrentTask() {
    if (currentTaskId) {
        copyTask(currentTaskId);
    }
}

function exportTaskPlan(taskId) {
    window.open(`${API_BASE}/tasks/${taskId}/export/json`);
}

async function importTaskFile(event) {
    const file = event.target.files[0];
    if (!file) return;
    
    event.target.value = '';
    
    const formData = new FormData();
    formData.append('file', file);
    
    try {
        const response = await fetch(`${API_BASE}/tasks/import`, {
            method: 'POST',
            body: formData
        });
        
        const data = await response.json();
        
        if (response.ok) {
            showToast('任务方案导入成功', 'success');
            loadTasks();
            loadStats();
            loadHistory();
        } else {
            if (data.conflict === 'name_exists') {
                const rename = confirm(
                    `任务名称已存在: ${file.name.replace('.json', '')}\n\n` +
                    '是否自动重命名导入？\n' +
                    '点击"确定"自动重命名，点击"取消"放弃导入。'
                );
                if (rename) {
                    const formData2 = new FormData();
                    formData2.append('file', file);
                    
                    const resp2 = await fetch(`${API_BASE}/tasks/import?conflict_mode=rename`, {
                        method: 'POST',
                        body: formData2
                    });
                    const data2 = await resp2.json();
                    
                    if (resp2.ok) {
                        showToast('任务方案已重命名导入', 'success');
                        loadTasks();
                        loadStats();
                        loadHistory();
                    } else {
                        showToast('导入失败: ' + data2.error, 'error');
                    }
                }
            } else {
                showToast('导入失败: ' + data.error, 'error');
            }
        }
    } catch (e) {
        showToast('导入失败: ' + e.message, 'error');
    }
}
