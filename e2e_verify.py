# -*- coding: utf-8 -*-
import requests
import json
import sqlite3
import sys
import time
import io

BASE = "http://localhost:5000"
DB_PATH = "data/pcr_planner.db"

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

print("=" * 60)
print("端到端验证：模板导出 + 复制 + 冲突处理 + 删除保护")
print("=" * 60)

print("\n[1/10] 检查模板表当前状态")
conn = get_conn()
templates_before = len(conn.execute('SELECT * FROM plate_templates').fetchall())
conn.close()
print(f"   模板数: {templates_before}")

print("\n[2/10] 导入板位模板 CSV")
unique_name = f"e2e_mgmt_{int(time.time())}"
with open("data/templates/96well_template.csv", "rb") as f:
    r = requests.post(f"{BASE}/api/templates/import",
                      files={"file": f},
                      data={"name": unique_name})
assert r.status_code == 201, f"导入失败: {r.status_code} {r.text}"
data = r.json()
template_id = data["id"]
print(f"   ✅ 导入成功: {data['name']} (id={template_id}, {len(data['wells'])} 孔)")

print("\n[3/10] 导出模板为 JSON")
r_json = requests.get(f"{BASE}/api/templates/{template_id}/export/json")
assert r_json.status_code == 200, f"JSON导出失败: {r_json.status_code}"
json_data = json.loads(r_json.content.decode('utf-8'))
assert json_data['name'] == unique_name, f"导出名称不匹配: {json_data['name']}"
assert len(json_data['wells']) == len(data['wells']), "导出孔位数不匹配"
print(f"   ✅ JSON导出: {json_data['name']}, {len(json_data['wells'])} 孔")

print("\n[4/10] 导出模板为 CSV")
r_csv = requests.get(f"{BASE}/api/templates/{template_id}/export/csv")
assert r_csv.status_code == 200, f"CSV导出失败: {r_csv.status_code}"
csv_content = r_csv.content.decode('utf-8-sig')
assert len(csv_content) > 0, "CSV导出为空"
csv_lines = csv_content.strip().split('\n')
print(f"   ✅ CSV导出: {len(csv_lines)} 行")

print("\n[5/10] 重新导入导出的 JSON（验证导出可再导入）")
reimport_name = f"{unique_name}_reimported"
r_reimport = requests.post(f"{BASE}/api/templates/import",
    json={'name': reimport_name, 'rows': json_data['rows'],
          'cols': json_data['cols'], 'wells': json_data['wells']})
assert r_reimport.status_code == 201, f"重新导入失败: {r_reimport.status_code} {r_reimport.text}"
reimported = r_reimport.json()
assert len(reimported['wells']) == len(json_data['wells']), "重新导入孔位数不匹配"
print(f"   ✅ 重新导入成功: {reimported['name']}, {len(reimported['wells'])} 孔")

print("\n[6/10] 复制模板")
r_copy = requests.post(f"{BASE}/api/templates/{template_id}/copy",
                       json={'name': f'{unique_name}_副本'})
assert r_copy.status_code == 201, f"复制失败: {r_copy.status_code} {r_copy.text}"
copied = r_copy.json()
assert copied['name'] == f'{unique_name}_副本', f"复制品名称不匹配: {copied['name']}"
assert len(copied['wells']) == len(data['wells']), "复制品孔位数不匹配"
print(f"   ✅ 复制成功: {copied['name']} (id={copied['id']}, {len(copied['wells'])} 孔)")

print("\n[7/10] 冲突处理 - 拒绝同名导入")
r_reject = requests.post(f"{BASE}/api/templates/import",
    json={'name': unique_name, 'rows': 2, 'cols': 3,
          'wells': [{'well_row': 1, 'well_col': 1, 'well_type': 'sample'}]})
assert r_reject.status_code == 409, f"拒绝模式应返回409: {r_reject.status_code}"
reject_data = r_reject.json()
assert reject_data['conflict'] == 'name_exists', f"冲突类型不对: {reject_data}"
print(f"   ✅ 拒绝模式: HTTP 409, conflict=name_exists")

