import json
from flask import Blueprint, request, jsonify, current_app

task_bp = Blueprint('tasks', __name__)

@task_bp.route('', methods=['GET'])
def list_tasks():
    from app.database import get_db
    from app.services.task_service import TaskService
    
    db = get_db(current_app)
    service = TaskService(db)
    
    status = request.args.get('status')
    tasks = service.list_tasks(status=status)
    
    return jsonify(tasks)

@task_bp.route('/<int:task_id>', methods=['GET'])
def get_task(task_id):
    from app.database import get_db
    from app.services.task_service import TaskService
    
    db = get_db(current_app)
    service = TaskService(db)
    
    task = service.get_task(task_id)
    if not task:
        return jsonify({'error': '任务不存在'}), 404
    
    return jsonify(task)

@task_bp.route('', methods=['POST'])
def create_task():
    from app.database import get_db
    from app.services.task_service import TaskService
    
    db = get_db(current_app)
    service = TaskService(db)
    
    data = request.get_json()
    
    try:
        task_id = service.create_task(
            name=data['name'],
            template_id=data['template_id'],
            total_volume=data.get('total_volume', 20),
            volume_unit=data.get('volume_unit', 'ul')
        )
        
        task = service.get_task(task_id)
        return jsonify(task), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@task_bp.route('/<int:task_id>/generate', methods=['POST'])
def generate_plan(task_id):
    from app.database import get_db
    from app.services.task_service import TaskService
    
    db = get_db(current_app)
    service = TaskService(db)
    
    data = request.get_json() or {}
    
    try:
        result = service.generate_plan(
            task_id=task_id,
            sample_assignments=data.get('sample_assignments'),
            primer_id=data.get('primer_id'),
            master_mix_id=data.get('master_mix_id'),
            water_id=data.get('water_id')
        )
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@task_bp.route('/<int:task_id>/approve', methods=['POST'])
def approve_task(task_id):
    from app.database import get_db
    from app.services.task_service import TaskService
    
    db = get_db(current_app)
    service = TaskService(db)
    
    data = request.get_json() or {}
    operator = data.get('operator', 'user')
    ignore_min_pipette = data.get('ignore_min_pipette', False)
    
    try:
        result = service.approve_task(task_id, operator=operator, ignore_min_pipette=ignore_min_pipette)
        return jsonify({'success': result, 'message': '任务已批准，库存已扣减'})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@task_bp.route('/<int:task_id>/reject', methods=['POST'])
def reject_task(task_id):
    from app.database import get_db
    from app.services.task_service import TaskService
    
    db = get_db(current_app)
    service = TaskService(db)
    
    data = request.get_json() or {}
    reason = data.get('reason', '')
    operator = data.get('operator', 'user')
    
    if not reason:
        return jsonify({'error': '驳回原因不能为空'}), 400
    
    try:
        result = service.reject_task(task_id, reason, operator=operator)
        return jsonify({'success': result, 'message': '任务已驳回'})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@task_bp.route('/<int:task_id>/revoke', methods=['POST'])
def revoke_task(task_id):
    from app.database import get_db
    from app.services.task_service import TaskService
    
    db = get_db(current_app)
    service = TaskService(db)
    
    data = request.get_json() or {}
    operator = data.get('operator', 'user')
    
    try:
        result = service.revoke_approval(task_id, operator=operator)
        return jsonify({'success': result, 'message': '已撤销确认，库存已退回'})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@task_bp.route('/<int:task_id>/deviation', methods=['POST'])
def add_deviation(task_id):
    from app.database import get_db
    from app.services.task_service import TaskService
    
    db = get_db(current_app)
    service = TaskService(db)
    
    data = request.get_json() or {}
    note = data.get('note', '')
    operator = data.get('operator', 'user')
    
    if not note:
        return jsonify({'error': '偏差备注不能为空'}), 400
    
    try:
        result = service.add_deviation_note(task_id, note, operator=operator)
        return jsonify({'success': result, 'message': '偏差备注已添加'})
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@task_bp.route('/<int:task_id>/copy', methods=['POST'])
def copy_task(task_id):
    from app.database import get_db
    from app.services.task_service import TaskService
    
    db = get_db(current_app)
    service = TaskService(db)
    
    data = request.get_json() or {}
    new_name = data.get('name')
    
    try:
        new_task_id = service.copy_task(task_id, new_name=new_name)
        new_task = service.get_task(new_task_id)
        return jsonify(new_task), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@task_bp.route('/<int:task_id>/export/json', methods=['GET'])
def export_task_json(task_id):
    from app.database import get_db
    from app.services.task_service import TaskService
    import io
    from flask import send_file
    
    db = get_db(current_app)
    service = TaskService(db)
    
    try:
        json_str = service.export_task_json(task_id)
        task = db.execute('SELECT name FROM tasks WHERE id = ?', (task_id,)).fetchone()
        
        json_bytes = json_str.encode('utf-8')
        output = io.BytesIO(json_bytes)
        output.seek(0)
        
        filename = f'{task["name"]}_方案.json' if task else 'task_plan.json'
        
        return send_file(
            output,
            mimetype='application/json',
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@task_bp.route('/import', methods=['POST'])
def import_task():
    from app.database import get_db
    from app.services.task_service import TaskService
    
    db = get_db(current_app)
    service = TaskService(db)
    
    conflict_mode = (request.form.get('conflict_mode')
                     or request.args.get('conflict_mode')
                     or 'reject')
    
    json_body = request.get_json(silent=True)
    
    if 'file' not in request.files:
        if json_body and 'task' in json_body:
            json_content = json.dumps(json_body, ensure_ascii=False)
            if not conflict_mode or conflict_mode == 'reject':
                conflict_mode = json_body.get('conflict_mode', 'reject')
        else:
            return jsonify({'error': '未上传文件且未提供JSON数据'}), 400
    else:
        file = request.files['file']
        content = file.read().decode('utf-8')
        json_content = content
    
    try:
        new_task_id = service.import_task_json(json_content, conflict_mode=conflict_mode)
        new_task = service.get_task(new_task_id)
        return jsonify(new_task), 201
    except Exception as e:
        error_msg = str(e)
        status_code = 400
        conflict_type = None
        existing_id = None
        
        if '名称已存在' in error_msg or '已存在' in error_msg:
            status_code = 409
            conflict_type = 'name_exists'
            existing = db.execute(
                "SELECT id FROM tasks WHERE name = ?", 
                (json.loads(json_content).get('task', {}).get('name', ''),)
            ).fetchone()
            if existing:
                existing_id = existing['id']
        
        response = {'error': error_msg}
        if conflict_type:
            response['conflict'] = conflict_type
        if existing_id:
            response['existing_id'] = existing_id
        
        return jsonify(response), status_code
