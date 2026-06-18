# PCR 板位配液规划工具

一个用于 PCR 实验板位配液规划的 Web 工具，支持样本、引物、试剂库存管理，自动计算配液方案，支持审批流程和完整的历史审计追踪。

## 功能特性

### 核心功能
- **数据导入**：支持 CSV 格式导入样本、引物、试剂库存和板位模板
- **方案计算**：自动计算每孔各组分用量，支持单位换算（体积/浓度）
- **最小移液验证**：检测低于最小移液体积的孔，需偏差备注后才能批准
- **阴阳性对照**：自动配置阳性对照 (PC) 和阴性对照 (NC) 孔
- **库存管理**：批准时自动扣减库存，撤销时自动退回库存
- **失败路径拦截**：孔位冲突、单位不兼容、库存不足、最小移液违规都会被拦截，失败计算不预占库存

### 审批流程
- 草稿 (draft) → 待复核 (pending_review) → 已批准 (approved) / 已驳回 (rejected) → 已撤销 (revoked)
- 支持偏差备注、确认、驳回、撤销确认等操作
- 所有操作均写入历史记录，支持 JSON/CSV 导出

### 任务改配（编辑并重算预览）
- **可编辑项**：板位模板、总体积、孔位分配（样本/对照/空孔）、样本孔增删
- **安全校验**：保存前自动拦截孔位冲突、模板不存在、超范围、非法类型、样本缺失、试剂/引物库存不足
- **版本控制**：编辑前后自动创建 pre_edit + edit 双快照，可对比差异、导出差异摘要、回滚到任意版本后重新生成
- **状态保护**：已批准和已撤销的任务保持只读，编辑不影响已扣库存、历史审批和已撤销记录

### 报告与审计
- 每孔用量明细，包含样本、引物、Master Mix、水的体积
- 对照孔标识和计算来源说明
- 库存扣减来源追踪
- 重启后数据一致性保证（SQLite 持久化）

### 版本快照与回滚
- **自动快照**：生成方案、导入方案、复制成草稿、批准前自动保存可追溯快照
- **版本列表**：任务详情页查看所有历史版本，含版本号、快照类型、状态、时间
- **版本对比**：对比任意两个版本的模板、总体积、孔位、引物/试剂用量和状态差异
- **回滚功能**：未批准任务可回滚到任意历史快照；已批准或已撤销任务禁止回滚，返回明确错误
- **持久化存储**：快照写入 SQLite，服务重启后仍可查看和回滚
- **导出导入**：导出的任务 JSON 包含快照摘要；导入时校验版本兼容性，遇不支持版本/重名/快照引用缺失整体拒绝，无脏数据残留
- **历史审计**：快照创建、版本对比、回滚操作、导入失败均写入历史记录

## 技术栈

- **后端**：Python 3 + Flask
- **数据库**：SQLite
- **前端**：纯 HTML + JavaScript + CSS
- **测试**：Python 原生测试框架

## 安装与运行

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 启动服务

```bash
python run.py
```

服务启动后访问：`http://localhost:5000`

## 使用说明

### 页面操作步骤

#### 步骤1：数据导入

打开 **"数据导入"** 标签页，依次导入：

1. **样本 CSV**：点击"导入样本"，选择 `data/samples/sample_samples.csv`
2. **引物 CSV**：点击"导入引物"，选择 `data/primers/sample_primers.csv`
3. **试剂 CSV**：点击"导入试剂"，选择 `data/reagents/sample_reagents.csv`
4. **板位模板 CSV**：点击"导入模板"，选择 `data/templates/96well_template.csv`

导入成功后会显示各数据的统计信息。

#### 步骤1.5：板位模板管理（导出 / 复制 / 冲突处理 / 删除保护）

在模板列表中对任意模板可执行以下操作：

| 操作 | 说明 |
|------|------|
| **导出 JSON** | `GET /api/templates/<id>/export/json` ，下载包含 name/rows/cols/description/wells 的 JSON 文件，可在任意环境重新导入。 |
| **导出 CSV** | `GET /api/templates/<id>/export/csv` ，下载网格格式 CSV，与 CSV 导入格式完全一致，可直接作为导入源。 |
| **复制模板** | `POST /api/templates/<id>/copy` ，支持自定义 name 与 description；若 name 已存在自动追加 `_副本` + 递增编号；复制后可直接用于创建任务。 |
| **删除模板** | `DELETE /api/templates/<id>` 。若模板已被任务引用，返回 HTTP 409 + `reason=template_in_use` + 引用任务列表，**拒绝删除**以保护历史任务数据；清理引用后可再删除。 |

**同名导入冲突处理** — 导入 CSV / JSON 时若目标模板名已存在，通过 `conflict_mode` 参数选择处理方式（支持 form 字段 / query 参数 / JSON body 三种传入方式）：

| conflict_mode | HTTP | 行为 |
|---------------|------|------|
| `reject` (默认) | **409** | 拒绝导入，响应体含 `conflict: "name_exists"` + `existing_id` 供前端提示。 |
| `rename` | **201** | 自动追加 `_2` / `_3` … 递增后缀，新建独立模板，**原模板内容不变**。 |
| `overwrite` | **200** | 保留原 ID，替换 rows / cols / description / wells 内容；响应含 `overwritten: true` 标记。 |

