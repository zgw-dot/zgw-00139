import os
import sys
import io
import json
import tempfile
import shutil
import traceback
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '_debug_result.txt')
f = open(out_path, 'w', encoding='utf-8')


def log(*args):
    print(*args, file=f, flush=True)


TEST_DB_PATH = None


def create_test_app():
    from flask import Flask
    import os as _os

    app = Flask(__name__, static_folder='../static', static_url_path='/static')
    app.config['SECRET_KEY'] = 'pcr-planner-test-key'
    app.config['DATABASE'] = TEST_DB_PATH
    app.config['DATA_DIR'] = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), 'data')

    from flask_cors import CORS
    CORS(app)

    from app.database import init_db
    init_db(app)

    from app.routes.main_routes import main_bp
    from app.routes.sample_routes import sample_bp
    from app.routes.primer_routes import primer_bp
    from app.routes.reagent_routes import reagent_bp
    from app.routes.template_routes import template_bp
    from app.routes.task_routes import task_bp
    from app.routes.history_routes import history_bp
    from app.routes.report_routes import report_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(sample_bp, url_prefix='/api/samples')
    app.register_blueprint(primer_bp, url_prefix='/api/primers')
    app.register_blueprint(reagent_bp, url_prefix='/api/reagents')
    app.register_blueprint(template_bp, url_prefix='/api/templates')
    app.register_blueprint(task_bp, url_prefix='/api/tasks')
    app.register_blueprint(history_bp, url_prefix='/api/history')
    app.register_blueprint(report_bp, url_prefix='/api/reports')

    return app


def build_reagents_csv(rows):
    headers = ['name', 'type', 'volume', 'volume_unit', 'concentration',
               'concentration_unit', 'batch_number', 'expiry_date',
               'frozen', 'min_usable_volume', 'min_usable_unit']
    lines = [','.join(headers)]
    for r in rows:
        vals = []
        for h in headers:
            v = r.get(h, '')
            if v is None:
                v = ''
            vals.append(str(v))
        lines.append(','.join(vals))
    return '\n'.join(lines)


if __name__ == '__main__':
    tmpdir = tempfile.mkdtemp(prefix='pcr_debug_')
    TEST_DB_PATH = os.path.join(tmpdir, 'pcr_test.db')
    log(f"DB: {TEST_DB_PATH}")

    try:
        app = create_test_app()
        client = app.test_client()

        today = datetime.now()
        exp_good = (today + timedelta(days=180)).strftime('%Y-%m-%d')
        exp_expired = (today - timedelta(days=10)).strftime('%Y-%m-%d')
        exp_near = (today + timedelta(days=15)).strftime('%Y-%m-%d')

        csv_content = build_reagents_csv([
            {'name': 'Master_Mix_2x', 'type': 'master_mix', 'volume': 1000,
             'volume_unit': 'ul', 'concentration': 2, 'concentration_unit': 'x',
             'batch_number': 'MM-001', 'expiry_date': exp_good,
             'frozen': 0, 'min_usable_volume': 50, 'min_usable_unit': 'ul'},
            {'name': 'Taq_Polymerase', 'type': 'enzyme', 'volume': 800,
             'volume_unit': 'ul', 'concentration': 5, 'concentration_unit': 'U/ul',
             'batch_number': 'TAQ-GOOD', 'expiry_date': exp_good,
             'frozen': 0, 'min_usable_volume': 10, 'min_usable_unit': 'ul'},
            {'name': 'Water_Nuclease_Free', 'type': 'buffer', 'volume': 5000,
             'volume_unit': 'ul', 'concentration': '', 'concentration_unit': '',
             'batch_number': 'W-001', 'expiry_date': '', 'frozen': 0},
        ])
        data = {'file': (io.BytesIO(csv_content.encode('utf-8')), 'test_reagents.csv')}
        resp = client.post('/api/reagents/import', data=data,
                           content_type='multipart/form-data')
        log(f"Import: status={resp.status_code}, body={resp.get_json()}")

        csv_tpl = (
            "well_row,well_col,well_type,sample_name,primer_name,sample_volume,"
            "sample_volume_unit,primer_volume,primer_volume_unit,master_mix_volume,"
            "master_mix_unit,water_volume,water_unit,total_volume,total_volume_unit,note\n"
            "A,1,sample,S1,P1,2,ul,1,ul,5,ul,2,ul,10,ul,\n"
            "A,2,sample,S2,P2,2,ul,1,ul,5,ul,2,ul,10,ul,\n"
        )
        data = {'file': (io.BytesIO(csv_tpl.encode('utf-8')), 'tpl.csv')}
        resp = client.post('/api/templates/import', data=data,
                           content_type='multipart/form-data')
        log(f"Tpl import: status={resp.status_code}")
        tpl = resp.get_json()
        log(f"Tpl type: {type(tpl)}, keys: {list(tpl.keys()) if isinstance(tpl, dict) else 'N/A'}")
        log(f"Tpl: {json.dumps(tpl, indent=2, ensure_ascii=False)[:1000]}")

        tpl_id = tpl.get('id')
        log(f"template_id = {tpl_id}")

        task_data = {
            'name': 'DebugTask',
            'template_id': tpl_id,
            'total_volume': 20,
            'volume_unit': 'ul',
        }
        log(f"Creating task with data: {task_data}")
        resp = client.post('/api/tasks', json=task_data)
        log(f"Create task: status={resp.status_code}, data={resp.data[:500]}")
        try:
            task = resp.get_json()
            log(f"Task type: {type(task)}, keys: {list(task.keys()) if isinstance(task, dict) else type(task)}")
        except Exception as e2:
            log(f"Parse task json err: {e2}")
            task = None
        log(f"Task: {json.dumps(task, indent=2, ensure_ascii=False)[:500] if isinstance(task, dict) else task}")

        task_id = task.get('id') if isinstance(task, dict) else None
        log(f"task_id = {task_id}")

        resp = client.post(f"/api/tasks/{task_id}/generate")
        log(f"Generate: status={resp.status_code}")
        log(f"Generate body (first 4000 chars): {resp.data.decode('utf-8')[:4000]}")
    except Exception as e:
        log("EXCEPTION:", e)
        log(traceback.format_exc())
    finally:
        f.close()
        try:
            shutil.rmtree(tmpdir)
        except Exception:
            pass
    print(f"Result written to: {out_path}")
