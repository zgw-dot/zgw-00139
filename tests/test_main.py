import sys
import os
import json
import sqlite3

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.services.unit_converter import UnitConverter


def assertAlmostEqual(a, b, msg="", places=3):
    if round(abs(a - b), places) != 0:
        raise AssertionError(f"{msg}: {a} != {b}")


def run_tests():
    db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'test_pcr_planner.db')
    
    if os.path.exists(db_path):
        os.remove(db_path)
    
    os.environ['FLASK_ENV'] = 'testing'
    
    from flask import Flask
    from flask_cors import CORS
    from app.database import init_db
    
    test_app = Flask(__name__, static_folder='../static', static_url_path='/static')
    test_app.config['SECRET_KEY'] = 'test-key'
    test_app.config['DATABASE'] = db_path
    test_app.config['DATA_DIR'] = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
    CORS(test_app)
    init_db(test_app)
    
    from app.routes.main_routes import main_bp
    from app.routes.sample_routes import sample_bp
    from app.routes.primer_routes import primer_bp
    from app.routes.reagent_routes import reagent_bp
    from app.routes.template_routes import template_bp
    from app.routes.task_routes import task_bp
    from app.routes.history_routes import history_bp
    from app.routes.report_routes import report_bp
    
    @test_app.route('/data/<path:filename>')
    def serve_data_file(filename):
        from flask import send_from_directory
        return send_from_directory(test_app.config['DATA_DIR'], filename)
    
    test_app.register_blueprint(main_bp)
    test_app.register_blueprint(sample_bp, url_prefix='/api/samples')
    test_app.register_blueprint(primer_bp, url_prefix='/api/primers')
    test_app.register_blueprint(reagent_bp, url_prefix='/api/reagents')
    test_app.register_blueprint(template_bp, url_prefix='/api/templates')
    test_app.register_blueprint(task_bp, url_prefix='/api/tasks')
    test_app.register_blueprint(history_bp, url_prefix='/api/history')
    test_app.register_blueprint(report_bp, url_prefix='/api/reports')
    
    test_results = []
    
    print("=" * 60)
    print("PCR 板位配液规划工具 - 测试套件")
    print("=" * 60)
    
    with test_app.app_context():
        from app.database import get_db
        from app.services.task_service import TaskService
        from app.services.history_service import HistoryService
        from app.services.report_service import ReportService
        from app.services.data_importer import DataImporter
        
        db = get_db(test_app)
        
        test_unit_conversion(test_results)
        test_import_samples(db, test_results)
        test_import_primers(db, test_results)
        test_import_reagents(db, test_results)
        test_import_template(db, test_results)
        test_template_migration_and_lifecycle(db, db_path, test_results)
        test_template_export_and_reimport(db, test_app, test_results)
        test_template_copy(db, test_app, test_results)
        test_template_import_conflict(db, test_app, test_results)
        test_template_delete_protection(db, test_app, test_results)
        test_template_history_records(db, test_results)
        test_well_conflict(db, test_results)
        test_invalid_unit_interception(db, test_app, test_results)
        test_create_tasks(db, test_results)
        test_generate_plans(db, test_results)
        test_normal_approval(db, test_results)
        test_min_pipette_blocking(db, test_results)
        test_deviation_and_approve(db, test_results)
        test_inventory_deduction(db, test_results)
        test_revoke_approval(db, test_results)
        test_reject_task(db, test_results)
        test_history_records(db, test_app, db_path, test_results)
        test_report_export(db, test_results)
        test_insufficient_inventory(db, test_results)
        test_user_template_flow_e2e(db, test_app, test_results)
        test_task_copy(db, test_app, test_results)
        test_task_export_import(db, test_app, test_results)
        test_task_import_conflict(db, test_app, test_results)
        test_task_import_then_approve(db, test_app, test_results)
        test_task_copy_status_restrictions(db, test_app, test_results)
        test_task_e2e_copy_import_approve(db, test_app, db_path, test_results)
        test_data_persistence(db, test_app, db_path, test_results)
        test_snapshot_create_on_generate(db, test_app, test_results)
        test_snapshot_list_and_compare(db, test_app, test_results)
        test_snapshot_rollback(db, test_app, test_results)
        test_snapshot_rollback_status_check(db, test_app, test_results)
        test_snapshot_export_import(db, test_app, test_results)
        test_snapshot_import_conflict(db, test_app, test_results)
        test_snapshot_persistence(db, test_app, db_path, test_results)
        test_snapshot_e2e_rollback_regenerate_approve(db, test_app, test_results)
        test_snapshot_history_records(db, test_app, test_results)
        test_snapshot_frontend_api_contract(db, test_app, test_results)
        test_snapshot_rollback_status_block_api(db, test_app, test_results)
        test_snapshot_compare_same_version_and_detail(db, test_app, test_results)
    
    if os.path.exists(db_path):
        os.remove(db_path)
    
    import re
    
    test_func_names = re.findall(r'def (test_\w+)\(', open(__file__, encoding='utf-8').read())
    expected_total = len(test_func_names)
    actual_total = len(test_results)
    
    doc_checks = []
    
    if expected_total != actual_total:
        doc_checks.append(f"测试函数数量({expected_total}) != 测试结果数量({actual_total})，检查是否有 AssertionError 被静默吞掉")
    
    test_entry = os.path.join(os.path.dirname(__file__), 'test_main.py')
    if not os.path.exists(test_entry):
        doc_checks.append(f"测试入口文件不存在: {test_entry}")
    
    fake_entry = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'run_tests.py')
    if os.path.exists(fake_entry):
        doc_checks.append(f"发现已废弃的假入口 {fake_entry}，只允许使用 tests/test_main.py")
    
    readme_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'README.md')
    if os.path.exists(readme_path):
        readme = open(readme_path, encoding='utf-8').read()
        
        m = re.search(r'运行完整测试套件[（(](\d+) 个测试用例[）)]', readme)
        if m:
            readme_count = int(m.group(1))
            if readme_count != expected_total:
                doc_checks.append(f"README 写的测试数({readme_count}) != 实际测试函数数({expected_total})")
        
        if 'run_tests.py' in readme:
            doc_checks.append("README 项目结构或命令中还引用不存在的 run_tests.py")

        # ================================================================
        # 【根因修复】双向 API 路径校验：自动扫描 Flask 真实路由 +
        #            对比 README 中声明的路径，防止文档与实现脱节
        # ================================================================
        _app = test_app
        real_rules = []
        for _rule in sorted(_app.url_map.iter_rules(), key=lambda r: r.rule):
            if not _rule.rule.startswith('/api/'):
                continue
            # 将 <int:xxx> 统一归一成 <int:...>，便于与 README 中写法匹配
            _normalized = re.sub(r'<int:\w+>', '<int:...>', _rule.rule)
            _methods = sorted(_rule.methods - {'HEAD', 'OPTIONS'})
            real_rules.append((_normalized, _methods))

        # README 中声明的路径：提取 API 概览表格或代码段中 /api/... 格式路径
        declared_paths = set()
        declared_pattern = re.compile(r'/api/[^\s`|\n)]+')
        for _m in declared_pattern.finditer(readme):
            raw = _m.group(0)
            # 截掉末尾可能跟着的 Markdown 语法符号 / query 参数
            raw = raw.split('?')[0]                 # 丢掉 ?query=xxx
            raw = re.sub(r'[>*]+$', '', raw)        # 去掉尾随 '>' '*'
            raw = raw.rstrip('.,;:|/-')
            if len(raw) < 5 or not raw.startswith('/api/'):
                continue
            # README 常写 <id> / <template_id> / <task_id>，统一归一为 <int:...>
            norm = re.sub(r'<\w+>', '<int:...>', raw)
            norm = re.sub(r'<int:\w+>', '<int:...>', norm)
            # curl 示例中常用纯数字 ID（如 /api/tasks/1/copy），也归一为 <int:...>
            segments = norm.split('/')
            for i in range(len(segments)):
                if segments[i].isdigit() and segments[i] != '':
                    segments[i] = '<int:...>'
            norm = '/'.join(segments)
            # 丢掉因 Markdown 表格语法被吃掉后半段的残缺占位（比如 "/api/templates/<int..."）
            if '<' in norm and '>' not in norm:
                continue
            declared_paths.add(norm)

        # 方向 1：README 声明了但真实代码里没有 → 文档写了假接口
        real_path_set = {p for p, _ in real_rules}
        for dp in sorted(declared_paths):
            dp_clean = dp.rstrip('/')
            real_has_exact = dp_clean in real_path_set
            real_has_prefix = any(rp.startswith(dp_clean + '/') for rp in real_path_set)
            # 含动态段时：前缀+后缀匹配即可
            real_match_param = False
            if not real_has_exact and '<int:...>' in dp_clean:
                parts = dp_clean.split('<int:...>')
                if len(parts) >= 2:
                    prefix = parts[0].rstrip('/')
                    suffix = parts[-1]
                    for rp in real_path_set:
                        if (rp.startswith(prefix + '/') and rp.endswith(suffix)
                            and '<int:...>' in rp):
                            real_match_param = True
                            break
            if not real_has_exact and not real_has_prefix and not real_match_param:
                doc_checks.append(f"README 声明接口但实现中不存在: {dp}")

        # 方向 2：真实存在的关键业务接口但 README 没提 → 能力漏文档
        _must_doc = [
            '/api/templates/import',
            '/api/templates/<int:...>/export/json',
            '/api/templates/<int:...>/export/csv',
            '/api/templates/<int:...>/copy',
            '/api/reports/task/<int:...>',
            '/api/reports/task/<int:...>/json',
            '/api/reports/task/<int:...>/csv',
            '/api/history/export/json',
            '/api/history/export/csv',
        ]
        for mp in _must_doc:
            mp_clean = mp.rstrip('/')
            doc_has = mp_clean in declared_paths or mp + '/' in declared_paths
            # 允许 README 用 <int:template_id> / <template_id> / <id> 等写法
            wildcard_ok = False
            if not doc_has and '<int:...>' in mp_clean:
                prefix = mp_clean.split('<int:...>')[0]
                suffix = mp_clean.split('<int:...>')[-1]
                for dp in declared_paths:
                    if (dp.startswith(prefix) and dp.endswith(suffix)
                        and re.search(r'/<[^>]+>/', dp)):
                        wildcard_ok = True
                        break
            if not doc_has and not wildcard_ok:
                doc_checks.append(f"关键能力已实现但 README 漏文档: {mp}")

        # 模板四大能力的文字说明必须在 README 使用说明章节出现
        # 关键词可以是 API 路径、冲突处理字段名、或是可读的中文提示
        _template_capabilities = [
            ('模板导出', ['/api/templates/', 'export/json', 'export/csv', '导出模板']),
            ('模板复制', ['/copy', '复制模板', '副本']),
            ('导入冲突处理', ['conflict_mode', 'reject', 'rename', 'overwrite', '冲突处理']),
            ('模板删除保护', ['template_in_use', '被任务引用', '删除保护', '拦截']),
        ]
        for cap_name, keywords in _template_capabilities:
            found = any(kw.lower() in readme.lower() for kw in keywords)
            if not found:
                doc_checks.append(f"README 使用说明缺少模板能力「{cap_name}」")

        required_files = [
            'run.py', 'requirements.txt', 'tests/test_main.py',
            'app/__init__.py', 'app/database.py', 'static/index.html'
        ]
        for rf in required_files:
            fp = os.path.join(os.path.dirname(os.path.dirname(__file__)), rf)
            if not os.path.exists(fp):
                doc_checks.append(f"README 项目结构要求的文件不存在: {rf}")
    
    if doc_checks:
        print("\n" + "=" * 60)
        print("⚠️  文档与一致性自检失败")
        print("=" * 60)
        for msg in doc_checks:
            print(f"  ❌ {msg}")
            test_results.append({'name': f'文档一致性: {msg[:50]}', 'passed': False, 'error': msg})
    
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    
    passed = sum(1 for r in test_results if r['passed'])
    total = len(test_results)
    
    for r in test_results:
        status = "✅ 通过" if r['passed'] else "❌ 失败"
        print(f"{status} - {r['name']}")
        if not r['passed']:
            print(f"     原因: {r['error']}")
    
    print(f"\n总计: {passed}/{total} 通过")
    
    return passed == total


def test_unit_conversion(results):
    print("\n--- 测试1: 单位换算 ---")
    try:
        assertAlmostEqual(UnitConverter.convert_volume(1, 'mL', 'ul'), 1000, "mL to ul")
        assertAlmostEqual(UnitConverter.convert_volume(1000, 'ul', 'mL'), 1, "ul to mL")
        assertAlmostEqual(UnitConverter.convert_volume(1, 'L', 'ul'), 1000000, "L to ul")
        assertAlmostEqual(UnitConverter.convert_volume(1, 'µL', 'uL'), 1, "µL to uL")
        
        assertAlmostEqual(UnitConverter.convert_concentration(1, 'mM', 'uM'), 1000, "mM to uM")
        assertAlmostEqual(UnitConverter.convert_concentration(1000, 'uM', 'mM'), 1, "uM to mM")
        assertAlmostEqual(UnitConverter.convert_concentration(1, 'µM', 'uM'), 1, "µM to uM")
        
        assert UnitConverter.is_volume_unit('ul'), "ul 应该是体积单位"
        assert UnitConverter.is_volume_unit('mL'), "mL 应该是体积单位"
        assert UnitConverter.is_volume_unit('µL'), "µL 应该是体积单位"
        
        assert UnitConverter.are_units_compatible('ul', 'mL', 'volume'), "ul 和 mL 应该兼容"
        
        try:
            UnitConverter.convert_volume(1, 'xyz', 'ul')
            raise AssertionError("无效单位应该报错")
        except ValueError:
            pass
        
        results.append({'name': '单位换算', 'passed': True})
        print("  ✅ 通过")
    except Exception as e:
        results.append({'name': '单位换算', 'passed': False, 'error': str(e)})
        print(f"  ❌ 失败: {e}")


def test_import_samples(db, results):
    print("\n--- 测试2: 导入样本 ---")
    try:
        samples_csv = """name,concentration,concentration_unit,volume,volume_unit,description
Test_Sample_1,50,uM,100,ul,测试样本1
Test_Sample_2,50,uM,100,ul,测试样本2
"""
        from app.services.data_importer import DataImporter
        samples = DataImporter.parse_samples_csv(samples_csv)
        
        assert len(samples) == 2, f"期望解析 2 个样本，实际 {len(samples)} 个"
        
        for s in samples:
            db.execute('''
                INSERT INTO samples (name, concentration, concentration_unit, volume, volume_unit, description)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (s['name'], s['concentration'], s['concentration_unit'], 
                  s['volume'], s['volume_unit'], s['description']))
        db.commit()
        
        count = db.execute('SELECT COUNT(*) as cnt FROM samples').fetchone()['cnt']
        assert count == 2, f"期望 2 个样本，实际 {count} 个"
        
        results.append({'name': '导入样本', 'passed': True})
        print("  ✅ 通过")
    except Exception as e:
        results.append({'name': '导入样本', 'passed': False, 'error': str(e)})
        print(f"  ❌ 失败: {e}")


def test_import_primers(db, results):
    print("\n--- 测试3: 导入引物 ---")
    try:
        primers_csv = """name,sequence,concentration,concentration_unit,volume,volume_unit,melting_temp,description
Test_Primer_F,ATCGATCG,10,uM,500,ul,58,测试正向引物
Test_Primer_R,CGATCGAT,10,uM,500,ul,58,测试反向引物
"""
        from app.services.data_importer import DataImporter
        primers = DataImporter.parse_primers_csv(primers_csv)
        
        assert len(primers) == 2, f"期望解析 2 个引物，实际 {len(primers)} 个"
        
        for p in primers:
            db.execute('''
                INSERT INTO primers (name, sequence, concentration, concentration_unit, 
                                    volume, volume_unit, melting_temp, description)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (p['name'], p['sequence'], p['concentration'], p['concentration_unit'],
                  p['volume'], p['volume_unit'], p['melting_temp'], p['description']))
        db.commit()
        
        count = db.execute('SELECT COUNT(*) as cnt FROM primers').fetchone()['cnt']
        assert count == 2, f"期望 2 个引物，实际 {count} 个"
        
        results.append({'name': '导入引物', 'passed': True})
        print("  ✅ 通过")
    except Exception as e:
        results.append({'name': '导入引物', 'passed': False, 'error': str(e)})
        print(f"  ❌ 失败: {e}")


def test_import_reagents(db, results):
    print("\n--- 测试4: 导入试剂 ---")
    try:
        reagents_csv = """name,type,concentration,concentration_unit,volume,volume_unit,min_pipette_volume,min_pipette_unit,description
Test_MM,master_mix,2,x,5000,ul,0.5,ul,测试Master Mix
Test_Water,water,,ul,10000,ul,0.5,ul,测试水
Low_Stock_Reagent,enzyme,5,U/uL,1,ul,0.5,ul,低库存试剂
"""
        from app.services.data_importer import DataImporter
        reagents = DataImporter.parse_reagents_csv(reagents_csv)
        
        assert len(reagents) == 3, f"期望解析 3 个试剂，实际 {len(reagents)} 个"
        
        for r in reagents:
            db.execute('''
                INSERT INTO reagents (name, type, concentration, concentration_unit, 
                                     volume, volume_unit, min_pipette_volume, min_pipette_unit, description)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (r['name'], r['type'], r['concentration'], r['concentration_unit'],
                  r['volume'], r['volume_unit'], r['min_pipette_volume'], 
                  r['min_pipette_unit'], r['description']))
        db.commit()
        
        count = db.execute('SELECT COUNT(*) as cnt FROM reagents').fetchone()['cnt']
        assert count == 3, f"期望 3 个试剂，实际 {count} 个"
        
        results.append({'name': '导入试剂', 'passed': True})
        print("  ✅ 通过")
    except Exception as e:
        results.append({'name': '导入试剂', 'passed': False, 'error': str(e)})
        print(f"  ❌ 失败: {e}")


def test_import_template(db, results):
    print("\n--- 测试5: 导入板位模板 ---")
    try:
        template_csv = """,1,2,3
A,Test_Sample_1,Test_Sample_2,PC
B,NC,EMPTY,Test_Sample_1
"""
        from app.services.data_importer import DataImporter
        template_data = DataImporter.parse_template_csv(template_csv)
        
        assert template_data['rows'] == 2, f"期望 2 行，实际 {template_data['rows']}"
        assert template_data['cols'] == 3, f"期望 3 列，实际 {template_data['cols']}"
        assert len(template_data['wells']) == 6, f"期望 6 个孔，实际 {len(template_data['wells'])}"
        
        cursor = db.execute('''
            INSERT INTO plate_templates (name, rows, cols, description)
            VALUES (?, ?, ?, ?)
        ''', ('测试模板', template_data['rows'], template_data['cols'], '用于测试'))
        template_id = cursor.lastrowid
        
        for well in template_data['wells']:
            db.execute('''
                INSERT INTO template_wells 
                (template_id, well_row, well_col, well_type, sample_name, note)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (template_id, well['well_row'], well['well_col'], 
                  well['well_type'], well.get('sample_name'), well.get('note', '')))
        db.commit()
        
        wells = db.execute(
            'SELECT * FROM template_wells WHERE template_id = ? ORDER BY well_row, well_col', 
            (template_id,)
        ).fetchall()
        assert len(wells) == 6, f"期望 6 个孔，实际 {len(wells)} 个"
        
        well_a1 = db.execute(
            'SELECT * FROM template_wells WHERE template_id = ? AND well_row = 1 AND well_col = 1',
            (template_id,)
        ).fetchone()
        assert well_a1['sample_name'] == 'Test_Sample_1', f"A1 样本名不匹配: {well_a1['sample_name']}"
        
        well_a3 = db.execute(
            'SELECT * FROM template_wells WHERE template_id = ? AND well_row = 1 AND well_col = 3',
            (template_id,)
        ).fetchone()
        assert well_a3['well_type'] == 'positive_control', f"A3 类型不对: {well_a3['well_type']}"
        
        well_b1 = db.execute(
            'SELECT * FROM template_wells WHERE template_id = ? AND well_row = 2 AND well_col = 1',
            (template_id,)
        ).fetchone()
        assert well_b1['well_type'] == 'negative_control', f"B1 类型不对: {well_b1['well_type']}"
        
        well_b2 = db.execute(
            'SELECT * FROM template_wells WHERE template_id = ? AND well_row = 2 AND well_col = 2',
            (template_id,)
        ).fetchone()
        assert well_b2['well_type'] == 'empty', f"B2 类型不对: {well_b2['well_type']}"
        
        results.append({'name': '导入板位模板', 'passed': True})
        print("  ✅ 通过")
    except Exception as e:
        results.append({'name': '导入板位模板', 'passed': False, 'error': str(e)})
        print(f"  ❌ 失败: {e}")


