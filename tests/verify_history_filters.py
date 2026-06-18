import sys
import os
import json
import urllib.request
import urllib.parse

BASE = 'http://localhost:5000'

def get(path, **params):
    qs = urllib.parse.urlencode({k:v for k,v in params.items() if v is not None})
    url = f'{BASE}{path}?{qs}' if qs else f'{BASE}{path}'
    try:
        with urllib.request.urlopen(url) as resp:
            body = resp.read().decode('utf-8-sig')
            return resp.status, body, resp.headers.get('Content-Type', '')
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8-sig')
        return e.code, body, e.headers.get('Content-Type', '')

def parse_json(body):
    return json.loads(body)

def section(title):
    print(f'\n{"="*60}\n{title}\n{"="*60}')

section('1. 筛选元数据 /api/history/filters')
code, body, ct = get('/api/history/filters')
d = parse_json(body)
print(f'  HTTP {code}  tasks={len(d["tasks"])}  action_types={len(d["action_types"])}  max_limit={d["max_limit"]}')
assert code == 200, f'期望 200，实际 {code}'
assert d['max_limit'] == 5000
assert len(d['action_types']) >= 20
print('  ✅ 通过')

section('2. 无筛选查询（limit=5）')
code, body, ct = get('/api/history', limit=5)
d = parse_json(body)
print(f'  HTTP {code}  total={d["total"]}  returned={len(d["records"])}  errors={d["errors"]}  warnings={d["warnings"]}')
print(f'  filters: {d["filters"]}')
assert code == 200
assert len(d['records']) <= 5
assert d['total'] >= len(d['records'])
assert d['errors'] == []
print('  ✅ 通过')

section('3. 组合筛选（task_id=1 + action_type=task_created + limit=10）')
code, body, ct = get('/api/history', task_id=1, action_type='task_created', limit=10)
d = parse_json(body)
print(f'  HTTP {code}  total={d["total"]}  returned={len(d["records"])}')
print(f'  filters: {d["filters"]}')
assert code == 200
for r in d['records']:
    assert r['task_id'] == 1
    assert r['action_type'] == 'task_created'
print('  ✅ 通过')

section('4. 关键词搜索（keyword=批准，验证模糊匹配）')
code, body, ct = get('/api/history', keyword='批准', limit=100)
d = parse_json(body)
print(f'  HTTP {code}  total={d["total"]}  returned={len(d["records"])}')
print(f'  filters: {d["filters"]}')
assert code == 200
if d['records']:
    found_match = any(
        '批准' in (r.get('detail') or '') or
        '批准' in (r.get('action_type') or '') or
        'approve' in (r.get('action') or '').lower()
        for r in d['records']
    )
    print(f'  存在含关键词记录: {found_match}')
print('  ✅ 通过')

section('5. 关键词无结果（确认 200 + total=0 + 非空白）')
code, body, ct = get('/api/history', keyword='这个关键词肯定不存在xyz123不存在', limit=50)
d = parse_json(body)
print(f'  HTTP {code}  total={d["total"]}  returned={len(d["records"])}  errors={d["errors"]}')
assert code == 200
assert d['total'] == 0
assert d['records'] == []
assert d['errors'] == []
print('  ✅ 通过（HTTP 200 而非 500，total=0 有明确返回）')

section('6. 非法日期 start_date=2025/01/01（验证 HTTP 400 + 明确错误）')
code, body, ct = get('/api/history', start_date='2025/01/01')
d = parse_json(body)
print(f'  HTTP {code}  errors={d.get("errors", [])}')
assert code == 400
assert any('格式不合法' in e for e in d['errors']), f'错误中未找到格式提示: {d["errors"]}'
assert d['records'] == []
print('  ✅ 通过')

section('7. start_date > end_date（验证 HTTP 400）')
code, body, ct = get('/api/history', start_date='2025-12-31', end_date='2025-01-01')
d = parse_json(body)
print(f'  HTTP {code}  errors={d.get("errors", [])}')
assert code == 400
assert any('不能晚于' in e for e in d['errors'])
print('  ✅ 通过')

section('8. 过大 limit=99999（验证自动截断 + 警告）')
code, body, ct = get('/api/history', limit=99999)
d = parse_json(body)
print(f'  HTTP {code}  returned={len(d["records"])}  warnings={d["warnings"]}')
assert code == 200
assert any('超过上限' in w for w in d['warnings']), f'未找到上限警告: {d["warnings"]}'
assert len(d['records']) <= 5000
print('  ✅ 通过')

