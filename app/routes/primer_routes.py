from flask import Blueprint, request, jsonify, current_app
from app.services.data_importer import DataImporter

primer_bp = Blueprint('primers', __name__)

@primer_bp.route('', methods=['GET'])
def list_primers():
    from app.database import get_db
    db = get_db(current_app)
    
    primers = db.execute(
        'SELECT * FROM primers ORDER BY created_at DESC'
    ).fetchall()
    
    return jsonify([dict(p) for p in primers])

@primer_bp.route('/<int:primer_id>', methods=['GET'])
def get_primer(primer_id):
    from app.database import get_db
    db = get_db(current_app)
    
    primer = db.execute('SELECT * FROM primers WHERE id = ?', (primer_id,)).fetchone()
    if not primer:
        return jsonify({'error': '引物不存在'}), 404
    
    return jsonify(dict(primer))

@primer_bp.route('', methods=['POST'])
def create_primer():
    from app.database import get_db
    db = get_db(current_app)
    
    data = request.get_json()
    
    try:
        cursor = db.execute('''
            INSERT INTO primers (name, sequence, concentration, concentration_unit, 
                                volume, volume_unit, melting_temp, description)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            data['name'],
            data.get('sequence', ''),
            data['concentration'],
            data['concentration_unit'],
            data['volume'],
            data['volume_unit'],
            data.get('melting_temp'),
            data.get('description', '')
        ))
        db.commit()
        
        primer = db.execute('SELECT * FROM primers WHERE id = ?', (cursor.lastrowid,)).fetchone()
        return jsonify(dict(primer)), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@primer_bp.route('/import', methods=['POST'])
def import_primers():
    from app.database import get_db
    db = get_db(current_app)
    
    if 'file' not in request.files:
        return jsonify({'error': '未上传文件'}), 400
    
    file = request.files['file']
    content = file.read().decode('utf-8')
    
    try:
        primers = DataImporter.parse_primers_csv(content)
    except Exception as e:
        return jsonify({'error': f'CSV 解析失败: {str(e)}'}), 400
    
    imported = 0
    errors = []
    
    for primer in primers:
        try:
            db.execute('''
                INSERT INTO primers (name, sequence, concentration, concentration_unit, 
                                    volume, volume_unit, melting_temp, description)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                primer['name'],
                primer.get('sequence', ''),
                primer['concentration'],
                primer['concentration_unit'],
                primer['volume'],
                primer['volume_unit'],
                primer.get('melting_temp'),
                primer.get('description', '')
            ))
            imported += 1
        except Exception as e:
            errors.append(f"引物 {primer['name']}: {str(e)}")
    
    db.commit()
    
    return jsonify({
        'imported': imported,
        'errors': errors,
        'total': len(primers)
    })

@primer_bp.route('/<int:primer_id>', methods=['PUT'])
def update_primer(primer_id):
    from app.database import get_db
    db = get_db(current_app)
    
    data = request.get_json()
    
    try:
        db.execute('''
            UPDATE primers SET name = ?, sequence = ?, concentration = ?, concentration_unit = ?,
            volume = ?, volume_unit = ?, melting_temp = ?, description = ? WHERE id = ?
        ''', (
            data['name'],
            data.get('sequence', ''),
            data['concentration'],
            data['concentration_unit'],
            data['volume'],
            data['volume_unit'],
            data.get('melting_temp'),
            data.get('description', ''),
            primer_id
        ))
        db.commit()
        
        primer = db.execute('SELECT * FROM primers WHERE id = ?', (primer_id,)).fetchone()
        return jsonify(dict(primer))
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@primer_bp.route('/<int:primer_id>', methods=['DELETE'])
def delete_primer(primer_id):
    from app.database import get_db
    db = get_db(current_app)
    
    try:
        db.execute('DELETE FROM primers WHERE id = ?', (primer_id,))
        db.commit()
        return jsonify({'message': '删除成功'})
    except Exception as e:
        return jsonify({'error': str(e)}), 400
