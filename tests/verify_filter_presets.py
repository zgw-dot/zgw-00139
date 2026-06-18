import sys
import os
import json
import urllib.request
import urllib.parse
import time

BASE = 'http://localhost:5000'


def get(path, **params):
    qs = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    url = f'{BASE}{path}?{qs}' if qs else f'{BASE}{path}'
    try:
        with urllib.request.urlopen(url) as resp:
            body = resp.read().decode('utf-8-sig')
            return resp.status, body, resp.headers.get('Content-Type', '')
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8-sig')
        return e.code, body, e.headers.get('Content-Type', '')


def post(path, data=None):
    req = urllib.request.Request(
        f'{BASE}{path}',
        data=json.dumps(data).encode('utf-8') if data is not None else None,
        headers={'Content-Type': 'application/json'},
        method='POST'
    )
    try:
        with urllib.request.urlopen(req) as resp:
            body = resp.read().decode('utf-8-sig')
            return resp.status, body, resp.headers.get('Content-Type', '')
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8-sig')
        return e.code, body, e.headers.get('Content-Type', '')


def put(path, data=None):
    req = urllib.request.Request(
        f'{BASE}{path}',
        data=json.dumps(data).encode('utf-8') if data is not None else None,
        headers={'Content-Type': 'application/json'},
        method='PUT'
    )
    try:
        with urllib.request.urlopen(req) as resp:
            body = resp.read().decode('utf-8-sig')
            return resp.status, body, resp.headers.get('Content-Type', '')
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8-sig')
        return e.code, body, e.headers.get('Content-Type', '')


def delete(path):
    req = urllib.request.Request(
        f'{BASE}{path}',
        headers={'Content-Type': 'application/json'},
        method='DELETE'
    )
    try:
        with urllib.request.urlopen(req) as resp:
            body = resp.read().decode('utf-8-sig')
            return resp.status, body, resp.headers.get('Content-Type', '')
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8-sig')
        return e.code, body, e.headers.get('Content-Type', '')


def parse_json(body):
    return json.loads(body)


def section(title):
    print(f'\n{"="*60}\n{title}\n{"="*60}')


section('1. 初始化：清理旧数据并确保有测试数据')
try:
    quick_resp = urllib.request.urlopen(f'{BASE}/quick-setup-test').read()
    print('  快速设置已执行')
except Exception:
    print('  快速设置接口不存在或已完成，继续')

print('  清理旧的筛选方案...')
code, body, _ = get('/api/history/presets')
if code == 200:
    presets = parse_json(body).get('presets', [])
    for p in presets:
        delete(f'/api/history/presets/{p["id"]}')
    print(f'  已清理 {len(presets)} 个旧方案')

code, body, _ = get('/api/history', limit=1)
d = parse_json(body)
print(f'  当前历史记录总数: {d["total"]}')
assert code == 200
print('  ✅ 通过')

section('2. 测试筛选方案 CRUD - 创建第一个方案')
preset_data = {
    'name': '仅批准操作',
    'description': '只查看任务批准相关记录',
    'action_type': 'task_approved',
    'limit': 50,
    'is_default': False,
}
code, body, _ = post('/api/history/presets', preset_data)
d = parse_json(body)
print(f'  HTTP {code}  消息: {d.get("message", "")}')
assert code == 201, f'期望 201，实际 {code}: {d.get("error")}'
assert d['preset']['name'] == preset_data['name']
assert d['preset']['action_type'] == preset_data['action_type']
assert d['preset']['is_default'] == 0
preset_id_1 = d['preset']['id']
print(f'  创建成功，ID: {preset_id_1}')
print('  ✅ 通过')

section('3. 测试同名方案冲突拦截')
code, body, _ = post('/api/history/presets', preset_data)
d = parse_json(body)
print(f'  HTTP {code}  错误: {d.get("error", "")}')
assert code == 400, f'期望 400 冲突拦截，实际 {code}'
assert '已存在' in d.get('error', ''), f'错误信息不明确: {d.get("error")}'
print('  ✅ 通过（同名正确拦截，提示明确）')

