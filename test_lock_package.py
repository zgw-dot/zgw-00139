import sys
import os
import json
import tempfile
import shutil

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import sqlite3
from flask import Flask
from flask_cors import CORS
from app.database import init_db
from app.services.protocol_lock_package_service import ProtocolLockPackageService
from app.services.task_service import TaskService

PASS = 0
FAIL = 0
TMPDIR = None
APP = None
DB_PATH = None


def _ok(label):
    global PASS
    PASS += 1
    print(f'  [PASS] {label}')


def _fail(label, detail=''):
    global FAIL
    FAIL += 1
    print(f'  [FAIL] {label}  -- {detail}')


def _make_app():
    global TMPDIR, DB_PATH
    TMPDIR = tempfile.mkdtemp(prefix='lock_pkg_test_')
    DB_PATH = os.path.join(TMPDIR, 'test.db')

    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'test-key'
    app.config['DATABASE'] = DB_PATH
    app.config['DATA_DIR'] = TMPDIR
    CORS(app)
    init_db(app)

    from app.routes.main_routes import main_bp
    from app.routes.protocol_lock_package_routes import lock_package_bp
    app.register_blueprint(main_bp)
    app.register_blueprint(lock_package_bp, url_prefix='/api/lock-packages')

    return app


def _get_db(app):
    db = sqlite3.connect(app.config['DATABASE'])
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


def _seed(db):
    db.execute(
        "INSERT INTO plate_templates (name, rows, cols) VALUES ('测试模板', 8, 12)"
    )
    db.execute(
        "INSERT INTO primers (name, concentration, concentration_unit, volume, volume_unit) "
        "VALUES ('测试引物', 10, 'uM', 200, 'ul')"
    )
    db.execute(
        "INSERT INTO reagents (name, type, volume, volume_unit) VALUES ('测试MM', 'master_mix', 500, 'ul')"
    )
    db.execute(
        "INSERT INTO reagents (name, type, volume, volume_unit) VALUES ('测试水', 'water', 1000, 'ul')"
    )
    db.commit()


def test_create_from_task():
    print('\n=== 1. 从任务创建锁定包 ===')
    app = _make_app()
    with app.app_context():
        db = _get_db(app)
        _seed(db)
        svc = ProtocolLockPackageService(db)

        t = db.execute("SELECT id FROM plate_templates LIMIT 1").fetchone()
        p = db.execute("SELECT id FROM primers LIMIT 1").fetchone()
        r_mm = db.execute("SELECT id FROM reagents WHERE type='master_mix' LIMIT 1").fetchone()
        r_w = db.execute("SELECT id FROM reagents WHERE type='water' LIMIT 1").fetchone()

        task_svc = TaskService(db)
        task_id = task_svc.create_task('lock_test_task', t['id'], 25, 'ul')

        try:
            task_svc.generate_plan(task_id, primer_id=p['id'],
                                   master_mix_id=r_mm['id'], water_id=r_w['id'])
        except Exception:
            pass

        try:
            pkg = svc.create_from_task(task_id, '测试锁定包A', operator='tester')
            if pkg and pkg['name'] == '测试锁定包A' and pkg['source_task_id'] == task_id:
                _ok('create_from_task 基本字段正确')
            else:
                _fail('create_from_task 基本字段', str(pkg))
        except Exception as e:
            _fail('create_from_task', str(e))

        try:
            svc.create_from_task(task_id, '测试锁定包A')
            _fail('重名冲突应拦截', '未抛异常')
        except ValueError as e:
            if len(e.args) > 1 and e.args[1] == 'name_conflict':
                _ok('重名冲突拦截正确 (name_conflict)')
            else:
                _ok('重名冲突拦截正确 (ValueError)')
        except Exception as e:
            _fail('重名冲突拦截异常', str(e))

        db.close()
    shutil.rmtree(TMPDIR, ignore_errors=True)


def test_manual_create_and_apply():
    print('\n=== 2. 手动创建 + 应用到任务 ===')
    app = _make_app()
    with app.app_context():
        db = _get_db(app)
        _seed(db)
        svc = ProtocolLockPackageService(db)

        t = db.execute("SELECT id FROM plate_templates LIMIT 1").fetchone()

        try:
            pkg = svc.create_manual(
                name='手动包B',
                description='手动测试',
                template_id=t['id'],
                total_volume=30,
                volume_unit='ul',
                operator='tester',
            )
            _ok('create_manual 成功')
        except Exception as e:
            _fail('create_manual', str(e))
            db.close()
            shutil.rmtree(TMPDIR, ignore_errors=True)
            return

        try:
            result = svc.apply_package_to_task(pkg['id'], operator='tester')
            if result['task_id'] and result['template_id'] == t['id'] and result['total_volume'] == 30:
                _ok('apply_package_to_task 参数冻结优先')
            else:
                _fail('apply_package_to_task 参数', str(result))
        except Exception as e:
            _fail('apply_package_to_task', str(e))

        db.close()
    shutil.rmtree(TMPDIR, ignore_errors=True)


