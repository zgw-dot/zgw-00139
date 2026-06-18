import io
from flask import Blueprint, request, jsonify, current_app, send_file

batch_trace_bp = Blueprint('batch_trace', __name__)


def _get_service():
    from app.database import get_db
    from app.services.batch_trace_service import BatchTraceService
    db = get_db(current_app)
    return BatchTraceService(db)


@batch_trace_bp.route('/ledger', methods=['GET'])
def query_ledger():
    try:
        service = _get_service()
        batch_id = request.args.get('batch_id', type=int)
        reagent_id = request.args.get('reagent_id', type=int)
        task_id = request.args.get('task_id', type=int)
        event_type = request.args.get('event_type')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        keyword = request.args.get('keyword')
        limit = request.args.get('limit', 1000, type=int)

        records = service.query_ledger(
            batch_id=batch_id,
            reagent_id=reagent_id,
            task_id=task_id,
            event_type=event_type,
            start_date=start_date,
            end_date=end_date,
            keyword=keyword,
            limit=limit,
        )
        return jsonify({
            'count': len(records),
            'records': records,
            'event_type_labels': service.EVENT_TYPE_LABELS,
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@batch_trace_bp.route('/batch/<int:batch_id>', methods=['GET'])
def trace_by_batch(batch_id):
    try:
        service = _get_service()
        result = service.trace_by_batch(batch_id=batch_id)
        return jsonify(result)
    except ValueError as e:
        return jsonify({'error': str(e)}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@batch_trace_bp.route('/task/<int:task_id>', methods=['GET'])
def trace_by_task(task_id):
    try:
        service = _get_service()
        result = service.trace_by_task(task_id=task_id)
        return jsonify(result)
    except ValueError as e:
        return jsonify({'error': str(e)}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@batch_trace_bp.route('/conflicts', methods=['GET'])
def list_conflicts():
    try:
        service = _get_service()
        reagent_name = request.args.get('reagent_name')
        batch_number = request.args.get('batch_number')
        conflict_type = request.args.get('conflict_type')
        resolved_raw = request.args.get('resolved')
        resolved = None
        if resolved_raw is not None:
            r = str(resolved_raw).strip().lower()
            if r in ('1', 'true', 'yes'):
                resolved = True
            elif r in ('0', 'false', 'no'):
                resolved = False
        limit = request.args.get('limit', 500, type=int)

        records = service.list_conflicts(
            reagent_name=reagent_name,
            batch_number=batch_number,
            conflict_type=conflict_type,
            resolved=resolved,
            limit=limit,
        )
        return jsonify({
            'count': len(records),
            'records': records,
            'conflict_type_labels': service.CONFLICT_TYPE_LABELS,
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@batch_trace_bp.route('/conflicts/<int:conflict_id>', methods=['GET'])
def get_conflict(conflict_id):
    try:
        service = _get_service()
        record = service.get_conflict(conflict_id)
        if not record:
            return jsonify({'error': '冲突记录不存在'}), 404
        return jsonify(record)
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@batch_trace_bp.route('/conflicts/<int:conflict_id>/resolve', methods=['POST'])
def resolve_conflict(conflict_id):
    try:
        service = _get_service()
        existing = service.get_conflict(conflict_id)
        if not existing:
            return jsonify({'error': '冲突记录不存在'}), 404
        data = request.get_json() or {}
        note = data.get('resolution_note') or data.get('note')
        if not note:
            return jsonify({'error': '必须提供解决说明 (resolution_note)'}), 400
        operator = data.get('operator', 'user')
        updated = service.resolve_conflict(conflict_id, note, operator=operator)
        return jsonify(updated)
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@batch_trace_bp.route('/batch/<int:batch_id>/safety', methods=['GET'])
def check_batch_safety(batch_id):
    try:
        service = _get_service()
        current_task_id = request.args.get('current_task_id', type=int)
        result = service.check_batch_occupied_safety(
            batch_id=batch_id,
            current_task_id=current_task_id,
        )
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@batch_trace_bp.route('/task/<int:task_id>/revoke-check', methods=['GET'])
def check_revoke_completeness(task_id):
    try:
        service = _get_service()
        result = service.check_revoke_completeness(task_id=task_id)
        status_code = 200 if result['complete'] else 409
        return jsonify(result), status_code
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@batch_trace_bp.route('/export/json', methods=['GET'])
def export_ledger_json():
    try:
        service = _get_service()
        batch_id = request.args.get('batch_id', type=int)
        reagent_id = request.args.get('reagent_id', type=int)
        task_id = request.args.get('task_id', type=int)
        event_type = request.args.get('event_type')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        keyword = request.args.get('keyword')
        limit = request.args.get('limit', 5000, type=int)

        json_str = service.export_ledger_json(
            batch_id=batch_id,
            reagent_id=reagent_id,
            task_id=task_id,
            event_type=event_type,
            start_date=start_date,
            end_date=end_date,
            keyword=keyword,
            limit=limit,
        )
        json_bytes = json_str.encode('utf-8')
        output = io.BytesIO(json_bytes)
        output.seek(0)
        timestamp = __import__('datetime').datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'batch_trace_ledger_{timestamp}.json'
        return send_file(
            output,
            mimetype='application/json',
            as_attachment=True,
            download_name=filename,
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@batch_trace_bp.route('/export/csv', methods=['GET'])
def export_ledger_csv():
    try:
        service = _get_service()
        batch_id = request.args.get('batch_id', type=int)
        reagent_id = request.args.get('reagent_id', type=int)
        task_id = request.args.get('task_id', type=int)
        event_type = request.args.get('event_type')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        keyword = request.args.get('keyword')
        limit = request.args.get('limit', 5000, type=int)

        csv_str = service.export_ledger_csv(
            batch_id=batch_id,
            reagent_id=reagent_id,
            task_id=task_id,
            event_type=event_type,
            start_date=start_date,
            end_date=end_date,
            keyword=keyword,
            limit=limit,
        )
        csv_bytes = ('\ufeff' + csv_str).encode('utf-8')
        output = io.BytesIO(csv_bytes)
        output.seek(0)
        timestamp = __import__('datetime').datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'batch_trace_ledger_{timestamp}.csv'
        return send_file(
            output,
            mimetype='text/csv',
            as_attachment=True,
            download_name=filename,
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@batch_trace_bp.route('/conflicts/export/json', methods=['GET'])
def export_conflicts_json():
    try:
        service = _get_service()
        limit = request.args.get('limit', 5000, type=int)
        json_str = service.export_conflicts_json(limit=limit)
        json_bytes = json_str.encode('utf-8')
        output = io.BytesIO(json_bytes)
        output.seek(0)
        timestamp = __import__('datetime').datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'batch_import_conflicts_{timestamp}.json'
        return send_file(
            output,
            mimetype='application/json',
            as_attachment=True,
            download_name=filename,
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@batch_trace_bp.route('/conflicts/export/csv', methods=['GET'])
def export_conflicts_csv():
    try:
        service = _get_service()
        limit = request.args.get('limit', 5000, type=int)
        csv_str = service.export_conflicts_csv(limit=limit)
        csv_bytes = ('\ufeff' + csv_str).encode('utf-8')
        output = io.BytesIO(csv_bytes)
        output.seek(0)
        timestamp = __import__('datetime').datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'batch_import_conflicts_{timestamp}.csv'
        return send_file(
            output,
            mimetype='text/csv',
            as_attachment=True,
            download_name=filename,
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@batch_trace_bp.route('/event-types', methods=['GET'])
def get_event_types():
    from app.services.batch_trace_service import BatchTraceService
    return jsonify({
        'event_types': BatchTraceService.EVENT_TYPES,
        'event_type_labels': BatchTraceService.EVENT_TYPE_LABELS,
    })


@batch_trace_bp.route('/conflict-types', methods=['GET'])
def get_conflict_types():
    from app.services.batch_trace_service import BatchTraceService
    return jsonify({
        'conflict_types': BatchTraceService.CONFLICT_TYPES,
        'conflict_type_labels': BatchTraceService.CONFLICT_TYPE_LABELS,
    })
