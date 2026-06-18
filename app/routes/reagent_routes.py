from flask import Blueprint, request, jsonify, current_app
from app.services.data_importer import DataImporter
from app.services.unit_converter import UnitConverter

reagent_bp = Blueprint('reagents', __name__)

@reagent_bp.route('', methods=['GET'])
def list_reagents():
    from app.database import get_db
    db = get_db(current_app)
    
    reagents = db.execute(
        'SELECT * FROM reagents ORDER BY created_at DESC'
    ).fetchall()
    
    result = []
    for r in reagents:
        r_dict = dict(r)
        batches = db.execute(
            'SELECT * FROM reagent_batches WHERE reagent_id = ? ORDER BY expiry_date ASC NULLS LAST, id ASC',
            (r['id'],)
        ).fetchall()
        r_dict['batches'] = [dict(b) for b in batches]
        result.append(r_dict)
    
    return jsonify(result)

@reagent_bp.route('/<int:reagent_id>', methods=['GET'])
def get_reagent(reagent_id):
    from app.database import get_db
    db = get_db(current_app)
    
    reagent = db.execute('SELECT * FROM reagents WHERE id = ?', (reagent_id,)).fetchone()
    if not reagent:
        return jsonify({'error': '试剂不存在'}), 404
    
    result = dict(reagent)
    batches = db.execute(
        'SELECT * FROM reagent_batches WHERE reagent_id = ? ORDER BY expiry_date ASC NULLS LAST, id ASC',
        (reagent_id,)
    ).fetchall()
    result['batches'] = [dict(b) for b in batches]
    
    return jsonify(result)

@reagent_bp.route('', methods=['POST'])
def create_reagent():
    from app.database import get_db
    db = get_db(current_app)
    
    data = request.get_json()
    
    try:
        if not UnitConverter.is_volume_unit(data['volume_unit']):
            raise ValueError(f"无效的体积单位: {data['volume_unit']}")
        min_pipette_unit = data.get('min_pipette_unit', 'ul')
        if not UnitConverter.is_volume_unit(min_pipette_unit):
            raise ValueError(f"无效的最小移液单位: {min_pipette_unit}")
        
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
        parsed_rows = DataImporter.parse_reagents_csv(content)
    except Exception as e:
        return jsonify({'error': f'CSV 解析失败: {str(e)}'}), 400
    
    imported_reagents = 0
    imported_batches = 0
    errors = []
    
    reagent_name_to_id = {}
    for row in parsed_rows:
        reagent = row['reagent']
        batch = row['batch']
        try:
            existing = db.execute(
                'SELECT id FROM reagents WHERE name = ?', (reagent['name'],)
            ).fetchone()
            
            if existing:
                reagent_id = existing['id']
            else:
                cursor = db.execute('''
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
                reagent_id = cursor.lastrowid
                imported_reagents += 1
                reagent_name_to_id[reagent['name']] = reagent_id
            
            if batch.get('batch_number'):
                existing_batch = db.execute(
                    'SELECT id FROM reagent_batches WHERE reagent_id = ? AND batch_number = ?',
                    (reagent_id, batch['batch_number'])
                ).fetchone()
                if existing_batch:
                    errors.append(f"试剂 {reagent['name']} 的批次 {batch['batch_number']} 已存在，跳过该批次")
                else:
                    db.execute('''
                        INSERT INTO reagent_batches 
                        (reagent_id, batch_number, volume, volume_unit, expiry_date, 
                         is_frozen, min_usable_volume, min_usable_unit, description)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        reagent_id,
                        batch['batch_number'],
                        reagent['volume'],
                        reagent['volume_unit'],
                        batch.get('expiry_date'),
                        1 if batch.get('is_frozen') else 0,
                        batch.get('min_usable_volume'),
                        batch.get('min_usable_unit', 'ul'),
                        reagent.get('description', '')
                    ))
                    imported_batches += 1
            
        except Exception as e:
            errors.append(f"试剂 {reagent['name']}: {str(e)}")
    
    db.commit()
    
    return jsonify({
        'imported_reagents': imported_reagents,
        'imported_batches': imported_batches,
        'errors': errors,
        'total': len(parsed_rows)
    })