def test_template_migration_and_lifecycle(db, db_path, results):
    print("\n--- 测试5b: 模板迁移 & 生命周期回归 ---")
    try:
        import sqlite3
        import os
        import tempfile
        
        # === 1. schema 迁移：旧库自动补 sample_name 列 ===
        tmp_db_path = os.path.join(os.path.dirname(__file__), '_tmp_old_schema.db')
        if os.path.exists(tmp_db_path):
            os.remove(tmp_db_path)
        
        old_conn = sqlite3.connect(tmp_db_path)
        old_conn.executescript('''
            CREATE TABLE plate_templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                rows INTEGER NOT NULL,
                cols INTEGER NOT NULL,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE template_wells (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                template_id INTEGER NOT NULL,
                well_row INTEGER NOT NULL,
                well_col INTEGER NOT NULL,
                well_type TEXT NOT NULL DEFAULT 'sample',
                sample_id INTEGER,
                reagent_id INTEGER,
                note TEXT,
                FOREIGN KEY (template_id) REFERENCES plate_templates(id) ON DELETE CASCADE,
                UNIQUE(template_id, well_row, well_col)
            );
        ''')
        old_conn.commit()
        old_conn.close()
        
        cols_before = [row[1] for row in sqlite3.connect(tmp_db_path).execute('PRAGMA table_info(template_wells)')]
        assert 'sample_name' not in cols_before, "旧库不应有 sample_name 列"
        
        from app.database import init_db
        class FakeApp:
            config = {'DATABASE': tmp_db_path}
            def teardown_appcontext(self, func): pass
        
        init_db(FakeApp())
        
        cols_after = [row[1] for row in sqlite3.connect(tmp_db_path).execute('PRAGMA table_info(template_wells)')]
        assert 'sample_name' in cols_after, "迁移后应该有 sample_name 列"
        print("  ✅ 旧库 schema 自动迁移")
        
        init_db(FakeApp())
        print("  ✅ 重复迁移幂等，不报错")
        
        # === 2. 导入失败不残留脏数据 ===
        db.commit()
        
        tpl_count_before = len(db.execute('SELECT * FROM plate_templates').fetchall())
        
        db.execute('BEGIN')
        cur = db.execute('''
            INSERT INTO plate_templates (name, rows, cols, description)
            VALUES (?, 2, 3, '事务测试')
        ''', ('_tx_test_template',))
        tx_id = cur.lastrowid
        db.execute('INSERT INTO template_wells (template_id, well_row, well_col, well_type) VALUES (?, 1, 1, ?)', (tx_id, 'sample'))
        db.rollback()
        
        after_rollback = db.execute('SELECT * FROM plate_templates WHERE id = ?', (tx_id,)).fetchone()
        wells_after_rollback = len(db.execute('SELECT * FROM template_wells WHERE template_id = ?', (tx_id,)).fetchall())
        assert after_rollback is None, "回滚后模板不应存在"
        assert wells_after_rollback == 0, "回滚后孔位不应存在"
        
        tpl_count_after = len(db.execute('SELECT * FROM plate_templates').fetchall())
        assert tpl_count_before == tpl_count_after, f"失败导入不应残留: {tpl_count_before} → {tpl_count_after}"
        print("  ✅ 失败不残留脏数据（事务回滚）")
        
        # === 3. 重启后模板仍可读（用独立连接验证持久化） ===
        tpl = db.execute('SELECT * FROM plate_templates LIMIT 1').fetchone()
        assert tpl is not None, "应该有模板"
        tpl_id = tpl['id']
        tpl_name = tpl['name']
        wells_from_main = len(db.execute('SELECT * FROM template_wells WHERE template_id = ?', (tpl_id,)).fetchall())
        
        assert db_path and os.path.exists(db_path), f"数据库文件应该存在: {db_path}"
        
        other_conn = sqlite3.connect(db_path)
        other_conn.row_factory = sqlite3.Row
        other_tpl = other_conn.execute('SELECT * FROM plate_templates WHERE id = ?', (tpl_id,)).fetchone()
        other_wells = len(other_conn.execute('SELECT * FROM template_wells WHERE template_id = ?', (tpl_id,)).fetchall())
        other_conn.close()
        assert other_tpl is not None, "重连后应该能读到模板"
        assert other_wells == wells_from_main, f"重连后孔位数不匹配: {wells_from_main} vs {other_wells}"
        print(f"  ✅ 重启后模板可读: {tpl_name} ({other_wells} 孔)")
        
        # === 4. 模板导入后能创建任务并生成方案 ===
        from app.services.task_service import TaskService
        service = TaskService(db)
        
        samples = db.execute('SELECT * FROM samples LIMIT 1').fetchall()
        primers = db.execute('SELECT * FROM primers LIMIT 1').fetchall()
        mm = db.execute("SELECT * FROM reagents WHERE type = 'master_mix' LIMIT 1").fetchall()
        water = db.execute("SELECT * FROM reagents WHERE type = 'water' LIMIT 1").fetchall()
        
        lifecycle_task_id = None
        try:
            if samples and primers and mm and water:
                lifecycle_task_id = service.create_task(
                    name='_lifecycle_test_task',
                    template_id=tpl_id,
                    total_volume=20,
                    volume_unit='ul'
                )
                assert lifecycle_task_id > 0
                
                plan = service.generate_plan(
                    task_id=lifecycle_task_id,
                    primer_id=primers[0]['id'],
                    master_mix_id=mm[0]['id'],
                    water_id=water[0]['id']
                )
                assert plan is not None
                assert plan['status'] == 'pending_review'
                
                wells = db.execute(
                    'SELECT * FROM task_wells WHERE task_id = ?',
                    (lifecycle_task_id,)
                ).fetchall()
                assert len(wells) > 0, "生成方案后应该有孔位数据"
                print(f"  ✅ 模板导入→创建任务→生成方案: {len(wells)} 孔")
            else:
                print("  ⚠️  跳过生成方案验证（缺少样本/引物/试剂数据）")
        finally:
            # 清理：删掉测试创建的任务，不影响后续测试
            if lifecycle_task_id:
                db.execute('DELETE FROM task_wells WHERE task_id = ?', (lifecycle_task_id,))
                db.execute('DELETE FROM task_reagent_usage WHERE task_id = ?', (lifecycle_task_id,))
                db.execute('DELETE FROM task_primer_usage WHERE task_id = ?', (lifecycle_task_id,))
                db.execute('DELETE FROM history WHERE task_id = ?', (lifecycle_task_id,))
                db.execute('DELETE FROM tasks WHERE id = ?', (lifecycle_task_id,))
                db.commit()
        
        # 清理临时文件（Windows 可能因文件锁延迟释放，忽略删除错误）
        try:
            if os.path.exists(tmp_db_path):
                os.remove(tmp_db_path)
        except OSError:
            pass
        
        results.append({'name': '模板迁移&生命周期回归', 'passed': True})
        print("  ✅ 通过")
    except Exception as e:
        import traceback
        err_detail = str(e) or type(e).__name__
        results.append({'name': '模板迁移&生命周期回归', 'passed': False, 'error': err_detail})
        print(f"  ❌ 失败: {err_detail}")


def test_template_export_and_reimport(db, app, results):
    print("\n--- 测试5c: 模板导出与重新导入 ---")
    try:
        client = app.test_client()
        template = db.execute('SELECT * FROM plate_templates LIMIT 1').fetchone()
        assert template is not None, "需要有至少一个模板"
        tpl_id = template['id']
        original_wells = db.execute(
            'SELECT * FROM template_wells WHERE template_id = ? ORDER BY well_row, well_col',
            (tpl_id,)
        ).fetchall()
        original_count = len(original_wells)

        resp_json = client.get(f'/api/templates/{tpl_id}/export/json')
        assert resp_json.status_code == 200, f"JSON导出失败: {resp_json.status_code}"
        json_data = json.loads(resp_json.data.decode('utf-8'))
        assert 'name' in json_data, "导出JSON缺少name"
        assert 'wells' in json_data, "导出JSON缺少wells"
        assert len(json_data['wells']) == original_count, \
            f"导出孔位数不匹配: {len(json_data['wells'])} vs {original_count}"
        print(f"  ✅ JSON导出: {json_data['name']}, {len(json_data['wells'])} 孔")

        resp_csv = client.get(f'/api/templates/{tpl_id}/export/csv')
        assert resp_csv.status_code == 200, f"CSV导出失败: {resp_csv.status_code}"
        csv_content = resp_csv.data.decode('utf-8-sig')
        assert len(csv_content) > 0, "CSV导出为空"
        csv_lines = csv_content.strip().split('\n')
        assert len(csv_lines) >= 2, "CSV至少有表头和一行数据"
        print(f"  ✅ CSV导出: {len(csv_lines)} 行")

        reimport_name = f'{template["name"]}_导出重导入测试'
        resp_reimport = client.post('/api/templates/import', json={
            'name': reimport_name,
            'description': json_data.get('description', ''),
            'rows': json_data['rows'],
            'cols': json_data['cols'],
            'wells': json_data['wells'],
        })
        assert resp_reimport.status_code == 201, f"重新导入失败: {resp_reimport.status_code} {resp_reimport.get_json()}"
        reimported = resp_reimport.get_json()
        assert reimported['name'] == reimport_name, f"重导入名称不匹配: {reimported['name']}"
        assert len(reimported['wells']) == original_count, \
            f"重导入孔位数不匹配: {len(reimported['wells'])} vs {original_count}"

        reimport_wells = db.execute(
            'SELECT * FROM template_wells WHERE template_id = ? ORDER BY well_row, well_col',
            (reimported['id'],)
        ).fetchall()
        assert len(reimport_wells) == original_count, \
            f"数据库孔位数不匹配: {len(reimport_wells)} vs {original_count}"

        for ow, rw in zip(original_wells, reimport_wells):
            assert ow['well_type'] == rw['well_type'], \
                f"孔位类型不匹配: ({ow['well_row']},{ow['well_col']}) {ow['well_type']} vs {rw['well_type']}"
            assert ow['sample_name'] == rw['sample_name'], \
                f"样本名不匹配: ({ow['well_row']},{ow['well_col']}) {ow['sample_name']} vs {rw['sample_name']}"
        print(f"  ✅ 重新导入: {reimported['name']}, {len(reimported['wells'])} 孔，内容一致")

        db.execute('DELETE FROM template_wells WHERE template_id = ?', (reimported['id'],))
        db.execute('DELETE FROM plate_templates WHERE id = ?', (reimported['id'],))
        db.commit()

        csv_reimport_name = f'{template["name"]}_CSV重导入测试'
        import io as _io
        csv_bytes = resp_csv.data
        resp_csv_reimport = client.post('/api/templates/import',
            data={'name': csv_reimport_name, 'description': 'CSV重导入',
                  'file': (_io.BytesIO(csv_bytes), 'test_template.csv',
                           'text/csv')})
        assert resp_csv_reimport.status_code == 201, \
            f"CSV重新导入失败: {resp_csv_reimport.status_code} {resp_csv_reimport.get_json()}"
        csv_reimported = resp_csv_reimport.get_json()
        assert len(csv_reimported['wells']) > 0, "CSV重导入孔位为空"
        print(f"  ✅ CSV重导入: {csv_reimported['name']}, {len(csv_reimported['wells'])} 孔")

        db.execute('DELETE FROM template_wells WHERE template_id = ?', (csv_reimported['id'],))
        db.execute('DELETE FROM plate_templates WHERE id = ?', (csv_reimported['id'],))
        db.commit()

        results.append({'name': '模板导出与重新导入', 'passed': True})
        print("  ✅ 通过")
    except Exception as e:
        results.append({'name': '模板导出与重新导入', 'passed': False, 'error': str(e)})
        print(f"  ❌ 失败: {e}")


def test_template_copy(db, app, results):
    print("\n--- 测试5d: 模板复制 ---")
    try:
        client = app.test_client()
        template = db.execute('SELECT * FROM plate_templates LIMIT 1').fetchone()
        assert template is not None, "需要有至少一个模板"
        tpl_id = template['id']
        original_wells = db.execute(
            'SELECT * FROM template_wells WHERE template_id = ? ORDER BY well_row, well_col',
            (tpl_id,)
        ).fetchall()

        resp = client.post(f'/api/templates/{tpl_id}/copy', json={})
        assert resp.status_code == 201, f"复制失败: {resp.status_code} {resp.get_json()}"
        copied = resp.get_json()
        assert copied['name'] != template['name'], "复制品名称不应与原件相同"
        assert copied['rows'] == template['rows'], "行数不匹配"
        assert copied['cols'] == template['cols'], "列数不匹配"
        print(f"  ✅ 复制成功: {template['name']} → {copied['name']}")

        copied_wells = db.execute(
            'SELECT * FROM template_wells WHERE template_id = ? ORDER BY well_row, well_col',
            (copied['id'],)
        ).fetchall()
        assert len(copied_wells) == len(original_wells), \
            f"孔位数不匹配: {len(copied_wells)} vs {len(original_wells)}"
        for ow, cw in zip(original_wells, copied_wells):
            assert ow['well_type'] == cw['well_type'], \
                f"孔位类型不匹配: {ow['well_type']} vs {cw['well_type']}"
            assert ow['sample_name'] == cw['sample_name'], \
                f"样本名不匹配: {ow['sample_name']} vs {cw['sample_name']}"
        print(f"  ✅ 复制品内容一致: {len(copied_wells)} 孔")

        from app.services.task_service import TaskService
        service = TaskService(db)
        copied_task_id = service.create_task(
            name='_copy_test_task',
            template_id=copied['id'],
            total_volume=20,
            volume_unit='ul'
        )

        primer = db.execute("SELECT * FROM primers LIMIT 1").fetchone()
        mm = db.execute("SELECT * FROM reagents WHERE type = 'master_mix' LIMIT 1").fetchone()
        water = db.execute("SELECT * FROM reagents WHERE type = 'water' LIMIT 1").fetchone()

        if primer and mm and water:
            plan = service.generate_plan(
                task_id=copied_task_id,
                primer_id=primer['id'],
                master_mix_id=mm['id'],
                water_id=water['id']
            )
            assert plan['status'] == 'pending_review', f"生成方案状态不对: {plan['status']}"
            print(f"  ✅ 复制品创建任务并生成方案: task_id={copied_task_id}")

        db.execute('DELETE FROM task_wells WHERE task_id = ?', (copied_task_id,))
        db.execute('DELETE FROM task_reagent_usage WHERE task_id = ?', (copied_task_id,))
        db.execute('DELETE FROM task_primer_usage WHERE task_id = ?', (copied_task_id,))
        db.execute('DELETE FROM history WHERE task_id = ?', (copied_task_id,))
        db.execute('DELETE FROM tasks WHERE id = ?', (copied_task_id,))
        db.execute('DELETE FROM template_wells WHERE template_id = ?', (copied['id'],))
        db.execute('DELETE FROM plate_templates WHERE id = ?', (copied['id'],))
        db.commit()

        resp_named = client.post(f'/api/templates/{tpl_id}/copy',
                                 json={'name': '自定义副本名', 'description': '自定义描述'})
        assert resp_named.status_code == 201, f"自定义名称复制失败: {resp_named.status_code}"
        named_copy = resp_named.get_json()
        assert named_copy['name'] == '自定义副本名', f"名称不匹配: {named_copy['name']}"
        print(f"  ✅ 自定义名称复制: {named_copy['name']}")

        db.execute('DELETE FROM template_wells WHERE template_id = ?', (named_copy['id'],))
        db.execute('DELETE FROM plate_templates WHERE id = ?', (named_copy['id'],))
        db.commit()

        results.append({'name': '模板复制', 'passed': True})
        print("  ✅ 通过")
    except Exception as e:
        results.append({'name': '模板复制', 'passed': False, 'error': str(e)})
        print(f"  ❌ 失败: {e}")