示例：

```bash
# 重命名模式导入 JSON 模板
curl -X POST http://localhost:5000/api/templates/import?conflict_mode=rename \
  -F "name=我的96孔板" \
  -F "file=@template.json"

# 覆盖模式导入（原模板内容会被替换）
curl -X POST http://localhost:5000/api/templates/import \
  -H "Content-Type: application/json" \
  -d '{"name":"96孔标准板","rows":8,"cols":12,"conflict_mode":"overwrite","wells":[...]}'
```

#### 步骤1.8：任务复跑（复制 / 导出方案 / 导入方案）

同一套板位和配液参数想再做一批时，无需从头新建，可使用任务复跑功能：

| 操作 | 说明 |
|------|------|
| **复制成新草稿** | `POST /api/tasks/<id>/copy` ，将现有任务复制为新草稿。复制内容：模板、总体积、孔位分配、已选引物/试剂。**不复制**：审批状态、库存扣减、历史记录。 |
| **导出方案 JSON** | `GET /api/tasks/<id>/export/json` ，下载完整任务方案 JSON，含 schema_version、task、template、wells、reagent_usage、primer_usage。 |
| **导入方案** | `POST /api/tasks/import` ，从 JSON 文件导入任务方案，导入后状态为 **草稿**，可重新生成、批准、撤销。 |

**可复制的任务状态**：草稿 (draft)、待复核 (pending_review)、已批准 (approved) 均可复制；已驳回 (rejected)、已撤销 (revoked) 不可复制。

**导入冲突拦截**（全量校验，失败无脏数据）：

| 校验项 | 失败响应 | 说明 |
|--------|----------|------|
| 模板不存在 | HTTP 400 | 导入的模板 ID 在当前库中不存在 |
| 模板尺寸不匹配 | HTTP 400 | 模板存在但行数/列数与导入数据不符 |
| 试剂不存在 | HTTP 400 | 导入引用的试剂在当前库中不存在 |
| 引物不存在 | HTTP 400 | 导入引用的引物在当前库中不存在 |
| 任务重名 | HTTP 409 | 任务名称已存在，响应含 `conflict=name_exists` + `existing_id` |

**任务重名冲突处理**：通过 `conflict_mode` 参数控制（任务导入仅支持 reject 和 rename）：

| conflict_mode | HTTP | 行为 |
|---------------|------|------|
| `reject` (默认) | **409** | 拒绝导入，提示重名 |
| `rename` | **201** | 自动追加 `_2` / `_3` … 递增后缀，新建独立任务 |

示例：

```bash
# 复制任务为新草稿
curl -X POST http://localhost:5000/api/tasks/1/copy \
  -H "Content-Type: application/json" \
  -d '{"name": "我的任务_副本"}'

# 导出任务方案 JSON
curl -o task_plan.json http://localhost:5000/api/tasks/1/export/json

# 导入任务方案（重命名模式处理重名）
curl -X POST http://localhost:5000/api/tasks/import?conflict_mode=rename \
  -F "file=@task_plan.json"
```

#### 步骤1.85：锁定包（Protocol Lock Package）

锁定包将实验参数（模板、引物、Master Mix、水、体系体积、偏差备注）**冻结打包**，保证复跑实验时参数完全一致。**严格模式**：依赖缺失或停用时直接报错，**绝不静默回退**到默认试剂。

| 操作 | 前端入口 | API | 说明 |
|------|----------|-----|------|
| **从任务建包** | 锁定包 Tab → +新建 → 选来源任务 | `POST /api/lock-packages` 带 `task_id` | 自动提取任务的引物/试剂冻结 |
| **手动建包** | 锁定包 Tab → +新建 → 不选任务 | `POST /api/lock-packages` 带各参数 | 手动指定引物、Master Mix、水 |
| **应用到任务** | 锁定包卡片 → ▶️ 应用建任务 | `POST /api/lock-packages/<id>/apply` | **自动生成方案**，参数缺失直接报错 |
| **停用/启用** | 锁定包卡片 → ⏸ 停用 / ▶ 启用 | `POST /api/lock-packages/<id>/disable\|/enable` | 停用后禁止新建任务，历史任务不受影响 |
| **复制** | 锁定包卡片 → 📋 复制 | `POST /api/lock-packages/<id>/copy` | 生成独立副本，可重命名 |
| **导入导出** | 锁定包 Tab → 📥 导入 / 📄 导出 | `/api/lock-packages/export/json\|/csv` + `/import` | 支持重名冲突 reject/rename |

**严格模式行为（关键差异）**：

| 场景 | 普通任务 | 锁定包任务 / 从锁定包创建 |
|------|----------|--------------------------|
| 未指定引物 | 静默使用列表第一个 | ❌ 报错：未指定引物且关联锁定包 |
| 引物 ID 不存在 | 静默回退默认 | ❌ 报错：锁定的引物不存在 |
| Master Mix/水同理 | 静默回退 | ❌ 拦截 |
| 锁定包已停用 | 无影响 | ❌ 无法应用到新任务 |