@reagent_bp.route('/<int:reagent_id>', methods=['PUT'])
def update_reagent(reagent_id):
    from app.database import get_db
    db = get_db(current_app)
    
    data = request.get_json()
    
    try:
        if not UnitConverter.is_volume_unit(data['volume_unit']):
            raise ValueError(f"无效的体积单位: {data['volume_unit']}")
        min_pipette_unit = data.get('min_pipette_unit', 'ul')
        if not UnitConverter.is_volume_unit(min_pipette_unit):
            raise ValueError(f"无效的最小移液单位: {min_pipette_unit}")
        
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


@reagent_bp.route('/<int:reagent_id>/batches', methods=['GET'])
def list_reagent_batches(reagent_id):
    from app.database import get_db
    db = get_db(current_app)
    
    reagent = db.execute('SELECT id FROM reagents WHERE id = ?', (reagent_id,)).fetchone()
    if not reagent:
        return jsonify({'error': '试剂不存在'}), 404
    
    batches = db.execute(
        'SELECT * FROM reagent_batches WHERE reagent_id = ? ORDER BY expiry_date ASC NULLS LAST, id ASC',
        (reagent_id,)
    ).fetchall()
    return jsonify([dict(b) for b in batches])


@reagent_bp.route('/<int:reagent_id>/batches', methods=['POST'])
def create_reagent_batch(reagent_id):
    from app.database import get_db
    db = get_db(current_app)
    
    reagent = db.execute('SELECT id FROM reagents WHERE id = ?', (reagent_id,)).fetchone()
    if not reagent:
        return jsonify({'error': '试剂不存在'}), 404
    
    data = request.get_json() or {}
    
    try:
        batch_number = (data.get('batch_number') or '').strip()
        if not batch_number:
            raise ValueError('批次号不能为空')
        
        volume_unit = data.get('volume_unit', 'ul')
        if not UnitConverter.is_volume_unit(volume_unit):
            raise ValueError(f'无效的体积单位: {volume_unit}')
        
        min_usable_unit = data.get('min_usable_unit', 'ul')
        if not UnitConverter.is_volume_unit(min_usable_unit):
            raise ValueError(f'无效的最小可用量单位: {min_usable_unit}')
        
        existing = db.execute(
            'SELECT id FROM reagent_batches WHERE reagent_id = ? AND batch_number = ?',
            (reagent_id, batch_number)
        ).fetchone()
        if existing:
            raise ValueError(f'同名批次已存在: {batch_number}')
        
        cursor = db.execute('''
            INSERT INTO reagent_batches 
            (reagent_id, batch_number, volume, volume_unit, expiry_date, 
             is_frozen, min_usable_volume, min_usable_unit, description)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            reagent_id,
            batch_number,
            float(data.get('volume', 0)),
            volume_unit,
            data.get('expiry_date'),
            1 if data.get('is_frozen') else 0,
            data.get('min_usable_volume'),
            min_usable_unit,
            data.get('description', '')
        ))
        db.commit()
        
        batch = db.execute('SELECT * FROM reagent_batches WHERE id = ?', (cursor.lastrowid,)).fetchone()
        return jsonify(dict(batch)), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@reagent_bp.route('/batches/<int:batch_id>', methods=['GET'])
def get_reagent_batch(batch_id):
    from app.database import get_db
    db = get_db(current_app)
    
    batch = db.execute('SELECT * FROM reagent_batches WHERE id = ?', (batch_id,)).fetchone()
    if not batch:
        return jsonify({'error': '批次不存在'}), 404
    return jsonify(dict(batch))


@reagent_bp.route('/batches/<int:batch_id>', methods=['PUT'])
def update_reagent_batch(batch_id):
    from app.database import get_db
    db = get_db(current_app)
    
    batch = db.execute('SELECT * FROM reagent_batches WHERE id = ?', (batch_id,)).fetchone()
    if not batch:
        return jsonify({'error': '批次不存在'}), 404
    
    data = request.get_json() or {}
    
    try:
        volume_unit = data.get('volume_unit', batch['volume_unit'])
        if not UnitConverter.is_volume_unit(volume_unit):
            raise ValueError(f'无效的体积单位: {volume_unit}')
        
        min_usable_unit = data.get('min_usable_unit', batch['min_usable_unit'])
        if min_usable_unit and not UnitConverter.is_volume_unit(min_usable_unit):
            raise ValueError(f'无效的最小可用量单位: {min_usable_unit}')
        
        new_batch_number = (data.get('batch_number') or batch['batch_number']).strip()
        if new_batch_number != batch['batch_number']:
            existing = db.execute(
                'SELECT id FROM reagent_batches WHERE reagent_id = ? AND batch_number = ? AND id != ?',
                (batch['reagent_id'], new_batch_number, batch_id)
            ).fetchone()
            if existing:
                raise ValueError(f'同名批次已存在: {new_batch_number}')
        
        db.execute('''
            UPDATE reagent_batches SET 
                batch_number = ?, volume = ?, volume_unit = ?, expiry_date = ?,
                is_frozen = ?, min_usable_volume = ?, min_usable_unit = ?, description = ?
            WHERE id = ?
        ''', (
            new_batch_number,
            float(data.get('volume', batch['volume'])),
            volume_unit,
            data.get('expiry_date', batch['expiry_date']),
            1 if data.get('is_frozen') else 0,
            data.get('min_usable_volume', batch['min_usable_volume']),
            min_usable_unit,
            data.get('description', batch.get('description', '')),
            batch_id
        ))
        db.commit()
        
        updated = db.execute('SELECT * FROM reagent_batches WHERE id = ?', (batch_id,)).fetchone()
        return jsonify(dict(updated))
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@reagent_bp.route('/batches/<int:batch_id>/freeze', methods=['POST'])
def freeze_batch(batch_id):
    from app.database import get_db
    db = get_db(current_app)
    
    batch = db.execute('SELECT * FROM reagent_batches WHERE id = ?', (batch_id,)).fetchone()
    if not batch:
        return jsonify({'error': '批次不存在'}), 404
    
    db.execute('UPDATE reagent_batches SET is_frozen = 1 WHERE id = ?', (batch_id,))
    db.commit()
    
    updated = db.execute('SELECT * FROM reagent_batches WHERE id = ?', (batch_id,)).fetchone()
    return jsonify(dict(updated))


@reagent_bp.route('/batches/<int:batch_id>/unfreeze', methods=['POST'])
def unfreeze_batch(batch_id):
    from app.database import get_db
    db = get_db(current_app)
    
    batch = db.execute('SELECT * FROM reagent_batches WHERE id = ?', (batch_id,)).fetchone()
    if not batch:
        return jsonify({'error': '批次不存在'}), 404
    
    db.execute('UPDATE reagent_batches SET is_frozen = 0 WHERE id = ?', (batch_id,))
    db.commit()
    
    updated = db.execute('SELECT * FROM reagent_batches WHERE id = ?', (batch_id,)).fetchone()
    return jsonify(dict(updated))


@reagent_bp.route('/batches/<int:batch_id>', methods=['DELETE'])
def delete_reagent_batch(batch_id):
    from app.database import get_db
    db = get_db(current_app)
    
    batch = db.execute('SELECT * FROM reagent_batches WHERE id = ?', (batch_id,)).fetchone()
    if not batch:
        return jsonify({'error': '批次不存在'}), 404
    
    used = db.execute(
        'SELECT COUNT(*) as cnt FROM task_reagent_usage WHERE batch_id = ?',
        (batch_id,)
    ).fetchone()
    if used and used['cnt'] > 0:
        return jsonify({'error': f'该批次已被 {used["cnt"]} 个任务使用，无法删除'}), 400
    
    db.execute('DELETE FROM reagent_batches WHERE id = ?', (batch_id,))
    db.commit()
    return jsonify({'message': '删除成功'})


@reagent_bp.route('/batches/<int:batch_id>/logs', methods=['GET'])
def get_batch_logs(batch_id):
    from app.database import get_db
    db = get_db(current_app)
    
    batch = db.execute('SELECT * FROM reagent_batches WHERE id = ?', (batch_id,)).fetchone()
    if not batch:
        return jsonify({'error': '批次不存在'}), 404
    
    logs = db.execute(
        'SELECT * FROM reagent_inventory_log WHERE batch_id = ? ORDER BY created_at DESC',
        (batch_id,)
    ).fetchall()
    return jsonify([dict(l) for l in logs])