print("\n[8/10] 冲突处理 - 改名同名导入")
r_rename = requests.post(f"{BASE}/api/templates/import",
    json={'name': unique_name, 'rows': 2, 'cols': 3, 'conflict_mode': 'rename',
          'wells': [{'well_row': 1, 'well_col': 1, 'well_type': 'sample'},
                    {'well_row': 1, 'well_col': 2, 'well_type': 'positive_control'},
                    {'well_row': 1, 'well_col': 3, 'well_type': 'negative_control'},
                    {'well_row': 2, 'well_col': 1, 'well_type': 'empty'},
                    {'well_row': 2, 'well_col': 2, 'well_type': 'sample'},
                    {'well_row': 2, 'well_col': 3, 'well_type': 'sample'}]})
assert r_rename.status_code == 201, f"改名模式应返回201: {r_rename.status_code}"
renamed = r_rename.json()
assert renamed['name'] != unique_name, f"改名后名称不应与原名相同: {renamed['name']}"
print(f"   ✅ 改名模式: {unique_name} → {renamed['name']}")

print("\n[9/10] 冲突处理 - 覆盖同名导入")
r_overwrite = requests.post(f"{BASE}/api/templates/import",
    json={'name': unique_name, 'rows': 2, 'cols': 3, 'conflict_mode': 'overwrite',
          'wells': [{'well_row': 1, 'well_col': 1, 'well_type': 'sample', 'sample_name': 'X'},
                    {'well_row': 1, 'well_col': 2, 'well_type': 'positive_control'},
                    {'well_row': 1, 'well_col': 3, 'well_type': 'negative_control'},
                    {'well_row': 2, 'well_col': 1, 'well_type': 'empty'},
                    {'well_row': 2, 'well_col': 2, 'well_type': 'sample', 'sample_name': 'Y'},
                    {'well_row': 2, 'well_col': 3, 'well_type': 'sample'}]})
assert r_overwrite.status_code == 200, f"覆盖模式应返回200: {r_overwrite.status_code}"
overwritten = r_overwrite.json()
assert overwritten.get('overwritten') == True, "覆盖响应应标记 overwritten=True"
assert overwritten['id'] == template_id, "覆盖后ID应保持不变"
print(f"   ✅ 覆盖模式: id={overwritten['id']}, overwritten=True, {len(overwritten['wells'])} 孔")

print("\n[10/10] 删除保护 - 引用中模板不可删除")
samples = requests.get(f"{BASE}/api/samples").json()
primers = requests.get(f"{BASE}/api/primers").json()
reagents = requests.get(f"{BASE}/api/reagents").json()

if samples and primers and reagents:
    r_task = requests.post(f"{BASE}/api/tasks", json={
        "name": "E2E_删除保护测试任务",
        "template_id": template_id,
        "total_volume": 20,
        "volume_unit": "ul"
    })
    assert r_task.status_code == 201, f"创建任务失败: {r_task.status_code} {r_task.text}"
    task_data = r_task.json()
    task_id = task_data.get("id") or task_data.get("task", {}).get("id")

    r_delete_blocked = requests.delete(f"{BASE}/api/templates/{template_id}")
    assert r_delete_blocked.status_code == 409, f"引用中模板应返回409: {r_delete_blocked.status_code}"
    blocked = r_delete_blocked.json()
    assert blocked['reason'] == 'template_in_use', f"拦截原因不对: {blocked}"
    assert blocked['task_count'] >= 1, f"引用任务数应为>=1: {blocked['task_count']}"
    print(f"   ✅ 删除保护: HTTP 409, reason=template_in_use, task_count={blocked['task_count']}")
else:
    print("   ⚠️  跳过删除保护验证（缺少样本/引物/试剂数据）")

print("\n" + "=" * 60)
print("✅ 端到端验证全部通过")
print("=" * 60)