```bash
# 创建锁定包（从任务自动冻结）
curl -X POST http://localhost:5000/api/lock-packages \
  -H "Content-Type: application/json" \
  -d '{"name": "2025Q2_Std_PCR", "task_id": 1, "operator": "user"}'

# 应用锁定包（自动生成方案，参数不全直接报错）
curl -X POST http://localhost:5000/api/lock-packages/1/apply \
  -H "Content-Type: application/json" \
  -d '{"task_name": "复跑_20250601", "auto_generate": true, "operator": "user"}'
```

#### 步骤1.9：编辑并重算预览（草稿 / 待复核）

草稿或待复核的任务想换模板、挪孔位、调总体积、补删样本孔，无需删除重跑，使用"编辑并重算预览"链路：

| 可编辑项 | 说明 |
|---------|------|
| **板位模板** | 可切换为任意已导入模板（行数/列数变化时，孔位按行列保留交集） |
| **总体积** | 调整每孔反应体系体积（如 20 µL → 25 µL） |
| **孔位分配** | 逐孔调整：样本 / 阳性对照 / 阴性对照 / 空孔，可指定样本名 |
| **样本孔增删** | 支持"自动填充样本"和"清空全部孔"一键操作 |

**保存前自动校验拦截**（校验失败不得保存，禁止留下半套方案）：

| 校验项 | 说明 |
|--------|------|
| 孔位冲突 | 同一行号列号重复分配 → 拦截 |
| 模板不存在 | 模板 ID 无效 → 拦截 |
| 孔位超范围 | 孔号超出模板行数/列数 → 拦截 |
| 非法孔位类型 | 不是 sample / positive_control / negative_control / empty → 拦截 |
| 样本不存在 | 引用了库中不存在的样本名 → 拦截 |
| 试剂/引物缺失 | 缺少 Master Mix / 水 / 引物 → 拦截 |
| 库存不足 | Master Mix 或引物可用量 < 所需量 → 拦截 |
| 低于最小移液体积 | 单孔某试剂 < 0.5 µL → 仅警告，不拦截 |

**保存后的影响**（保证审批、库存、历史记录不被改乱）：

- 自动创建 **pre_edit（编辑前）** 和 **edit（编辑后）** 两个版本快照
- 任务状态重置为 **草稿**，旧试剂用量清空（需重新生成方案 → 重新复核 → 重新批准）
- 差异摘要写入 `history` 表（含模板/体积/孔位增删改明细）
- **不触碰**已批准扣减的库存、历史审批记录、已撤销记录

**只读状态**：**已批准 (approved)** 和 **已撤销 (revoked)** 状态的任务不可编辑，所有编辑接口返回 HTTP 409。

**回退与重新生成**：可在"版本快照"区对比 pre_edit 和 edit 两个版本，点击"回滚到版本"可在编辑前后任意切换，回滚到草稿状态后重新生成方案即可继续审批链路。

**差异导出**：编辑面板中点击"📤 导出差异摘要"，可下载结构化 TXT 文件，包含所有变更明细 + 校验错误/警告。

**操作入口**：
- 任务详情页 → 草稿/待复核状态显示 **"✏️ 编辑并重算"** 按钮
- 已批准/已撤销显示灰色禁用的"编辑"按钮，并提示"只读"

#### 步骤2：创建任务

打开 **"任务管理"** 标签页：

1. 点击 **"新建任务"**
2. 填写任务名称、选择板位模板、设置总体系体积（如 20 µL）
3. 点击"创建"，任务进入 **草稿** 状态

#### 步骤3：生成配液方案

1. 在任务列表中找到刚创建的草稿任务
2. 点击任务卡片上的 **"🔬 生成方案"** 按钮（或先点 **"👁 查看"** 进详情页，再点 **"🔬 生成方案"**）
3. 在弹窗中选择引物、Master Mix 试剂、水试剂
4. 点击 **"确认生成"**，系统自动计算每孔配方
5. 生成后任务进入 **待复核** 状态

#### 步骤4：复核与批准

1. 点击任务卡片上的 **"👁 查看"** 按钮，查看配液详情
2. 检查每孔用量、对照孔设置、库存是否充足
3. 可在 **"版本快照"** 区块选择两个版本，点 **"🔍 对比差异"** 查看孔位/试剂/引物的新增、删除、修改明细
4. 如无问题，点击 **"✓ 批准"** 按钮
5. 若存在低于最小移液体积的警告：
   - 需要先点击 **"📝 添加偏差备注"**
   - 填写偏差说明后保存
   - 再点击"批准"，选择"忽略最小移液警告"

批准后库存自动扣减。

#### 步骤5：导出报告

1. 在任务详情页点击 **"📊 导出报告"**
2. 在弹窗中选择格式：**"CSV 格式"** 或 **"JSON 格式"**
3. 浏览器自动下载报告，包含：孔位明细、试剂使用汇总、库存扣减记录

#### 步骤6：撤销与驳回

- **撤销批准**：已批准的任务可以撤销，库存自动退回
- **驳回**：待复核的任务可以驳回，驳回后可重新生成方案

#### 步骤7：历史记录（高级筛选 + 导出）

打开 **"历史记录"** 标签页：

##### 🔍 筛选条件（全部可选，组合生效）

