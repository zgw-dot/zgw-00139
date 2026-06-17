# -*- coding: utf-8 -*-
import sqlite3
import requests
import json

BASE = "http://localhost:5000"
DB_PATH = "data/pcr_planner.db"

print("=" * 60)
print("复现：真实服务+真实数据库下的模板导入问题")
print("=" * 60)

print("\n1. 数据库表结构:")
conn = sqlite3.connect(DB_PATH)
cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
for row in cur:
    print(f"   {row[0]}")

print("\n2. template_wells 列定义:")
cur2 = conn.execute('PRAGMA table_info(template_wells)')
cols = []
for row in cur2:
    print(f"   {row[1]} ({row[2]})")
    cols.append(row[1])

print("\n3. plate_templates 列定义:")
cur3 = conn.execute('PRAGMA table_info(plate_templates)')
for row in cur3:
    print(f"   {row[1]} ({row[2]})")

conn.close()

print("\n4. 尝试导入板位模板:")
with open("data/templates/96well_template.csv", "rb") as f:
    r = requests.post(f"{BASE}/api/templates/import", files={"file": f})

print(f"   HTTP {r.status_code}")
data = r.json()
print(f"   响应: {json.dumps(data, ensure_ascii=False, indent=6)}")

if not data.get("success"):
    print(f"\n   ❌ 失败: {data.get('error', '')}")
else:
    print(f"\n   ✅ 成功: 导入了 {data.get('imported', 0)} 个模板")