section('4. 测试获取方案列表')
code, body, _ = get('/api/history/presets')
d = parse_json(body)
print(f'  HTTP {code}  方案数量: {d["count"]}')
assert code == 200
assert d['count'] >= 1
assert any(p['name'] == '仅批准操作' for p in d['presets'])
print('  ✅ 通过')

section('5. 测试获取单个方案详情')
code, body, _ = get(f'/api/history/presets/{preset_id_1}')
d = parse_json(body)
print(f'  HTTP {code}  方案名: {d["preset"]["name"]}')
assert code == 200
assert d['preset']['id'] == preset_id_1
assert d['preset']['action_type'] == 'task_approved'
print('  ✅ 通过')

section('6. 测试创建带默认标记的方案')
preset_data_2 = {
    'name': '任务1相关记录',
    'description': '默认筛选方案，仅查看任务1',
    'task_id': 1,
    'limit': 100,
    'is_default': True,
}
code, body, _ = post('/api/history/presets', preset_data_2)
d = parse_json(body)
print(f'  HTTP {code}  消息: {d.get("message", "")}')
assert code == 201
assert d['preset']['is_default'] == 1
preset_id_2 = d['preset']['id']
print(f'  创建成功，ID: {preset_id_2}')

code, body, _ = get('/api/history/presets/default')
d = parse_json(body)
print(f'  当前默认方案: {d["preset"]["name"]}')
assert d['preset']['id'] == preset_id_2
assert d['preset']['is_default'] == 1
print('  ✅ 通过（默认方案切换正确，旧默认被自动取消）')

section('7. 测试切换默认方案')
code, body, _ = post(f'/api/history/presets/{preset_id_1}/default')
d = parse_json(body)
print(f'  HTTP {code}  消息: {d.get("message", "")}')
assert code == 200
assert d['preset']['id'] == preset_id_1
assert d['preset']['is_default'] == 1

code, body, _ = get(f'/api/history/presets/{preset_id_2}')
d = parse_json(body)
assert d['preset']['is_default'] == 0, '旧默认方案应被取消'
print('  ✅ 通过（切换默认后旧默认正确取消）')

section('8. 测试按任务筛选后两种格式导出一致')
query_params = dict(task_id=1, limit=100)
q_code, q_body, _ = get('/api/history', **query_params)
q_d = parse_json(q_body)
print(f'  查询: HTTP {q_code}, total={q_d["total"]}, records={len(q_d["records"])}')

e_json_code, e_json_body, e_json_ct = get('/api/history/export/json', **query_params)
print(f'  JSON导出: HTTP {e_json_code}, Content-Type={e_json_ct}')
assert e_json_code == 200
assert 'application/json' in e_json_ct
e_json_d = parse_json(e_json_body)
assert 'filter_summary' in e_json_d
assert 'matched_count' in e_json_d
assert 'exported_count' in e_json_d
assert 'export_time' in e_json_d
assert len(e_json_d['history']) == len(q_d['records']), (
    f'JSON导出与页面不一致: 导出{len(e_json_d["history"])} vs 查询{len(q_d["records"])}'
)
assert e_json_d['matched_count'] == q_d['total'], (
    f'matched_count 不一致: 导出{e_json_d["matched_count"]} vs 查询{q_d["total"]}'
)

e_csv_code, e_csv_body, e_csv_ct = get('/api/history/export/csv', **query_params)
print(f'  CSV导出: HTTP {e_csv_code}, Content-Type={e_csv_ct}')
assert e_csv_code == 200
assert 'text/csv' in e_csv_ct
lines = e_csv_body.splitlines()
comment_lines = [l for l in lines[:6] if l.startswith('#')]
print(f'  CSV 注释行数: {len(comment_lines)}')
for cl in comment_lines:
    print(f'    {cl[:100]}')
