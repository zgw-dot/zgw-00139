# -*- coding: utf-8 -*-
import requests
import json
import sqlite3
import sys

BASE = "http://localhost:5000"
DB_PATH = "data/pcr_planner.db"

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

print("=" * 60)
print("端到端验证：模板导入 + 创建任务 + 生成方案")
print("=" * 60)

print("\n[1/6] 检查模板表当前状态")
conn = get_conn()
templates_before = len(conn.execute('SELECT * FROM plate_templates').fetchall())
wells_before = len(conn.execute('SELECT * FROM template_wells').fetchall())
print(f"   模板数: {templates_before}")
print(f"   孔位数: {wells_before}")
conn.close()

print("\n[2/6] 导入板位模板 CSV")
import time
unique_name = f"e2e_test_{int(time.time())}"
with open("data/templates/96well_template.csv", "rb") as f:
    r = requests.post(f"{BASE}/api/templates/import", 
                      files={"file": f},
                      data={"name": unique_name})

print(f"   HTTP {r.status_code}")
data = r.json()
if r.status_code == 201:
    template_id = data["id"]
    print(f"   ✅ 导入成功: {data['name']} (id={template_id})")
    print(f"   孔数: {len(data['wells'])}")
    print(f"   第一个孔: {data['wells'][0]['well_row']}{data['wells'][0]['well_col']} = {data['wells'][0]['well_type']}")
else:
    print(f"   ❌ 失败: {data.get('error')}")
    sys.exit(1)

print("\n[3/6] 验证模板可读取（重启后也能读的前置验证）")
r2 = requests.get(f"{BASE}/api/templates/{template_id}")
assert r2.status_code == 200
data2 = r2.json()
assert len(data2["wells"]) == len(data["wells"])
print(f"   ✅ 模板可读: {data2['name']}, {len(data2['wells'])} 孔")

print("\n[4/6] 验证模板列表可读（重启后仍能读）")
templates_list = requests.get(f"{BASE}/api/templates").json()
print(f"   模板总数: {len(templates_list)}")
found = any(t["id"] == template_id for t in templates_list)
assert found, f"新建的模板 (id={template_id}) 应该在列表里"
print(f"   ✅ 模板列表包含新建模板")

print("\n[5/6] 创建任务 + 生成方案")
# 先查第一个样本、引物、试剂
samples = requests.get(f"{BASE}/api/samples").json()
primers = requests.get(f"{BASE}/api/primers").json()
reagents = requests.get(f"{BASE}/api/reagents").json()

sample_id = samples[0]["id"]
primer_id = primers[0]["id"]
mm_id = [r for r in reagents if r["type"] == "master_mix"][0]["id"]
water_id = [r for r in reagents if r["type"] == "water"][0]["id"]

print(f"   样本: {samples[0]['name']} (id={sample_id})")
print(f"   引物: {primers[0]['name']} (id={primer_id})")
print(f"   MasterMix: {[r for r in reagents if r['type']=='master_mix'][0]['name']} (id={mm_id})")
print(f"   Water: {[r for r in reagents if r['type']=='water'][0]['name']} (id={water_id})")

task_payload = {
    "name": "E2E_模板验证任务",
    "template_id": template_id,
    "total_volume": 20,
    "volume_unit": "ul"
}
r_task = requests.post(f"{BASE}/api/tasks", json=task_payload)
assert r_task.status_code == 201, f"创建任务失败: {r_task.status_code} - {r_task.text}"
task = r_task.json()
print(f"   创建任务响应: {list(task.keys())[:10]}")
task_id = task.get("id") or task.get("task", {}).get("id")
assert task_id, f"找不到任务 id: {task}"
print(f"   ✅ 创建任务成功: {task.get('name', task.get('task',{}).get('name','?'))} (id={task_id})")

plan_payload = {
    "primer_id": primer_id,
    "master_mix_id": mm_id,
    "water_id": water_id
}
r_plan = requests.post(f"{BASE}/api/tasks/{task_id}/generate", json=plan_payload)
print(f"   生成方案: HTTP {r_plan.status_code}")
plan_data = r_plan.json()
if r_plan.status_code == 200:
    print(f"   ✅ 生成方案成功: {len(plan_data.get('wells', []))} 个孔位")
    print(f"   状态: {plan_data.get('task', {}).get('status')}")
else:
    print(f"   ❌ 失败: {plan_data.get('error')}")
    sys.exit(1)

print("\n[6/6] 验证报告导出")
for fmt in ["json", "csv"]:
    r_report = requests.get(f"{BASE}/api/reports/task/{task_id}/{fmt}")
    print(f"   /api/reports/task/{task_id}/{fmt} → HTTP {r_report.status_code}")
    assert r_report.status_code == 200

print("\n" + "=" * 60)
print("✅ 端到端验证全部通过")
print("=" * 60)
