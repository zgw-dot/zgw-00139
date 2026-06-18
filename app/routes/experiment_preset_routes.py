import json
import io
from flask import Blueprint, request, jsonify, current_app, send_file

experiment_preset_bp = Blueprint('experiment_presets', __name__)


def _get_service(db):
    from app.services.experiment_preset_service import ExperimentPresetService
    return ExperimentPresetService(db)


@experiment_preset_bp.route('', methods=['GET'])
def list_presets():
    from app.database import get_db
    db = get_db(current_app)
    service = _get_service(db)

    is_enabled = request.args.get('is_enabled')
    if is_enabled is not None:
        is_enabled = is_enabled.lower() in ('1', 'true', 'yes')
    keyword = request.args.get('keyword')

    presets = service.list_presets(is_enabled=is_enabled, keyword=keyword)
    return jsonify({'presets': presets, 'count': len(presets)})


@experiment_preset_bp.route('/<int:preset_id>', methods=['GET'])
def get_preset(preset_id):
    from app.database import get_db
    db = get_db(current_app)
    service = _get_service(db)

    preset = service.get_preset(preset_id)
    if not preset:
        return jsonify({'error': '预设不存在'}), 404
    return jsonify(preset)


@experiment_preset_bp.route('', methods=['POST'])
def create_preset():
    from app.database import get_db
    db = get_db(current_app)
    service = _get_service(db)

    data = request.get_json() or {}
    try:
        preset = service.create_preset(
            name=data.get('name', ''),
            description=data.get('description'),
            template_id=data.get('template_id'),
            total_volume=data.get('total_volume'),
            volume_unit=data.get('volume_unit', 'ul'),
            primer_id=data.get('primer_id'),
            master_mix_id=data.get('master_mix_id'),
            water_id=data.get('water_id'),
            deviation_note_template=data.get('deviation_note_template'),
            operator=data.get('operator', 'user'),
        )
        return jsonify(preset), 201
    except ValueError as e:
        error_msg = str(e)
        resp = {'error': error_msg}
        if len(e.args) > 1 and e.args[1] == 'name_conflict':
            resp['conflict'] = 'name_exists'
            return jsonify(resp), 409
        return jsonify(resp), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@experiment_preset_bp.route('/<int:preset_id>', methods=['PUT'])
def update_preset(preset_id):
    from app.database import get_db
    db = get_db(current_app)
    service = _get_service(db)

    data = request.get_json() or {}
    try:
        preset = service.update_preset(
            preset_id=preset_id,
            name=data.get('name'),
            description=data.get('description'),
            template_id=data.get('template_id'),
            total_volume=data.get('total_volume'),
            volume_unit=data.get('volume_unit'),
            primer_id=data.get('primer_id'),
            master_mix_id=data.get('master_mix_id'),
            water_id=data.get('water_id'),
            deviation_note_template=data.get('deviation_note_template'),
            operator=data.get('operator', 'user'),
        )
        return jsonify(preset)
    except ValueError as e:
        error_msg = str(e)
        resp = {'error': error_msg}
        if len(e.args) > 1 and e.args[1] == 'name_conflict':
            resp['conflict'] = 'name_exists'
            return jsonify(resp), 409
        return jsonify(resp), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@experiment_preset_bp.route('/<int:preset_id>', methods=['DELETE'])
def delete_preset(preset_id):
    from app.database import get_db
    db = get_db(current_app)
    service = _get_service(db)

    data = request.get_json(silent=True) or {}
    try:
        result = service.delete_preset(
            preset_id,
            operator=data.get('operator', 'user'),
        )
        return jsonify(result)
    except ValueError as e:
        error_msg = str(e)
        resp = {'error': error_msg}
        if len(e.args) > 1 and e.args[1] == 'preset_referenced':
            resp['reason'] = 'preset_referenced'
            return jsonify(resp), 409
        return jsonify(resp), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@experiment_preset_bp.route('/<int:preset_id>/copy', methods=['POST'])
def copy_preset(preset_id):
    from app.database import get_db
    db = get_db(current_app)
    service = _get_service(db)

    data = request.get_json() or {}
    try:
        new_preset = service.copy_preset(
            preset_id,
            new_name=data.get('name'),
            operator=data.get('operator', 'user'),
        )
        return jsonify(new_preset), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@experiment_preset_bp.route('/<int:preset_id>/enable', methods=['POST'])
def enable_preset(preset_id):
    from app.database import get_db
    db = get_db(current_app)
    service = _get_service(db)

    data = request.get_json() or {}
    try:
        preset = service.enable_preset(
            preset_id,
            operator=data.get('operator', 'user'),
        )
        return jsonify(preset)
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@experiment_preset_bp.route('/<int:preset_id>/disable', methods=['POST'])
def disable_preset(preset_id):
    from app.database import get_db
    db = get_db(current_app)
    service = _get_service(db)

    data = request.get_json() or {}
    try:
        preset = service.disable_preset(
            preset_id,
            operator=data.get('operator', 'user'),
        )
        return jsonify(preset)
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@experiment_preset_bp.route('/<int:preset_id>/validate', methods=['GET'])
def validate_dependencies(preset_id):
    from app.database import get_db
    db = get_db(current_app)
    service = _get_service(db)

    try:
        result = service.validate_dependencies(preset_id)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@experiment_preset_bp.route('/<int:preset_id>/apply', methods=['POST'])
