# -*- coding: utf-8 -*-
import sqlite3
import requests
import json
import sys

BASE = "http://localhost:5000"
DB_PATH = "data/pcr_planner.db"

print("=" * 60)
print("复现：真实服务+真实数据库下的模板导入问题")
print("=" * 60)

print("\n1. 数据库表结构:")
conn = sqlite3.connect(DB_PATH)
cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
tables = [row[0] for row in cur]
for t in tables:
    print(f"   - {t}")

print("\n2. template_wells 列定义:")
cur2 = conn.execute('PRAGMA table_info(template_wells)')
cols = []
for row in cur2:
    print(f"   - {row[1]} ({row[2]})")
    cols.append(row[1])

print("\n3. plate_templates 列定义:")
cur3 = conn.execute('PRAGMA table_info(plate_templates)')
for row in cur3:
    print(f"   - {row[1]} ({row[2]})")

print("\n4. 当前 template_wells 记录数:")
cur4 = conn.execute('SELECT COUNT(*) FROM template_wells')
print(f"   {cur4.fetchone()[0]} 条")

conn.close()

print("\n5. 尝试导入板位模板:")
with open("data/templates/96well_template.csv", "rb") as f:
    r = requests.post(f"{BASE}/api/templates/import", files={"file": f})

print(f"   HTTP {r.status_code}")
try:
    data = r.json()
    print(f"   success: {data.get('success')}")
    print(f"   imported: {data.get('imported')}")
    print(f"   error: {data.get('error')}")
except Exception:
    print(f"   响应非 JSON: {r.text[:200]}")

print("\n6. 导入后 template_wells 记录数:")
conn = sqlite3.connect(DB_PATH)
cur5 = conn.execute('SELECT COUNT(*) FROM template_wells')
print(f"   {cur5.fetchone()[0]} 条")
conn.close()
