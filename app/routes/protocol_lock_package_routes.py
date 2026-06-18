import json
import io
from flask import Blueprint, request, jsonify, current_app, send_file

lock_package_bp = Blueprint('lock_packages', __name__)


def _get_service(db):
    from app.services.protocol_lock_package_service import ProtocolLockPackageService
    return ProtocolLockPackageService(db)


@lock_package_bp.route('', methods=['GET'])
def list_packages():
    from app.database import get_db
    db = get_db(current_app)
    service = _get_service(db)

    is_enabled = request.args.get('is_enabled')
    if is_enabled is not None:
        is_enabled = is_enabled.lower() in ('1', 'true', 'yes')
    keyword = request.args.get('keyword')

    packages = service.list_packages(is_enabled=is_enabled, keyword=keyword)
    return jsonify({'packages': packages, 'count': len(packages)})


@lock_package_bp.route('/<int:package_id>', methods=['GET'])
def get_package(package_id):
    from app.database import get_db
    db = get_db(current_app)
    service = _get_service(db)

    pkg = service.get_package(package_id)
    if not pkg:
        return jsonify({'error': '锁定包不存在'}), 404
    return jsonify(pkg)


@lock_package_bp.route('', methods=['POST'])
def create_package():
    from app.database import get_db
    db = get_db(current_app)
    service = _get_service(db)

    data = request.get_json() or {}
    try:
        if data.get('task_id'):
            pkg = service.create_from_task(
                task_id=data['task_id'],
                name=data.get('name', ''),
                description=data.get('description'),
                operator=data.get('operator', 'user'),
            )
        else:
            pkg = service.create_manual(
                name=data.get('name', ''),
                description=data.get('description'),
                template_id=data.get('template_id'),
                total_volume=data.get('total_volume'),
                volume_unit=data.get('volume_unit', 'ul'),
                primer_id=data.get('primer_id'),
                master_mix_id=data.get('master_mix_id'),
                water_id=data.get('water_id'),
                deviation_note=data.get('deviation_note'),
                operator=data.get('operator', 'user'),
            )
        return jsonify(pkg), 201
    except ValueError as e:
        error_msg = str(e)
        resp = {'error': error_msg}
        if len(e.args) > 1 and e.args[1] == 'name_conflict':
            resp['conflict'] = 'name_exists'
            return jsonify(resp), 409
        return jsonify(resp), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@lock_package_bp.route('/<int:package_id>', methods=['PUT'])
def update_package(package_id):
    from app.database import get_db
    db = get_db(current_app)
    service = _get_service(db)

    data = request.get_json() or {}
    try:
        pkg = service.update_package(
            package_id=package_id,
            name=data.get('name'),
            description=data.get('description'),
            template_id=data.get('template_id'),
            total_volume=data.get('total_volume'),
            volume_unit=data.get('volume_unit'),
            primer_id=data.get('primer_id'),
            master_mix_id=data.get('master_mix_id'),
            water_id=data.get('water_id'),
            deviation_note=data.get('deviation_note'),
            operator=data.get('operator', 'user'),
        )
        return jsonify(pkg)
    except ValueError as e:
        error_msg = str(e)
        resp = {'error': error_msg}
        if len(e.args) > 1 and e.args[1] == 'name_conflict':
            resp['conflict'] = 'name_exists'
            return jsonify(resp), 409
        return jsonify(resp), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@lock_package_bp.route('/<int:package_id>', methods=['DELETE'])
def delete_package(package_id):
    from app.database import get_db
    db = get_db(current_app)
    service = _get_service(db)

    data = request.get_json(silent=True) or {}
    try:
        result = service.delete_package(
            package_id,
            operator=data.get('operator', 'user'),
        )
        return jsonify(result)
    except ValueError as e:
        error_msg = str(e)
        resp = {'error': error_msg}
        if len(e.args) > 1 and e.args[1] == 'package_referenced':
            resp['reason'] = 'package_referenced'
            return jsonify(resp), 409
        return jsonify(resp), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@lock_package_bp.route('/<int:package_id>/copy', methods=['POST'])
def copy_package(package_id):
    from app.database import get_db
    db = get_db(current_app)
    service = _get_service(db)

    data = request.get_json() or {}
    try:
        new_pkg = service.copy_package(
            package_id,
            new_name=data.get('name'),
            operator=data.get('operator', 'user'),
        )
        return jsonify(new_pkg), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@lock_package_bp.route('/<int:package_id>/enable', methods=['POST'])
def enable_package(package_id):
    from app.database import get_db
    db = get_db(current_app)
    service = _get_service(db)

    data = request.get_json() or {}
    try:
        pkg = service.enable_package(
            package_id,
            operator=data.get('operator', 'user'),
        )
        return jsonify(pkg)
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@lock_package_bp.route('/<int:package_id>/disable', methods=['POST'])
def disable_package(package_id):
    from app.database import get_db
    db = get_db(current_app)
    service = _get_service(db)

    data = request.get_json() or {}
    try:
        pkg = service.disable_package(
            package_id,
            operator=data.get('operator', 'user'),
        )
        return jsonify(pkg)
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@lock_package_bp.route('/<int:package_id>/validate', methods=['GET'])
def validate_dependencies(package_id):
    from app.database import get_db
    db = get_db(current_app)
    service = _get_service(db)

    try:
        result = service.validate_dependencies(package_id)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@lock_package_bp.route('/<int:package_id>/apply', methods=['POST'])
