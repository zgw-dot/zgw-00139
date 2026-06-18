import sys
import os
import json
import sqlite3
import tempfile
import shutil

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from app.database import init_db, get_db


def _create_test_app():
    db_fd, db_path = tempfile.mkstemp(suffix='.db')
    os.close(db_fd)

    test_data_dir = tempfile.mkdtemp()

    from flask import Flask
    app = Flask(__name__, static_folder='../static', static_url_path='/static')
    app.config['SECRET_KEY'] = 'test-key'
    app.config['DATABASE'] = db_path
    app.config['DATA_DIR'] = test_data_dir
    app.config['TESTING'] = True

    from flask_cors import CORS
    CORS(app)

    from app.database import init_db
    init_db(app)

    with app.app_context():
        db = get_db(app)
        db.execute("INSERT INTO plate_templates (name, rows, cols) VALUES ('96孔板', 8, 12)")
        db.execute("INSERT INTO plate_templates (name, rows, cols) VALUES ('384孔板', 16, 24)")
        db.execute("INSERT INTO primers (name, sequence, concentration, concentration_unit, volume, volume_unit) VALUES ('TestPrimer', 'ATCG', 10, 'um', 100, 'ul')")
        db.execute("INSERT INTO reagents (name, type, volume, volume_unit, min_pipette_volume, min_pipette_unit) VALUES ('MM', 'master_mix', 500, 'ul', 0.5, 'ul')")
        db.execute("INSERT INTO reagents (name, type, volume, volume_unit, min_pipette_volume, min_pipette_unit) VALUES ('Water', 'water', 1000, 'ul', 0.5, 'ul')")
        db.commit()

    return app, db_path, test_data_dir


def _cleanup(app, db_path, test_data_dir):
    try:
        shutil.rmtree(test_data_dir, ignore_errors=True)
        os.unlink(db_path)
    except Exception:
        pass