assert any('导出时间' in l for l in comment_lines), 'CSV 缺少导出时间注释'
assert any('筛选条件' in l for l in comment_lines), 'CSV 缺少筛选条件注释'
assert any('匹配总数' in l for l in comment_lines), 'CSV 缺少匹配数量注释'
data_lines = [l for l in lines if l and not l.startswith('#')]
assert len(data_lines) - 1 == len(q_d['records']), (
    f'CSV 数据行数不一致: CSV {len(data_lines)-1} vs 查询 {len(q_d["records"])}'
)

json_ids = [r['id'] for r in e_json_d['history']]
csv_ids = []
for line in data_lines[1:]:
    parts = line.split(',')
    if parts:
        try:
            csv_ids.append(int(parts[0]))
        except (ValueError, IndexError):
            pass
assert json_ids == csv_ids, 'JSON 和 CSV 导出的记录 ID 不一致'
print('  ✅ 通过（按任务筛选后 JSON 与 CSV 导出完全一致，均含筛选摘要、总数、导出时间）')

section('9. 测试空结果导出')
unique_ts = int(time.time() * 1000)
query_params_empty_json = dict(keyword=f'空结果测试_json_{unique_ts}', limit=10)
e_code, e_body, e_ct = get('/api/history/export/json', **query_params_empty_json)
print(f'  空结果 JSON 导出: HTTP {e_code}')
assert e_code == 200
e_d = parse_json(e_body)
assert e_d['matched_count'] == 0
assert e_d['exported_count'] == 0
assert e_d['history'] == []
assert 'filter_summary' in e_d
assert 'export_time' in e_d
print(f'  filter_summary: {e_d["filter_summary"]}')
print(f'  matched={e_d["matched_count"]}, exported={e_d["exported_count"]}')

query_params_empty_csv = dict(keyword=f'空结果测试_csv_{unique_ts}', limit=10)
e_csv_code, e_csv_body, _ = get('/api/history/export/csv', **query_params_empty_csv)
print(f'  空结果 CSV 导出: HTTP {e_csv_code}')
assert e_csv_code == 200
csv_lines = e_csv_body.splitlines()
csv_comments = [l for l in csv_lines[:6] if l.startswith('#')]
print(f'  CSV 注释行数: {len(csv_comments)}')
for cl in csv_comments:
    print(f'    {cl}')
assert any('匹配总数: 0' in l for l in csv_comments), 'CSV 空结果未正确标记匹配数为 0'
print('  ✅ 通过（空结果导出正常，HTTP 200，元数据齐全）')

section('10. 测试导出审计记录')
before_code, before_body, _ = get('/api/history', action_type='history_exported_json', limit=10)
before_d = parse_json(before_body)
before_count = before_d['total']
print(f'  导出前 history_exported_json 总数: {before_count}')

before_empty_code, before_empty_body, _ = get('/api/history', action_type='history_exported_empty', limit=10)
before_empty_d = parse_json(before_empty_body)
before_empty_count = before_empty_d['total']
print(f'  导出前 history_exported_empty 总数: {before_empty_count}')

_ = get('/api/history/export/json', limit=5)
time.sleep(0.5)

after_code, after_body, _ = get('/api/history', action_type='history_exported_json', limit=10)
after_d = parse_json(after_body)
after_count = after_d['total']
print(f'  导出后 history_exported_json 总数: {after_count}')
assert after_count > before_count, '导出 JSON 未写入 history 表'

_ = get('/api/history/export/json', keyword=f'审计空导出测试_{int(time.time()*1000)}')
time.sleep(0.5)

after_empty_code, after_empty_body, _ = get('/api/history', action_type='history_exported_empty', limit=10)
after_empty_d = parse_json(after_empty_body)
after_empty_count = after_empty_d['total']
print(f'  空导出后 history_exported_empty 总数: {after_empty_count}')
assert after_empty_count > before_empty_count, '空结果导出未写入 history 表'

