from flask import Blueprint, request, jsonify, current_app, send_file
import io

report_bp = Blueprint('reports', __name__)

@report_bp.route('/task/<int:task_id>', methods=['GET'])
def get_task_report(task_id):
    from app.database import get_db
    from app.services.report_service import ReportService
    
    db = get_db(current_app)
    service = ReportService(db)
    
    try:
        report = service.generate_task_report(task_id)
        return jsonify(report)
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@report_bp.route('/task/<int:task_id>/csv', methods=['GET'])
def export_report_csv(task_id):
    from app.database import get_db
    from app.services.report_service import ReportService
    
    db = get_db(current_app)
    service = ReportService(db)
    
    try:
        csv_data = service.export_report_csv(task_id)
        
        output = io.BytesIO(csv_data.encode('utf-8-sig'))
        output.seek(0)
        
        return send_file(
            output,
            mimetype='text/csv',
            as_attachment=True,
            download_name=f'task_{task_id}_report.csv'
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@report_bp.route('/task/<int:task_id>/json', methods=['GET'])
def export_report_json(task_id):
    from app.database import get_db
    from app.services.report_service import ReportService
    
    db = get_db(current_app)
    service = ReportService(db)
    
    try:
        json_data = service.export_report_json(task_id)
        
        output = io.BytesIO(json_data.encode('utf-8'))
        output.seek(0)
        
        return send_file(
            output,
            mimetype='application/json',
            as_attachment=True,
            download_name=f'task_{task_id}_report.json'
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 400