def apply_preset(preset_id):
    from app.database import get_db
    db = get_db(current_app)
    service = _get_service(db)

    data = request.get_json() or {}
    try:
        result = service.apply_preset_to_task(
            preset_id,
            task_name=data.get('task_name'),
            operator=data.get('operator', 'user'),
        )
        return jsonify(result), 201
    except ValueError as e:
        error_msg = str(e)
        resp = {'error': error_msg}
        if len(e.args) > 1 and e.args[1] == 'dependency_missing':
            resp['reason'] = 'dependency_missing'
            preset = service._get_preset(preset_id)
            dep_result = service.validate_dependencies(preset_id)
            resp['missing'] = dep_result.get('missing', [])
            return jsonify(resp), 422
        return jsonify(resp), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@experiment_preset_bp.route('/save-from-task', methods=['POST'])
def save_from_task():
    from app.database import get_db
    db = get_db(current_app)
    service = _get_service(db)

    data = request.get_json() or {}
    task_id = data.get('task_id')
    preset_name = data.get('preset_name')

    if not task_id:
        return jsonify({'error': '缺少 task_id'}), 400
    if not preset_name:
        return jsonify({'error': '缺少预设名称 preset_name'}), 400

    try:
        preset = service.save_task_as_preset(
            task_id=task_id,
            preset_name=preset_name,
            description=data.get('description'),
            operator=data.get('operator', 'user'),
        )
        return jsonify(preset), 201
    except ValueError as e:
        error_msg = str(e)
        resp = {'error': error_msg}
        if len(e.args) > 1 and e.args[1] == 'name_conflict':
            resp['conflict'] = 'name_exists'
            return jsonify(resp), 409
        return jsonify(resp), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@experiment_preset_bp.route('/<int:preset_id>/history', methods=['GET'])
def get_preset_history(preset_id):
    from app.database import get_db
    db = get_db(current_app)
    service = _get_service(db)

    limit = request.args.get('limit', 200, type=int)
    try:
        records = service.get_preset_history(preset_id, limit=limit)
        return jsonify({'records': records, 'count': len(records)})
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@experiment_preset_bp.route('/<int:preset_id>/referenced-tasks', methods=['GET'])
def get_referenced_tasks(preset_id):
    from app.database import get_db
    db = get_db(current_app)
    service = _get_service(db)

    try:
        tasks = service.get_preset_referenced_tasks(preset_id)
        return jsonify({'tasks': tasks, 'count': len(tasks)})
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@experiment_preset_bp.route('/task/<int:task_id>/preset-ref', methods=['GET'])
def get_task_preset_ref(task_id):
    from app.database import get_db
    db = get_db(current_app)
    service = _get_service(db)

    try:
        refs = service.get_task_preset_reference(task_id)
        return jsonify({'references': refs, 'count': len(refs)})
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@experiment_preset_bp.route('/import', methods=['POST'])
def import_presets():
    from app.database import get_db
    db = get_db(current_app)
    service = _get_service(db)

    conflict_mode = (request.form.get('conflict_mode')
                     or request.args.get('conflict_mode')
                     or 'reject')

    json_body = request.get_json(silent=True)

    if 'file' not in request.files:
        if json_body:
            json_content = json.dumps(json_body, ensure_ascii=False)
            if not conflict_mode or conflict_mode == 'reject':
                conflict_mode = json_body.get('conflict_mode', 'reject')
        else:
            return jsonify({'error': '未上传文件且未提供JSON数据'}), 400
    else:
        file = request.files['file']
        filename = (file.filename or '').lower()
        content = file.read().decode('utf-8')

        if filename.endswith('.csv'):
            try:
                result = service.import_presets_csv(
                    content, conflict_mode=conflict_mode,
                    operator=request.form.get('operator', 'user'),
                )
                return jsonify(result)
            except ValueError as e:
                return jsonify({'error': str(e)}), 400
        else:
            json_content = content

    try:
        result = service.import_presets_json(
            json_content, conflict_mode=conflict_mode,
            operator=(json_body or {}).get('operator', 'user') if json_body else 'user',
        )
        return jsonify(result)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400


@experiment_preset_bp.route('/export/json', methods=['GET'])
def export_presets_json():
    from app.database import get_db
    db = get_db(current_app)
    service = _get_service(db)

    preset_ids_str = request.args.get('preset_ids')
    is_enabled = request.args.get('is_enabled')
    if is_enabled is not None:
        is_enabled = is_enabled.lower() in ('1', 'true', 'yes')

    preset_ids = None
    if preset_ids_str:
        preset_ids = [int(x) for x in preset_ids_str.split(',') if x.strip()]

    try:
        json_str = service.export_presets_json(
            preset_ids=preset_ids, is_enabled=is_enabled
        )
        json_bytes = json_str.encode('utf-8')
        output = io.BytesIO(json_bytes)
        output.seek(0)

        return send_file(
            output,
            mimetype='application/json',
            as_attachment=True,
            download_name='experiment_presets.json'
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@experiment_preset_bp.route('/export/csv', methods=['GET'])
def export_presets_csv():
    from app.database import get_db
    db = get_db(current_app)
    service = _get_service(db)

    preset_ids_str = request.args.get('preset_ids')
    is_enabled = request.args.get('is_enabled')
    if is_enabled is not None:
        is_enabled = is_enabled.lower() in ('1', 'true', 'yes')

    preset_ids = None
    if preset_ids_str:
        preset_ids = [int(x) for x in preset_ids_str.split(',') if x.strip()]

    try:
        csv_str = service.export_presets_csv(
            preset_ids=preset_ids, is_enabled=is_enabled
        )
        csv_bytes = csv_str.encode('utf-8-sig')
        output = io.BytesIO(csv_bytes)
        output.seek(0)

        return send_file(
            output,
            mimetype='text/csv',
            as_attachment=True,
            download_name='experiment_presets.csv'
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 400
