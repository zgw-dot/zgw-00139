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