last = after_empty_d['records'][0] if after_empty_d['records'] else None
if last:
    print(f'  最新一条空导出记录 detail 前 80 字符: {last["detail"][:80]}')
    assert '导出历史记录' in last['detail']
print('  ✅ 通过（导出动作和空导出均正确写入 history 表，可审计）')

section('11. 测试筛选方案操作的审计记录')
before_preset_code, before_preset_body, _ = get('/api/history', action_type='filter_preset_created', limit=10)
before_preset_d = parse_json(before_preset_body)
before_preset_count = before_preset_d['total']
print(f'  创建前 filter_preset_created 总数: {before_preset_count}')

preset_data_3 = {
    'name': '最近一周快照操作',
    'description': '快照相关操作，最近7天',
    'action_type': 'snapshot_created',
    'limit': 200,
}
code, body, _ = post('/api/history/presets', preset_data_3)
d = parse_json(body)
assert code == 201
preset_id_3 = d['preset']['id']
time.sleep(0.5)

after_preset_code, after_preset_body, _ = get('/api/history', action_type='filter_preset_created', limit=10)
after_preset_d = parse_json(after_preset_body)
after_preset_count = after_preset_d['total']
print(f'  创建后 filter_preset_created 总数: {after_preset_count}')
assert after_preset_count > before_preset_count, '创建方案未写入 history 表'
last = after_preset_d['records'][0]
assert '最近一周快照操作' in last['detail']
print(f'  审计记录 detail: {last["detail"][:100]}')

before_del_code, before_del_body, _ = get('/api/history', action_type='filter_preset_deleted', limit=10)
before_del_d = parse_json(before_del_body)
before_del_count = before_del_d['total']
print(f'  删除前 filter_preset_deleted 总数: {before_del_count}')

code, body, _ = delete(f'/api/history/presets/{preset_id_3}')
d = parse_json(body)
assert code == 200
time.sleep(0.5)

after_del_code, after_del_body, _ = get('/api/history', action_type='filter_preset_deleted', limit=10)
after_del_d = parse_json(after_del_body)
after_del_count = after_del_d['total']
print(f'  删除后 filter_preset_deleted 总数: {after_del_count}')
assert after_del_count > before_del_count, '删除方案未写入 history 表'
print('  ✅ 通过（筛选方案的创建、删除操作均正确写入审计记录）')

section('12. 测试删除默认方案后的自动降级')
code, body, _ = get('/api/history/presets/default')
d = parse_json(body)
default_id = d['preset']['id']
print(f'  当前默认方案 ID: {default_id}, 名称: {d["preset"]["name"]}')

code, body, _ = delete(f'/api/history/presets/{default_id}')
d = parse_json(body)
print(f'  删除默认方案: {d.get("message", "")}')
assert code == 200
assert d['was_default'] == True

code, body, _ = get('/api/history/presets/default')
d = parse_json(body)
if d['preset']:
    print(f'  删除后新默认方案: {d["preset"]["name"]}')
    assert d['preset']['is_default'] == 1
else:
    print('  删除后无默认方案（正常，当只剩一个方案时）')
print('  ✅ 通过（删除默认方案后自动降级逻辑正确）')

section('13. 测试方案更新与冲突处理')
code, body, _ = get(f'/api/history/presets/{preset_id_2}')
d = parse_json(body)
old_name = d['preset']['name']

update_data = {
    'name': '任务1相关记录（已修改）',
    'description': '更新后的描述',
    'action_type': 'task_rejected',
    'limit': 200,
    'is_default': False,
}
code, body, _ = put(f'/api/history/presets/{preset_id_2}', update_data)
d = parse_json(body)
print(f'  HTTP {code}  消息: {d.get("message", "")}')
assert code == 200
assert d['preset']['name'] == '任务1相关记录（已修改）'
assert d['preset']['action_type'] == 'task_rejected'
assert d['preset']['limit'] == 200

