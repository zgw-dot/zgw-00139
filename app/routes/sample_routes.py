from flask import Blueprint, request, jsonify, current_app
from app.services.data_importer import DataImporter

sample_bp = Blueprint('samples', __name__)

@sample_bp.route('', methods=['GET'])
def list_samples():
    from app.database import get_db
    db = get_db(current_app)
    
    samples = db.execute(
        'SELECT * FROM samples ORDER BY created_at DESC'
    ).fetchall()
    
    return jsonify([dict(s) for s in samples])

@sample_bp.route('/<int:sample_id>', methods=['GET'])
def get_sample(sample_id):
    from app.database import get_db
    db = get_db(current_app)
    
    sample = db.execute('SELECT * FROM samples WHERE id = ?', (sample_id,)).fetchone()
    if not sample:
        return jsonify({'error': '样本不存在'}), 404
    
    return jsonify(dict(sample))

@sample_bp.route('', methods=['POST'])
def create_sample():
    from app.database import get_db
    db = get_db(current_app)
    
    data = request.get_json()
    
    try:
        cursor = db.execute('''
            INSERT INTO samples (name, concentration, concentration_unit, volume, volume_unit, description)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            data['name'],
            data['concentration'],
            data['concentration_unit'],
            data['volume'],
            data['volume_unit'],
            data.get('description', '')
        ))
        db.commit()
        
        sample = db.execute('SELECT * FROM samples WHERE id = ?', (cursor.lastrowid,)).fetchone()
        return jsonify(dict(sample)), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@sample_bp.route('/import', methods=['POST'])
def import_samples():
    from app.database import get_db
    db = get_db(current_app)
    
    if 'file' not in request.files:
        return jsonify({'error': '未上传文件'}), 400
    
    file = request.files['file']
    content = file.read().decode('utf-8')
    
    try:
        samples = DataImporter.parse_samples_csv(content)
    except Exception as e:
        return jsonify({'error': f'CSV 解析失败: {str(e)}'}), 400
    
    imported = 0
    errors = []
    
    for sample in samples:
        try:
            db.execute('''
                INSERT INTO samples (name, concentration, concentration_unit, volume, volume_unit, description)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                sample['name'],
                sample['concentration'],
                sample['concentration_unit'],
                sample['volume'],
                sample['volume_unit'],
                sample.get('description', '')
            ))
            imported += 1
        except Exception as e:
            errors.append(f"样本 {sample['name']}: {str(e)}")
    
    db.commit()
    
    return jsonify({
        'imported': imported,
        'errors': errors,
        'total': len(samples)
    })

@sample_bp.route('/<int:sample_id>', methods=['PUT'])
def update_sample(sample_id):
    from app.database import get_db
    db = get_db(current_app)
    
    data = request.get_json()
    
    try:
        db.execute('''
            UPDATE samples SET name = ?, concentration = ?, concentration_unit = ?, 
            volume = ?, volume_unit = ?, description = ? WHERE id = ?
        ''', (
            data['name'],
            data['concentration'],
            data['concentration_unit'],
            data['volume'],
            data['volume_unit'],
            data.get('description', ''),
            sample_id
        ))
        db.commit()
        
        sample = db.execute('SELECT * FROM samples WHERE id = ?', (sample_id,)).fetchone()
        return jsonify(dict(sample))
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@sample_bp.route('/<int:sample_id>', methods=['DELETE'])
def delete_sample(sample_id):
    from app.database import get_db
    db = get_db(current_app)
    
    try:
        db.execute('DELETE FROM samples WHERE id = ?', (sample_id,))
        db.commit()
        return jsonify({'message': '删除成功'})
    except Exception as e:
        return jsonify({'error': str(e)}), 400