| 筛选项 | 说明 | 持久化 |
|--------|------|--------|
| **任务** | 下拉选择某个任务，只看该任务相关记录（创建、生成、批准、撤销、驳回等） | ✅ 刷新后保留（localStorage） |
| **操作类型** | 按 action_type 精确筛选（创建任务/生成方案/批准/驳回/回滚快照/导出历史等 20+ 种） | ✅ 刷新后保留 |
| **起始日期** | `YYYY-MM-DD`，筛选 `created_at >= 该日 00:00:00` | ✅ 刷新后保留 |
| **结束日期** | `YYYY-MM-DD`，筛选 `created_at <= 该日 23:59:59` | ✅ 刷新后保留 |
| **关键词搜索** | 模糊匹配 `action` / `action_type` / `detail` / `operator` / `task_id`，包含即命中 | ✅ 刷新后保留 |
| **返回条数** | 20 / 50 / 100 / 200 / 500 / 1000；接口最大 5000，超限自动截断并警告 | ✅ 刷新后保留 |

点击 **"🔍 应用筛选"** 生效并持久化；点击 **"↺ 重置"** 清空所有筛选并移除本地存储。

##### 📊 页面信息

- **筛选摘要条**（蓝色）：显示当前所有已应用的筛选条件，一目了然
- **警告条**（橙色）：`limit` 超过上限被截断、未知操作类型等非致命警告
- **错误条**（红色）：非法日期格式、`start_date > end_date`、`limit` 非正数等致命错误，此时 records 为空，HTTP 400
- **结果计数**：`共 X 条匹配，当前显示 Y 条`（total 不依赖 limit，真实匹配数）
- **无结果提示**：有筛选但 0 条时，显示"😕 没有匹配的历史记录 + 放宽条件建议"，不再是空白的"暂无"

##### 📤 导出（与页面结果一致）

| 按钮 | 接口 | 说明 |
|------|------|------|
| 📄 导出 JSON | `GET /api/history/export/json` | **吃同一套筛选 query 参数**，导出 JSON 含：`export_time`、`filter_summary`、`filters`（结构化）、`matched_count`、`exported_count`、`warnings`、`history`（仅匹配记录）、`tasks/samples/primers/reagents/inventory_logs` |
| 📊 导出 CSV | `GET /api/history/export/csv` | **吃同一套筛选 query 参数**，CSV 文件头 4 行注释：导出时间、筛选条件摘要、匹配/导出条数、警告。字段列：`id, task_id, action, action_type, detail, operator, created_at` |

> ✅ 导出动作本身会写入 `history` 表，`action=export`，`action_type=history_exported_json` 或 `history_exported_csv`，detail 字段包含筛选摘要 + 匹配数 + 导出数，可用于审计"谁在何时导出了什么范围的数据"。

##### 🔧 接口参数总览（所有 history 接口统一参数）

`GET /api/history`、`GET /api/history/export/json`、`GET /api/history/export/csv` 均接受以下 **query 参数**（全部可选）：

| 参数 | 类型 | 默认 | 校验 & 行为 |
|------|------|------|-------------|
| `task_id` | int | — | 非整数 → HTTP 400 |
| `action_type` | string | — | 不在已知列表中 → 警告 + 正常查询（可能 0 条） |
| `start_date` | string | — | 非法格式（不是 `YYYY-MM-DD[ HH:MM[:SS]]`）→ HTTP 400 |
| `end_date` | string | — | 非法格式 → HTTP 400；仅日期时补到 `23:59:59` |
| `keyword` | string | — | 空字符串等同未提供；前后空白自动 trim |
| `limit` | int | 100 | `<1` → HTTP 400；`>5000` → 警告 + 截断为 5000 |

`GET /api/history` 响应结构（200 或 400 均返回 JSON）：

```json
{
  "records": [ { "id": 1, "task_id": 2, "action": "create", "action_type": "task_created", "detail": "...", "operator": "system", "created_at": "2025-..." }, ... ],
  "total": 42,
  "filters": "任务#2 | 操作类型:创建任务 | 起始:2025-01-01 00:00:00 | 条数上限:100",
  "errors": [],
  "warnings": []
}
```

`GET /api/history/filters` 返回前端填充筛选下拉所需的元数据：`{ tasks, action_types, max_limit, default_limit }`。

##### 🧪 验证命令（curl / PowerShell）

**1️⃣ 组合筛选（按任务 + 批准操作 + 时间范围 + 关键词）**
```bash
curl -s "http://localhost:5000/api/history?task_id=1&action_type=task_approved&start_date=2025-01-01&end_date=2025-12-31&keyword=库存&limit=50" | jq '{total, filters, count: .records | length}'
```

**PowerShell 版本：**
```powershell
(iwr "http://localhost:5000/api/history?task_id=1&action_type=task_approved&start_date=2025-01-01&end_date=2025-12-31&keyword=库存&limit=50").Content | ConvertFrom-Json | Select-Object total, filters, @{n='count';e={$_.records.Count}}
```

**2️⃣ 关键词无结果（确认返回友好提示而非空白）**
```bash
curl -s "http://localhost:5000/api/history?keyword=这个关键词肯定不存在xyz123" | jq '{total, count: .records | length, errors, warnings}'
```
期望：`total=0, count=0, errors=[], warnings=[]`（HTTP 200，非 500）

