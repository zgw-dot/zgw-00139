from flask import Blueprint, request, jsonify, current_app, send_file
import io

history_bp = Blueprint('history', __name__)

@history_bp.route('', methods=['GET'])
def list_history():
    from app.database import get_db
    from app.services.history_service import HistoryService
    
    db = get_db(current_app)
    service = HistoryService(db, current_app.config['DATA_DIR'])
    
    task_id = request.args.get('task_id', type=int)
    action_type = request.args.get('action_type')
    limit = request.args.get('limit', 100, type=int)
    
    history = service.get_history(task_id=task_id, action_type=action_type, limit=limit)
    return jsonify(history)

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
    
    task_id = request.args.get('task_id', type=int)
    json_data = service.export_history_json(task_id=task_id)
    
    output = io.BytesIO(json_data.encode('utf-8'))
    output.seek(0)
    
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
    
    task_id = request.args.get('task_id', type=int)
    csv_data = service.export_history_csv(task_id=task_id)
    
    output = io.BytesIO(csv_data.encode('utf-8-sig'))
    output.seek(0)
    
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
    task_id = data.get('task_id')
    
    result = service.save_history_export(task_id=task_id)
    return jsonify(result)
