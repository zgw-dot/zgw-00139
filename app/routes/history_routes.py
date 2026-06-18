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


@history_bp.route('', methods=['GET'])
def list_history():
    from app.database import get_db
    from app.services.history_service import HistoryService

    db = get_db(current_app)
    service = HistoryService(db, current_app.config['DATA_DIR'])

    filters = _get_filter_args()
    result = service.query_history(**filters)

    if result.get('errors'):
        return jsonify({
            'records': [],
            'total': 0,
            'filters': result.get('filters', ''),
            'errors': result['errors'],
            'warnings': result.get('warnings', []),
        }), 400

    return jsonify({
        'records': result['records'],
        'total': result['total'],
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