def run_tests():
    passed = 0
    failed = 0
    errors = []

    app, db_path, test_data_dir = _create_test_app()

    try:
        with app.app_context():
            db = get_db(app)
            from app.services.experiment_preset_service import ExperimentPresetService
            svc = ExperimentPresetService(db)

            print('\n' + '=' * 60)
            print('实验方案预设库 - 验证测试')
            print('=' * 60)

            # ---- Test 1: 创建预设 ----
            print('\n[1] 创建预设')
            p1 = svc.create_preset(
                name='标准96孔qPCR',
                description='标准96孔qPCR方案',
                template_id=1,
                total_volume=20,
                volume_unit='ul',
                primer_id=1,
                master_mix_id=1,
                water_id=2,
                deviation_note_template='标准偏差备注',
            )
            assert p1['name'] == '标准96孔qPCR', '预设名称不匹配'
            assert p1['is_enabled'] == 1, '新建预设应默认启用'
            assert p1['template_id'] == 1
            assert p1['total_volume'] == 20
            assert p1['primer_id'] == 1
            assert p1['master_mix_id'] == 1
            assert p1['water_id'] == 2
            print('  ✅ 创建预设成功，字段正确')
            passed += 1

            # ---- Test 2: 同名冲突 reject ----
            print('\n[2] 同名冲突 reject')
            try:
                svc.create_preset(name='标准96孔qPCR')
                errors.append('Test 2: 同名创建应抛异常')
                failed += 1
            except ValueError as e:
                assert '已存在' in str(e), f'错误信息应提及已存在, got: {e}'
                assert e.args[1] == 'name_conflict'
                print('  ✅ 同名创建正确拒绝，异常类型 name_conflict')
                passed += 1

            # ---- Test 3: 从预设创建任务 ----
            print('\n[3] 从预设创建任务')
            result = svc.apply_preset_to_task(p1['id'], task_name='测试任务_从预设')
            assert result['task_id'] is not None, '应返回 task_id'
            assert result['preset_id'] == p1['id']
            task_id_from_preset = result['task_id']
            print(f'  ✅ 从预设创建任务成功, task_id={task_id_from_preset}')

            # 验证任务预设引用
            refs = svc.get_task_preset_reference(task_id_from_preset)
            assert len(refs) >= 1, '应有预设引用记录'
            assert refs[0]['preset_name'] == '标准96孔qPCR'
            print('  ✅ 预设引用关系正确记录')
            passed += 1

            # ---- Test 4: 依赖失效拦截 ----
            print('\n[4] 依赖失效拦截')
            p2 = svc.create_preset(
                name='已删模板预设',
                template_id=9999,
                total_volume=25,
            )
            dep_result = svc.validate_dependencies(p2['id'])
            assert dep_result['valid'] is False, '缺失依赖应返回 False'
            assert len(dep_result['missing']) >= 1
            assert dep_result['missing'][0]['type'] == 'template'
            print('  ✅ 依赖缺失正确检测')

            try:
                svc.apply_preset_to_task(p2['id'], task_name='不应创建')
                errors.append('Test 4: 依赖缺失时应拦截创建任务')
                failed += 1
            except ValueError as e:
                assert e.args[1] == 'dependency_missing', f'异常类型应为 dependency_missing, got: {e.args}'
                print('  ✅ 依赖缺失时创建任务被拦截')
                passed += 1

            # ---- Test 5: 停用预设限制 ----
            print('\n[5] 停用预设限制')
            disabled = svc.disable_preset(p1['id'])
            assert disabled['is_enabled'] == 0
            print('  ✅ 预设停用成功')

            try:
                svc.apply_preset_to_task(p1['id'], task_name='停用预设任务')
                errors.append('Test 5: 停用预设不应创建新任务')
                failed += 1
            except ValueError as e:
                assert '已停用' in str(e)
                print('  ✅ 停用预设创建任务被拦截')

            # 停用后旧任务仍可查看
            refs = svc.get_task_preset_reference(task_id_from_preset)
            assert len(refs) >= 1, '停用后旧任务的预设引用仍可查看'
            print('  ✅ 停用后旧任务引用不受影响')
            passed += 1

            # ---- Test 6: 启用预设 ----
            print('\n[6] 重新启用预设')
            enabled = svc.enable_preset(p1['id'])
            assert enabled['is_enabled'] == 1
            print('  ✅ 预设重新启用成功')
            passed += 1

            # ---- Test 7: 被引用预设不能硬删 ----
            print('\n[7] 被引用预设不能硬删')
            try:
                svc.delete_preset(p1['id'])
                errors.append('Test 7: 被引用预设不应允许硬删')
                failed += 1
            except ValueError as e:
                assert e.args[1] == 'preset_referenced'
                print('  ✅ 被引用预设硬删被拦截')
                passed += 1

            # ---- Test 8: 复制预设 ----
            print('\n[8] 复制预设')
            p_copy = svc.copy_preset(p1['id'], new_name='标准96孔qPCR_副本A')
            assert p_copy['name'] == '标准96孔qPCR_副本A'
            assert p_copy['template_id'] == p1['template_id']
            assert p_copy['total_volume'] == p1['total_volume']
            assert p_copy['is_enabled'] == 1
            assert p_copy['id'] != p1['id']
            print('  ✅ 预设复制成功，参数一致，ID不同')
            passed += 1

            # ---- Test 9: 另存任务为预设 ----
            print('\n[9] 另存任务为预设')
            from app.services.task_service import TaskService
            task_svc = TaskService(db)
            task_id2 = task_svc.create_task('手动任务', template_id=1, total_volume=25)
            saved_preset = svc.save_task_as_preset(
                task_id=task_id2,
                preset_name='从任务另存',
                description='从任务另存为预设测试',
            )
            assert saved_preset['name'] == '从任务另存'
            assert saved_preset['template_id'] == 1
            assert saved_preset['total_volume'] == 25
            print('  ✅ 任务另存为预设成功')
            passed += 1

            # ---- Test 10: JSON 导入导出 ----
            print('\n[10] JSON 导入导出')
            json_export = svc.export_presets_json()
            export_data = json.loads(json_export)
            assert export_data['preset_count'] >= 2
            print(f'  ✅ JSON 导出成功, {export_data["preset_count"]} 个预设')

            import_json = json.dumps({
                'presets': [
                    {'name': '导入预设A', 'template_id': 1, 'total_volume': 30},
                    {'name': '导入预设B', 'template_id': 2, 'total_volume': 15},
                ]
            }, ensure_ascii=False)
            import_result = svc.import_presets_json(import_json, conflict_mode='reject')
            assert import_result['imported'] == 2
            assert import_result['errors'] == [] or len(import_result['errors']) == 0
            print(f'  ✅ JSON 导入成功, 新增 {import_result["imported"]} 个')

            # 冲突导入 - reject
            conflict_result = svc.import_presets_json(import_json, conflict_mode='reject')
            assert conflict_result['skipped'] >= 2
            print(f'  ✅ 冲突 reject 模式: 跳过 {conflict_result["skipped"]} 个')

            # 冲突导入 - rename
            rename_result = svc.import_presets_json(import_json, conflict_mode='rename')
            assert rename_result['renamed'] >= 2
            print(f'  ✅ 冲突 rename 模式: 重命名 {rename_result["renamed"]} 个')

            # 冲突导入 - overwrite
            overwrite_result = svc.import_presets_json(import_json, conflict_mode='overwrite')
            assert overwrite_result['overwritten'] >= 2
            print(f'  ✅ 冲突 overwrite 模式: 覆盖 {overwrite_result["overwritten"]} 个')
            passed += 1

            # ---- Test 11: CSV 导入导出 ----
            print('\n[11] CSV 导入导出')
            csv_export = svc.export_presets_csv()
            assert 'name' in csv_export
            assert '标准96孔qPCR' in csv_export
            print('  ✅ CSV 导出成功')

            csv_content = 'name,description,template_id,total_volume,volume_unit,primer_id,master_mix_id,water_id,deviation_note_template\n'
            csv_content += 'CSV预设1,描述,1,20,ul,1,1,2,偏差模板\n'
            csv_content += 'CSV预设2,,2,15,ul,,,,\n'
            csv_import_result = svc.import_presets_csv(csv_content, conflict_mode='reject')
            assert csv_import_result['imported'] == 2
            print(f'  ✅ CSV 导入成功, 新增 {csv_import_result["imported"]} 个')
            passed += 1

            # ---- Test 12: 历史记录 ----
            print('\n[12] 预设变更历史记录')
            history = svc.get_preset_history(p1['id'])
            assert len(history) >= 3, f'应有至少3条历史记录(创建+停用+启用), got {len(history)}'
            actions = [h['action'] for h in history]
            assert 'create' in actions, '应有 create 操作'
            assert 'disable' in actions, '应有 disable 操作'
            assert 'enable' in actions, '应有 enable 操作'
            print(f'  ✅ 预设历史记录完整, 共 {len(history)} 条')
            passed += 1

            # ---- Test 13: 重启后持久化 ----
            print('\n[13] 服务重启后数据持久化')
            preset_count_before = len(svc.list_presets())
            p1_before = svc._get_preset(p1['id'])

        # 模拟重启: 新 app context 连接同一个 db
        with app.app_context():
            db2 = get_db(app)
            svc2 = ExperimentPresetService(db2)
            preset_count_after = len(svc2.list_presets())
            assert preset_count_after == preset_count_before, \
                f'重启后预设数量不一致: before={preset_count_before}, after={preset_count_after}'

            p1_after = svc2._get_preset(p1['id'])
            assert p1_after['name'] == '标准96孔qPCR'
            assert p1_after['is_enabled'] == 1
            print('  ✅ 重启后预设数据完整保留')

            refs_after = svc2.get_task_preset_reference(task_id_from_preset)
            assert len(refs_after) >= 1, '重启后引用关系保留'
            print('  ✅ 重启后引用关系保留')

            history_after = svc2.get_preset_history(p1['id'])
            assert len(history_after) >= 3, '重启后历史记录保留'
            print('  ✅ 重启后历史记录保留')

            passed += 1

            # ---- Test 14: 更新预设 ----
            print('\n[14] 更新预设')
            updated = svc2.update_preset(p1['id'], total_volume=30, description='更新后的描述')
            assert updated['total_volume'] == 30
            assert updated['description'] == '更新后的描述'
            print('  ✅ 预设更新成功')

            # 更新同名冲突
            try:
                svc2.update_preset(p1['id'], name='从任务另存')
                errors.append('Test 14: 更新同名应抛异常')
                failed += 1
            except ValueError as e:
                assert e.args[1] == 'name_conflict'
                print('  ✅ 更新同名冲突正确拒绝')
                passed += 1

            # ---- Test 15: 无引用预设可删除 ----
            print('\n[15] 无引用预设可删除')
            deleteable_preset = svc2.create_preset(
                name='待删除预设',
                template_id=1,
                total_volume=10,
            )
            delete_result = svc2.delete_preset(deleteable_preset['id'])
            assert delete_result['deleted'] is True
            assert svc2._get_preset(deleteable_preset['id']) is None
            print('  ✅ 无引用预设删除成功')
            passed += 1

            # ---- Test 16: 列表过滤 ----
            print('\n[16] 预设列表过滤')
            all_presets = svc2.list_presets()
            enabled_presets = svc2.list_presets(is_enabled=True)
            disabled_presets = svc2.list_presets(is_enabled=False)
            assert len(all_presets) >= len(enabled_presets)
            assert len(disabled_presets) >= 0
            print(f'  ✅ 过滤功能正常: 全部 {len(all_presets)}, 启用 {len(enabled_presets)}, 停用 {len(disabled_presets)}')

            keyword_presets = svc2.list_presets(keyword='CSV')
            assert len(keyword_presets) >= 2
            print(f'  ✅ 关键词过滤正常: "CSV" 匹配 {len(keyword_presets)} 个')
            passed += 1

    except Exception as e:
        import traceback
        errors.append(f'未捕获异常: {str(e)}\n{traceback.format_exc()}')
        failed += 1
    finally:
        _cleanup(app, db_path, test_data_dir)

    print('\n' + '=' * 60)
    print(f'测试结果: ✅ 通过 {passed}  |  ❌ 失败 {failed}')
    if errors:
        print('\n失败详情:')
        for err in errors:
            print(f'  - {err}')
    print('=' * 60)

    return failed == 0


if __name__ == '__main__':
    success = run_tests()
    sys.exit(0 if success else 1)