**3️⃣ 非法日期拦截（HTTP 400 + 清晰错误）**
```bash
curl -v "http://localhost:5000/api/history?start_date=2025/01/01"
# 期望: HTTP 400，body.errors 包含 "start_date 格式不合法，请使用 YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS"

curl -v "http://localhost:5000/api/history?start_date=2025-12-31&end_date=2025-01-01"
# 期望: HTTP 400，body.errors 包含 "start_date 不能晚于 end_date"
```

**4️⃣ 过大 limit 自动截断（HTTP 200 + 警告提示）**
```bash
curl -s "http://localhost:5000/api/history?limit=99999" | jq '{warnings, returned: (.records | length)}'
# 期望: warnings=["limit 超过上限 5000，已自动截断为 5000"], returned<=5000
```

**5️⃣ 按筛选导出 JSON（与页面结果一致）**
```bash
curl -s -o filtered_history.json -w "HTTP %{http_code}, size=%{size_download}\n" \
  "http://localhost:5000/api/history/export/json?action_type=snapshot_created&limit=100"
# 期望: HTTP 200，JSON 文件中 filter_summary / matched_count / exported_count 与查询接口一致
jq '{filter_summary, matched_count, exported_count, history_count: (.history | length)}' filtered_history.json
```

**6️⃣ 按筛选导出 CSV（首行注释带筛选摘要）**
```bash
curl -s -o filtered_history.csv "http://localhost:5000/api/history/export/csv?task_id=1&limit=50"
# 期望: CSV 前 4 行以 # 开头，分别是 导出时间 / 筛选条件 / 匹配+导出条数 / 警告
head -6 filtered_history.csv
```

**7️⃣ 刷新保留筛选条件 + 服务重启后查询一致（GUI 验证）**
```
① 在浏览器历史记录页 → 设置任务=某任务 + 操作类型=生成方案 + 关键词=方案 + limit=20
② 点 "🔍 应用筛选"，记下显示的 "共 X 条匹配"
③ 按 F5 刷新页面 → 筛选控件值自动恢复，结果与刷新前完全一致
④ 停掉服务（Ctrl+C）→ 重新执行 python run.py 启动
⑤ 再次进入历史记录页 → 点刷新 → 查询接口正常返回，数据与重启前一致（SQLite 持久化）
```

##### 📁 筛选方案预设（Filter Presets）—— 可复用、持久化、可导出

将一套复杂的筛选条件（任务、操作类型、时间范围、关键词、条数限制）**命名保存**为方案，后续一键应用，无需重复配置。

**核心特性：**
| 特性 | 说明 |
|------|------|
| **💾 命名保存** | 给当前筛选条件起个名字和描述，保存为预设方案 |
| **⭐ 设为默认** | 任意方案可设为默认，页面加载时自动应用 |
| **🔄 切换应用** | 下拉选择任意已保存方案，一键填充所有筛选条件 |
| **🗑️ 删除方案** | 不再需要的方案可删除；删除默认方案时自动降级到最早创建的方案 |
| **🔒 冲突处理** | 同名方案创建/更新时自动拦截，提示明确错误 |
| **📦 持久化** | 方案存储在 SQLite `history_filter_presets` 表，**刷新浏览器/重启服务均不丢失** |
| **📜 审计记录** | 所有预设操作（创建/更新/删除/切换默认）均写入 `history` 表，可追溯 |

**前端操作入口**（历史记录页筛选栏新增"筛选方案"行）：
- 下拉选择框：列出所有已保存方案，选择即应用
- 💾 保存：将当前筛选条件保存为新方案（弹窗输入名称、描述、是否设为默认）
- ⭐ 设默认：将当前选中的方案设为默认
- 🗑️ 删除：删除当前选中的方案
- 🔄 刷新：重新加载方案列表

**📤 导出增强**（JSON/CSV 导出均包含）：
- `export_time`：导出时间戳
- `filter_summary`：筛选条件摘要（如 `任务#1 | 操作类型:批准 | 条数上限:100`）
- `matched_count`：符合条件的总记录数（不受 limit 影响）
- `exported_count`：实际导出的记录数
- `filters`：结构化的筛选参数对象
- 空结果导出仍返回 **HTTP 200**，含完整元数据（`matched=0, exported=0`），不报错

**🔌 筛选方案 API 端点**：
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/history/presets` | 获取所有方案列表 |
| GET | `/api/history/presets/default` | 获取当前默认方案 |
| GET | `/api/history/presets/<id>` | 获取单个方案详情 |
| POST | `/api/history/presets` | 创建新方案（body: `{name, description?, task_id?, action_type?, start_date?, end_date?, keyword?, limit?, is_default?}`） |
| PUT | `/api/history/presets/<id>` | 更新方案（body 字段同上） |
| POST | `/api/history/presets/<id>/default` | 将该方案设为默认 |
| DELETE | `/api/history/presets/<id>` | 删除方案；删除默认方案时自动降级 |

**响应示例（创建成功）：**
```json
{
  "message": "筛选方案 \"仅批准操作\" 创建成功",
  "preset": {
    "id": 1,
    "name": "仅批准操作",
    "description": "只查看任务批准相关记录",
    "task_id": null,
    "action_type": "task_approved",
    "start_date": null,
    "end_date": null,
    "keyword": null,
    "limit": 50,
    "is_default": 0,
    "created_at": "2025-06-18T10:00:00",
    "updated_at": "2025-06-18T10:00:00"
  }
}
```

**错误处理：**
- **400** 名称为空 / 名称已存在 / 非法日期格式 / 方案不存在
- **404** 方案 ID 不存在
- 所有错误均含中文 `error` 字段，提示明确

**8️⃣ 验证筛选方案持久化（保存后重启仍在）**
```
① 启动服务，创建筛选方案：
   curl -X POST http://localhost:5000/api/history/presets \
     -H "Content-Type: application/json" \
     -d '{"name":"持久化测试方案","action_type":"task_approved","limit":100,"is_default":true}'