def apply_package(package_id):
    from app.database import get_db
    db = get_db(current_app)
    service = _get_service(db)

    data = request.get_json() or {}
    try:
        auto_generate = data.get('auto_generate', True)
        result = service.apply_package_to_task(
            package_id,
            task_name=data.get('task_name'),
            operator=data.get('operator', 'user'),
            auto_generate=auto_generate,
        )
        return jsonify(result), 201
    except ValueError as e:
        error_msg = str(e)
        resp = {'error': error_msg}
        if len(e.args) > 1 and e.args[1] == 'package_disabled':
            resp['reason'] = 'package_disabled'
            return jsonify(resp), 422
        if len(e.args) > 1 and e.args[1] == 'dependency_missing':
            resp['reason'] = 'dependency_missing'
            dep_result = service.validate_dependencies(package_id)
            resp['missing'] = dep_result.get('missing', [])
            resp['disabled'] = dep_result.get('disabled', [])
            return jsonify(resp), 422
        if len(e.args) > 1 and e.args[1] == 'frozen_params_incomplete':
            resp['reason'] = 'frozen_params_incomplete'
            return jsonify(resp), 422
        if len(e.args) > 1 and e.args[1] == 'generate_from_lock_failed':
            resp['reason'] = 'generate_from_lock_failed'
            return jsonify(resp), 422
        return jsonify(resp), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@lock_package_bp.route('/<int:package_id>/history', methods=['GET'])
def get_package_history(package_id):
    from app.database import get_db
    db = get_db(current_app)
    service = _get_service(db)

    limit = request.args.get('limit', 200, type=int)
    try:
        records = service.get_package_history(package_id, limit=limit)
        return jsonify({'records': records, 'count': len(records)})
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@lock_package_bp.route('/<int:package_id>/referenced-tasks', methods=['GET'])
def get_referenced_tasks(package_id):
    from app.database import get_db
    db = get_db(current_app)
    service = _get_service(db)

    try:
        tasks = service.get_package_referenced_tasks(package_id)
        return jsonify({'tasks': tasks, 'count': len(tasks)})
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@lock_package_bp.route('/task/<int:task_id>/package-ref', methods=['GET'])
def get_task_package_ref(task_id):
    from app.database import get_db
    db = get_db(current_app)
    service = _get_service(db)

    try:
        refs = service.get_task_package_reference(task_id)
        return jsonify({'references': refs, 'count': len(refs)})
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@lock_package_bp.route('/task/<int:task_id>/frozen-params', methods=['GET'])
def get_task_frozen_params(task_id):
    from app.database import get_db
    db = get_db(current_app)
    service = _get_service(db)

    try:
        frozen = service.get_task_frozen_params(task_id)
        if frozen is None:
            return jsonify({'has_lock_package': False, 'frozen_params': None})
        return jsonify({'has_lock_package': True, 'frozen_params': frozen})
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@lock_package_bp.route('/import', methods=['POST'])
def import_packages():
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
                result = service.import_packages_csv(
                    content, conflict_mode=conflict_mode,
                    operator=request.form.get('operator', 'user'),
                )
                return jsonify(result)
            except ValueError as e:
                return jsonify({'error': str(e)}), 400
        else:
            json_content = content

    try:
        result = service.import_packages_json(
            json_content, conflict_mode=conflict_mode,
            operator=(json_body or {}).get('operator', 'user') if json_body else 'user',
        )
        return jsonify(result)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400


@lock_package_bp.route('/export/json', methods=['GET'])
def export_packages_json():
    from app.database import get_db
    db = get_db(current_app)
    service = _get_service(db)

    package_ids_str = request.args.get('package_ids')
    is_enabled = request.args.get('is_enabled')
    if is_enabled is not None:
        is_enabled = is_enabled.lower() in ('1', 'true', 'yes')

    package_ids = None
    if package_ids_str:
        package_ids = [int(x) for x in package_ids_str.split(',') if x.strip()]

    try:
        json_str = service.export_packages_json(
            package_ids=package_ids, is_enabled=is_enabled
        )
        json_bytes = json_str.encode('utf-8')
        output = io.BytesIO(json_bytes)
        output.seek(0)

        return send_file(
            output,
            mimetype='application/json',
            as_attachment=True,
            download_name='protocol_lock_packages.json'
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@lock_package_bp.route('/export/csv', methods=['GET'])
def export_packages_csv():
    from app.database import get_db
    db = get_db(current_app)
    service = _get_service(db)

    package_ids_str = request.args.get('package_ids')
    is_enabled = request.args.get('is_enabled')
    if is_enabled is not None:
        is_enabled = is_enabled.lower() in ('1', 'true', 'yes')

    package_ids = None
    if package_ids_str:
        package_ids = [int(x) for x in package_ids_str.split(',') if x.strip()]

    try:
        csv_str = service.export_packages_csv(
            package_ids=package_ids, is_enabled=is_enabled
        )
        csv_bytes = csv_str.encode('utf-8-sig')
        output = io.BytesIO(csv_bytes)
        output.seek(0)

        return send_file(
            output,
            mimetype='text/csv',
            as_attachment=True,
            download_name='protocol_lock_packages.csv'
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 400