def test_template_import_conflict(db, app, results):
    print("\n--- 测试5e: 模板导入冲突处理 ---")
    try:
        client = app.test_client()
        template = db.execute('SELECT * FROM plate_templates LIMIT 1').fetchone()
        assert template is not None, "需要有至少一个模板"
        existing_name = template['name']

        resp_reject = client.post('/api/templates/import', json={
            'name': existing_name,
            'rows': 2,
            'cols': 3,
            'wells': [
                {'well_row': 1, 'well_col': 1, 'well_type': 'sample', 'sample_name': 'X'},
                {'well_row': 1, 'well_col': 2, 'well_type': 'positive_control'},
                {'well_row': 1, 'well_col': 3, 'well_type': 'negative_control'},
                {'well_row': 2, 'well_col': 1, 'well_type': 'empty'},
                {'well_row': 2, 'well_col': 2, 'well_type': 'sample', 'sample_name': 'Y'},
                {'well_row': 2, 'well_col': 3, 'well_type': 'sample'},
            ],
        })
        assert resp_reject.status_code == 409, f"拒绝模式应返回409: {resp_reject.status_code}"
        reject_data = resp_reject.get_json()
        assert 'conflict' in reject_data, "冲突响应应包含conflict字段"
        assert reject_data['conflict'] == 'name_exists', f"冲突类型不对: {reject_data['conflict']}"
        assert 'existing_id' in reject_data, "冲突响应应包含existing_id"
        print(f"  ✅ 拒绝模式: HTTP {resp_reject.status_code}, conflict={reject_data['conflict']}")

        original_wells_before = db.execute(
            'SELECT COUNT(*) as cnt FROM template_wells WHERE template_id = ?',
            (template['id'],)
        ).fetchone()['cnt']

        resp_rename = client.post('/api/templates/import?conflict_mode=rename', json={
            'name': existing_name,
            'rows': 2,
            'cols': 3,
            'wells': [
                {'well_row': 1, 'well_col': 1, 'well_type': 'sample', 'sample_name': 'X'},
                {'well_row': 1, 'well_col': 2, 'well_type': 'positive_control'},
                {'well_row': 1, 'well_col': 3, 'well_type': 'negative_control'},
                {'well_row': 2, 'well_col': 1, 'well_type': 'empty'},
                {'well_row': 2, 'well_col': 2, 'well_type': 'sample', 'sample_name': 'Y'},
                {'well_row': 2, 'well_col': 3, 'well_type': 'sample'},
            ],
        })
        assert resp_rename.status_code == 201, f"改名模式应返回201: {resp_rename.status_code}"
        renamed = resp_rename.get_json()
        assert renamed['name'] != existing_name, f"改名后名称不应与原名相同: {renamed['name']}"
        assert renamed['name'].startswith(existing_name), f"改名应基于原名: {renamed['name']}"
        assert len(renamed['wells']) == 6, f"改名后孔位数不对: {len(renamed['wells'])}"
        print(f"  ✅ 改名模式: {existing_name} → {renamed['name']}")

        renamed_wells = db.execute(
            'SELECT * FROM template_wells WHERE template_id = ?',
            (renamed['id'],)
        ).fetchall()
        assert len(renamed_wells) == 6, f"改名后数据库孔位数不对: {len(renamed_wells)}"

        original_wells_after = db.execute(
            'SELECT COUNT(*) as cnt FROM template_wells WHERE template_id = ?',
            (template['id'],)
        ).fetchone()['cnt']
        assert original_wells_before == original_wells_after, \
            "改名导入不应修改原模板孔位"
        print(f"  ✅ 改名后原模板未受影响: {original_wells_after} 孔")

        db.execute('DELETE FROM template_wells WHERE template_id = ?', (renamed['id'],))
        db.execute('DELETE FROM plate_templates WHERE id = ?', (renamed['id'],))
        db.commit()

        original_template_before = db.execute(
            'SELECT * FROM plate_templates WHERE id = ?', (template['id'],)
        ).fetchone()
        original_wells_before_overwrite = db.execute(
            'SELECT * FROM template_wells WHERE template_id = ? ORDER BY well_row, well_col',
            (template['id'],)
        ).fetchall()

        resp_overwrite = client.post('/api/templates/import?conflict_mode=overwrite', json={
            'name': existing_name,
            'rows': 2,
            'cols': 3,
            'wells': [
                {'well_row': 1, 'well_col': 1, 'well_type': 'sample', 'sample_name': 'X'},
                {'well_row': 1, 'well_col': 2, 'well_type': 'positive_control'},
                {'well_row': 1, 'well_col': 3, 'well_type': 'negative_control'},
                {'well_row': 2, 'well_col': 1, 'well_type': 'empty'},
                {'well_row': 2, 'well_col': 2, 'well_type': 'sample', 'sample_name': 'Y'},
                {'well_row': 2, 'well_col': 3, 'well_type': 'sample'},
            ],
        })
        assert resp_overwrite.status_code == 200, f"覆盖模式应返回200: {resp_overwrite.status_code}"
        overwritten = resp_overwrite.get_json()
        assert overwritten.get('overwritten') == True, "覆盖响应应标记overwritten=True"
        assert overwritten['name'] == existing_name, f"覆盖后名称不应变: {overwritten['name']}"
        assert overwritten['id'] == template['id'], "覆盖后ID应保持不变"
        assert len(overwritten['wells']) == 6, f"覆盖后孔位数不对: {len(overwritten['wells'])}"
        print(f"  ✅ 覆盖模式: id={overwritten['id']}, wells={len(overwritten['wells'])}, overwritten=True")

        overwritten_wells = db.execute(
            'SELECT * FROM template_wells WHERE template_id = ? ORDER BY well_row, well_col',
            (template['id'],)
        ).fetchall()
        assert len(overwritten_wells) == 6, f"覆盖后数据库孔位数不对: {len(overwritten_wells)}"
        well_a1 = [w for w in overwritten_wells if w['well_row'] == 1 and w['well_col'] == 1][0]
        assert well_a1['sample_name'] == 'X', f"覆盖后A1样本名不对: {well_a1['sample_name']}"

        db.execute('DELETE FROM template_wells WHERE template_id = ?', (template['id'],))
        for w in original_wells_before_overwrite:
            db.execute('''
                INSERT INTO template_wells (template_id, well_row, well_col, well_type, sample_name, note)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (template['id'], w['well_row'], w['well_col'], w['well_type'],
                  w['sample_name'], w['note']))
        db.execute('''
            UPDATE plate_templates SET rows = ?, cols = ? WHERE id = ?
        ''', (original_template_before['rows'], original_template_before['cols'], template['id']))
        db.commit()

        results.append({'name': '模板导入冲突处理', 'passed': True})
        print("  ✅ 通过 (拒绝/改名/覆盖三种模式)")
    except Exception as e:
        results.append({'name': '模板导入冲突处理', 'passed': False, 'error': str(e)})
        print(f"  ❌ 失败: {e}")


def test_template_delete_protection(db, app, results):
    print("\n--- 测试5f: 模板删除保护 ---")
    try:
        client = app.test_client()

        cursor = db.execute('''
            INSERT INTO plate_templates (name, rows, cols, description)
            VALUES (?, ?, ?, ?)
        ''', ('_delete_test_template', 2, 3, '删除保护测试'))
        free_tpl_id = cursor.lastrowid
        for r in range(1, 3):
            for c in range(1, 4):
                db.execute('''
                    INSERT INTO template_wells (template_id, well_row, well_col, well_type)
                    VALUES (?, ?, ?, ?)
                ''', (free_tpl_id, r, c, 'sample'))
        db.commit()

        resp_free = client.delete(f'/api/templates/{free_tpl_id}')
        assert resp_free.status_code == 200, f"无引用模板应可删除: {resp_free.status_code}"
        print(f"  ✅ 无引用模板可删除: id={free_tpl_id}")

        cursor2 = db.execute('''
            INSERT INTO plate_templates (name, rows, cols, description)
            VALUES (?, ?, ?, ?)
        ''', ('_referenced_test_template', 2, 3, '被引用测试'))
        ref_tpl_id = cursor2.lastrowid
        for r in range(1, 3):
            for c in range(1, 4):
                db.execute('''
                    INSERT INTO template_wells (template_id, well_row, well_col, well_type)
                    VALUES (?, ?, ?, ?)
                ''', (ref_tpl_id, r, c, 'sample'))
        db.commit()

        from app.services.task_service import TaskService
        service = TaskService(db)
        ref_task_id = service.create_task(
            name='_delete_protection_test_task',
            template_id=ref_tpl_id,
            total_volume=20,
            volume_unit='ul'
        )

        resp_blocked = client.delete(f'/api/templates/{ref_tpl_id}')
        assert resp_blocked.status_code == 409, f"有引用模板应返回409: {resp_blocked.status_code}"
        blocked_data = resp_blocked.get_json()
        assert 'referencing_tasks' in blocked_data, "拦截响应应包含referencing_tasks"
        assert blocked_data['task_count'] >= 1, f"引用任务数应为>=1: {blocked_data['task_count']}"
        assert blocked_data['reason'] == 'template_in_use', f"原因不对: {blocked_data['reason']}"
        print(f"  ✅ 有引用模板被拦截: HTTP 409, reason=template_in_use, "
              f"task_count={blocked_data['task_count']}")

        template_still_exists = db.execute(
            'SELECT * FROM plate_templates WHERE id = ?', (ref_tpl_id,)
        ).fetchone()
        assert template_still_exists is not None, "被拦截的模板不应被删除"
        print(f"  ✅ 被拦截的模板仍然存在: {template_still_exists['name']}")

        db.execute('DELETE FROM task_wells WHERE task_id = ?', (ref_task_id,))
        db.execute('DELETE FROM task_reagent_usage WHERE task_id = ?', (ref_task_id,))
        db.execute('DELETE FROM task_primer_usage WHERE task_id = ?', (ref_task_id,))
        db.execute('DELETE FROM history WHERE task_id = ?', (ref_task_id,))
        db.execute('DELETE FROM tasks WHERE id = ?', (ref_task_id,))
        db.commit()

        resp_after_cleanup = client.delete(f'/api/templates/{ref_tpl_id}')
        assert resp_after_cleanup.status_code == 200, \
            f"清理引用后应可删除: {resp_after_cleanup.status_code}"
        print(f"  ✅ 清理引用后模板可删除: id={ref_tpl_id}")

        deleted_check = db.execute(
            'SELECT * FROM plate_templates WHERE id = ?', (ref_tpl_id,)
        ).fetchone()
        assert deleted_check is None, "模板应该已被删除"

        results.append({'name': '模板删除保护', 'passed': True})
        print("  ✅ 通过")
    except Exception as e:
        results.append({'name': '模板删除保护', 'passed': False, 'error': str(e)})
        print(f"  ❌ 失败: {e}")


def test_template_history_records(db, results):
    print("\n--- 测试5g: 模板操作历史记录 ---")
    try:
        from app.services.history_service import HistoryService
        history_service = HistoryService(db, '')

        template_actions = history_service.get_history(action_type='template_created', limit=100)
        template_actions += history_service.get_history(action_type='template_exported', limit=100)
        template_actions += history_service.get_history(action_type='template_copied', limit=100)
        template_actions += history_service.get_history(action_type='template_imported', limit=100)
        template_actions += history_service.get_history(action_type='template_deleted', limit=100)

        assert len(template_actions) > 0, "应该有模板操作历史记录"
        print(f"  ✅ 模板历史记录: {len(template_actions)} 条")

        action_types = set(h['action_type'] for h in template_actions)
        assert 'template_imported' in action_types, "缺少template_imported记录"
        print(f"  ✅ 操作类型: {', '.join(sorted(action_types))}")

        for h in template_actions:
            assert h['task_id'] is None, f"模板操作历史task_id应为None: {h['task_id']}"
            assert h['detail'], f"模板操作历史detail不应为空: id={h['id']}"

        results.append({'name': '模板操作历史记录', 'passed': True})
        print("  ✅ 通过")
    except Exception as e:
        results.append({'name': '模板操作历史记录', 'passed': False, 'error': str(e)})
        print(f"  ❌ 失败: {e}")


def test_well_conflict(db, results):
    print("\n--- 测试6: 孔位冲突检测 ---")
    try:
        template = db.execute('SELECT * FROM plate_templates LIMIT 1').fetchone()
        
        try:
            db.execute('''
                INSERT INTO template_wells (template_id, well_row, well_col, well_type)
                VALUES (?, ?, ?, ?)
            ''', (template['id'], 1, 1, 'sample'))
            db.commit()
            results.append({'name': '孔位冲突检测', 'passed': False, 'error': '应该报唯一约束错误'})
            print("  ❌ 失败: 重复孔位未被拦截")
        except sqlite3.IntegrityError:
            db.rollback()
            results.append({'name': '孔位冲突检测', 'passed': True})
            print("  ✅ 通过 (正确拦截重复孔位)")
    except Exception as e:
        results.append({'name': '孔位冲突检测', 'passed': False, 'error': str(e)})
        print(f"  ❌ 失败: {e}")


def test_invalid_unit_interception(db, app, results):
    print("\n--- 测试7: 非法单位拦截 ---")
    try:
        from app.services.data_importer import DataImporter
        from app.services.task_service import TaskService
        service = TaskService(db)
        
        client = app.test_client()
        
        bad_sample_csv = "name,concentration,concentration_unit,volume,volume_unit,description\nBadS1,50,uM,100,foobar,坏样本\n"
        try:
            DataImporter.parse_samples_csv(bad_sample_csv)
            results.append({'name': '非法单位拦截', 'passed': False, 'error': '样本非法体积单位未拦截'})
            print("  ❌ 失败: 样本非法体积单位未在导入阶段拦截")
            return
        except ValueError as e:
            if '体积单位无效' not in str(e):
                raise
            print(f"  ✅ 样本导入拦截: {str(e)[:60]}")
        
        bad_primer_csv = "name,sequence,volume,volume_unit,concentration,concentration_unit,description\nBadP1,ATCG,500,foobar,10,uM,坏引物\n"
        try:
            DataImporter.parse_primers_csv(bad_primer_csv)
            results.append({'name': '非法单位拦截', 'passed': False, 'error': '引物非法体积单位未拦截'})
            print("  ❌ 失败: 引物非法体积单位未在导入阶段拦截")
            return
        except ValueError as e:
            if '体积单位无效' not in str(e):
                raise
            print(f"  ✅ 引物导入拦截: {str(e)[:60]}")
        
        bad_reagent_csv = "name,type,volume,volume_unit,concentration,concentration_unit,min_pipette_volume,description\nBadR1,water,1000,xyz,,0.5,,\n"
        try:
            DataImporter.parse_reagents_csv(bad_reagent_csv)
            results.append({'name': '非法单位拦截', 'passed': False, 'error': '试剂非法体积单位未拦截'})
            print("  ❌ 失败: 试剂非法体积单位未在导入阶段拦截")
            return
        except ValueError as e:
            if '体积单位无效' not in str(e):
                raise
            print(f"  ✅ 试剂导入拦截: {str(e)[:60]}")
        
        samples_before = db.execute('SELECT COUNT(*) as c FROM samples').fetchone()['c']
        resp = client.post('/api/samples', json={
            'name': 'APIBadSample',
            'concentration': 50,
            'concentration_unit': 'uM',
            'volume': 100,
            'volume_unit': 'BAD_UNIT',
            'description': '通过API录入的坏样本'
        })
        assert resp.status_code == 400, f"API录入-样本应该返回400，实际 {resp.status_code}"
        resp_data = resp.get_json()
        assert '体积单位' in resp_data.get('error', ''), f"API录入-样本错误信息不对: {resp_data}"
        samples_after = db.execute('SELECT COUNT(*) as c FROM samples').fetchone()['c']
        assert samples_before == samples_after, f"API录入-样本失败不应入库 ({samples_before} → {samples_after})"
        print(f"  ✅ API录入-样本拦截: {resp_data['error'][:55]}")
        
        primers_before = db.execute('SELECT COUNT(*) as c FROM primers').fetchone()['c']
        resp = client.post('/api/primers', json={
            'name': 'APIBadPrimer',
            'sequence': 'ATCGATCG',
            'concentration': 10,
            'concentration_unit': 'uM',
            'volume': 500,
            'volume_unit': 'BAD_UNIT'
        })
        assert resp.status_code == 400, f"API录入-引物应该返回400，实际 {resp.status_code}"
        resp_data = resp.get_json()
        assert '体积单位' in resp_data.get('error', ''), f"API录入-引物错误信息不对: {resp_data}"
        primers_after = db.execute('SELECT COUNT(*) as c FROM primers').fetchone()['c']
        assert primers_before == primers_after, f"API录入-引物失败不应入库 ({primers_before} → {primers_after})"
        print(f"  ✅ API录入-引物拦截: {resp_data['error'][:55]}")
        
        reagents_before = db.execute('SELECT COUNT(*) as c FROM reagents').fetchone()['c']
        resp = client.post('/api/reagents', json={
            'name': 'APIBadReagent',
            'type': 'water',
            'volume': 1000,
            'volume_unit': 'BAD_UNIT',
            'min_pipette_volume': 0.5
        })
        assert resp.status_code == 400, f"API录入-试剂应该返回400，实际 {resp.status_code}"
        resp_data = resp.get_json()
        assert '体积单位' in resp_data.get('error', ''), f"API录入-试剂错误信息不对: {resp_data}"
        reagents_after = db.execute('SELECT COUNT(*) as c FROM reagents').fetchone()['c']
        assert reagents_before == reagents_after, f"API录入-试剂失败不应入库 ({reagents_before} → {reagents_after})"
        print(f"  ✅ API录入-试剂拦截: {resp_data['error'][:55]}")
        
        resp = client.post('/api/reagents', json={
            'name': 'APIBadReagent2',
            'type': 'water',
            'volume': 1000,
            'volume_unit': 'ul',
            'min_pipette_volume': 0.5,
            'min_pipette_unit': 'BAD_UNIT'
        })
        assert resp.status_code == 400, f"API录入-试剂最小移液单位应该返回400，实际 {resp.status_code}"
        resp_data = resp.get_json()
        assert '最小移液单位' in resp_data.get('error', ''), f"API录入-最小移液单位错误信息不对: {resp_data}"
        print(f"  ✅ API录入-最小移液单位拦截: {resp_data['error'][:55]}")
        
        inv_before_api = db.execute('SELECT SUM(volume) as v FROM reagents').fetchone()['v']
        
        template = db.execute('SELECT * FROM plate_templates LIMIT 1').fetchone()
        try:
            service.create_task(
                name='坏单位任务',
                template_id=template['id'],
                total_volume=20,
                volume_unit='not_a_unit'
            )
            results.append({'name': '非法单位拦截', 'passed': False, 'error': '任务创建非法单位未拦截'})
            print("  ❌ 失败: 任务创建阶段非法单位未拦截")
            return
        except ValueError as e:
            if '无效的体积单位' not in str(e):
                raise
            print(f"  ✅ 任务创建拦截: {str(e)[:60]}")
        
        bad_task_id = service.create_task(
            name='暂时合法后续被污染的任务',
            template_id=template['id'],
            total_volume=20,
            volume_unit='ul'
        )
        db.execute("UPDATE tasks SET volume_unit = 'broken' WHERE id = ?", (bad_task_id,))
        db.commit()
        
        primer = db.execute("SELECT * FROM primers LIMIT 1").fetchone()
        mm = db.execute("SELECT * FROM reagents WHERE type = 'master_mix'").fetchone()
        water = db.execute("SELECT * FROM reagents WHERE type = 'water'").fetchone()
        
        wells_before = db.execute('SELECT COUNT(*) as c FROM task_wells WHERE task_id = ?', (bad_task_id,)).fetchone()['c']
        usage_before_r = db.execute('SELECT COUNT(*) as c FROM task_reagent_usage WHERE task_id = ?', (bad_task_id,)).fetchone()['c']
        usage_before_p = db.execute('SELECT COUNT(*) as c FROM task_primer_usage WHERE task_id = ?', (bad_task_id,)).fetchone()['c']
        status_before = db.execute('SELECT status FROM tasks WHERE id = ?', (bad_task_id,)).fetchone()['status']
        
        try:
            service.generate_plan(task_id=bad_task_id, primer_id=primer['id'], master_mix_id=mm['id'], water_id=water['id'])
            results.append({'name': '非法单位拦截', 'passed': False, 'error': '生成方案阶段非法单位未拦截'})
            print("  ❌ 失败: 生成方案阶段非法单位未拦截")
            return
        except ValueError as e:
            if '体积单位无效' not in str(e):
                raise
            print(f"  ✅ 生成方案拦截: {str(e)[:60]}")
        
        wells_after = db.execute('SELECT COUNT(*) as c FROM task_wells WHERE task_id = ?', (bad_task_id,)).fetchone()['c']
        usage_after_r = db.execute('SELECT COUNT(*) as c FROM task_reagent_usage WHERE task_id = ?', (bad_task_id,)).fetchone()['c']
        usage_after_p = db.execute('SELECT COUNT(*) as c FROM task_primer_usage WHERE task_id = ?', (bad_task_id,)).fetchone()['c']
        status_after = db.execute('SELECT status FROM tasks WHERE id = ?', (bad_task_id,)).fetchone()['status']
        
        inv_after = db.execute('SELECT SUM(volume) as v FROM reagents').fetchone()['v']
        
        assert wells_before == wells_after, f"失败生成不应写孔位数据 ({wells_before} → {wells_after})"
        assert usage_before_r == usage_after_r, "失败生成不应写试剂使用数据"
        assert usage_before_p == usage_after_p, "失败生成不应写引物使用数据"
        assert status_before == status_after, f"失败生成不应改任务状态 ({status_before} → {status_after})"
        assert inv_before_api == inv_after, f"失败生成不应扣减库存 ({inv_before_api} → {inv_after})"
        assert inv_before_api == inv_after, f"API失败操作不应扣减库存 ({inv_before_api} → {inv_after})"
        
        db.execute('DELETE FROM tasks WHERE id = ?', (bad_task_id,))
        db.commit()
        
        resp = client.post('/api/samples', json={
            'name': 'API_Good_Sample',
            'concentration': 50,
            'concentration_unit': 'uM',
            'volume': 100,
            'volume_unit': 'ul',
            'description': '合法单位样本'
        })
        assert resp.status_code == 201, f"合法单位样本应该创建成功，实际 {resp.status_code}"
        print(f"  ✅ API录入-合法单位成功: 样本 {resp.get_json()['name']}")
        
        db.execute("DELETE FROM samples WHERE name = 'API_Good_Sample'")
        db.execute("DELETE FROM tasks WHERE name IN ('坏单位任务', '暂时合法后续被污染的任务')")
        db.commit()
        
        results.append({'name': '非法单位拦截', 'passed': True})
        print(f"  ✅ 通过 (CSV/API/创建/生成四阶段均拦截，失败无脏数据)")
    except Exception as e:
        results.append({'name': '非法单位拦截', 'passed': False, 'error': str(e)})
        print(f"  ❌ 失败: {e}")


def test_create_tasks(db, results):
    print("\n--- 测试8: 创建任务 ---")
    try:
        from app.services.task_service import TaskService
        service = TaskService(db)
        template = db.execute('SELECT * FROM plate_templates LIMIT 1').fetchone()
        
        task1_id = service.create_task(
            name='测试任务-正常体积',
            template_id=template['id'],
            total_volume=20,
            volume_unit='ul'
        )
        
        task2_id = service.create_task(
            name='测试任务-小体积',
            template_id=template['id'],
            total_volume=2,
            volume_unit='ul'
        )
        
        for task_id in [task1_id, task2_id]:
            task = db.execute('SELECT * FROM tasks WHERE id = ?', (task_id,)).fetchone()
            assert task is not None, "任务创建失败"
            assert task['status'] == 'draft', f"期望状态 draft，实际 {task['status']}"
        
        count = db.execute('SELECT COUNT(*) as cnt FROM tasks').fetchone()['cnt']
        assert count == 2, f"期望 2 个任务，实际 {count} 个"
        
        results.append({'name': '创建任务', 'passed': True})
        print(f"  ✅ 通过 (2 个任务)")
    except Exception as e:
        results.append({'name': '创建任务', 'passed': False, 'error': str(e)})
        print(f"  ❌ 失败: {e}")


def test_generate_plans(db, results):
    print("\n--- 测试9: 生成配液方案 ---")
    try:
        from app.services.task_service import TaskService
        service = TaskService(db)
        
        primer = db.execute("SELECT * FROM primers WHERE name = 'Test_Primer_F'").fetchone()
        master_mix = db.execute("SELECT * FROM reagents WHERE type = 'master_mix'").fetchone()
        water = db.execute("SELECT * FROM reagents WHERE type = 'water'").fetchone()
        
        for task_name in ['测试任务-正常体积', '测试任务-小体积']:
            task = db.execute("SELECT * FROM tasks WHERE name = ?", (task_name,)).fetchone()
            assert task['status'] == 'draft', f"{task_name} 应该是草稿状态"
            
            result = service.generate_plan(
                task_id=task['id'],
                primer_id=primer['id'],
                master_mix_id=master_mix['id'],
                water_id=water['id']
            )
            
            updated_task = db.execute('SELECT * FROM tasks WHERE id = ?', (task['id'],)).fetchone()
            assert updated_task['status'] == 'pending_review', f"{task_name} 期望状态 pending_review"
            
            wells = db.execute('SELECT * FROM task_wells WHERE task_id = ?', (task['id'],)).fetchall()
            assert len(wells) == 6, f"{task_name} 期望 6 个孔位，实际 {len(wells)} 个"
            
            for w in wells:
                if w['well_type'] != 'empty':
                    assert w['total_volume'] > 0, f"{task_name} 孔 {w['well_row']},{w['well_col']} 总体系不对"
        
        results.append({'name': '生成配液方案', 'passed': True})
        print("  ✅ 通过 (2 个任务方案)")
    except Exception as e:
        results.append({'name': '生成配液方案', 'passed': False, 'error': str(e)})
        print(f"  ❌ 失败: {e}")


def test_normal_approval(db, results):
    print("\n--- 测试10: 正常体积任务直接批准 ---")
    try:
        from app.services.task_service import TaskService
        service = TaskService(db)
        task = db.execute("SELECT * FROM tasks WHERE name = '测试任务-正常体积'").fetchone()
        
        mm_before = db.execute("SELECT volume FROM reagents WHERE type = 'master_mix'").fetchone()['volume']
        primer_before = db.execute("SELECT volume FROM primers WHERE name = 'Test_Primer_F'").fetchone()['volume']
        
        result = service.approve_task(task['id'], ignore_min_pipette=False)
        assert result == True, "批准失败"
        
        approved_task = db.execute('SELECT * FROM tasks WHERE id = ?', (task['id'],)).fetchone()
        assert approved_task['status'] == 'approved', f"期望状态 approved，实际 {approved_task['status']}"
        
        mm_after = db.execute("SELECT volume FROM reagents WHERE type = 'master_mix'").fetchone()['volume']
        primer_after = db.execute("SELECT volume FROM primers WHERE name = 'Test_Primer_F'").fetchone()['volume']
        
        assert mm_after < mm_before, f"试剂库存未减少 (前: {mm_before}, 后: {mm_after})"
        assert primer_after < primer_before, "引物库存未减少"
        
        results.append({'name': '正常体积任务批准', 'passed': True})
        print(f"  ✅ 通过 (试剂: {mm_before} → {mm_after} µL)")
    except Exception as e:
        results.append({'name': '正常体积任务批准', 'passed': False, 'error': str(e)})
        print(f"  ❌ 失败: {e}")


def test_min_pipette_blocking(db, results):
    print("\n--- 测试11: 小体积任务最小移液拦截 ---")
    try:
        from app.services.task_service import TaskService
        service = TaskService(db)
        task = db.execute("SELECT * FROM tasks WHERE name = '测试任务-小体积'").fetchone()
        
        mm_before = db.execute("SELECT volume FROM reagents WHERE type = 'master_mix'").fetchone()['volume']
        
        try:
            service.approve_task(task['id'], ignore_min_pipette=False)
            results.append({'name': '最小移液体积拦截', 'passed': False, 'error': '应该被拦截但未被拦截'})
            print("  ❌ 失败: 低于最小移液体积的任务未被拦截")
        except ValueError as e:
            if '低于最小移液体积' in str(e):
                mm_after = db.execute("SELECT volume FROM reagents WHERE type = 'master_mix'").fetchone()['volume']
                assert mm_before == mm_after, "失败计算不应该扣减库存"
                
                task_after = db.execute('SELECT status FROM tasks WHERE id = ?', (task['id'],)).fetchone()
                assert task_after['status'] == 'pending_review', "失败后任务状态应该还是 pending_review"
                
                results.append({'name': '最小移液体积拦截', 'passed': True})
                print(f"  ✅ 通过 (正确拦截且不扣减库存)")
            else:
                raise e
        
    except Exception as e:
        results.append({'name': '最小移液体积拦截', 'passed': False, 'error': str(e)})
        print(f"  ❌ 失败: {e}")


def test_deviation_and_approve(db, results):
    print("\n--- 测试12: 偏差备注后批准 ---")
    try:
        from app.services.task_service import TaskService
        service = TaskService(db)
        task = db.execute("SELECT * FROM tasks WHERE name = '测试任务-小体积'").fetchone()
        
        mm_before = db.execute("SELECT volume FROM reagents WHERE type = 'master_mix'").fetchone()['volume']
        
        service.add_deviation_note(task['id'], '测试偏差：小体积反应，允许低于最小移液体积')
        
        task_with_note = db.execute('SELECT * FROM tasks WHERE id = ?', (task['id'],)).fetchone()
        assert task_with_note['deviation_note'] is not None, "偏差备注未保存"
        
        result = service.approve_task(task['id'], ignore_min_pipette=True)
        assert result == True, "带偏差批准失败"
        
        approved_task = db.execute('SELECT * FROM tasks WHERE id = ?', (task['id'],)).fetchone()
        assert approved_task['status'] == 'approved', f"期望状态 approved，实际 {approved_task['status']}"
        
        mm_after = db.execute("SELECT volume FROM reagents WHERE type = 'master_mix'").fetchone()['volume']
        assert mm_after < mm_before, "批准后库存应该减少"
        
        results.append({'name': '偏差备注后批准', 'passed': True})
        print("  ✅ 通过")
    except Exception as e:
        results.append({'name': '偏差备注后批准', 'passed': False, 'error': str(e)})
        print(f"  ❌ 失败: {e}")


def test_inventory_deduction(db, results):
    print("\n--- 测试13: 库存扣减验证 ---")
    try:
        task = db.execute("SELECT * FROM tasks WHERE name = '测试任务-正常体积'").fetchone()
        
        reagent_usage = db.execute(
            'SELECT * FROM task_reagent_usage WHERE task_id = ? AND source = ?',
            (task['id'], 'master_mix')
        ).fetchone()
        
        assert reagent_usage is not None, "未找到试剂使用记录"
        
        inventory_logs = db.execute(
            'SELECT * FROM reagent_inventory_log WHERE task_id = ?',
            (task['id'],)
        ).fetchall()
        
        assert len(inventory_logs) > 0, "未生成库存变更日志"
        
        deduct_logs = [l for l in inventory_logs if l['change_type'] == 'deduct']
        assert len(deduct_logs) > 0, "未找到扣减日志"
        
        primer_logs = db.execute(
            'SELECT * FROM primer_inventory_log WHERE task_id = ?',
            (task['id'],)
        ).fetchall()
        
        assert len(primer_logs) > 0, "未生成引物库存变更日志"
        
        results.append({'name': '库存扣减验证', 'passed': True})
        print(f"  ✅ 通过 (扣减日志: {len(inventory_logs)} 条试剂, {len(primer_logs)} 条引物)")
    except Exception as e:
        results.append({'name': '库存扣减验证', 'passed': False, 'error': str(e)})
        print(f"  ❌ 失败: {e}")


def test_revoke_approval(db, results):
    print("\n--- 测试14: 撤销确认 ---")
    try:
        from app.services.task_service import TaskService
        service = TaskService(db)
        task = db.execute("SELECT * FROM tasks WHERE name = '测试任务-正常体积'").fetchone()
        master_mix_before = db.execute("SELECT * FROM reagents WHERE type = 'master_mix'").fetchone()
        
        before_ul = UnitConverter.convert_volume(
            master_mix_before['volume'], master_mix_before['volume_unit'], 'ul'
        )
        
        result = service.revoke_approval(task['id'])
        assert result == True, "撤销失败"
        
        revoked_task = db.execute('SELECT * FROM tasks WHERE id = ?', (task['id'],)).fetchone()
        assert revoked_task['status'] == 'revoked', f"期望状态 revoked，实际 {revoked_task['status']}"
        
        master_mix_after = db.execute(
            'SELECT * FROM reagents WHERE id = ?', (master_mix_before['id'],)
        ).fetchone()
        
        after_ul = UnitConverter.convert_volume(
            master_mix_after['volume'], master_mix_after['volume_unit'], 'ul'
        )
        
        assert after_ul > before_ul, f"库存未退回 (前: {before_ul}, 后: {after_ul})"
        
        refund_logs = db.execute(
            "SELECT * FROM reagent_inventory_log WHERE reagent_id = ? AND change_type = 'refund'",
            (master_mix_before['id'],)
        ).fetchall()
        assert len(refund_logs) > 0, "未找到退回库存日志"
        
        results.append({'name': '撤销确认', 'passed': True})
        print(f"  ✅ 通过 (撤销后库存: {after_ul:.2f} µL)")
    except Exception as e:
        results.append({'name': '撤销确认', 'passed': False, 'error': str(e)})
        print(f"  ❌ 失败: {e}")


def test_reject_task(db, results):
    print("\n--- 测试15: 驳回任务 ---")
    try:
        from app.services.task_service import TaskService
        service = TaskService(db)
        template = db.execute('SELECT * FROM plate_templates LIMIT 1').fetchone()
        
        task_id = service.create_task(
            name='测试任务-驳回测试',
            template_id=template['id'],
            total_volume=20,
            volume_unit='ul'
        )
        
        primer = db.execute("SELECT * FROM primers LIMIT 1").fetchone()
        master_mix = db.execute("SELECT * FROM reagents WHERE type = 'master_mix'").fetchone()
        water = db.execute("SELECT * FROM reagents WHERE type = 'water'").fetchone()
        
        service.generate_plan(task_id=task_id, primer_id=primer['id'],
                             master_mix_id=master_mix['id'], water_id=water['id'])
        
        master_mix_before = db.execute(
            'SELECT volume, volume_unit FROM reagents WHERE id = ?', (master_mix['id'],)
        ).fetchone()
        before_vol = master_mix_before['volume']
        
        result = service.reject_task(task_id, reason='方案不符合要求，需要调整')
        assert result == True, "驳回失败"
        
        rejected_task = db.execute('SELECT * FROM tasks WHERE id = ?', (task_id,)).fetchone()
        assert rejected_task['status'] == 'rejected', f"期望状态 rejected，实际 {rejected_task['status']}"
        assert rejected_task['rejected_reason'] == '方案不符合要求，需要调整', "驳回原因不匹配"
        
        master_mix_after = db.execute(
            'SELECT volume, volume_unit FROM reagents WHERE id = ?', (master_mix['id'],)
        ).fetchone()
        
        assert before_vol == master_mix_after['volume'], "驳回不应该扣减库存"
        
        results.append({'name': '驳回任务', 'passed': True})
        print("  ✅ 通过 (驳回不扣减库存)")
    except Exception as e:
        results.append({'name': '驳回任务', 'passed': False, 'error': str(e)})
        print(f"  ❌ 失败: {e}")


def test_history_records(db, app, db_path, results):
    print("\n--- 测试16: 历史记录 ---")
    try:
        from app.services.history_service import HistoryService
        history_service = HistoryService(db, app.config['DATA_DIR'])
        
        task_normal = db.execute("SELECT * FROM tasks WHERE name = '测试任务-正常体积'").fetchone()
        history_normal = history_service.get_history(task_id=task_normal['id'])
        assert len(history_normal) >= 4, f"正常任务历史记录不足，期望至少 4 条，实际 {len(history_normal)} 条"
        
        action_types_normal = [h['action_type'] for h in history_normal]
        assert 'task_created' in action_types_normal, "正常任务缺少创建记录"
        assert 'plan_generated' in action_types_normal, "正常任务缺少生成方案记录"
        assert 'task_approved' in action_types_normal, "正常任务缺少批准记录"
        assert 'approval_revoked' in action_types_normal, "正常任务缺少撤销记录"
        
        task_small = db.execute("SELECT * FROM tasks WHERE name = '测试任务-小体积'").fetchone()
        history_small = history_service.get_history(task_id=task_small['id'])
        assert len(history_small) >= 4, f"小体积任务历史记录不足，期望至少 4 条，实际 {len(history_small)} 条"
        
        action_types_small = [h['action_type'] for h in history_small]
        assert 'task_created' in action_types_small, "小体积任务缺少创建记录"
        assert 'plan_generated' in action_types_small, "小体积任务缺少生成方案记录"
        assert 'deviation_note_added' in action_types_small, "小体积任务缺少偏差备注记录"
        assert 'task_approved' in action_types_small, "小体积任务缺少批准记录"
        
        all_history = history_service.get_history(limit=100)
        assert len(all_history) >= 10, f"总历史记录不足，期望至少 10 条，实际 {len(all_history)} 条"
        
        json_export = history_service.export_history_json()
        assert len(json_export) > 0, "JSON 导出为空"
        
        json_data = json.loads(json_export)
        assert 'tasks' in json_data, "导出数据缺少 tasks"
        assert 'history' in json_data, "导出数据缺少 history"
        assert 'inventory_logs' in json_data, "导出数据缺少 inventory_logs"
        
        results.append({'name': '历史记录与导出', 'passed': True})
        print(f"  ✅ 通过 (正常任务 {len(history_normal)} 条, 小体积任务 {len(history_small)} 条, 总计 {len(all_history)} 条)")
    except Exception as e:
        results.append({'name': '历史记录与导出', 'passed': False, 'error': str(e)})
        print(f"  ❌ 失败: {e}")


def test_report_export(db, results):
    print("\n--- 测试17: 报告导出 ---")
    try:
        from app.services.report_service import ReportService
        report_service = ReportService(db)
        
        task = db.execute("SELECT * FROM tasks WHERE name = '测试任务-正常体积'").fetchone()
        
        report = report_service.generate_task_report(task['id'])
        
        assert 'task' in report, "报告缺少任务信息"
        assert 'wells' in report, "报告缺少孔位信息"
        assert 'reagent_usage' in report, "报告缺少试剂使用信息"
        assert 'inventory_deduction' in report, "报告缺少库存扣减信息"
        assert 'summary' in report, "报告缺少汇总信息"
        
        assert report['summary']['sample_wells'] == 3, "样本孔数量不对"
        assert report['summary']['positive_controls'] == 1, "阳性对照数量不对"
        assert report['summary']['negative_controls'] == 1, "阴性对照数量不对"
        
        csv_report = report_service.export_report_csv(task['id'])
        assert len(csv_report) > 0, "CSV 报告为空"
        assert '孔位' in csv_report or 'PCR' in csv_report, "CSV 报告格式不正确"
        
        json_report = report_service.export_report_json(task['id'])
        assert len(json_report) > 0, "JSON 报告为空"
        
        json_data = json.loads(json_report)
        assert 'wells' in json_data, "JSON 报告缺少 wells"
        
        results.append({'name': '报告导出', 'passed': True})
        print("  ✅ 通过")
    except Exception as e:
        results.append({'name': '报告导出', 'passed': False, 'error': str(e)})
        print(f"  ❌ 失败: {e}")


def test_insufficient_inventory(db, results):
    print("\n--- 测试18: 库存不足拦截 ---")
    try:
        from app.services.task_service import TaskService
        service = TaskService(db)
        template = db.execute('SELECT * FROM plate_templates LIMIT 1').fetchone()
        
        db.execute('''
            INSERT INTO reagents (name, type, concentration, concentration_unit, 
                                 volume, volume_unit, min_pipette_volume, min_pipette_unit, description)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', ('Empty_MM', 'master_mix', '2', 'x', 0.1, 'ul', 0.5, 'ul', '空库存MM'))
        db.commit()
        
        task_id = service.create_task(
            name='测试任务-库存不足',
            template_id=template['id'],
            total_volume=20,
            volume_unit='ul'
        )
        
        primer = db.execute("SELECT * FROM primers LIMIT 1").fetchone()
        empty_mm = db.execute("SELECT * FROM reagents WHERE name = 'Empty_MM'").fetchone()
        water = db.execute("SELECT * FROM reagents WHERE type = 'water'").fetchone()
        
        service.generate_plan(task_id=task_id, primer_id=primer['id'],
                             master_mix_id=empty_mm['id'], water_id=water['id'])
        
        empty_mm_before = db.execute(
            'SELECT volume FROM reagents WHERE id = ?', (empty_mm['id'],)
        ).fetchone()['volume']
        
        try:
            service.approve_task(task_id, ignore_min_pipette=True)
            results.append({'name': '库存不足拦截', 'passed': False, 'error': '库存不足应该被拦截'})
            print("  ❌ 失败: 库存不足未被拦截")
        except ValueError as e:
            if '库存不足' in str(e):
                empty_mm_after = db.execute(
                    'SELECT volume FROM reagents WHERE id = ?', (empty_mm['id'],)
                ).fetchone()['volume']
                assert empty_mm_before == empty_mm_after, "失败计算不应该预占/扣减库存"
                results.append({'name': '库存不足拦截', 'passed': True})
                print(f"  ✅ 通过 (正确拦截且不扣减库存)")
            else:
                raise e
        
    except Exception as e:
        results.append({'name': '库存不足拦截', 'passed': False, 'error': str(e)})
        print(f"  ❌ 失败: {e}")


def test_task_copy(db, app, results):
    print("\n--- 测试21: 任务复制成新草稿 ---")
    try:
        from app.services.task_service import TaskService
        service = TaskService(db)
        
        template = db.execute('SELECT * FROM plate_templates LIMIT 1').fetchone()
        assert template is not None, "需要至少一个模板"
        
        task_id = service.create_task(
            name='_复制测试_源任务',
            template_id=template['id'],
            total_volume=20,
            volume_unit='ul'
        )
        
        primer = db.execute("SELECT * FROM primers LIMIT 1").fetchone()
        mm = db.execute("SELECT * FROM reagents WHERE type = 'master_mix' LIMIT 1").fetchone()
        water = db.execute("SELECT * FROM reagents WHERE type = 'water' LIMIT 1").fetchone()
        
        service.generate_plan(
            task_id=task_id,
            primer_id=primer['id'],
            master_mix_id=mm['id'],
            water_id=water['id'],
        )
        
        original_task = db.execute('SELECT * FROM tasks WHERE id = ?', (task_id,)).fetchone()
        original_wells = db.execute(
            'SELECT well_row, well_col, well_type, sample_name, primer_name, master_mix_volume, water_volume, total_volume '
            'FROM task_wells WHERE task_id = ? ORDER BY well_row, well_col',
            (task_id,)
        ).fetchall()
        original_reagent_usage = db.execute(
            'SELECT reagent_name, source, used_volume FROM task_reagent_usage WHERE task_id = ? ORDER BY reagent_name',
            (task_id,)
        ).fetchall()
        original_primer_usage = db.execute(
            'SELECT primer_name, used_volume FROM task_primer_usage WHERE task_id = ?',
            (task_id,)
        ).fetchall()
        
        new_task_id = service.copy_task(task_id)
        assert new_task_id != task_id, "复制任务应该有新的 ID"
        
        new_task = db.execute('SELECT * FROM tasks WHERE id = ?', (new_task_id,)).fetchone()
        assert new_task is not None, "复制的任务应该存在"
        assert new_task['status'] == 'draft', f"复制后状态应为 draft，实际 {new_task['status']}"
        assert new_task['name'] != original_task['name'], "复制的任务名称应不同"
        assert new_task['template_id'] == original_task['template_id'], "模板 ID 应一致"
        assert new_task['total_volume'] == original_task['total_volume'], "总体积应一致"
        assert new_task['deviation_note'] is None, "偏差备注不应复制"
        assert new_task['rejected_reason'] is None, "驳回原因不应复制"
        print(f"  ✅ 任务复制成功: #{task_id} → #{new_task_id}, 状态=草稿")
        
        new_wells = db.execute(
            'SELECT well_row, well_col, well_type, sample_name, primer_name, master_mix_volume, water_volume, total_volume '
            'FROM task_wells WHERE task_id = ? ORDER BY well_row, well_col',
            (new_task_id,)
        ).fetchall()
        assert len(new_wells) == len(original_wells), \
            f"孔位数量不一致: {len(new_wells)} vs {len(original_wells)}"
        
        for ow, nw in zip(original_wells, new_wells):
            assert ow['well_row'] == nw['well_row'], "孔位行号不一致"
            assert ow['well_col'] == nw['well_col'], "孔位列号不一致"
            assert ow['well_type'] == nw['well_type'], "孔位类型不一致"
            assert ow['sample_name'] == nw['sample_name'], "样本名不一致"
            assert ow['primer_name'] == nw['primer_name'], "引物名不一致"
            assert ow['master_mix_volume'] == nw['master_mix_volume'], "MM体积不一致"
            assert ow['water_volume'] == nw['water_volume'], "水体积不一致"
            assert ow['total_volume'] == nw['total_volume'], "总体积不一致"
        print(f"  ✅ 孔位数据完全复制: {len(new_wells)} 孔")
        
        new_reagent_usage = db.execute(
            'SELECT reagent_name, source, used_volume FROM task_reagent_usage WHERE task_id = ? ORDER BY reagent_name',
            (new_task_id,)
        ).fetchall()
        assert len(new_reagent_usage) == len(original_reagent_usage), \
            f"试剂用量记录数不一致: {len(new_reagent_usage)} vs {len(original_reagent_usage)}"
        for oru, nru in zip(original_reagent_usage, new_reagent_usage):
            assert oru['reagent_name'] == nru['reagent_name'], "试剂名不一致"
            assert oru['used_volume'] == nru['used_volume'], "试剂用量不一致"
        print(f"  ✅ 试剂用量记录复制: {len(new_reagent_usage)} 条")
        
        new_primer_usage = db.execute(
            'SELECT primer_name, used_volume FROM task_primer_usage WHERE task_id = ?',
            (new_task_id,)
        ).fetchall()
        assert len(new_primer_usage) == len(original_primer_usage), \
            f"引物用量记录数不一致"
        print(f"  ✅ 引物用量记录复制: {len(new_primer_usage)} 条")
        
        from app.services.history_service import HistoryService
        history_service = HistoryService(db, '')
        
        copy_history = history_service.get_history(task_id=new_task_id, action_type='task_copied', limit=10)
        assert len(copy_history) >= 1, "新任务应该有复制历史记录"
        print(f"  ✅ 新任务有复制历史记录")
        
        copy_from_history = history_service.get_history(task_id=task_id, action_type='task_copied_from', limit=10)
        assert len(copy_from_history) >= 1, "源任务应该有被复制历史记录"
        print(f"  ✅ 源任务有被复制历史记录")
        
        db.execute('DELETE FROM task_wells WHERE task_id = ?', (task_id,))
        db.execute('DELETE FROM task_reagent_usage WHERE task_id = ?', (task_id,))
        db.execute('DELETE FROM task_primer_usage WHERE task_id = ?', (task_id,))
        db.execute('DELETE FROM history WHERE task_id = ?', (task_id,))
        db.execute('DELETE FROM tasks WHERE id = ?', (task_id,))
        db.execute('DELETE FROM task_wells WHERE task_id = ?', (new_task_id,))
        db.execute('DELETE FROM task_reagent_usage WHERE task_id = ?', (new_task_id,))
        db.execute('DELETE FROM task_primer_usage WHERE task_id = ?', (new_task_id,))
        db.execute('DELETE FROM history WHERE task_id = ?', (new_task_id,))
        db.execute('DELETE FROM tasks WHERE id = ?', (new_task_id,))
        db.commit()
        
        results.append({'name': '任务复制成新草稿', 'passed': True})
        print("  ✅ 通过 (含孔位/试剂/引物/历史记录验证)")
    except Exception as e:
        import traceback
        traceback.print_exc()
        results.append({'name': '任务复制成新草稿', 'passed': False, 'error': str(e)})
        print(f"  ❌ 失败: {e}")


def test_task_export_import(db, app, results):
    print("\n--- 测试22: 任务方案 JSON 导出与导入 ---")
    try:
        client = app.test_client()
        from app.services.task_service import TaskService
        service = TaskService(db)
        
        template = db.execute('SELECT * FROM plate_templates LIMIT 1').fetchone()
        assert template is not None, "需要至少一个模板"
        
        task_id = service.create_task(
            name='_导出导入测试_源任务',
            template_id=template['id'],
            total_volume=25,
            volume_unit='ul'
        )
        
        primer = db.execute("SELECT * FROM primers LIMIT 1").fetchone()
        mm = db.execute("SELECT * FROM reagents WHERE type = 'master_mix' LIMIT 1").fetchone()
        water = db.execute("SELECT * FROM reagents WHERE type = 'water' LIMIT 1").fetchone()
        
        service.generate_plan(
            task_id=task_id,
            primer_id=primer['id'],
            master_mix_id=mm['id'],
            water_id=water['id'],
        )
        
        original_wells = db.execute(
            'SELECT well_row, well_col, well_type, sample_name '
            'FROM task_wells WHERE task_id = ? ORDER BY well_row, well_col',
            (task_id,)
        ).fetchall()
        
        resp = client.get(f'/api/tasks/{task_id}/export/json')
        assert resp.status_code == 200, f"导出失败: HTTP {resp.status_code}"
        json_data = json.loads(resp.data.decode('utf-8'))
        
        assert 'schema_version' in json_data, "导出 JSON 缺少 schema_version"
        assert 'task' in json_data, "导出 JSON 缺少 task"
        assert 'template' in json_data, "导出 JSON 缺少 template"
        assert 'wells' in json_data, "导出 JSON 缺少 wells"
        assert 'reagent_usage' in json_data, "导出 JSON 缺少 reagent_usage"
        assert 'primer_usage' in json_data, "导出 JSON 缺少 primer_usage"
        assert json_data['task']['total_volume'] == 25, "导出的总体积不对"
        assert json_data['template']['name'] == template['name'], "导出的模板名不对"
        assert len(json_data['wells']) == len(original_wells), "导出的孔位数不对"
        print(f"  ✅ JSON 导出成功: schema={json_data['schema_version']}, wells={len(json_data['wells'])}")
        
        import_task_name = '_导出导入测试_导入任务'
        import_data = dict(json_data)
        import_data['task'] = dict(json_data['task'])
        import_data['task']['name'] = import_task_name
        
        resp_import = client.post('/api/tasks/import', json=import_data)
        assert resp_import.status_code == 201, \
            f"导入失败: HTTP {resp_import.status_code} - {resp_import.get_json()}"
        
        imported = resp_import.get_json()
        assert imported['task']['name'] == import_task_name, "导入任务名不对"
        assert imported['task']['status'] == 'draft', f"导入后状态应为 draft，实际 {imported['task']['status']}"
        assert imported['task']['total_volume'] == 25, "导入总体积不对"
        print(f"  ✅ JSON 导入成功: task_id={imported['task']['id']}, status={imported['task']['status']}")
        
        imported_wells = db.execute(
            'SELECT well_row, well_col, well_type, sample_name '
            'FROM task_wells WHERE task_id = ? ORDER BY well_row, well_col',
            (imported['task']['id'],)
        ).fetchall()
        assert len(imported_wells) == len(original_wells), \
            f"导入孔位数不一致: {len(imported_wells)} vs {len(original_wells)}"
        
        for ow, iw in zip(original_wells, imported_wells):
            assert ow['well_row'] == iw['well_row'], "孔位行号不一致"
            assert ow['well_col'] == iw['well_col'], "孔位列号不一致"
            assert ow['well_type'] == iw['well_type'], "孔位类型不一致"
            assert ow['sample_name'] == iw['sample_name'], "样本名不一致"
        print(f"  ✅ 导入孔位数据一致: {len(imported_wells)} 孔")
        
        from app.services.history_service import HistoryService
        history_service = HistoryService(db, '')
        import_history = history_service.get_history(
            task_id=imported['task']['id'], action_type='task_imported', limit=10
        )
        assert len(import_history) >= 1, "导入任务应该有历史记录"
        print(f"  ✅ 导入历史记录已记录")
        
        export_history = history_service.get_history(
            task_id=task_id, action_type='task_exported', limit=10
        )
        assert len(export_history) >= 1, "导出任务应该有历史记录"
        print(f"  ✅ 导出历史记录已记录")
        
        db.execute('DELETE FROM task_wells WHERE task_id = ?', (task_id,))
        db.execute('DELETE FROM task_reagent_usage WHERE task_id = ?', (task_id,))
        db.execute('DELETE FROM task_primer_usage WHERE task_id = ?', (task_id,))
        db.execute('DELETE FROM history WHERE task_id = ?', (task_id,))
        db.execute('DELETE FROM tasks WHERE id = ?', (task_id,))
        db.execute('DELETE FROM task_wells WHERE task_id = ?', (imported['task']['id'],))
        db.execute('DELETE FROM task_reagent_usage WHERE task_id = ?', (imported['task']['id'],))
        db.execute('DELETE FROM task_primer_usage WHERE task_id = ?', (imported['task']['id'],))
        db.execute('DELETE FROM history WHERE task_id = ?', (imported['task']['id'],))
        db.execute('DELETE FROM tasks WHERE id = ?', (imported['task']['id'],))
        db.commit()
        
        results.append({'name': '任务方案JSON导出与导入', 'passed': True})
        print("  ✅ 通过 (导出→导入→孔位一致→历史记录)")
    except Exception as e:
        import traceback
        traceback.print_exc()
        results.append({'name': '任务方案JSON导出与导入', 'passed': False, 'error': str(e)})
        print(f"  ❌ 失败: {e}")


def test_task_import_conflict(db, app, results):
    print("\n--- 测试23: 任务导入冲突拦截 ---")
    try:
        client = app.test_client()
        from app.services.task_service import TaskService
        service = TaskService(db)
        
        template = db.execute('SELECT * FROM plate_templates LIMIT 1').fetchone()
        assert template is not None, "需要至少一个模板"
        
        task_id = service.create_task(
            name='_冲突测试_同名任务',
            template_id=template['id'],
            total_volume=20,
            volume_unit='ul'
        )
        
        primer = db.execute("SELECT * FROM primers LIMIT 1").fetchone()
        mm = db.execute("SELECT * FROM reagents WHERE type = 'master_mix' LIMIT 1").fetchone()
        water = db.execute("SELECT * FROM reagents WHERE type = 'water' LIMIT 1").fetchone()
        
        service.generate_plan(
            task_id=task_id,
            primer_id=primer['id'],
            master_mix_id=mm['id'],
            water_id=water['id'],
        )
        
        resp = client.get(f'/api/tasks/{task_id}/export/json')
        json_data = json.loads(resp.data.decode('utf-8'))
        
        import_data = dict(json_data)
        import_data['task'] = dict(json_data['task'])
        import_data['task']['name'] = '_冲突测试_同名任务'
        
        resp_reject = client.post('/api/tasks/import', json=import_data)
        assert resp_reject.status_code == 409, \
            f"同名导入默认应返回 409，实际 {resp_reject.status_code}"
        reject_data = resp_reject.get_json()
        assert 'conflict' in reject_data, "冲突响应应含 conflict 字段"
        assert reject_data['conflict'] == 'name_exists', "冲突类型应为 name_exists"
        assert 'existing_id' in reject_data, "冲突响应应含 existing_id"
        print(f"  ✅ 同名冲突拒绝: HTTP 409, conflict=name_exists")
        
        tasks_before_rename = db.execute('SELECT COUNT(*) as cnt FROM tasks').fetchone()['cnt']
        resp_rename = client.post('/api/tasks/import?conflict_mode=rename', json=import_data)
        assert resp_rename.status_code == 201, \
            f"rename 模式应返回 201，实际 {resp_rename.status_code}"
        renamed = resp_rename.get_json()
        assert renamed['task']['name'] != '_冲突测试_同名任务', "rename 后名称应不同"
        assert renamed['task']['name'].startswith('_冲突测试_同名任务'), "rename 应基于原名"
        tasks_after_rename = db.execute('SELECT COUNT(*) as cnt FROM tasks').fetchone()['cnt']
        assert tasks_after_rename == tasks_before_rename + 1, "应新增 1 个任务"
        print(f"  ✅ rename 模式: 原任务保留，新增任务 {renamed['task']['name']}")
        
        bad_template_data = dict(json_data)
        bad_template_data['template'] = dict(json_data['template'])
        bad_template_data['template']['name'] = '不存在的模板_xxx'
        bad_template_data['task'] = dict(json_data['task'])
        bad_template_data['task']['name'] = '_冲突测试_坏模板'
        
        resp_bad_tpl = client.post('/api/tasks/import', json=bad_template_data)
        assert resp_bad_tpl.status_code == 400, \
            f"不存在的模板应返回 400，实际 {resp_bad_tpl.status_code}"
        assert '模板不存在' in resp_bad_tpl.get_json()['error'], \
            "错误信息应包含模板不存在"
        print(f"  ✅ 模板不存在拦截: HTTP 400")
        
        bad_size_data = dict(json_data)
        bad_size_data['template'] = dict(json_data['template'])
        bad_size_data['template']['rows'] = 99
        bad_size_data['template']['cols'] = 99
        bad_size_data['task'] = dict(json_data['task'])
        bad_size_data['task']['name'] = '_冲突测试_尺寸不匹配'
        
        resp_bad_size = client.post('/api/tasks/import', json=bad_size_data)
        assert resp_bad_size.status_code == 400, \
            f"模板尺寸不匹配应返回 400，实际 {resp_bad_size.status_code}"
        assert '尺寸不匹配' in resp_bad_size.get_json()['error'], \
            "错误信息应包含尺寸不匹配"
        print(f"  ✅ 模板尺寸不匹配拦截: HTTP 400")
        
        bad_reagent_data = dict(json_data)
        bad_reagent_data['reagent_usage'] = [
            {'reagent_name': '不存在的试剂_xyz', 'source': 'master_mix', 'used_volume': 10, 'used_volume_unit': 'ul'}
        ]
        bad_reagent_data['task'] = dict(json_data['task'])
        bad_reagent_data['task']['name'] = '_冲突测试_缺试剂'
        
        resp_bad_reagent = client.post('/api/tasks/import', json=bad_reagent_data)
        assert resp_bad_reagent.status_code == 400, \
            f"缺少试剂应返回 400，实际 {resp_bad_reagent.status_code}"
        assert '缺少试剂' in resp_bad_reagent.get_json()['error'], \
            "错误信息应包含缺少试剂"
        print(f"  ✅ 缺失试剂拦截: HTTP 400")
        
        bad_primer_data = dict(json_data)
        bad_primer_data['primer_usage'] = [
            {'primer_name': '不存在的引物_xyz', 'source': 'primer', 'used_volume': 5, 'used_volume_unit': 'ul'}
        ]
        bad_primer_data['task'] = dict(json_data['task'])
        bad_primer_data['task']['name'] = '_冲突测试_缺引物'
        
        resp_bad_primer = client.post('/api/tasks/import', json=bad_primer_data)
        assert resp_bad_primer.status_code == 400, \
            f"缺少引物应返回 400，实际 {resp_bad_primer.status_code}"
        assert '缺少引物' in resp_bad_primer.get_json()['error'], \
            "错误信息应包含缺少引物"
        print(f"  ✅ 缺失引物拦截: HTTP 400")
        
        tasks_final = db.execute('SELECT COUNT(*) as cnt FROM tasks').fetchone()['cnt']
        assert tasks_final == tasks_before_rename + 1, \
            "失败导入不应残留任务（除了 rename 成功的那个）"
        print(f"  ✅ 失败导入无脏数据残留")
        
        db.execute('DELETE FROM task_wells WHERE task_id = ?', (task_id,))
        db.execute('DELETE FROM task_reagent_usage WHERE task_id = ?', (task_id,))
        db.execute('DELETE FROM task_primer_usage WHERE task_id = ?', (task_id,))
        db.execute('DELETE FROM history WHERE task_id = ?', (task_id,))
        db.execute('DELETE FROM tasks WHERE id = ?', (task_id,))
        db.execute('DELETE FROM task_wells WHERE task_id = ?', (renamed['task']['id'],))
        db.execute('DELETE FROM task_reagent_usage WHERE task_id = ?', (renamed['task']['id'],))
        db.execute('DELETE FROM task_primer_usage WHERE task_id = ?', (renamed['task']['id'],))
        db.execute('DELETE FROM history WHERE task_id = ?', (renamed['task']['id'],))
        db.execute('DELETE FROM tasks WHERE id = ?', (renamed['task']['id'],))
        db.commit()
        
        results.append({'name': '任务导入冲突拦截', 'passed': True})
        print("  ✅ 通过 (重名/缺模板/尺寸错/缺试剂/缺引物 → 全拦截，无脏数据)")
    except Exception as e:
        import traceback
        traceback.print_exc()
        results.append({'name': '任务导入冲突拦截', 'passed': False, 'error': str(e)})
        print(f"  ❌ 失败: {e}")


def test_task_import_then_approve(db, app, results):
    print("\n--- 测试24: 导入任务后审批流程 ---")
    try:
        client = app.test_client()
        from app.services.task_service import TaskService
        service = TaskService(db)
        
        template = db.execute('SELECT * FROM plate_templates LIMIT 1').fetchone()
        
        source_task_id = service.create_task(
            name='_审批测试_源任务',
            template_id=template['id'],
            total_volume=20,
            volume_unit='ul'
        )
        
        primer = db.execute("SELECT * FROM primers LIMIT 1").fetchone()
        mm = db.execute("SELECT * FROM reagents WHERE type = 'master_mix' LIMIT 1").fetchone()
        water = db.execute("SELECT * FROM reagents WHERE type = 'water' LIMIT 1").fetchone()
        
        service.generate_plan(
            task_id=source_task_id,
            primer_id=primer['id'],
            master_mix_id=mm['id'],
            water_id=water['id'],
        )
        
        resp = client.get(f'/api/tasks/{source_task_id}/export/json')
        json_data = json.loads(resp.data.decode('utf-8'))
        
        import_data = dict(json_data)
        import_data['task'] = dict(json_data['task'])
        import_data['task']['name'] = '_审批测试_导入任务'
        
        resp_import = client.post('/api/tasks/import', json=import_data)
        assert resp_import.status_code == 201
        imported = resp_import.get_json()
        imported_id = imported['task']['id']
        print(f"  ✅ 任务导入成功: id={imported_id}, status={imported['task']['status']}")
        
        assert imported['task']['status'] == 'draft', "导入任务应为草稿状态"
        
        resp_gen = client.post(f'/api/tasks/{imported_id}/generate', json={})
        assert resp_gen.status_code == 200, \
            f"导入的任务应能重新生成方案: {resp_gen.status_code}"
        gen_result = resp_gen.get_json()
        assert gen_result['status'] == 'pending_review', "生成后应为待复核状态"
        print(f"  ✅ 导入任务可重新生成方案: status={gen_result['status']}")
        
        mm_before = db.execute(
            'SELECT volume FROM reagents WHERE id = ?', (mm['id'],)
        ).fetchone()['volume']
        
        resp_approve = client.post(f'/api/tasks/{imported_id}/approve', 
                                   json={'ignore_min_pipette': True})
        assert resp_approve.status_code == 200, \
            f"导入任务应能批准: {resp_approve.status_code}"
        print(f"  ✅ 导入任务可成功批准")
        
        mm_after = db.execute(
            'SELECT volume FROM reagents WHERE id = ?', (mm['id'],)
        ).fetchone()['volume']
        assert mm_after < mm_before, "批准后库存应扣减"
        print(f"  ✅ 批准后库存正常扣减: {mm_before:.2f} → {mm_after:.2f} µL")
        
        task_after = db.execute('SELECT status FROM tasks WHERE id = ?', (imported_id,)).fetchone()
        assert task_after['status'] == 'approved', "批准后状态应为 approved"
        
        resp_revoke = client.post(f'/api/tasks/{imported_id}/revoke', json={})
        assert resp_revoke.status_code == 200, \
            f"导入任务应能撤销: {resp_revoke.status_code}"
        print(f"  ✅ 导入任务可撤销批准")
        
        mm_revoked = db.execute(
            'SELECT volume FROM reagents WHERE id = ?', (mm['id'],)
        ).fetchone()['volume']
        assert mm_revoked == mm_before, "撤销后库存应退回"
        print(f"  ✅ 撤销后库存退回: {mm_after:.2f} → {mm_revoked:.2f} µL")
        
        db.execute('DELETE FROM task_wells WHERE task_id = ?', (source_task_id,))
        db.execute('DELETE FROM task_reagent_usage WHERE task_id = ?', (source_task_id,))
        db.execute('DELETE FROM task_primer_usage WHERE task_id = ?', (source_task_id,))
        db.execute('DELETE FROM history WHERE task_id = ?', (source_task_id,))
        db.execute('DELETE FROM tasks WHERE id = ?', (source_task_id,))
        db.execute('DELETE FROM task_wells WHERE task_id = ?', (imported_id,))
        db.execute('DELETE FROM task_reagent_usage WHERE task_id = ?', (imported_id,))
        db.execute('DELETE FROM task_primer_usage WHERE task_id = ?', (imported_id,))
        db.execute('DELETE FROM reagent_inventory_log WHERE task_id = ?', (imported_id,))
        db.execute('DELETE FROM primer_inventory_log WHERE task_id = ?', (imported_id,))
        db.execute('DELETE FROM history WHERE task_id = ?', (imported_id,))
        db.execute('DELETE FROM tasks WHERE id = ?', (imported_id,))
        db.commit()
        
        results.append({'name': '导入任务后审批流程', 'passed': True})
        print("  ✅ 通过 (导入→生成→批准→扣库存→撤销→退库存 全链路)")
    except Exception as e:
        import traceback
        traceback.print_exc()
        results.append({'name': '导入任务后审批流程', 'passed': False, 'error': str(e)})
        print(f"  ❌ 失败: {e}")


def test_task_copy_status_restrictions(db, app, results):
    print("\n--- 测试25: 任务复制状态限制 ---")
    try:
        from app.services.task_service import TaskService
        service = TaskService(db)
        
        template = db.execute('SELECT * FROM plate_templates LIMIT 1').fetchone()
        
        draft_id = service.create_task(
            name='_状态测试_草稿',
            template_id=template['id'],
            total_volume=20,
            volume_unit='ul'
        )
        draft_copy_id = service.copy_task(draft_id)
        assert draft_copy_id > 0, "草稿任务应能复制"
        print(f"  ✅ 草稿状态可复制")
        
        pending_id = service.create_task(
            name='_状态测试_待复核',
            template_id=template['id'],
            total_volume=20,
            volume_unit='ul'
        )
        primer = db.execute("SELECT * FROM primers LIMIT 1").fetchone()
        mm = db.execute("SELECT * FROM reagents WHERE type = 'master_mix' LIMIT 1").fetchone()
        water = db.execute("SELECT * FROM reagents WHERE type = 'water' LIMIT 1").fetchone()
        service.generate_plan(task_id=pending_id, primer_id=primer['id'],
                             master_mix_id=mm['id'], water_id=water['id'])
        pending_copy_id = service.copy_task(pending_id)
        assert pending_copy_id > 0, "待复核任务应能复制"
        print(f"  ✅ 待复核状态可复制")
        
        approved_id = service.create_task(
            name='_状态测试_已批准',
            template_id=template['id'],
            total_volume=20,
            volume_unit='ul'
        )
        service.generate_plan(task_id=approved_id, primer_id=primer['id'],
                             master_mix_id=mm['id'], water_id=water['id'])
        service.approve_task(approved_id, ignore_min_pipette=True)
        approved_copy_id = service.copy_task(approved_id)
        assert approved_copy_id > 0, "已批准任务应能复制"
        approved_copy = db.execute('SELECT status FROM tasks WHERE id = ?', 
                                  (approved_copy_id,)).fetchone()
        assert approved_copy['status'] == 'draft', \
            "复制已批准任务后状态应为草稿，不继承审批状态"
        print(f"  ✅ 已批准状态可复制，复制后重置为草稿")
        
        service.reject_task(pending_id, reason='测试驳回')
        try:
            service.copy_task(pending_id)
            results.append({'name': '任务复制状态限制', 'passed': False, 
                           'error': '已驳回任务应该不能复制'})
            print("  ❌ 失败: 已驳回任务被允许复制了")
        except ValueError as e:
            if '才能复制' in str(e):
                print(f"  ✅ 已驳回状态正确拦截")
            else:
                raise e
        
        for tid in [draft_id, draft_copy_id, pending_id, pending_copy_id, 
                   approved_id, approved_copy_id]:
            db.execute('DELETE FROM task_wells WHERE task_id = ?', (tid,))
            db.execute('DELETE FROM task_reagent_usage WHERE task_id = ?', (tid,))
            db.execute('DELETE FROM task_primer_usage WHERE task_id = ?', (tid,))
            db.execute('DELETE FROM reagent_inventory_log WHERE task_id = ?', (tid,))
            db.execute('DELETE FROM primer_inventory_log WHERE task_id = ?', (tid,))
            db.execute('DELETE FROM history WHERE task_id = ?', (tid,))
            db.execute('DELETE FROM tasks WHERE id = ?', (tid,))
        db.commit()
        
        results.append({'name': '任务复制状态限制', 'passed': True})
        print("  ✅ 通过 (草稿/待复核/已批准可复制，已驳回拦截)")
    except Exception as e:
        import traceback
        traceback.print_exc()
        results.append({'name': '任务复制状态限制', 'passed': False, 'error': str(e)})
        print(f"  ❌ 失败: {e}")


def test_task_e2e_copy_import_approve(db, app, db_path, results):
    print("\n--- 测试26: 任务复跑全链路端到端验证 ---")
    try:
        client = app.test_client()
        from app.services.task_service import TaskService
        service = TaskService(db)
        from app.services.history_service import HistoryService
        history_service = HistoryService(db, app.config['DATA_DIR'])
        
        template = db.execute('SELECT * FROM plate_templates LIMIT 1').fetchone()
        
        task_id = service.create_task(
            name='_e2e_原始任务',
            template_id=template['id'],
            total_volume=20,
            volume_unit='ul'
        )
        
        primer = db.execute("SELECT * FROM primers LIMIT 1").fetchone()
        mm = db.execute("SELECT * FROM reagents WHERE type = 'master_mix' LIMIT 1").fetchone()
        water = db.execute("SELECT * FROM reagents WHERE type = 'water' LIMIT 1").fetchone()
        
        service.generate_plan(
            task_id=task_id,
            primer_id=primer['id'],
            master_mix_id=mm['id'],
            water_id=water['id'],
        )
        service.approve_task(task_id, ignore_min_pipette=True)
        
        history_before = db.execute('SELECT COUNT(*) as cnt FROM history').fetchone()['cnt']
        print(f"  初始状态: 任务 #{task_id} 已批准, 历史记录 {history_before} 条")
        
        resp_copy = client.post(f'/api/tasks/{task_id}/copy', json={})
        assert resp_copy.status_code == 201
        copied = resp_copy.get_json()
        copy_id = copied['task']['id']
        assert copied['task']['status'] == 'draft', "复制后应为草稿"
        assert copied['task']['total_volume'] == 20, "总体积应一致"
        print(f"  ① 复制成功: #{task_id} → #{copy_id} (草稿)")
        
        resp_export = client.get(f'/api/tasks/{task_id}/export/json')
        assert resp_export.status_code == 200
        export_json = json.loads(resp_export.data.decode('utf-8'))
        
        import_data = dict(export_json)
        import_data['task'] = dict(export_json['task'])
        import_data['task']['name'] = '_e2e_导入任务'
        
        resp_import = client.post('/api/tasks/import', json=import_data)
        assert resp_import.status_code == 201
        imported = resp_import.get_json()
        import_id = imported['task']['id']
        assert imported['task']['status'] == 'draft'
        print(f"  ② 导入成功: #{import_id} (草稿)")
        
        resp_gen = client.post(f'/api/tasks/{import_id}/generate', json={})
        assert resp_gen.status_code == 200
        print(f"  ③ 导入任务生成方案: status={resp_gen.get_json()['status']}")
        
        resp_approve = client.post(f'/api/tasks/{import_id}/approve', 
                                   json={'ignore_min_pipette': True})
        assert resp_approve.status_code == 200
        print(f"  ④ 导入任务批准成功")
        
        all_history = history_service.get_history(limit=200)
        action_types = set(h['action_type'] for h in all_history)
        
        assert 'task_copied' in action_types, "缺少 task_copied 历史"
        assert 'task_copied_from' in action_types, "缺少 task_copied_from 历史"
        assert 'task_exported' in action_types, "缺少 task_exported 历史"
        assert 'task_imported' in action_types, "缺少 task_imported 历史"
        print(f"  ⑤ 历史记录完整: {', '.join(sorted(action_types & {'task_copied','task_copied_from','task_exported','task_imported'}))}")
        
        import sqlite3
        verify_conn = sqlite3.connect(db_path)
        verify_conn.row_factory = sqlite3.Row
        
        restart_copied = verify_conn.execute(
            'SELECT id, name, status, total_volume FROM tasks WHERE id = ?',
            (copy_id,)
        ).fetchone()
        assert restart_copied is not None, "重启后复制的任务应存在"
        assert restart_copied['status'] == 'draft', "重启后状态应为草稿"
        
        restart_imported = verify_conn.execute(
            'SELECT id, name, status FROM tasks WHERE id = ?',
            (import_id,)
        ).fetchone()
        assert restart_imported is not None, "重启后导入的任务应存在"
        assert restart_imported['status'] == 'approved', "重启后状态应为已批准"
        
        restart_history = verify_conn.execute(
            "SELECT COUNT(*) as cnt FROM history WHERE action_type IN "
            "('task_copied','task_copied_from','task_exported','task_imported')"
        ).fetchone()['cnt']
        assert restart_history >= 4, "重启后相关历史记录应保留"
        
        print(f"  ⑥ 重启验证: 复制任务=#{restart_copied['id']} ({restart_copied['status']}), "
              f"导入任务=#{restart_imported['id']} ({restart_imported['status']}), "
              f"历史记录={restart_history} 条")
        
        verify_conn.close()
        
        resp_revoke = client.post(f'/api/tasks/{import_id}/revoke', json={})
        assert resp_revoke.status_code == 200, "重启后应能继续撤销"
        print(f"  ⑦ 重启后可继续操作: 撤销成功")
        
        for tid in [task_id, copy_id, import_id]:
            db.execute('DELETE FROM task_wells WHERE task_id = ?', (tid,))
            db.execute('DELETE FROM task_reagent_usage WHERE task_id = ?', (tid,))
            db.execute('DELETE FROM task_primer_usage WHERE task_id = ?', (tid,))
            db.execute('DELETE FROM reagent_inventory_log WHERE task_id = ?', (tid,))
            db.execute('DELETE FROM primer_inventory_log WHERE task_id = ?', (tid,))
            db.execute('DELETE FROM history WHERE task_id = ?', (tid,))
            db.execute('DELETE FROM tasks WHERE id = ?', (tid,))
        db.commit()
        
        results.append({'name': '任务复跑全链路端到端', 'passed': True})
        print("  ✅ 通过 (复制→导出→导入→生成→批准→历史→重启→撤销 全通)")
    except Exception as e:
        import traceback
        traceback.print_exc()
        results.append({'name': '任务复跑全链路端到端', 'passed': False, 'error': str(e)})
        print(f"  ❌ 失败: {e}")


def test_data_persistence(db, app, db_path, results):
    print("\n--- 测试19: 重启后数据一致性 ---")
    try:
        tasks_before = db.execute('SELECT id, name, status FROM tasks ORDER BY id').fetchall()
        reagents_before = db.execute('SELECT id, name, volume FROM reagents ORDER BY id').fetchall()
        history_before = db.execute('SELECT COUNT(*) as cnt FROM history').fetchone()['cnt']
        
        task_ids = [t['id'] for t in tasks_before]
        reagent_volumes = {r['name']: r['volume'] for r in reagents_before}
        
        approved_before = db.execute(
            "SELECT COUNT(*) as cnt FROM tasks WHERE status = 'approved'"
        ).fetchone()['cnt']
        revoked_before = db.execute(
            "SELECT COUNT(*) as cnt FROM tasks WHERE status = 'revoked'"
        ).fetchone()['cnt']
        
        import sqlite3
        verify_conn = sqlite3.connect(db_path)
        verify_conn.row_factory = sqlite3.Row
        
        tasks_after = verify_conn.execute('SELECT id, name, status FROM tasks ORDER BY id').fetchall()
        reagents_after = verify_conn.execute('SELECT id, name, volume FROM reagents ORDER BY id').fetchall()
        history_after = verify_conn.execute('SELECT COUNT(*) as cnt FROM history').fetchone()['cnt']
        
        task_ids_after = [t['id'] for t in tasks_after]
        assert task_ids == task_ids_after, "重启后任务列表不一致"
        
        for r in reagents_after:
            assert r['volume'] == reagent_volumes[r['name']], f"试剂 {r['name']} 库存不一致"
        
        assert history_after == history_before, "重启后历史记录数不一致"
        
        approved_after = verify_conn.execute(
            "SELECT COUNT(*) as cnt FROM tasks WHERE status = 'approved'"
        ).fetchone()['cnt']
        revoked_after = verify_conn.execute(
            "SELECT COUNT(*) as cnt FROM tasks WHERE status = 'revoked'"
        ).fetchone()['cnt']
        
        assert approved_before == approved_after, "重启后已批准任务数不一致"
        assert revoked_before == revoked_after, "重启后已撤销任务数不一致"
        
        print(f"  已批准任务: {approved_after} 个")
        print(f"  已撤销任务: {revoked_after} 个")
        print(f"  历史记录: {history_after} 条")
        
        from app.services.history_service import HistoryService
        history_service = HistoryService(db, app.config['DATA_DIR'])
        json_export = history_service.export_history_json()
        export_data = json.loads(json_export)
        
        assert len(export_data['tasks']) == len(tasks_before), "JSON 导出任务数不一致"
        assert len(export_data['history']) == history_before, "JSON 导出历史记录数不一致"
        
        verify_conn.close()
        
        results.append({'name': '重启后数据一致性', 'passed': True})
        print("  ✅ 通过")
    except Exception as e:
        results.append({'name': '重启后数据一致性', 'passed': False, 'error': str(e)})
        print(f"  ❌ 失败: {e}")


def test_user_template_flow_e2e(db, app, results):
    """用户可感知链路验证：导出模板→再导入→复制→建任务→生成方案
    覆盖用户照着 README 一步步点下来能否完整走通。"""
    print("\n--- 测试15: 用户链路端到端 (导出→再导入→复制→建任务)")
    try:
        client = app.test_client()

        # === Step 0: 选一个已有模板作为起点
        base = db.execute('SELECT * FROM plate_templates LIMIT 1').fetchone()
        assert base is not None, "需要至少一个模板"
        base_wells = db.execute(
            'SELECT well_row, well_col, well_type, sample_name '
            'FROM template_wells WHERE template_id = ? ORDER BY well_row, well_col',
            (base['id'],)
        ).fetchall()

        # === Step 1: 导出 JSON (模拟用户在模板列表点"导出 JSON")
        resp_json = client.get(f'/api/templates/{base["id"]}/export/json')
        assert resp_json.status_code == 200, f"导出 JSON 失败 HTTP {resp_json.status_code}"
        raw_json = json.loads(resp_json.data.decode('utf-8'))
        assert raw_json['name'] == base['name'], f"导出的 JSON 中 name 不匹配"
        assert len(raw_json['wells']) == len(base_wells), \
            f"导出孔位数不匹配: {len(raw_json['wells'])} vs {len(base_wells)}"
        print(f"  ① 导出 JSON  OK  →  filename={base['name']}.json, wells={len(raw_json['wells'])}")

        # === Step 2: 用导出的 JSON 重新导入 (模拟用户换了一台机器重新导入)
        reimport_name = base['name'] + '_重新导入'
        resp_import = client.post('/api/templates/import', json={
            'name': reimport_name,
            'rows': raw_json['rows'],
            'cols': raw_json['cols'],
            'wells': raw_json['wells'],
        })
        assert resp_import.status_code == 201, \
            f"重新导入失败: {resp_import.status_code} {resp_import.get_json()}"
        reimported = resp_import.get_json()

        # 校验孔位内容完全一致
        reimported_wells = db.execute(
            'SELECT well_row, well_col, well_type, sample_name '
            'FROM template_wells WHERE template_id = ? ORDER BY well_row, well_col',
            (reimported['id'],)
        ).fetchall()
        assert len(reimported_wells) == len(base_wells), \
            f"重导入后孔位数不一致: {len(reimported_wells)} vs {len(base_wells)}"
        for bw, rw in zip(base_wells, reimported_wells):
            assert (bw['well_row'] == rw['well_row'] and
                  bw['well_col'] == rw['well_col'] and
                  bw['well_type'] == rw['well_type'] and
                  bw['sample_name'] == rw['sample_name']), \
                f"孔位不一致: base=({bw['well_row']},{bw['well_col']}) {bw['well_type']}/{bw['sample_name']} " \
                f"vs reimported=({rw['well_row']},{rw['well_col']}) {rw['well_type']}/{rw['sample_name']}"
        print(f"  ② JSON 重新导入 OK  →  name={reimported['name']}, wells={len(reimported_wells)}, 内容一致")

        # === Step 3: 复制模板 (模拟用户想基于已有模板微调)
        copy_name = base['name'] + '_用户副本'
        resp_copy = client.post(f'/api/templates/{base["id"]}/copy',
                            json={'name': copy_name})
        assert resp_copy.status_code == 201, f"复制失败: {resp_copy.status_code} {resp_copy.get_json()}"
        copied = resp_copy.get_json()
        copied_wells = db.execute(
            'SELECT well_row, well_col, well_type, sample_name '
            'FROM template_wells WHERE template_id = ? ORDER BY well_row, well_col',
            (copied['id'],)
        ).fetchall()
        for bw, cw in zip(base_wells, copied_wells):
            assert bw['well_type'] == cw['well_type'], \
                f"复制后孔位类型不匹配: ({cw['well_row']},{cw['well_col']})"
        print(f"  ③ 复制模板   OK  →  {base['name']} → {copied['name']}, wells={len(copied_wells)}")

        # === Step 4: 用复制出的模板创建任务 + 生成方案 (验证复制品可以真能用)
        from app.services.task_service import TaskService
        service = TaskService(db)
        task_id = service.create_task(
            name='_用户链路_副本建任务',
            template_id=copied['id'],
            total_volume=20,
            volume_unit='ul'
        )
        primer = db.execute("SELECT * FROM primers LIMIT 1").fetchone()
        mm = db.execute("SELECT * FROM reagents WHERE type = 'master_mix' LIMIT 1").fetchone()
        water = db.execute("SELECT * FROM reagents WHERE type = 'water' LIMIT 1").fetchone()
        assert all([primer, mm, water]), "缺少基础数据不足，无法生成方案"
        plan = service.generate_plan(
            task_id=task_id,
            primer_id=primer['id'],
            master_mix_id=mm['id'],
            water_id=water['id'],
        )
        assert plan['status'] == 'pending_review', f"方案生成状态异常: {plan['status']}"
        task_after = db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        assert task_after['status'] == 'pending_review', \
            f"任务状态应为 pending_review，实为 {task_after['status']}"
        usage_count = db.execute(
            "SELECT COUNT(*) AS cnt FROM task_reagent_usage WHERE task_id = ?", (task_id,)
        ).fetchone()['cnt']
        assert usage_count > 0, "应生成试剂用量"
        print(f"  ④ 副本建任务  OK  →  task_id={task_id}, reagents={usage_count}, status={plan['status']}")

        # === Step 5: 同名导入冲突拒绝验证
        resp_conflict = client.post('/api/templates/import', json={
            'name': base['name'],
            'rows': 2,
            'cols': 3,
            'wells': [{'well_row': 1, 'well_col': 1, 'well_type': 'sample'}],
        })
        assert resp_conflict.status_code == 409, f"同名冲突默认应为 409, got {resp_conflict.status_code}"
        conflict_info = resp_conflict.get_json()
        assert conflict_info.get('conflict') == 'name_exists', \
            f"冲突字段不对: {conflict_info}"
        print(f"  ⑤ 冲突拒绝   OK  →  HTTP 409, conflict=name_exists")

        # 清理测试留下的临时数据，避免污染后续测试
        for tid in [task_id]:
            db.execute('DELETE FROM task_wells WHERE task_id = ?', (tid,))
            db.execute('DELETE FROM task_reagent_usage WHERE task_id = ?', (tid,))
            db.execute('DELETE FROM task_primer_usage WHERE task_id = ?', (tid,))
            db.execute('DELETE FROM history WHERE task_id = ?', (tid,))
            db.execute('DELETE FROM tasks WHERE id = ?', (tid,))
        for tplid in [reimported['id'], copied['id']]:
            db.execute('DELETE FROM template_wells WHERE template_id = ?', (tplid,))
            db.execute('DELETE FROM plate_templates WHERE id = ?', (tplid,))
        db.commit()

        results.append({'name': '用户链路端到端', 'passed': True})
        print("  ✅ 通过 (5 步全链路均 OK)")
    except Exception as e:
        import traceback as _tb
        _tb.print_exc()
        results.append({'name': '用户链路端到端', 'passed': False, 'error': str(e)})
        print(f"  ❌ 失败: {e}")


def test_snapshot_create_on_generate(db, app, results):
    print("\n--- 测试26: 生成方案自动创建快照 ---")
    try:
        client = app.test_client()
        from app.services.task_service import TaskService
        from app.services.snapshot_service import SnapshotService
        service = TaskService(db)
        snap_service = SnapshotService(db)

        template = db.execute('SELECT * FROM plate_templates LIMIT 1').fetchone()
        assert template is not None, "需要模板"

        task_id = service.create_task(
            name='_快照测试_生成方案',
            template_id=template['id'],
            total_volume=20,
            volume_unit='ul'
        )

        snapshots_before = snap_service.list_snapshots(task_id)
        assert len(snapshots_before) == 0, "生成方案前应无快照"

        primer = db.execute("SELECT * FROM primers LIMIT 1").fetchone()
        mm = db.execute("SELECT * FROM reagents WHERE type = 'master_mix' LIMIT 1").fetchone()
        water = db.execute("SELECT * FROM reagents WHERE type = 'water' LIMIT 1").fetchone()

        result = service.generate_plan(
            task_id=task_id,
            primer_id=primer['id'],
            master_mix_id=mm['id'],
            water_id=water['id']
        )

        assert 'snapshot_version' in result, "生成方案应返回快照版本号"
        assert result['snapshot_version'] == 1, "第一个快照版本应为 1"

        snapshots_after = snap_service.list_snapshots(task_id)
        assert len(snapshots_after) == 1, f"生成方案后应有 1 个快照，实际 {len(snapshots_after)}"
        assert snapshots_after[0]['snapshot_type'] == 'generate', "快照类型应为 generate"
        assert snapshots_after[0]['status'] == 'pending_review', "快照状态应为 pending_review"

        print(f"  ✅ 生成方案自动创建快照: v{snapshots_after[0]['version']}, 类型={snapshots_after[0]['snapshot_type']}")

        db.execute('DELETE FROM task_snapshots WHERE task_id = ?', (task_id,))
        db.execute('DELETE FROM task_wells WHERE task_id = ?', (task_id,))
        db.execute('DELETE FROM task_reagent_usage WHERE task_id = ?', (task_id,))
        db.execute('DELETE FROM task_primer_usage WHERE task_id = ?', (task_id,))
        db.execute('DELETE FROM history WHERE task_id = ?', (task_id,))
        db.execute('DELETE FROM tasks WHERE id = ?', (task_id,))
        db.commit()

        results.append({'name': '生成方案自动创建快照', 'passed': True})
        print("  ✅ 通过")
    except Exception as e:
        import traceback as _tb
        _tb.print_exc()
        results.append({'name': '生成方案自动创建快照', 'passed': False, 'error': str(e)})
        print(f"  ❌ 失败: {e}")


def test_snapshot_list_and_compare(db, app, results):
    print("\n--- 测试27: 快照列表与版本对比 ---")
    try:
        client = app.test_client()
        from app.services.task_service import TaskService
        from app.services.snapshot_service import SnapshotService
        service = TaskService(db)
        snap_service = SnapshotService(db)

        template = db.execute('SELECT * FROM plate_templates LIMIT 1').fetchone()
        assert template is not None, "需要模板"

        task_id = service.create_task(
            name='_快照测试_版本对比',
            template_id=template['id'],
            total_volume=20,
            volume_unit='ul'
        )

        primer = db.execute("SELECT * FROM primers LIMIT 1").fetchone()
        mm = db.execute("SELECT * FROM reagents WHERE type = 'master_mix' LIMIT 1").fetchone()
        water = db.execute("SELECT * FROM reagents WHERE type = 'water' LIMIT 1").fetchone()

        service.generate_plan(
            task_id=task_id,
            primer_id=primer['id'],
            master_mix_id=mm['id'],
            water_id=water['id']
        )

        db.execute("UPDATE tasks SET total_volume = 50, updated_at = ? WHERE id = ?",
                   ('2025-01-01T00:00:00', task_id))
        db.commit()
        snap_service.create_snapshot(task_id, 'manual', '手动快照: 修改总体积')

        snapshots = snap_service.list_snapshots(task_id)
        assert len(snapshots) == 2, f"应有 2 个快照，实际 {len(snapshots)}"
        assert snapshots[0]['version'] == 2, "最新快照版本应为 2"
        assert snapshots[1]['version'] == 1, "旧快照版本应为 1"
        print(f"  ✅ 快照列表: {len(snapshots)} 个版本，按版本倒序排列")

        diff = snap_service.compare_snapshots(task_id, 1, 2)
        assert diff['version_a'] == 1
        assert diff['version_b'] == 2

        assert 'total_volume' in diff['task_differences'], "应检测到 total_volume 差异"
        assert diff['task_differences']['total_volume']['old'] == 20
        assert diff['task_differences']['total_volume']['new'] == 50
        print(f"  ✅ 版本对比: 检测到 task_differences.total_volume 变化")

        summary = diff['summary']
        assert isinstance(summary['wells_modified'], int), "summary 应包含 wells_modified 计数"
        print(f"  ✅ 对比摘要: wells_modified={summary['wells_modified']}, reagents_modified={summary['reagents_modified']}")

        db.execute('DELETE FROM task_snapshots WHERE task_id = ?', (task_id,))
        db.execute('DELETE FROM task_wells WHERE task_id = ?', (task_id,))
        db.execute('DELETE FROM task_reagent_usage WHERE task_id = ?', (task_id,))
        db.execute('DELETE FROM task_primer_usage WHERE task_id = ?', (task_id,))
        db.execute('DELETE FROM history WHERE task_id = ?', (task_id,))
        db.execute('DELETE FROM tasks WHERE id = ?', (task_id,))
        db.commit()

        results.append({'name': '快照列表与版本对比', 'passed': True})
        print("  ✅ 通过")
    except Exception as e:
        import traceback as _tb
        _tb.print_exc()
        results.append({'name': '快照列表与版本对比', 'passed': False, 'error': str(e)})
        print(f"  ❌ 失败: {e}")


def test_snapshot_rollback(db, app, results):
    print("\n--- 测试28: 快照回滚功能 ---")
    try:
        client = app.test_client()
        from app.services.task_service import TaskService
        from app.services.snapshot_service import SnapshotService
        service = TaskService(db)
        snap_service = SnapshotService(db)

        template = db.execute('SELECT * FROM plate_templates LIMIT 1').fetchone()
        assert template is not None, "需要模板"

        task_id = service.create_task(
            name='_快照测试_回滚',
            template_id=template['id'],
            total_volume=20,
            volume_unit='ul'
        )

        primer = db.execute("SELECT * FROM primers LIMIT 1").fetchone()
        mm = db.execute("SELECT * FROM reagents WHERE type = 'master_mix' LIMIT 1").fetchone()
        water = db.execute("SELECT * FROM reagents WHERE type = 'water' LIMIT 1").fetchone()

        service.generate_plan(
            task_id=task_id,
            primer_id=primer['id'],
            master_mix_id=mm['id'],
            water_id=water['id']
        )

        v1_wells = db.execute(
            'SELECT COUNT(*) as cnt FROM task_wells WHERE task_id = ?', (task_id,)
        ).fetchone()['cnt']

        db.execute('DELETE FROM task_wells WHERE task_id = ?', (task_id,))
        db.execute(
            "INSERT INTO task_wells (task_id, well_row, well_col, well_type, total_volume, total_volume_unit) VALUES (?, 1, 1, 'sample', 10, 'ul')",
            (task_id,)
        )
        db.commit()
        snap_service.create_snapshot(task_id, 'manual', '修改后快照')

        v2_wells = db.execute(
            'SELECT COUNT(*) as cnt FROM task_wells WHERE task_id = ?', (task_id,)
        ).fetchone()['cnt']
        assert v2_wells == 1, "v2 应有 1 个孔"

        rollback_result = snap_service.rollback_to_snapshot(task_id, 1)
        assert rollback_result['rolled_back_to'] == 1
        assert rollback_result['previous_status'] == 'pending_review'
        assert rollback_result['new_status'] == 'pending_review'

        after_rollback_wells = db.execute(
            'SELECT COUNT(*) as cnt FROM task_wells WHERE task_id = ?', (task_id,)
        ).fetchone()['cnt']
        assert after_rollback_wells == v1_wells, f"回滚后孔位数应恢复为 v1 的 {v1_wells}，实际 {after_rollback_wells}"

        task_after = db.execute('SELECT * FROM tasks WHERE id = ?', (task_id,)).fetchone()
        assert task_after['status'] == 'pending_review', "回滚后状态应恢复"

        print(f"  ✅ 回滚成功: v1 ({v1_wells} 孔) ← v2 ({v2_wells} 孔) → 回滚后 {after_rollback_wells} 孔")

        db.execute('DELETE FROM task_snapshots WHERE task_id = ?', (task_id,))
        db.execute('DELETE FROM task_wells WHERE task_id = ?', (task_id,))
        db.execute('DELETE FROM task_reagent_usage WHERE task_id = ?', (task_id,))
        db.execute('DELETE FROM task_primer_usage WHERE task_id = ?', (task_id,))
        db.execute('DELETE FROM history WHERE task_id = ?', (task_id,))
        db.execute('DELETE FROM tasks WHERE id = ?', (task_id,))
        db.commit()

        results.append({'name': '快照回滚功能', 'passed': True})
        print("  ✅ 通过")
    except Exception as e:
        import traceback as _tb
        _tb.print_exc()
        results.append({'name': '快照回滚功能', 'passed': False, 'error': str(e)})
        print(f"  ❌ 失败: {e}")


def test_snapshot_rollback_status_check(db, app, results):
    print("\n--- 测试29: 回滚状态校验（已批准/已撤销不能回滚） ---")
    try:
        client = app.test_client()
        from app.services.task_service import TaskService
        from app.services.snapshot_service import SnapshotService
        service = TaskService(db)
        snap_service = SnapshotService(db)

        template = db.execute('SELECT * FROM plate_templates LIMIT 1').fetchone()
        assert template is not None, "需要模板"

        task_id = service.create_task(
            name='_快照测试_回滚状态校验',
            template_id=template['id'],
            total_volume=20,
            volume_unit='ul'
        )

        primer = db.execute("SELECT * FROM primers LIMIT 1").fetchone()
        mm = db.execute("SELECT * FROM reagents WHERE type = 'master_mix' LIMIT 1").fetchone()
        water = db.execute("SELECT * FROM reagents WHERE type = 'water' LIMIT 1").fetchone()

        service.generate_plan(
            task_id=task_id,
            primer_id=primer['id'],
            master_mix_id=mm['id'],
            water_id=water['id']
        )

        snap_v1 = snap_service.list_snapshots(task_id)
        assert len(snap_v1) >= 1, "应有至少 1 个快照"

        approved = False
        try:
            service.approve_task(task_id, ignore_min_pipette=True)
            approved = True
        except ValueError:
            pass

        task_approved = db.execute('SELECT status FROM tasks WHERE id = ?', (task_id,)).fetchone()

        if approved and task_approved and task_approved['status'] == 'approved':
            try:
                snap_service.rollback_to_snapshot(task_id, 1)
                raise AssertionError("已批准任务应该不能回滚")
            except ValueError as e:
                assert '不能回滚' in str(e) or '已批准' in str(e), f"错误信息应包含不能回滚提示: {e}"
                print(f"  ✅ 已批准任务回滚被正确拦截: {e}")

            resp = client.post(f'/api/tasks/{task_id}/snapshots/rollback',
                               json={'version': 1})
            assert resp.status_code == 409, f"已批准任务回滚应返回 409，实际 {resp.status_code}"
            print(f"  ✅ API 层已批准任务回滚返回 HTTP 409")

            service.revoke_approval(task_id)
            try:
                snap_service.rollback_to_snapshot(task_id, 1)
                raise AssertionError("已撤销任务应该不能回滚")
            except ValueError as e:
                assert '不能回滚' in str(e) or '已撤销' in str(e), f"错误信息应包含不能回滚提示: {e}"
                print(f"  ✅ 已撤销任务回滚被正确拦截: {e}")
        else:
            print("  ⚠️  跳过完整批准回滚测试（因库存不足等原因未成功批准）")

        db.execute('DELETE FROM task_snapshots WHERE task_id = ?', (task_id,))
        db.execute('DELETE FROM task_wells WHERE task_id = ?', (task_id,))
        db.execute('DELETE FROM task_reagent_usage WHERE task_id = ?', (task_id,))
        db.execute('DELETE FROM task_primer_usage WHERE task_id = ?', (task_id,))
        db.execute('DELETE FROM reagent_inventory_log WHERE task_id = ?', (task_id,))
        db.execute('DELETE FROM primer_inventory_log WHERE task_id = ?', (task_id,))
        db.execute('DELETE FROM history WHERE task_id = ?', (task_id,))
        db.execute('DELETE FROM tasks WHERE id = ?', (task_id,))
        db.commit()

        results.append({'name': '回滚状态校验', 'passed': True})
        print("  ✅ 通过")
    except Exception as e:
        import traceback as _tb
        _tb.print_exc()
        results.append({'name': '回滚状态校验', 'passed': False, 'error': str(e)})
        print(f"  ❌ 失败: {e}")


def test_snapshot_export_import(db, app, results):
    print("\n--- 测试30: 导出带快照摘要 & 导入还原 ---")
    try:
        client = app.test_client()
        from app.services.task_service import TaskService
        from app.services.snapshot_service import SnapshotService
        service = TaskService(db)
        snap_service = SnapshotService(db)

        template = db.execute('SELECT * FROM plate_templates LIMIT 1').fetchone()
        assert template is not None, "需要模板"

        task_id = service.create_task(
            name='_快照测试_导出导入',
            template_id=template['id'],
            total_volume=20,
            volume_unit='ul'
        )

        primer = db.execute("SELECT * FROM primers LIMIT 1").fetchone()
        mm = db.execute("SELECT * FROM reagents WHERE type = 'master_mix' LIMIT 1").fetchone()
        water = db.execute("SELECT * FROM reagents WHERE type = 'water' LIMIT 1").fetchone()

        service.generate_plan(
            task_id=task_id,
            primer_id=primer['id'],
            master_mix_id=mm['id'],
            water_id=water['id']
        )

        snap_service.create_snapshot(task_id, 'manual', '测试手动快照')

        snapshots_before = snap_service.list_snapshots(task_id)
        assert len(snapshots_before) == 2, f"应有 2 个快照，实际 {len(snapshots_before)}"

        resp = client.get(f'/api/tasks/{task_id}/export/json')
        assert resp.status_code == 200, f"导出失败: {resp.status_code}"

        export_data = json.loads(resp.data.decode('utf-8'))
        assert 'snapshots' in export_data, "导出 JSON 应包含 snapshots 字段"
        assert export_data['snapshots']['snapshot_count'] == 2, f"快照数量应为 2，实际 {export_data['snapshots']['snapshot_count']}"
        assert 'schema_version' in export_data['snapshots'], "快照摘要应有 schema_version"
        print(f"  ✅ 导出包含快照摘要: {export_data['snapshots']['snapshot_count']} 个快照")

        import_name = '_快照测试_导入副本'
        import_data = json.loads(json.dumps(export_data))
        import_data['task']['name'] = import_name

        resp_import = client.post('/api/tasks/import',
                                  json=import_data,
                                  content_type='application/json')
        assert resp_import.status_code == 201, f"导入失败: {resp_import.status_code} {resp_import.get_json()}"

        imported = resp_import.get_json()
        imported_task_id = imported['task']['id']

        imported_snapshots = snap_service.list_snapshots(imported_task_id)
        assert len(imported_snapshots) >= 1, f"导入后应有至少 1 个快照（导入快照），实际 {len(imported_snapshots)}"
        print(f"  ✅ 导入任务有快照: {len(imported_snapshots)} 个")

        db.execute('DELETE FROM task_snapshots WHERE task_id = ?', (task_id,))
        db.execute('DELETE FROM task_wells WHERE task_id = ?', (task_id,))
        db.execute('DELETE FROM task_reagent_usage WHERE task_id = ?', (task_id,))
        db.execute('DELETE FROM task_primer_usage WHERE task_id = ?', (task_id,))
        db.execute('DELETE FROM history WHERE task_id = ?', (task_id,))
        db.execute('DELETE FROM tasks WHERE id = ?', (task_id,))

        db.execute('DELETE FROM task_snapshots WHERE task_id = ?', (imported_task_id,))
        db.execute('DELETE FROM task_wells WHERE task_id = ?', (imported_task_id,))
        db.execute('DELETE FROM task_reagent_usage WHERE task_id = ?', (imported_task_id,))
        db.execute('DELETE FROM task_primer_usage WHERE task_id = ?', (imported_task_id,))
        db.execute('DELETE FROM history WHERE task_id = ?', (imported_task_id,))
        db.execute('DELETE FROM tasks WHERE id = ?', (imported_task_id,))
        db.commit()

        results.append({'name': '导出带快照摘要&导入还原', 'passed': True})
        print("  ✅ 通过")
    except Exception as e:
        import traceback as _tb
        _tb.print_exc()
        results.append({'name': '导出带快照摘要&导入还原', 'passed': False, 'error': str(e)})
        print(f"  ❌ 失败: {e}")


def test_snapshot_import_conflict(db, app, results):
    print("\n--- 测试31: 导入冲突拦截（版本不支持/重名/整体拒绝无脏数据） ---")
    try:
        client = app.test_client()
        from app.services.task_service import TaskService
        from app.services.snapshot_service import SnapshotService
        service = TaskService(db)
        snap_service = SnapshotService(db)

        template = db.execute('SELECT * FROM plate_templates LIMIT 1').fetchone()
        assert template is not None, "需要模板"

        task_id = service.create_task(
            name='_快照测试_冲突源',
            template_id=template['id'],
            total_volume=20,
            volume_unit='ul'
        )

        primer = db.execute("SELECT * FROM primers LIMIT 1").fetchone()
        mm = db.execute("SELECT * FROM reagents WHERE type = 'master_mix' LIMIT 1").fetchone()
        water = db.execute("SELECT * FROM reagents WHERE type = 'water' LIMIT 1").fetchone()

        service.generate_plan(
            task_id=task_id,
            primer_id=primer['id'],
            master_mix_id=mm['id'],
            water_id=water['id']
        )

        resp = client.get(f'/api/tasks/{task_id}/export/json')
        export_data = json.loads(resp.data.decode('utf-8'))

        bad_schema_data = json.loads(json.dumps(export_data))
        bad_schema_data['task']['name'] = '_快照测试_坏版本测试'
        bad_schema_data['snapshots']['schema_version'] = '99.0'

        tasks_before = len(db.execute('SELECT * FROM tasks').fetchall())

        resp_bad = client.post('/api/tasks/import',
                               json=bad_schema_data,
                               content_type='application/json')
        assert resp_bad.status_code == 400, f"版本不支持应返回 400，实际 {resp_bad.status_code}"
        bad_resp = resp_bad.get_json()
        assert '不支持' in bad_resp.get('error', ''), "错误信息应包含版本不支持"
        print(f"  ✅ 快照 schema 版本不支持被拦截: HTTP {resp_bad.status_code}")

        tasks_after_bad = len(db.execute('SELECT * FROM tasks').fetchall())
        assert tasks_after_bad == tasks_before, f"导入失败不应留下脏数据: {tasks_before} → {tasks_after_bad}"
        print(f"  ✅ 导入失败无残留: 任务数保持 {tasks_before}")

        same_name_data = json.loads(json.dumps(export_data))
        same_name_data['task']['name'] = '_快照测试_冲突源'

        resp_same = client.post('/api/tasks/import',
                                json=same_name_data,
                                content_type='application/json')
        assert resp_same.status_code == 409, f"重名应返回 409，实际 {resp_same.status_code}"
        same_resp = resp_same.get_json()
        assert same_resp.get('conflict') == 'name_exists', "冲突类型应为 name_exists"
        print(f"  ✅ 任务重名被拦截: HTTP {resp_same.status_code}, conflict=name_exists")

        tasks_after_same = len(db.execute('SELECT * FROM tasks').fetchall())
        assert tasks_after_same == tasks_before, f"重名导入失败不应残留: {tasks_before} → {tasks_after_same}"

        import_fail_history = db.execute(
            "SELECT * FROM history WHERE action_type = 'task_import_failed' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert import_fail_history is not None, "应有导入失败的历史记录"
        print(f"  ✅ 导入失败已写入历史记录: {import_fail_history['detail'][:50]}...")

        db.execute('DELETE FROM task_snapshots WHERE task_id = ?', (task_id,))
        db.execute('DELETE FROM task_wells WHERE task_id = ?', (task_id,))
        db.execute('DELETE FROM task_reagent_usage WHERE task_id = ?', (task_id,))
        db.execute('DELETE FROM task_primer_usage WHERE task_id = ?', (task_id,))
        db.execute('DELETE FROM history WHERE task_id = ?', (task_id,))
        db.execute('DELETE FROM tasks WHERE id = ?', (task_id,))
        db.commit()

        results.append({'name': '导入冲突拦截&无脏数据', 'passed': True})
        print("  ✅ 通过")
    except Exception as e:
        import traceback as _tb
        _tb.print_exc()
        results.append({'name': '导入冲突拦截&无脏数据', 'passed': False, 'error': str(e)})
        print(f"  ❌ 失败: {e}")


def test_snapshot_persistence(db, app, db_path, results):
    print("\n--- 测试32: 快照数据持久化（重启后可读） ---")
    try:
        from app.services.snapshot_service import SnapshotService
        from app.services.task_service import TaskService
        service = TaskService(db)
        snap_service = SnapshotService(db)

        template = db.execute('SELECT * FROM plate_templates LIMIT 1').fetchone()
        assert template is not None, "需要模板"

        task_id = service.create_task(
            name='_快照测试_持久化',
            template_id=template['id'],
            total_volume=25,
            volume_unit='ul'
        )

        primer = db.execute("SELECT * FROM primers LIMIT 1").fetchone()
        mm = db.execute("SELECT * FROM reagents WHERE type = 'master_mix' LIMIT 1").fetchone()
        water = db.execute("SELECT * FROM reagents WHERE type = 'water' LIMIT 1").fetchone()

        service.generate_plan(
            task_id=task_id,
            primer_id=primer['id'],
            master_mix_id=mm['id'],
            water_id=water['id']
        )

        snap_service.create_snapshot(task_id, 'manual', '持久化测试快照')

        snapshots_before = snap_service.list_snapshots(task_id)
        assert len(snapshots_before) == 2, "应有 2 个快照"

        assert db_path and os.path.exists(db_path), f"数据库文件应存在: {db_path}"

        other_conn = sqlite3.connect(db_path)
        other_conn.row_factory = sqlite3.Row
        other_snapshots = other_conn.execute(
            'SELECT * FROM task_snapshots WHERE task_id = ? ORDER BY version',
            (task_id,)
        ).fetchall()
        assert len(other_snapshots) == 2, f"独立连接应能读到 2 个快照，实际 {len(other_snapshots)}"

        snap1 = other_conn.execute(
            'SELECT * FROM task_snapshots WHERE task_id = ? AND version = 1', (task_id,)
        ).fetchone()
        assert snap1 is not None, "v1 快照应存在"
        assert snap1['snapshot_type'] == 'generate', "v1 类型应为 generate"
        assert snap1['wells_data'] is not None and len(snap1['wells_data']) > 0, "v1 应有孔位数据"

        snap2 = other_conn.execute(
            'SELECT * FROM task_snapshots WHERE task_id = ? AND version = 2', (task_id,)
        ).fetchone()
        assert snap2 is not None, "v2 快照应存在"
        assert snap2['snapshot_type'] == 'manual', "v2 类型应为 manual"

        other_conn.close()
        print(f"  ✅ 重启后快照可读: {len(other_snapshots)} 个，数据完整")

        db.execute('DELETE FROM task_snapshots WHERE task_id = ?', (task_id,))
        db.execute('DELETE FROM task_wells WHERE task_id = ?', (task_id,))
        db.execute('DELETE FROM task_reagent_usage WHERE task_id = ?', (task_id,))
        db.execute('DELETE FROM task_primer_usage WHERE task_id = ?', (task_id,))
        db.execute('DELETE FROM history WHERE task_id = ?', (task_id,))
        db.execute('DELETE FROM tasks WHERE id = ?', (task_id,))
        db.commit()

        results.append({'name': '快照数据持久化', 'passed': True})
        print("  ✅ 通过")
    except Exception as e:
        import traceback as _tb
        _tb.print_exc()
        results.append({'name': '快照数据持久化', 'passed': False, 'error': str(e)})
        print(f"  ❌ 失败: {e}")


def test_snapshot_e2e_rollback_regenerate_approve(db, app, results):
    print("\n--- 测试33: 端到端 - 回滚后重新生成&批准 ---")
    try:
        client = app.test_client()
        from app.services.task_service import TaskService
        from app.services.snapshot_service import SnapshotService
        service = TaskService(db)
        snap_service = SnapshotService(db)

        template = db.execute('SELECT * FROM plate_templates LIMIT 1').fetchone()
        assert template is not None, "需要模板"

        task_id = service.create_task(
            name='_快照E2E测试_回滚重生成',
            template_id=template['id'],
            total_volume=20,
            volume_unit='ul'
        )

        primer = db.execute("SELECT * FROM primers LIMIT 1").fetchone()
        mm = db.execute("SELECT * FROM reagents WHERE type = 'master_mix' LIMIT 1").fetchone()
        water = db.execute("SELECT * FROM reagents WHERE type = 'water' LIMIT 1").fetchone()

        snap_service.create_snapshot(task_id, 'manual', '初始草稿快照')
        v_draft = snap_service.list_snapshots(task_id)[0]['version']
        assert v_draft == 1
        print(f"  ① 草稿快照: v{v_draft}, status=draft")

        result1 = service.generate_plan(
            task_id=task_id,
            primer_id=primer['id'],
            master_mix_id=mm['id'],
            water_id=water['id']
        )
        v_gen = result1['snapshot_version']
        assert v_gen == 2
        task_v2 = db.execute('SELECT status FROM tasks WHERE id = ?', (task_id,)).fetchone()
        assert task_v2['status'] == 'pending_review'
        print(f"  ② 生成方案: v{v_gen}, status={task_v2['status']}")

        rollback_result = snap_service.rollback_to_snapshot(task_id, v_draft)
        assert rollback_result['rolled_back_to'] == v_draft
        assert rollback_result['previous_status'] == 'pending_review'
        assert rollback_result['new_status'] == 'draft'
        task_after_rollback = db.execute('SELECT status FROM tasks WHERE id = ?', (task_id,)).fetchone()
        assert task_after_rollback['status'] == 'draft'
        print(f"  ③ 回滚到草稿 v{v_draft}: status={task_after_rollback['status']}")

        result2 = service.generate_plan(
            task_id=task_id,
            primer_id=primer['id'],
            master_mix_id=mm['id'],
            water_id=water['id']
        )
        v3 = result2['snapshot_version']
        assert v3 == 3, f"重新生成后快照版本应为 3，实际 {v3}"
        print(f"  ④ 重新生成方案: v{v3}")

        snapshots = snap_service.list_snapshots(task_id)
        assert len(snapshots) == 3, f"应有 3 个快照，实际 {len(snapshots)}"

        diff = snap_service.compare_snapshots(task_id, v_draft, v3)
        assert diff is not None
        print(f"  ⑤ 版本对比正常: wells_modified={diff['summary']['wells_modified']}, reagents_modified={diff['summary']['reagents_modified']}")

        try:
            approve_result = service.approve_task(task_id, ignore_min_pipette=True)
            if approve_result:
                task_approved = db.execute('SELECT status FROM tasks WHERE id = ?', (task_id,)).fetchone()
                assert task_approved['status'] == 'approved'

                pre_approve_snap = snap_service.list_snapshots(task_id)
                has_pre_approve = any(s['snapshot_type'] == 'pre_approve' for s in pre_approve_snap)
                assert has_pre_approve, "批准前应创建 pre_approve 快照"
                print(f"  ⑥ 批准成功，有批准前快照: {len(pre_approve_snap)} 个快照")
        except ValueError as e:
            print(f"  ⚠️  批准跳过（库存可能不足）: {e}")

        db.execute('DELETE FROM task_snapshots WHERE task_id = ?', (task_id,))
        db.execute('DELETE FROM task_wells WHERE task_id = ?', (task_id,))
        db.execute('DELETE FROM task_reagent_usage WHERE task_id = ?', (task_id,))
        db.execute('DELETE FROM task_primer_usage WHERE task_id = ?', (task_id,))
        db.execute('DELETE FROM reagent_inventory_log WHERE task_id = ?', (task_id,))
        db.execute('DELETE FROM primer_inventory_log WHERE task_id = ?', (task_id,))
        db.execute('DELETE FROM history WHERE task_id = ?', (task_id,))
        db.execute('DELETE FROM tasks WHERE id = ?', (task_id,))
        db.commit()

        results.append({'name': '端到端回滚重生成批准', 'passed': True})
        print("  ✅ 通过")
    except Exception as e:
        import traceback as _tb
        _tb.print_exc()
        results.append({'name': '端到端回滚重生成批准', 'passed': False, 'error': str(e)})
        print(f"  ❌ 失败: {e}")


def test_snapshot_history_records(db, app, results):
    print("\n--- 测试34: 快照操作历史记录 ---")
    try:
        from app.services.task_service import TaskService
        from app.services.snapshot_service import SnapshotService
        from app.services.history_service import HistoryService
        service = TaskService(db)
        snap_service = SnapshotService(db)
        history_service = HistoryService(db, '')

        template = db.execute('SELECT * FROM plate_templates LIMIT 1').fetchone()
        assert template is not None, "需要模板"

        task_id = service.create_task(
            name='_快照测试_历史记录',
            template_id=template['id'],
            total_volume=20,
            volume_unit='ul'
        )

        primer = db.execute("SELECT * FROM primers LIMIT 1").fetchone()
        mm = db.execute("SELECT * FROM reagents WHERE type = 'master_mix' LIMIT 1").fetchone()
        water = db.execute("SELECT * FROM reagents WHERE type = 'water' LIMIT 1").fetchone()

        history_before = len(history_service.get_history(task_id=task_id, limit=1000))

        service.generate_plan(
            task_id=task_id,
            primer_id=primer['id'],
            master_mix_id=mm['id'],
            water_id=water['id']
        )

        snap_service.create_snapshot(task_id, 'manual', '测试快照')

        snap_service.rollback_to_snapshot(task_id, 1)

        history_after = history_service.get_history(task_id=task_id, limit=1000)
        action_types = set(h['action_type'] for h in history_after)

        assert 'snapshot_created' in action_types, "应有 snapshot_created 历史记录"
        assert 'snapshot_rollback' in action_types, "应有 snapshot_rollback 历史记录"
        print(f"  ✅ 快照相关历史记录: snapshot_created + snapshot_rollback")

        created_records = [h for h in history_after if h['action_type'] == 'snapshot_created']
        assert len(created_records) >= 2, f"应有至少 2 条 snapshot_created，实际 {len(created_records)}"
        print(f"  ✅ 快照创建记录数: {len(created_records)}")

        rollback_records = [h for h in history_after if h['action_type'] == 'snapshot_rollback']
        assert len(rollback_records) == 1, f"应有 1 条回滚记录，实际 {len(rollback_records)}"
        assert '回滚到版本' in rollback_records[0]['detail'], "回滚记录详情应包含版本号"
        print(f"  ✅ 回滚历史记录: {rollback_records[0]['detail'][:60]}...")

        db.execute('DELETE FROM task_snapshots WHERE task_id = ?', (task_id,))
        db.execute('DELETE FROM task_wells WHERE task_id = ?', (task_id,))
        db.execute('DELETE FROM task_reagent_usage WHERE task_id = ?', (task_id,))
        db.execute('DELETE FROM task_primer_usage WHERE task_id = ?', (task_id,))
        db.execute('DELETE FROM history WHERE task_id = ?', (task_id,))
        db.execute('DELETE FROM tasks WHERE id = ?', (task_id,))
        db.commit()

        results.append({'name': '快照操作历史记录', 'passed': True})
        print("  ✅ 通过")
    except Exception as e:
        import traceback as _tb
        _tb.print_exc()
        results.append({'name': '快照操作历史记录', 'passed': False, 'error': str(e)})
        print(f"  ❌ 失败: {e}")


def test_snapshot_frontend_api_contract(db, app, results):
    print("\n--- 测试35: 前端API契约 - 页面交互接口联动 ---")
    try:
        client = app.test_client()
        from app.services.task_service import TaskService
        from app.services.snapshot_service import SnapshotService
        service = TaskService(db)
        snap_service = SnapshotService(db)

        template = db.execute('SELECT * FROM plate_templates LIMIT 1').fetchone()
        assert template is not None, "需要模板"

        task_id = service.create_task(
            name='_前端契约测试_快照API',
            template_id=template['id'],
            total_volume=20,
            volume_unit='ul'
        )

        primer = db.execute("SELECT * FROM primers LIMIT 1").fetchone()
        mm = db.execute("SELECT * FROM reagents WHERE type = 'master_mix' LIMIT 1").fetchone()
        water = db.execute("SELECT * FROM reagents WHERE type = 'water' LIMIT 1").fetchone()

        snap_service.create_snapshot(task_id, 'manual', '初始草稿快照')

        gen_result = service.generate_plan(
            task_id=task_id,
            primer_id=primer['id'],
            master_mix_id=mm['id'],
            water_id=water['id']
        )

        list_resp = client.get(f'/api/tasks/{task_id}/snapshots')
        assert list_resp.status_code == 200, f"快照列表API失败: {list_resp.status_code}"
        snap_list = list_resp.get_json()
        assert isinstance(snap_list, list), "快照列表应为数组"
        assert len(snap_list) >= 2, f"至少2个快照，实际{len(snap_list)}"

        required_fields = ['id', 'version', 'snapshot_type', 'status', 'task_id',
                           'template_id', 'template_name', 'total_volume', 'volume_unit',
                           'well_count', 'created_at', 'note']
        for s in snap_list:
            for f in required_fields:
                assert f in s, f"快照列表缺少字段: {f}"
        print(f"  ① 快照列表API: {len(snap_list)} 个快照，字段完整")

        assert snap_list[0]['version'] > snap_list[1]['version'], "快照列表应按版本倒序"
        print(f"  ② 倒序排列正确: v{snap_list[0]['version']} > v{snap_list[1]['version']}")

        compare_resp = client.get(
            f'/api/tasks/{task_id}/snapshots/compare?version_a=1&version_b=2'
        )
        assert compare_resp.status_code == 200
        diff = compare_resp.get_json()

        diff_required = ['version_a', 'version_b', 'summary', 'task_differences',
                         'template_differences', 'well_differences',
                         'reagent_differences', 'primer_differences']
        for f in diff_required:
            assert f in diff, f"对比结果缺少字段: {f}"

        summary_fields = ['wells_added', 'wells_removed', 'wells_modified',
                          'reagents_added', 'reagents_removed', 'reagents_modified',
                          'primers_added', 'primers_removed', 'primers_modified']
        for f in summary_fields:
            assert f in diff['summary'], f"对比summary缺少字段: {f}"
        print(f"  ③ 对比API字段完整: wells +{diff['summary']['wells_added']}/-{diff['summary']['wells_removed']}")

        manual_resp = client.post(
            f'/api/tasks/{task_id}/snapshots',
            json={'note': '手动快照_前端测试'}
        )
        assert manual_resp.status_code == 201
        manual_data = manual_resp.get_json()
        assert 'version' in manual_data
        assert 'snapshot_type' in manual_data
        assert manual_data['snapshot_type'] == 'manual'
        print(f"  ④ 手动创建快照API: v{manual_data['version']}")

        rollback_resp = client.post(
            f'/api/tasks/{task_id}/snapshots/rollback',
            json={'version': 1, 'operator': 'tester'}
        )
        assert rollback_resp.status_code == 200
        rollback_data = rollback_resp.get_json()
        rollback_fields = ['rolled_back_to', 'previous_status', 'new_status', 'task_id']
        for f in rollback_fields:
            assert f in rollback_data, f"回滚结果缺少字段: {f}"
        print(f"  ⑤ 回滚API字段完整: rolled_back_to={rollback_data['rolled_back_to']}")

        task_after = db.execute('SELECT status FROM tasks WHERE id = ?', (task_id,)).fetchone()
        assert task_after['status'] == rollback_data['new_status'], "回滚后状态应一致"
        print(f"  ⑥ 回滚后状态同步: {task_after['status']}")

        db.execute('DELETE FROM task_snapshots WHERE task_id = ?', (task_id,))
        db.execute('DELETE FROM task_wells WHERE task_id = ?', (task_id,))
        db.execute('DELETE FROM task_reagent_usage WHERE task_id = ?', (task_id,))
        db.execute('DELETE FROM task_primer_usage WHERE task_id = ?', (task_id,))
        db.execute('DELETE FROM reagent_inventory_log WHERE task_id = ?', (task_id,))
        db.execute('DELETE FROM primer_inventory_log WHERE task_id = ?', (task_id,))
        db.execute('DELETE FROM history WHERE task_id = ?', (task_id,))
        db.execute('DELETE FROM tasks WHERE id = ?', (task_id,))
        db.commit()

        results.append({'name': '前端API契约-页面交互接口联动', 'passed': True})
        print("  ✅ 通过")
    except Exception as e:
        import traceback as _tb
        _tb.print_exc()
        results.append({'name': '前端API契约-页面交互接口联动', 'passed': False, 'error': str(e)})
        print(f"  ❌ 失败: {e}")


def test_snapshot_rollback_status_block_api(db, app, results):
    print("\n--- 测试36: 已批准/已撤销任务回滚拦截 API ---")
    try:
        client = app.test_client()
        from app.services.task_service import TaskService
        from app.services.snapshot_service import SnapshotService
        service = TaskService(db)
        snap_service = SnapshotService(db)

        template = db.execute('SELECT * FROM plate_templates LIMIT 1').fetchone()
        assert template is not None

        task_id = service.create_task(
            name='_拦截测试_已批准回滚',
            template_id=template['id'],
            total_volume=20,
            volume_unit='ul'
        )

        primer = db.execute("SELECT * FROM primers LIMIT 1").fetchone()
        mm = db.execute("SELECT * FROM reagents WHERE type = 'master_mix' LIMIT 1").fetchone()
        water = db.execute("SELECT * FROM reagents WHERE type = 'water' LIMIT 1").fetchone()

        snap_service.create_snapshot(task_id, 'manual', '草稿快照')
        service.generate_plan(
            task_id=task_id,
            primer_id=primer['id'],
            master_mix_id=mm['id'],
            water_id=water['id']
        )

        db.execute("UPDATE tasks SET status = 'approved' WHERE id = ?", (task_id,))
        db.commit()

        rollback_resp = client.post(
            f'/api/tasks/{task_id}/snapshots/rollback',
            json={'version': 1}
        )
        assert rollback_resp.status_code == 409, f"已批准任务回滚应返回409，实际{rollback_resp.status_code}"
        err_data = rollback_resp.get_json()
        assert 'error' in err_data, "错误响应应包含error字段"
        print(f"  ① 已批准任务回滚拦截: {err_data['error'][:40]}...")

        db.execute("UPDATE tasks SET status = 'revoked' WHERE id = ?", (task_id,))
        db.commit()

        rollback_resp2 = client.post(
            f'/api/tasks/{task_id}/snapshots/rollback',
            json={'version': 1}
        )
        assert rollback_resp2.status_code == 409
        err_data2 = rollback_resp2.get_json()
        assert 'error' in err_data2
        print(f"  ② 已撤销任务回滚拦截: {err_data2['error'][:40]}...")

        snaps_after = snap_service.list_snapshots(task_id)
        v_count = len(snaps_after)
        task_status = db.execute('SELECT status FROM tasks WHERE id = ?', (task_id,)).fetchone()['status']
        assert task_status == 'revoked', "拦截后任务状态不应改变"
        print(f"  ③ 拦截后状态不变: status={task_status}, 快照数={v_count}")

        db.execute('DELETE FROM task_snapshots WHERE task_id = ?', (task_id,))
        db.execute('DELETE FROM task_wells WHERE task_id = ?', (task_id,))
        db.execute('DELETE FROM task_reagent_usage WHERE task_id = ?', (task_id,))
        db.execute('DELETE FROM task_primer_usage WHERE task_id = ?', (task_id,))
        db.execute('DELETE FROM reagent_inventory_log WHERE task_id = ?', (task_id,))
        db.execute('DELETE FROM primer_inventory_log WHERE task_id = ?', (task_id,))
        db.execute('DELETE FROM history WHERE task_id = ?', (task_id,))
        db.execute('DELETE FROM tasks WHERE id = ?', (task_id,))
        db.commit()

        results.append({'name': '已批准/已撤销任务回滚拦截API', 'passed': True})
        print("  ✅ 通过")
    except Exception as e:
        import traceback as _tb
        _tb.print_exc()
        results.append({'name': '已批准/已撤销任务回滚拦截API', 'passed': False, 'error': str(e)})
        print(f"  ❌ 失败: {e}")


def test_snapshot_compare_same_version_and_detail(db, app, results):
    print("\n--- 测试37: 快照对比边界场景 & 快照详情 ---")
    try:
        client = app.test_client()
        from app.services.task_service import TaskService
        from app.services.snapshot_service import SnapshotService
        service = TaskService(db)
        snap_service = SnapshotService(db)

        template = db.execute('SELECT * FROM plate_templates LIMIT 1').fetchone()

        task_id = service.create_task(
            name='_对比边界测试_快照详情',
            template_id=template['id'],
            total_volume=20,
            volume_unit='ul'
        )

        primer = db.execute("SELECT * FROM primers LIMIT 1").fetchone()
        mm = db.execute("SELECT * FROM reagents WHERE type = 'master_mix' LIMIT 1").fetchone()
        water = db.execute("SELECT * FROM reagents WHERE type = 'water' LIMIT 1").fetchone()

        snap_service.create_snapshot(task_id, 'manual', 'snap1')
        service.generate_plan(
            task_id=task_id,
            primer_id=primer['id'],
            master_mix_id=mm['id'],
            water_id=water['id']
        )

        same_resp = client.get(
            f'/api/tasks/{task_id}/snapshots/compare?version_a=1&version_b=1'
        )
        assert same_resp.status_code == 200
        same_diff = same_resp.get_json()
        s = same_diff['summary']
        assert s['wells_added'] == 0 and s['wells_removed'] == 0 and s['wells_modified'] == 0
        assert s['reagents_added'] == 0 and s['reagents_removed'] == 0
        assert s['primers_added'] == 0 and s['primers_removed'] == 0
        print(f"  ① 同版本对比: 所有差异为0")

        detail_resp = client.get(f'/api/tasks/{task_id}/snapshots/1')
        assert detail_resp.status_code == 200
        detail = detail_resp.get_json()
        detail_required = ['id', 'version', 'snapshot_type', 'status', 'task_id',
                           'task_data', 'wells_data', 'reagent_usage_data', 'primer_usage_data']
        for f in detail_required:
            assert f in detail, f"快照详情缺少字段: {f}"
        assert isinstance(detail['wells_data'], list), "wells_data 应为列表"
        print(f"  ② 快照详情API字段完整: wells_data({len(detail['wells_data'])} 条)")

        invalid_resp = client.get(
            f'/api/tasks/{task_id}/snapshots/compare?version_a=999&version_b=1'
        )
        assert invalid_resp.status_code in [400, 404], f"无效版本应返回错误，实际{invalid_resp.status_code}"
        print(f"  ③ 无效版本对比错误处理: status={invalid_resp.status_code}")

        db.execute('DELETE FROM task_snapshots WHERE task_id = ?', (task_id,))
        db.execute('DELETE FROM task_wells WHERE task_id = ?', (task_id,))
        db.execute('DELETE FROM task_reagent_usage WHERE task_id = ?', (task_id,))
        db.execute('DELETE FROM task_primer_usage WHERE task_id = ?', (task_id,))
        db.execute('DELETE FROM reagent_inventory_log WHERE task_id = ?', (task_id,))
        db.execute('DELETE FROM primer_inventory_log WHERE task_id = ?', (task_id,))
        db.execute('DELETE FROM history WHERE task_id = ?', (task_id,))
        db.execute('DELETE FROM tasks WHERE id = ?', (task_id,))
        db.commit()

        results.append({'name': '快照对比边界&详情API', 'passed': True})
        print("  ✅ 通过")
    except Exception as e:
        import traceback as _tb
        _tb.print_exc()
        results.append({'name': '快照对比边界&详情API', 'passed': False, 'error': str(e)})
        print(f"  ❌ 失败: {e}")


if __name__ == '__main__':
    success = run_tests()
    sys.exit(0 if success else 1)