def test_import_conflict():
    print('\n=== 3. 导入冲突处理 ===')
    app = _make_app()
    with app.app_context():
        db = _get_db(app)
        _seed(db)
        svc = ProtocolLockPackageService(db)

        t = db.execute("SELECT id FROM plate_templates LIMIT 1").fetchone()

        svc.create_manual(name='冲突包C', template_id=t['id'], total_volume=20)

        json_data = json.dumps({
            'packages': [
                {'name': '冲突包C', 'template_id': t['id'], 'total_volume': 20},
                {'name': '新包D', 'template_id': t['id'], 'total_volume': 25},
            ]
        })

        try:
            result = svc.import_packages_json(json_data, conflict_mode='rename', operator='tester')
            if result['renamed'] >= 1 and result['imported'] >= 1:
                _ok('rename 冲突处理正确')
            else:
                _fail('rename 冲突处理', str(result))
        except Exception as e:
            _fail('import rename', str(e))

        json_data_reject = json.dumps({
            'packages': [
                {'name': '冲突包C', 'template_id': t['id'], 'total_volume': 20},
            ]
        })
        try:
            result = svc.import_packages_json(json_data_reject, conflict_mode='reject')
            if result['skipped'] >= 1:
                _ok('reject 冲突处理正确')
            else:
                _fail('reject 冲突处理', str(result))
        except Exception as e:
            _fail('import reject', str(e))

        db.close()
    shutil.rmtree(TMPDIR, ignore_errors=True)


def test_missing_dependency_intercept():
    print('\n=== 4. 失效依赖拦截 ===')
    app = _make_app()
    with app.app_context():
        db = _get_db(app)
        _seed(db)
        svc = ProtocolLockPackageService(db)

        fake_template_id = 99999
        pkg = None
        try:
            pkg = svc.create_manual(
                name='失效依赖包E',
                template_id=fake_template_id,
                total_volume=20,
            )
        except Exception:
            pkg = None

        if pkg is None:
            db.close()
            raw = sqlite3.connect(DB_PATH, isolation_level=None)
            raw.execute("PRAGMA foreign_keys = OFF")
            raw.execute(
                "INSERT INTO protocol_lock_packages "
                "(name, template_id, total_volume, volume_unit, frozen_params, is_enabled, updated_at) "
                "VALUES ('失效依赖包E', 99999, 20, 'ul', '{}', 1, datetime('now'))"
            )
            raw.close()
            db = _get_db(app)
            svc = ProtocolLockPackageService(db)
            pkg_row = db.execute(
                "SELECT * FROM protocol_lock_packages WHERE name='失效依赖包E'"
            ).fetchone()
            pkg = dict(pkg_row) if pkg_row else None

        if pkg:
            dep_result = svc.validate_dependencies(pkg['id'])
            if not dep_result['valid'] and len(dep_result.get('missing', [])) > 0:
                _ok('validate_dependencies 检测到缺失依赖')
            else:
                _fail('validate_dependencies 未检测到缺失', str(dep_result))

            try:
                svc.apply_package_to_task(pkg['id'])
                _fail('apply 应拦截缺失依赖', '未抛异常')
            except ValueError as e:
                if len(e.args) > 1 and e.args[1] == 'dependency_missing':
                    _ok('apply 缺失依赖拦截正确 (dependency_missing)')
                else:
                    _ok('apply 缺失依赖拦截正确 (ValueError)')
            except Exception as e:
                _fail('apply 缺失依赖', str(e))
        else:
            _fail('创建/插入失效依赖包', 'pkg is None')

        db.close()
    shutil.rmtree(TMPDIR, ignore_errors=True)


def test_disable_restriction():
    print('\n=== 5. 停用限制 ===')
    app = _make_app()
    with app.app_context():
        db = _get_db(app)
        _seed(db)
        svc = ProtocolLockPackageService(db)

        t = db.execute("SELECT id FROM plate_templates LIMIT 1").fetchone()

        pkg = svc.create_manual(
            name='停用测试包F',
            template_id=t['id'],
            total_volume=20,
        )

        try:
            disabled = svc.disable_package(pkg['id'], operator='tester')
            if disabled['is_enabled'] == 0:
                _ok('disable 成功')
            else:
                _fail('disable', str(disabled))
        except Exception as e:
            _fail('disable', str(e))

        try:
            svc.apply_package_to_task(pkg['id'])
            _fail('停用包应用应拦截', '未抛异常')
        except ValueError as e:
            if len(e.args) > 1 and e.args[1] == 'package_disabled':
                _ok('停用包应用拦截正确 (package_disabled)')
            else:
                _ok('停用包应用拦截正确 (ValueError)')
        except Exception as e:
            _fail('停用包应用', str(e))

        try:
            re_enabled = svc.enable_package(pkg['id'], operator='tester')
            if re_enabled['is_enabled'] == 1:
                _ok('enable 成功')
            else:
                _fail('enable', str(re_enabled))
        except Exception as e:
            _fail('enable', str(e))

        db.close()
    shutil.rmtree(TMPDIR, ignore_errors=True)