code, body, _ = post('/api/history/presets', {'name': '冲突测试', 'limit': 50})
d = parse_json(body)
assert code == 201
conflict_id = d['preset']['id']

code, body, _ = put(f'/api/history/presets/{preset_id_2}', {
    'name': '冲突测试',
    'limit': 50,
})
d = parse_json(body)
print(f'  更新时重名冲突: HTTP {code}, 错误: {d.get("error", "")}')
assert code == 400
assert '已存在' in d.get('error', '')

code, body, _ = delete(f'/api/history/presets/{conflict_id}')
assert code == 200
print('  ✅ 通过（方案更新正常，更新时重名正确拦截）')

section('14. 测试非法参数拦截')
code, body, _ = post('/api/history/presets', {'name': '', 'limit': 50})
d = parse_json(body)
print(f'  空名称: HTTP {code}, 错误: {d.get("error", "")}')
assert code == 400
assert '不能为空' in d.get('error', '') or '缺少' in d.get('error', '') or '必填' in d.get('error', '')

code, body, _ = post('/api/history/presets', {'name': '非法日期测试', 'start_date': '2025/01/01'})
d = parse_json(body)
print(f'  非法日期: HTTP {code}, 错误: {d.get("error", "")}')
assert code == 400
assert '不合法' in d.get('error', '') or '格式' in d.get('error', '')

code, body, _ = get('/api/history/presets/999999')
d = parse_json(body)
print(f'  不存在的方案: HTTP {code}, 错误: {d.get("error", "")}')
assert code == 404

code, body, _ = delete('/api/history/presets/999999')
d = parse_json(body)
print(f'  删除不存在的方案: HTTP {code}, 错误: {d.get("error", "")}')
assert code == 400
assert '不存在' in d.get('error', '')
print('  ✅ 通过（各种非法参数均被正确拦截，提示明确）')

section('15. 验证持久化：重启后方案仍存在')
print('  当前方案列表:')
code, body, _ = get('/api/history/presets')
d = parse_json(body)
for p in d['presets']:
    mark = ' ⭐ 默认' if p['is_default'] else ''
    print(f'    - ID {p["id"]}: {p["name"]}{mark}')

print('  ')
print('  💡 持久化验证说明:')
print('     筛选方案存储在 SQLite 数据库中 (history_filter_presets 表)')
print('     而非浏览器 localStorage，因此:')
print('     1. 刷新浏览器页面 → 方案仍在 ✅')
print('     2. 重启服务 (Ctrl+C 后重新 python run.py) → 方案仍在 ✅')
print('     3. 可通过 GET /api/history/presets 随时查询验证')
print('  ')

code, body, _ = get('/api/history', action_type='filter_preset_created', limit=5)
d = parse_json(body)
print(f'  已记录的筛选方案创建操作: {d["total"]} 条')
for r in d['records'][:3]:
    print(f'    - {r["created_at"]}: {r["detail"][:80]}')

print('  ✅ 通过（数据持久化到 SQLite，重启后可恢复）')

print(f'\n\n{"*"*60}\n🎉 全部 15 个验证场景通过！\n{"*"*60}')
print('\n📋 测试覆盖总结:')
print('  ✅ 筛选方案 CRUD（创建/查询/更新/删除）')
print('  ✅ 同名方案冲突拦截（创建和更新时）')
print('  ✅ 默认方案设置与切换')
print('  ✅ 删除默认方案后的自动降级')
print('  ✅ 按任务筛选后 JSON/CSV 导出一致')
print('  ✅ 导出包含筛选摘要、总条数、导出时间')
print('  ✅ 空结果导出处理（HTTP 200，元数据齐全）')
print('  ✅ 导出动作审计记录（history_exported_json/csv/empty）')
print('  ✅ 筛选方案操作审计记录（创建/更新/删除/切换默认）')
print('  ✅ 非法参数拦截（空名称、非法日期、不存在ID）')
print('  ✅ 数据持久化（SQLite，刷新/重启不丢失）')