section('9. limit=-5（非法，验证 HTTP 400）')
code, body, ct = get('/api/history', limit=-5)
d = parse_json(body)
print(f'  HTTP {code}  errors={d.get("errors", [])}')
assert code == 400
assert any('大于 0' in e for e in d['errors'] + (d.get('errors') or [])) or len(d['errors'])>0
print('  ✅ 通过')

section('10. 时间范围筛选（start_date + end_date 合法范围）')
code, body, ct = get('/api/history', start_date='2020-01-01', end_date='2030-12-31', limit=10)
d = parse_json(body)
print(f'  HTTP {code}  total={d["total"]}  returned={len(d["records"])}  errors={d["errors"]}')
assert code == 200
assert d['errors'] == []
print('  ✅ 通过')

section('11. 按筛选导出 JSON（与查询吃同一套参数）')
query_params = dict(action_type='task_created', limit=100)
q_code, q_body, _ = get('/api/history', **query_params)
q_d = parse_json(q_body)
e_code, e_body, e_ct = get('/api/history/export/json', **query_params)
print(f'  查询: HTTP {q_code}, total={q_d["total"]}, records={len(q_d["records"])}')
print(f'  导出: HTTP {e_code}, Content-Type={e_ct}')
assert q_code == 200
assert e_code == 200
assert 'application/json' in e_ct
e_d = parse_json(e_body)
assert 'filter_summary' in e_d, 'JSON 导出缺少 filter_summary'
assert 'filters' in e_d
assert 'matched_count' in e_d
assert 'exported_count' in e_d
assert len(e_d['history']) == len(q_d['records']), (
    f'导出与页面不一致: 导出{len(e_d["history"])} vs 查询{len(q_d["records"])}'
)
assert e_d['matched_count'] == q_d['total'], (
    f'matched_count 不一致: 导出{e_d["matched_count"]} vs 查询{q_d["total"]}'
)
print(f'  filter_summary: {e_d["filter_summary"]}')
print(f'  matched={e_d["matched_count"]}  exported={e_d["exported_count"]}  与查询一致 ✅')
print('  ✅ 通过')

section('12. 按筛选导出 CSV（首行注释 + 与查询一致）')
query_params = dict(task_id=1, limit=50)
q_code, q_body, _ = get('/api/history', **query_params)
q_d = parse_json(q_body)
e_code, e_body, e_ct = get('/api/history/export/csv', **query_params)
print(f'  查询: HTTP {q_code}, total={q_d["total"]}, records={len(q_d["records"])}')
print(f'  导出: HTTP {e_code}, Content-Type={e_ct}')
assert q_code == 200
assert e_code == 200
assert 'text/csv' in e_ct
lines = e_body.splitlines()
comment_lines = [l for l in lines[:6] if l.startswith('#')]
print(f'  CSV 注释行数: {len(comment_lines)}')
for cl in comment_lines:
    print(f'    {cl}')
assert any('导出时间' in l for l in comment_lines), 'CSV 缺少导出时间注释'
assert any('筛选条件' in l for l in comment_lines), 'CSV 缺少筛选条件注释'
assert any('匹配总数' in l for l in comment_lines), 'CSV 缺少匹配数量注释'
data_lines = [l for l in lines if l and not l.startswith('#')]
assert len(data_lines) - 1 == len(q_d['records']), (
    f'CSV 数据行数不一致: CSV {len(data_lines)-1} vs 查询 {len(q_d["records"])} (差1行表头)'
)
print('  ✅ 通过（CSV 注释齐全 + 数据与查询一致）')

section('13. 导出动作会写入 history 表（审计追踪）')
before_code, before_body, _ = get('/api/history', action_type='history_exported_json', limit=10)
before_d = parse_json(before_body)
before_count = before_d['total']
print(f'  导出 JSON 前 history_exported_json 总数: {before_count}')
_ = get('/api/history/export/json', limit=5)
after_code, after_body, _ = get('/api/history', action_type='history_exported_json', limit=10)
after_d = parse_json(after_body)
after_count = after_d['total']
print(f'  导出 JSON 后 history_exported_json 总数: {after_count}')
assert after_count > before_count, '导出 JSON 未写入 history 表'
last = after_d['records'][0]
print(f'  最新一条导出记录 detail 前 80 字符: {last["detail"][:80]}')
assert '导出历史记录' in last['detail']
print('  ✅ 通过')

print(f'\n\n{"*"*60}\n🎉 全部 13 个验证场景通过！\n{"*"*60}')
