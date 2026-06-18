from flask import Blueprint, request, jsonify, current_app, send_file
import io

history_bp = Blueprint('history', __name__)


def _get_filter_args():
    return {
        'task_id': request.args.get('task_id'),
        'action_type': request.args.get('action_type'),
        'start_date': request.args.get('start_date'),
        'end_date': request.args.get('end_date'),
        'keyword': request.args.get('keyword'),
        'limit': request.args.get('limit', 100, type=int),
    }


def _get_batch_number():
    return (request.args.get('batch_number') or '').strip() or None


@history_bp.route('', methods=['GET'])
def list_history():
    from app.database import get_db
    from app.services.history_service import HistoryService
    from app.services.batch_trace_service import BatchTraceService

    db = get_db(current_app)
    service = HistoryService(db, current_app.config['DATA_DIR'])

    filters = _get_filter_args()
    batch_number = _get_batch_number()
    result = service.query_history(**filters)

    if result.get('errors'):
        return jsonify({
            'records': [],
            'total': 0,
            'filters': result.get('filters', ''),
            'errors': result['errors'],
            'warnings': result.get('warnings', []),
        }), 400

    records = result['records']
    total = result['total']
    if batch_number:
        trace_service = BatchTraceService(db)
        records = trace_service.enrich_history_with_batch_filter(
            records, batch_number=batch_number
        )
        total = len(records)
        extra = f' | 批次号:{batch_number}'
        result['filters'] = (result.get('filters', '') + extra).strip()

    return jsonify({
        'records': records,
        'total': total,
        'filters': result['filters'],
        'errors': [],
        'warnings': result.get('warnings', []),
    })


@history_bp.route('/filters', methods=['GET'])
def list_filters():
    from app.database import get_db
    from app.services.history_service import HistoryService

    db = get_db(current_app)
    service = HistoryService(db, current_app.config['DATA_DIR'])

    try:
        tasks = service.list_tasks()
    except Exception as e:
        tasks = []

    action_types = []
    for at in service.ACTION_TYPES:
        action_types.append({
            'value': at,
            'label': service.ACTION_TYPE_LABELS.get(at, at),
        })

    return jsonify({
        'tasks': tasks,
        'action_types': action_types,
        'max_limit': 5000,
        'default_limit': 100,
    })


@history_bp.route('/inventory', methods=['GET'])
def list_inventory_logs():
    from app.database import get_db
    from app.services.history_service import HistoryService

    db = get_db(current_app)
    service = HistoryService(db, current_app.config['DATA_DIR'])

    reagent_id = request.args.get('reagent_id', type=int)
    primer_id = request.args.get('primer_id', type=int)
    limit = request.args.get('limit', 100, type=int)

    logs = service.get_inventory_logs(reagent_id=reagent_id, primer_id=primer_id, limit=limit)
    return jsonify(logs)


@history_bp.route('/export/json', methods=['GET'])
def export_history_json():
    from app.database import get_db
    from app.services.history_service import HistoryService

    db = get_db(current_app)
    service = HistoryService(db, current_app.config['DATA_DIR'])

    filters = _get_filter_args()

    try:
        json_data = service.export_history_json(**filters)
    except ValueError as e:
        return jsonify({
            'error': str(e),
            'filters': filters,
        }), 400
    except Exception as e:
        return jsonify({
            'error': f'导出失败: {str(e)}',
            'filters': filters,
        }), 500

    output = io.BytesIO(json_data.encode('utf-8'))
    output.seek(0)

    task_id = filters.get('task_id')
    filename = 'history_export.json'
    if task_id:
        filename = f'history_task_{task_id}_export.json'

    return send_file(
        output,
        mimetype='application/json',
        as_attachment=True,
        download_name=filename
    )


@history_bp.route('/export/csv', methods=['GET'])
def export_history_csv():
    from app.database import get_db
    from app.services.history_service import HistoryService

    db = get_db(current_app)
    service = HistoryService(db, current_app.config['DATA_DIR'])

    filters = _get_filter_args()

    try:
        csv_data = service.export_history_csv(**filters)
    except ValueError as e:
        return jsonify({
            'error': str(e),
            'filters': filters,
        }), 400
    except Exception as e:
        return jsonify({
            'error': f'导出失败: {str(e)}',
            'filters': filters,
        }), 500

    output = io.BytesIO(csv_data.encode('utf-8-sig'))
    output.seek(0)

    task_id = filters.get('task_id')
    filename = 'history_export.csv'
    if task_id:
        filename = f'history_task_{task_id}_export.csv'

    return send_file(
        output,
        mimetype='text/csv',
        as_attachment=True,
        download_name=filename
    )


@history_bp.route('/export/save', methods=['POST'])
def save_history_export():
    from app.database import get_db
    from app.services.history_service import HistoryService

    db = get_db(current_app)
    service = HistoryService(db, current_app.config['DATA_DIR'])

    data = request.get_json() or {}
    filters = {
        'task_id': data.get('task_id'),
        'action_type': data.get('action_type'),
        'start_date': data.get('start_date'),
        'end_date': data.get('end_date'),
        'keyword': data.get('keyword'),
        'limit': data.get('limit', 5000),
    }

    try:
        result = service.save_history_export(**filters)
        return jsonify(result)
    except ValueError as e:
        return jsonify({'error': str(e), 'filters': filters}), 400
    except Exception as e:
        return jsonify({'error': f'保存失败: {str(e)}', 'filters': filters}), 500