② 记下返回的 preset id，查询验证：
   curl -s http://localhost:5000/api/history/presets/<id> | jq '.preset.name'
③ 停掉服务（Ctrl+C）→ 重新启动 python run.py
④ 再次查询同一 ID，验证方案仍存在且 is_default=1
   curl -s http://localhost:5000/api/history/presets/<id> | jq '{name, is_default}'
⑤ 验证默认方案接口：
   curl -s http://localhost:5000/api/history/presets/default | jq '.preset.name'
```

**9️⃣ 验证按任务筛选后两种格式导出一致**
```
# 先按任务筛选查询
curl -s "http://localhost:5000/api/history?task_id=1&limit=100" | jq '{total, count: .records | length}'

# 导出 JSON
curl -s "http://localhost:5000/api/history/export/json?task_id=1&limit=100" | jq '{matched_count, exported_count, filter_summary}'

# 导出 CSV，检查首行注释
curl -s "http://localhost:5000/api/history/export/csv?task_id=1&limit=100" | head -4
# 应包含：导出时间、筛选条件摘要、匹配总数、导出条数
```

**1️⃣0️⃣ 验证同名方案冲突处理**
```
# 创建第一个方案
curl -X POST http://localhost:5000/api/history/presets \
  -H "Content-Type: application/json" \
  -d '{"name":"冲突测试","limit":50}'
# 期望: HTTP 201

# 同名再创建一次
curl -X POST http://localhost:5000/api/history/presets \
  -H "Content-Type: application/json" \
  -d '{"name":"冲突测试","limit":50}'
# 期望: HTTP 400，body.error 包含 "已存在"
```

**1️⃣1️⃣ 验证导出记录可查（审计追踪）**
```
# 执行一次导出
curl -s "http://localhost:5000/api/history/export/json?limit=5" > /dev/null

