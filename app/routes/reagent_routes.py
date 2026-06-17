from flask import Blueprint, request, jsonify, current_app
from app.services.data_importer import DataImporter

reagent_bp = Blueprint('reagents', __name__)

@reagent_bp.route('', methods=['GET'])
def list_reagents():
    from app.database import get_db
    db = get_db(current_app)
    
    reagents = db.execute(
        'SELECT * FROM reagents ORDER BY created_at DESC'
    ).fetchall()
    
    return jsonify([dict(r) for r in reagents])

@reagent_bp.route('/<int:reagent_id>', methods=['GET'])
def get_reagent(reagent_id):
    from app.database import get_db
    db = get_db(current_app)
    
    reagent = db.execute('SELECT * FROM reagents WHERE id = ?', (reagent_id,)).fetchone()
    if not reagent:
        return jsonify({'error': '试剂不存在'}), 404
    
    return jsonify(dict(reagent))

@reagent_bp.route('', methods=['POST'])
def create_reagent():
    from app.database import get_db
    db = get_db(current_app)
    
    data = request.get_json()
    
    try:
        cursor = db.execute('''
            INSERT INTO reagents (name, type, concentration, concentration_unit, 
                                 volume, volume_unit, min_pipette_volume, min_pipette_unit, description)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            data['name'],
            data['type'],
            data.get('concentration'),
            data.get('concentration_unit'),
            data['volume'],
            data['volume_unit'],
            data.get('min_pipette_volume'),
            data.get('min_pipette_unit', 'ul'),
            data.get('description', '')
        ))
        db.commit()
        
        reagent = db.execute('SELECT * FROM reagents WHERE id = ?', (cursor.lastrowid,)).fetchone()
        return jsonify(dict(reagent)), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@reagent_bp.route('/import', methods=['POST'])
def import_reagents():
    from app.database import get_db
    db = get_db(current_app)
    
    if 'file' not in request.files:
        return jsonify({'error': '未上传文件'}), 400
    
    file = request.files['file']
    content = file.read().decode('utf-8')
    
    try:
        reagents = DataImporter.parse_reagents_csv(content)
    except Exception as e:
        return jsonify({'error': f'CSV 解析失败: {str(e)}'}), 400
    
    imported = 0
    errors = []
    
    for reagent in reagents:
        try:
            db.execute('''
                INSERT INTO reagents (name, type, concentration, concentration_unit, 
                                     volume, volume_unit, min_pipette_volume, min_pipette_unit, description)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                reagent['name'],
                reagent['type'],
                reagent.get('concentration'),
                reagent.get('concentration_unit'),
                reagent['volume'],
                reagent['volume_unit'],
                reagent.get('min_pipette_volume'),
                reagent.get('min_pipette_unit', 'ul'),
                reagent.get('description', '')
            ))
            imported += 1
        except Exception as e:
            errors.append(f"试剂 {reagent['name']}: {str(e)}")
    
    db.commit()
    
    return jsonify({
        'imported': imported,
        'errors': errors,
        'total': len(reagents)
    })

@reagent_bp.route('/<int:reagent_id>', methods=['PUT'])
def update_reagent(reagent_id):
    from app.database import get_db
    db = get_db(current_app)
    
    data = request.get_json()
    
    try:
        db.execute('''
            UPDATE reagents SET name = ?, type = ?, concentration = ?, concentration_unit = ?,
            volume = ?, volume_unit = ?, min_pipette_volume = ?, min_pipette_unit = ?, description = ? 
            WHERE id = ?
        ''', (
            data['name'],
            data['type'],
            data.get('concentration'),
            data.get('concentration_unit'),
            data['volume'],
            data['volume_unit'],
            data.get('min_pipette_volume'),
            data.get('min_pipette_unit', 'ul'),
            data.get('description', ''),
            reagent_id
        ))
        db.commit()
        
        reagent = db.execute('SELECT * FROM reagents WHERE id = ?', (reagent_id,)).fetchone()
        return jsonify(dict(reagent))
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@reagent_bp.route('/<int:reagent_id>', methods=['DELETE'])
def delete_reagent(reagent_id):
    from app.database import get_db
    db = get_db(current_app)
    
    try:
        db.execute('DELETE FROM reagents WHERE id = ?', (reagent_id,))
        db.commit()
        return jsonify({'message': '删除成功'})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@reagent_bp.route('/<int:reagent_id>/logs', methods=['GET'])
def get_reagent_logs(reagent_id):
    from app.database import get_db
    from app.services.history_service import HistoryService
    
    db = get_db(current_app)
    history_service = HistoryService(db, current_app.config['DATA_DIR'])
    
    logs = history_service.get_inventory_logs(reagent_id=reagent_id)
    return jsonify(logs)