@history_bp.route('/presets', methods=['GET'])
def list_filter_presets():
    from app.database import get_db
    from app.services.history_service import HistoryService

    db = get_db(current_app)
    service = HistoryService(db, current_app.config['DATA_DIR'])

    try:
        presets = service.list_filter_presets()
        return jsonify({
            'presets': presets,
            'count': len(presets),
        })
    except Exception as e:
        return jsonify({'error': f'获取筛选方案列表失败: {str(e)}'}), 500


@history_bp.route('/presets/default', methods=['GET'])
def get_default_filter_preset():
    from app.database import get_db
    from app.services.history_service import HistoryService

    db = get_db(current_app)
    service = HistoryService(db, current_app.config['DATA_DIR'])

    try:
        preset = service.get_default_filter_preset()
        return jsonify({
            'preset': preset,
        })
    except Exception as e:
        return jsonify({'error': f'获取默认筛选方案失败: {str(e)}'}), 500


@history_bp.route('/presets/<int:preset_id>', methods=['GET'])
def get_filter_preset(preset_id):
    from app.database import get_db
    from app.services.history_service import HistoryService

    db = get_db(current_app)
    service = HistoryService(db, current_app.config['DATA_DIR'])

    try:
        preset = service.get_filter_preset(preset_id)
        if not preset:
            return jsonify({'error': f'筛选方案 #{preset_id} 不存在'}), 404
        return jsonify({
            'preset': preset,
        })
    except Exception as e:
        return jsonify({'error': f'获取筛选方案失败: {str(e)}'}), 500


@history_bp.route('/presets', methods=['POST'])
def create_filter_preset():
    from app.database import get_db
    from app.services.history_service import HistoryService

    db = get_db(current_app)
    service = HistoryService(db, current_app.config['DATA_DIR'])

    data = request.get_json() or {}
    required_fields = ['name']
    for field in required_fields:
        if field not in data or not str(data[field]).strip():
            return jsonify({'error': f'缺少必填字段: {field}'}), 400

    try:
        preset = service.save_filter_preset(
            name=data.get('name'),
            description=data.get('description'),
            task_id=data.get('task_id'),
            action_type=data.get('action_type'),
            start_date=data.get('start_date'),
            end_date=data.get('end_date'),
            keyword=data.get('keyword'),
            limit=data.get('limit', 100),
            is_default=data.get('is_default', False),
        )
        return jsonify({
            'preset': preset,
            'message': f'筛选方案 "{preset["name"]}" 创建成功',
        }), 201
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': f'创建筛选方案失败: {str(e)}'}), 500


@history_bp.route('/presets/<int:preset_id>', methods=['PUT'])
def update_filter_preset(preset_id):
    from app.database import get_db
    from app.services.history_service import HistoryService

    db = get_db(current_app)
    service = HistoryService(db, current_app.config['DATA_DIR'])

    data = request.get_json() or {}
    required_fields = ['name']
    for field in required_fields:
        if field not in data or not str(data[field]).strip():
            return jsonify({'error': f'缺少必填字段: {field}'}), 400

    try:
        preset = service.save_filter_preset(
            name=data.get('name'),
            description=data.get('description'),
            task_id=data.get('task_id'),
            action_type=data.get('action_type'),
            start_date=data.get('start_date'),
            end_date=data.get('end_date'),
            keyword=data.get('keyword'),
            limit=data.get('limit', 100),
            is_default=data.get('is_default', False),
            preset_id=preset_id,
        )
        return jsonify({
            'preset': preset,
            'message': f'筛选方案 "{preset["name"]}" 更新成功',
        })
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': f'更新筛选方案失败: {str(e)}'}), 500


@history_bp.route('/presets/<int:preset_id>/default', methods=['POST'])
def set_default_filter_preset(preset_id):
    from app.database import get_db
    from app.services.history_service import HistoryService

    db = get_db(current_app)
    service = HistoryService(db, current_app.config['DATA_DIR'])

    try:
        preset = service.set_default_filter_preset(preset_id)
        return jsonify({
            'preset': preset,
            'message': f'已将 "{preset["name"]}" 设为默认筛选方案',
        })
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': f'设置默认筛选方案失败: {str(e)}'}), 500


@history_bp.route('/presets/<int:preset_id>', methods=['DELETE'])
def delete_filter_preset(preset_id):
    from app.database import get_db
    from app.services.history_service import HistoryService

    db = get_db(current_app)
    service = HistoryService(db, current_app.config['DATA_DIR'])

    try:
        result = service.delete_filter_preset(preset_id)
        message = '筛选方案删除成功'
        if result.get('was_default'):
            remaining = service.get_default_filter_preset()
            if remaining:
                message += f'，已自动将 "{remaining["name"]}" 设为新的默认方案'
            else:
                message += '，当前无默认筛选方案'
        return jsonify({
            'deleted': result['deleted'],
            'was_default': result['was_default'],
            'message': message,
        })
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': f'删除筛选方案失败: {str(e)}'}), 500