# 查询导出审计记录
curl -s "http://localhost:5000/api/history?action_type=history_exported_json&limit=5" | jq '{total, records: [.records[] | {detail, created_at}]}'
# 应能看到刚才的导出记录，detail 包含筛选摘要和匹配/导出数
```

### 验证命令

运行完整测试套件（74 个测试用例）：

**Windows PowerShell（推荐，自动处理编码）：**
```powershell
$env:PYTHONIOENCODING="utf-8" ; python -m tests.test_main
```

**Windows CMD：**
```cmd
set PYTHONIOENCODING=utf-8 && python -m tests.test_main
```

**Linux / macOS：**
```bash
python -m tests.test_main
```

> 注意：Windows 默认控制台编码为 GBK，测试输出中的中文和 µ 字符需要 UTF-8 编码支持，否则会因编码错误中断。设置 `PYTHONIOENCODING=utf-8` 可确保输出正常。

测试内容包括：

| 测试编号 | 测试名称 | 说明 |
|---------|---------|------|
| 1 | 单位换算 | 体积/浓度单位换算，含特殊字符 µ |
| 2-5 | 数据导入 | 样本、引物、试剂、板位模板导入 |
| 5b | 模板迁移 & 生命周期 | schema 迁移、事务回滚、重启可读、导入→任务→方案 |
| 5c | 模板导出 & 重新导入 | JSON/CSV 导出后再导入，孔位与类型完全一致 |
| 5d | 模板复制 | 深拷贝内容一致，支持自定义名称，复制品可建任务 |
| 5e | 导入冲突处理 | reject 拒绝 / rename 改名 / overwrite 覆盖三种模式 |
| 5f | 模板删除保护 | 被任务引用时 409 拦截（template_in_use），清理后可删 |
| 5g | 模板历史记录 | 模板类操作全量写入 history 表 |
| 6 | 孔位冲突检测 | 同一孔位重复分配拦截 |
| 7 | 非法单位拦截 | 导入/创建/生成三阶段均拦截非法体积单位，失败无脏数据 |
| 8 | 创建任务 | 多任务创建 |
| 9 | 生成配液方案 | 正常体积和小体积方案生成 |
| 10 | 正常体积批准 | 无警告时直接批准 |
| 11 | 最小移液拦截 | 低于最小移液体积时拦截，不扣库存 |
| 12 | 偏差备注后批准 | 添加偏差备注后可强制批准 |
| 13 | 库存扣减验证 | 批准后试剂、引物库存扣减 |
| 14 | 撤销确认 | 撤销后库存退回 |
| 15 | 驳回任务 | 驳回不扣减库存 |
| 16 | 历史记录与导出 | 历史记录完整性和 JSON/CSV 导出 |
| 17 | 报告导出 | 配液报告导出 |
| 18 | 库存不足拦截 | 库存不足时拦截，不预占库存 |
| 19 | 用户链路端到端 | 导出 JSON → 重新导入 → 复制模板 → 建任务生成方案 → 冲突拒绝（5 步完整链路） |
| 20-25 | 任务复跑全链路 | 复制任务、JSON 导入导出、导入冲突、导入后审批、状态限制、复跑全链路、重启一致 |
| 26 | 生成方案自动快照 | 生成配液方案后自动创建 generate 类型快照 |
| 27 | 快照列表与版本对比 | 列出所有版本快照，对比两个版本差异 |
| 28 | 快照回滚功能 | 回滚到指定版本，孔位/用量/状态完全恢复 |
| 29 | 回滚状态校验 | 已批准/已撤销任务禁止回滚，返回 HTTP 409 |
| 30 | 导出带快照摘要 & 导入还原 | 导出 JSON 含快照摘要，导入后还原历史快照 |
| 31 | 导入冲突拦截 & 无脏数据 | 版本不支持/重名整体拒绝，失败不留半套数据 |
| 32 | 快照数据持久化 | 重启后快照可读，数据完整 |
| 33 | 端到端回滚重生成批准 | 草稿快照 → 生成 → 回滚 → 重生成 → 批准 完整链路 |
| 34 | 快照操作历史记录 | 快照创建/对比/回滚/导入失败均写入 history |
| 35 | 前端API契约 | 快照列表/对比/创建/回滚接口字段完整，前端可直接解析渲染 |
| 36 | 已批准/已撤销回滚拦截 | 已批准和已撤销任务禁止回滚，返回 HTTP 409 |
| 37 | 快照对比边界 & 详情 | 同版本对比全零、快照详情 API 字段完整、无效版本错误处理 |
| 38 | 对比API数据结构契约 | well/reagent/primer differences 结构稳定，前端解析无歧义 |
| 39 | README & GUI 入口按钮一致性 | 文档与前端按钮名称一一对应，任务列表 API status 字段完整 |
| 40 | 编辑预览 & 状态拦截 | 草稿/待复核任务可预览，已批准/已撤销编辑被拦截（409） |
| 41 | 编辑校验拦截 | 孔位冲突/模板不存在/样本不存在/非法类型/超范围/库存不足全部拦截 |
| 42 | 编辑差异计算 | 总体积/模板/孔位增删改差异正确识别，空编辑无差异 |
| 43 | 编辑保存 | pre_edit + edit 双快照自动创建，状态重置为 draft，差异摘要写 history，旧用量清空 |
| 44 | 编辑后回滚 & 重生成 | pre_edit/edit 两个版本可切换回滚，回退后可重新生成方案 |
| 45 | 编辑数据重启持久化 | 重启后任务配置/快照/历史记录全部保留，API 仍可查看和操作 |
| 46 | 编辑端到端全链路 | GET /edit → validate → diff → POST /edit → 快照对比 → 回滚完整链路 |

## CSV 数据格式

### 样本 CSV

```csv
name,volume,volume_unit,concentration,concentration_unit,description
Sample_001,100,ul,50,ng/uL,样本1
```

### 引物 CSV

```csv
name,sequence,volume,volume_unit,concentration,concentration_unit,description
Test_Primer_F,ATCGATCGATCGATCG,500,ul,10,uM,正向引物
```

### 试剂 CSV

```csv
name,type,volume,volume_unit,concentration,concentration_unit,min_pipette_volume,description
Taq_Man_Master_Mix,master_mix,5000,ul,2,x,0.5,2x 预混液
```

试剂类型：`master_mix`、`water`、`enzyme`、`buffer`、`dntp`、`other`

### 板位模板 CSV

网格格式，第一行第一列为空，表头为列号（1-12），第一列为行号（A-H）：

```csv
,1,2,3,4,5,6,7,8,9,10,11,12
A,Sample_001,Sample_002,Sample_003,PC,NC,EMPTY,...
B,...
```

单元格值：
- 样本名称：分配样本到该孔
- `PC`：阳性对照孔
- `NC`：阴性对照孔
- `EMPTY`：空孔

## 项目结构

```
zgw-00139/
├── app/                      # 后端应用
│   ├── __init__.py          # 应用工厂
│   ├── database.py          # 数据库初始化
│   ├── routes/              # API 路由
│   │   ├── main_routes.py
│   │   ├── sample_routes.py
│   │   ├── primer_routes.py
│   │   ├── reagent_routes.py
│   │   ├── template_routes.py
│   │   ├── task_routes.py
│   │   ├── history_routes.py
│   │   └── report_routes.py
│   └── services/            # 业务服务
│       ├── unit_converter.py      # 单位换算
│       ├── liquid_handling_engine.py  # 配液计算引擎
│       ├── data_importer.py        # 数据导入
│       ├── task_service.py         # 任务管理
│       ├── snapshot_service.py     # 版本快照与回滚
│       ├── history_service.py      # 历史记录
│       └── report_service.py       # 报告生成
├── static/                   # 前端静态文件
│   ├── index.html
│   ├── css/style.css
│   └── js/app.js
├── data/                     # 数据目录
│   ├── samples/
│   ├── primers/
│   ├── reagents/
│   ├── templates/
│   └── pcr_planner.db        # SQLite 数据库
├── tests/                    # 测试套件
│   └── test_main.py
├── run.py                    # 应用入口
└── requirements.txt          # 依赖清单
```

## 数据库表结构

- `samples`：样本库
- `primers`：引物库
- `reagents`：试剂库存
- `plate_templates` / `template_wells`：板位模板
- `tasks` / `task_wells`：任务与孔位数据
- `task_reagent_usage` / `task_primer_usage`：试剂/引物使用记录
- `task_snapshots`：任务版本快照（含完整状态、孔位、用量）
- `history`：操作历史
- `reagent_inventory_log` / `primer_inventory_log`：库存变更日志

## API 接口概览

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/stats` | 统计信息 |
| POST | `/api/samples/import` | 导入样本 CSV |
| POST | `/api/primers/import` | 导入引物 CSV |
| POST | `/api/reagents/import` | 导入试剂 CSV |
| POST | `/api/templates/import` | 导入板位模板（CSV/JSON），支持冲突处理 |
| GET | `/api/templates/<id>/export/json` | 导出模板为 JSON |
| GET | `/api/templates/<id>/export/csv` | 导出模板为 CSV |
| POST | `/api/templates/<id>/copy` | 复制模板 |
| DELETE | `/api/templates/<id>` | 删除模板（被引用时拦截） |
| GET | `/api/tasks` | 任务列表 |
| POST | `/api/tasks` | 创建任务 |
| POST | `/api/tasks/<id>/generate` | 生成配液方案 |
| POST | `/api/tasks/<id>/approve` | 批准任务 |
| POST | `/api/tasks/<id>/reject` | 驳回任务 |
| POST | `/api/tasks/<id>/revoke` | 撤销批准 |
| POST | `/api/tasks/<id>/deviation` | 添加偏差备注 |
| POST | `/api/tasks/<id>/copy` | 复制任务为新草稿 |
| GET | `/api/tasks/<id>/export/json` | 导出任务方案 JSON |
| POST | `/api/tasks/import` | 从 JSON 导入任务方案（支持 `conflict_mode`） |
| GET | `/api/tasks/<id>/snapshots` | 任务快照列表（按版本号倒序） |
| GET | `/api/tasks/<id>/snapshots/<version>` | 指定版本快照详情 |
| GET | `/api/tasks/<id>/snapshots/compare` | 对比两个版本快照差异（`version_a` + `version_b`） |
| POST | `/api/tasks/<id>/snapshots/rollback` | 回滚到指定版本快照 |
| POST | `/api/tasks/<id>/snapshots` | 手动创建快照 |
| **GET** | **`/api/tasks/<id>/edit`** | **获取编辑预览**（任务信息 + 当前模板/孔位 + 可用模板/样本。已批准/已撤销返回 409） |
| **POST** | **`/api/tasks/<id>/edit/validate`** | **校验编辑数据**（孔位冲突/模板/范围/样本/库存拦截，返回 valid/errors/warnings） |
| **POST** | **`/api/tasks/<id>/edit/diff`** | **计算编辑差异**（总体积/模板/孔位增删改摘要） |
| **POST** | **`/api/tasks/<id>/edit`** | **保存编辑**（pre_edit + edit 双快照 + 写历史 + 状态重置为 draft。已批准/已撤销返回 409） |
| **GET** | **`/api/history`** | **历史记录（带高级筛选）**。query 参数（均可选）：`task_id`(int)、`action_type`(string)、`start_date`(YYYY-MM-DD)、`end_date`(YYYY-MM-DD)、`keyword`(模糊搜索)、`limit`(int, 默认100, 上限5000)。返回 `{records, total, filters, errors, warnings}`。参数错误时 HTTP 400 + errors 明细 |
| **GET** | **`/api/history/filters`** | **筛选元数据**。返回任务列表、所有操作类型枚举、`max_limit=5000`、`default_limit=100`，用于前端填充下拉选项 |
| **GET** | **`/api/history/export/json`** | **导出历史 JSON（吃同一套筛选参数）**。与页面查询完全一致的 query 参数。导出文件含 `export_time`、`filter_summary`、`filters`、`matched_count`、`exported_count`、匹配的 `history[]`。导出动作本身写入 history 表 |
| **GET** | **`/api/history/export/csv`** | **导出历史 CSV（吃同一套筛选参数）**。与页面查询完全一致的 query 参数。CSV 前 4 行 `#` 注释：导出时间 / 筛选摘要 / 匹配+导出条数 / 警告。导出动作本身写入 history 表 |
| GET | `/api/reports/task/<task_id>` | 获取任务报告（内嵌 JSON） |
| GET | `/api/reports/task/<task_id>/json` | 导出任务报告 JSON |
| GET | `/api/reports/task/<task_id>/csv` | 导出任务报告 CSV |

## 配液计算规则

默认配比（体积百分比）：
- **样本**：10%
- **引物**：10%
- **Master Mix**：50%
- **水**：补足剩余体积

阳性对照孔：与样本孔配方相同
阴性对照孔：不含样本，水补足体积

默认最小移液体积：0.5 µL
