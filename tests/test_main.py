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
        test_well_conflict(db, test_results)
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
        test_data_persistence(db, test_app, db_path, test_results)
    
    if os.path.exists(db_path):
        os.remove(db_path)
    
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


def test_create_tasks(db, results):
    print("\n--- 测试7: 创建任务 ---")
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
    print("\n--- 测试8: 生成配液方案 ---")
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
    print("\n--- 测试9: 正常体积任务直接批准 ---")
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
    print("\n--- 测试10: 小体积任务最小移液拦截 ---")
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
    print("\n--- 测试11: 偏差备注后批准 ---")
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
    print("\n--- 测试12: 库存扣减验证 ---")
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
    print("\n--- 测试13: 撤销确认 ---")
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
    print("\n--- 测试14: 驳回任务 ---")
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
    print("\n--- 测试15: 历史记录 ---")
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
    print("\n--- 测试16: 报告导出 ---")
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
    print("\n--- 测试17: 库存不足拦截 ---")
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


def test_data_persistence(db, app, db_path, results):
    print("\n--- 测试18: 重启后数据一致性 ---")
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
        
        db.close()
        
        from flask import Flask
        from flask_cors import CORS
        from app.database import init_db
        
        new_app = Flask(__name__, static_folder='../static', static_url_path='/static')
        new_app.config['SECRET_KEY'] = 'test-key'
        new_app.config['DATABASE'] = db_path
        new_app.config['DATA_DIR'] = app.config['DATA_DIR']
        CORS(new_app)
        init_db(new_app)
        
        with new_app.app_context():
            from app.database import get_db
            new_db = get_db(new_app)
            
            tasks_after = new_db.execute('SELECT id, name, status FROM tasks ORDER BY id').fetchall()
            reagents_after = new_db.execute('SELECT id, name, volume FROM reagents ORDER BY id').fetchall()
            history_after = new_db.execute('SELECT COUNT(*) as cnt FROM history').fetchone()['cnt']
            
            task_ids_after = [t['id'] for t in tasks_after]
            assert task_ids == task_ids_after, "重启后任务列表不一致"
            
            for r in reagents_after:
                assert r['volume'] == reagent_volumes[r['name']], f"试剂 {r['name']} 库存不一致"
            
            assert history_after == history_before, "重启后历史记录数不一致"
            
            approved_after = new_db.execute(
                "SELECT COUNT(*) as cnt FROM tasks WHERE status = 'approved'"
            ).fetchone()['cnt']
            revoked_after = new_db.execute(
                "SELECT COUNT(*) as cnt FROM tasks WHERE status = 'revoked'"
            ).fetchone()['cnt']
            
            assert approved_before == approved_after, "重启后已批准任务数不一致"
            assert revoked_before == revoked_after, "重启后已撤销任务数不一致"
            
            print(f"  已批准任务: {approved_after} 个")
            print(f"  已撤销任务: {revoked_after} 个")
            print(f"  历史记录: {history_after} 条")
            
            from app.services.history_service import HistoryService
            history_service = HistoryService(new_db, new_app.config['DATA_DIR'])
            json_export = history_service.export_history_json()
            export_data = json.loads(json_export)
            
            assert len(export_data['tasks']) == len(tasks_before), "JSON 导出任务数不一致"
            assert len(export_data['history']) == history_before, "JSON 导出历史记录数不一致"
            
            results.append({'name': '重启后数据一致性', 'passed': True})
            print("  ✅ 通过")
    except Exception as e:
        results.append({'name': '重启后数据一致性', 'passed': False, 'error': str(e)})
        print(f"  ❌ 失败: {e}")


if __name__ == '__main__':
    success = run_tests()
    sys.exit(0 if success else 1)
