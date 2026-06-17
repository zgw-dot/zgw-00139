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

### 报告与审计
- 每孔用量明细，包含样本、引物、Master Mix、水的体积
- 对照孔标识和计算来源说明
- 库存扣减来源追踪
- 重启后数据一致性保证（SQLite 持久化）

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

#### 步骤2：创建任务

打开 **"任务管理"** 标签页：

1. 点击 **"新建任务"**
2. 填写任务名称、选择板位模板、设置总体系体积（如 20 µL）
3. 点击"创建"，任务进入 **草稿** 状态

#### 步骤3：生成配液方案

1. 在任务列表中找到刚创建的任务
2. 点击 **"生成方案"**
3. 选择引物、Master Mix 试剂、水试剂
4. 点击"确认生成"，系统自动计算每孔配方
5. 生成后任务进入 **待复核** 状态

#### 步骤4：复核与批准

1. 点击任务的 **"查看"** 按钮，查看配液详情
2. 检查每孔用量、对照孔设置、库存是否充足
3. 如无问题，点击 **"批准"** 按钮
4. 若存在低于最小移液体积的警告：
   - 需要先点击 **"添加偏差备注"**
   - 填写偏差说明后保存
   - 再点击"批准"，选择"忽略最小移液警告"

批准后库存自动扣减。

#### 步骤5：导出报告

1. 在任务详情页点击 **"导出报告"**
2. 支持 JSON 和 CSV 两种格式
3. 报告包含：孔位明细、试剂使用汇总、库存扣减记录

#### 步骤6：撤销与驳回

- **撤销批准**：已批准的任务可以撤销，库存自动退回
- **驳回**：待复核的任务可以驳回，驳回后可重新生成方案

#### 步骤7：历史记录

打开 **"历史记录"** 标签页：
- 查看所有操作历史
- 支持按任务筛选
- 支持 JSON/CSV 导出

### 验证命令

运行完整测试套件（20 个测试用例）：

**Windows PowerShell（推荐，自动处理编码）：**
```powershell
$env:PYTHONIOENCODING="utf-8" ; python tests/test_main.py
```

**Windows CMD：**
```cmd
set PYTHONIOENCODING=utf-8 && python tests\test_main.py
```

**Linux / macOS：**
```bash
python tests/test_main.py
```

> 注意：Windows 默认控制台编码为 GBK，测试输出中的中文和 µ 字符需要 UTF-8 编码支持，否则会因编码错误中断。设置 `PYTHONIOENCODING=utf-8` 可确保输出正常。

测试内容包括：

| 测试编号 | 测试名称 | 说明 |
|---------|---------|------|
| 1 | 单位换算 | 体积/浓度单位换算，含特殊字符 µ |
| 2-5 | 数据导入 | 样本、引物、试剂、板位模板导入 |
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
| 19 | 重启后数据一致性 | 模拟重启验证数据持久化 |

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
- `history`：操作历史
- `reagent_inventory_log` / `primer_inventory_log`：库存变更日志

## API 接口概览

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/stats` | 统计信息 |
| POST | `/api/samples/import` | 导入样本 CSV |
| POST | `/api/primers/import` | 导入引物 CSV |
| POST | `/api/reagents/import` | 导入试剂 CSV |
| POST | `/api/templates/import` | 导入板位模板 CSV |
| GET | `/api/tasks` | 任务列表 |
| POST | `/api/tasks` | 创建任务 |
| POST | `/api/tasks/<id>/generate` | 生成配液方案 |
| POST | `/api/tasks/<id>/approve` | 批准任务 |
| POST | `/api/tasks/<id>/reject` | 驳回任务 |
| POST | `/api/tasks/<id>/revoke` | 撤销批准 |
| POST | `/api/tasks/<id>/deviation` | 添加偏差备注 |
| GET | `/api/history` | 历史记录 |
| GET | `/api/history/export/json` | 导出历史 JSON |
| GET | `/api/history/export/csv` | 导出历史 CSV |
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