def test_restart_persistence():
    print('\n=== 6. 重启后持久化 ===')
    app = _make_app()
    pkg_id = None
    db_path = None

    with app.app_context():
        db = _get_db(app)
        _seed(db)
        svc = ProtocolLockPackageService(db)

        t = db.execute("SELECT id FROM plate_templates LIMIT 1").fetchone()

        pkg = svc.create_manual(
            name='持久化测试包G',
            template_id=t['id'],
            total_volume=20,
            deviation_note='测试偏差',
        )
        pkg_id = pkg['id']
        db_path = app.config['DATABASE']
        db.close()

    app2 = Flask(__name__)
    app2.config['SECRET_KEY'] = 'test-key'
    app2.config['DATABASE'] = db_path
    app2.config['DATA_DIR'] = os.path.dirname(db_path)
    CORS(app2)
    init_db(app2)
    from app.routes.main_routes import main_bp
    from app.routes.protocol_lock_package_routes import lock_package_bp
    app2.register_blueprint(main_bp)
    app2.register_blueprint(lock_package_bp, url_prefix='/api/lock-packages')

    with app2.app_context():
        db2 = _get_db(app2)
        svc2 = ProtocolLockPackageService(db2)

        found = svc2.get_package(pkg_id)
        if found and found['name'] == '持久化测试包G' and found['deviation_note'] == '测试偏差':
            _ok('重启后锁定包信息持久化')
        else:
            _fail('重启后持久化', str(found))

        history = svc2.get_package_history(pkg_id)
        if len(history) > 0:
            _ok('重启后历史记录持久化')
        else:
            _fail('重启后历史记录持久化', 'history为空')

        db2.close()

    shutil.rmtree(os.path.dirname(db_path), ignore_errors=True)


def test_copy_and_export():
    print('\n=== 7. 复制 + 导出/导入 ===')
    app = _make_app()
    with app.app_context():
        db = _get_db(app)
        _seed(db)
        svc = ProtocolLockPackageService(db)

        t = db.execute("SELECT id FROM plate_templates LIMIT 1").fetchone()

        pkg = svc.create_manual(
            name='导出测试包H',
            template_id=t['id'],
            total_volume=25,
            deviation_note='导出偏差',
        )

        try:
            copied = svc.copy_package(pkg['id'], operator='tester')
            if copied['name'].startswith('导出测试包H_副本') and copied['total_volume'] == 25:
                _ok('copy_package 成功')
            else:
                _fail('copy_package', str(copied))
        except Exception as e:
            _fail('copy_package', str(e))

        try:
            json_str = svc.export_packages_json(package_ids=[pkg['id']])
            data = json.loads(json_str)
            if data['package_count'] == 1 and data['packages'][0]['name'] == '导出测试包H':
                _ok('export_packages_json 成功')
            else:
                _fail('export_packages_json', str(data))
        except Exception as e:
            _fail('export_packages_json', str(e))

        try:
            csv_str = svc.export_packages_csv(package_ids=[pkg['id']])
            if '导出测试包H' in csv_str:
                _ok('export_packages_csv 成功')
            else:
                _fail('export_packages_csv', '名称未出现在导出中')
        except Exception as e:
            _fail('export_packages_csv', str(e))

        db.close()
    shutil.rmtree(TMPDIR, ignore_errors=True)


def test_task_reference():
    print('\n=== 8. 引用关系 ===')
    app = _make_app()
    with app.app_context():
        db = _get_db(app)
        _seed(db)
        svc = ProtocolLockPackageService(db)

        t = db.execute("SELECT id FROM plate_templates LIMIT 1").fetchone()

        pkg = svc.create_manual(
            name='引用测试包I',
            template_id=t['id'],
            total_volume=20,
        )

        result = svc.apply_package_to_task(pkg['id'], task_name='引用测试任务', operator='tester')
        task_id = result['task_id']

        try:
            refs = svc.get_package_referenced_tasks(pkg['id'])
            if len(refs) > 0 and refs[0]['task_id'] == task_id:
                _ok('get_package_referenced_tasks 正确')
            else:
                _fail('get_package_referenced_tasks', str(refs))
        except Exception as e:
            _fail('get_package_referenced_tasks', str(e))

        try:
            task_refs = svc.get_task_package_reference(task_id)
            if len(task_refs) > 0 and task_refs[0]['package_name'] == '引用测试包I':
                _ok('get_task_package_reference 正确')
            else:
                _fail('get_task_package_reference', str(task_refs))
        except Exception as e:
            _fail('get_task_package_reference', str(e))

        db.close()
    shutil.rmtree(TMPDIR, ignore_errors=True)


if __name__ == '__main__':
    test_create_from_task()
    test_manual_create_and_apply()
    test_import_conflict()
    test_missing_dependency_intercept()
    test_disable_restriction()
    test_restart_persistence()
    test_copy_and_export()
    test_task_reference()

    print(f'\n{"="*50}')
    print(f'结果: {PASS} PASS, {FAIL} FAIL')
    if FAIL == 0:
        print('全部通过!')
    sys.exit(0 if FAIL == 0 else 1)
