from flask import Blueprint, request, jsonify, current_app
from app.services.data_importer import DataImporter

template_bp = Blueprint('templates', __name__)

@template_bp.route('', methods=['GET'])
def list_templates():
    from app.database import get_db
    db = get_db(current_app)
    
    templates = db.execute(
        'SELECT * FROM plate_templates ORDER BY created_at DESC'
    ).fetchall()
    
    return jsonify([dict(t) for t in templates])

@template_bp.route('/<int:template_id>', methods=['GET'])
def get_template(template_id):
    from app.database import get_db
    db = get_db(current_app)
    
    template = db.execute('SELECT * FROM plate_templates WHERE id = ?', (template_id,)).fetchone()
    if not template:
        return jsonify({'error': '模板不存在'}), 404
    
    wells = db.execute(
        'SELECT * FROM template_wells WHERE template_id = ? ORDER BY well_row, well_col',
        (template_id,)
    ).fetchall()
    
    result = dict(template)
    result['wells'] = [dict(w) for w in wells]
    
    return jsonify(result)

@template_bp.route('', methods=['POST'])
def create_template():
    from app.database import get_db
    db = get_db(current_app)
    
    data = request.get_json()
    name = data.get('name', '')
    rows = data.get('rows', 8)
    cols = data.get('cols', 12)
    description = data.get('description', '')
    wells = data.get('wells', [])
    
    try:
        cursor = db.execute('''
            INSERT INTO plate_templates (name, rows, cols, description)
            VALUES (?, ?, ?, ?)
        ''', (name, rows, cols, description))
        template_id = cursor.lastrowid
        
        if not wells:
            for r in range(1, rows + 1):
                for c in range(1, cols + 1):
                    db.execute('''
                        INSERT INTO template_wells (template_id, well_row, well_col, well_type)
                        VALUES (?, ?, ?, ?)
                    ''', (template_id, r, c, 'sample'))
        else:
            for well in wells:
                db.execute('''
                    INSERT INTO template_wells 
                    (template_id, well_row, well_col, well_type, sample_name, note)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (
                    template_id,
                    well['well_row'],
                    well['well_col'],
                    well.get('well_type', 'sample'),
                    well.get('sample_name'),
                    well.get('note', '')
                ))
        
        db.commit()
        
        template = db.execute('SELECT * FROM plate_templates WHERE id = ?', (template_id,)).fetchone()
        wells = db.execute(
            'SELECT * FROM template_wells WHERE template_id = ? ORDER BY well_row, well_col',
            (template_id,)
        ).fetchall()
        
        result = dict(template)
        result['wells'] = [dict(w) for w in wells]
        
        return jsonify(result), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@template_bp.route('/import', methods=['POST'])
def import_template():
    from app.database import get_db
    db = get_db(current_app)
    
    if 'file' not in request.files:
        return jsonify({'error': '未上传文件'}), 400
    
    file = request.files['file']
    content = file.read().decode('utf-8')
    name = request.form.get('name', file.filename)
    description = request.form.get('description', '')
    
    try:
        template_data = DataImporter.parse_template_csv(content)
    except Exception as e:
        return jsonify({'error': f'CSV 解析失败: {str(e)}'}), 400
    
    try:
        cursor = db.execute('''
            INSERT INTO plate_templates (name, rows, cols, description)
            VALUES (?, ?, ?, ?)
        ''', (name, template_data['rows'], template_data['cols'], description))
        template_id = cursor.lastrowid
        
        for well in template_data['wells']:
            db.execute('''
                INSERT INTO template_wells 
                (template_id, well_row, well_col, well_type, sample_name, note)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                template_id,
                well['well_row'],
                well['well_col'],
                well['well_type'],
                well.get('sample_name'),
                well.get('note', '')
            ))
        
        db.commit()
        
        template = db.execute('SELECT * FROM plate_templates WHERE id = ?', (template_id,)).fetchone()
        wells = db.execute(
            'SELECT * FROM template_wells WHERE template_id = ? ORDER BY well_row, well_col',
            (template_id,)
        ).fetchall()
        
        result = dict(template)
        result['wells'] = [dict(w) for w in wells]
        
        return jsonify(result), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@template_bp.route('/<int:template_id>', methods=['DELETE'])
def delete_template(template_id):
    from app.database import get_db
    db = get_db(current_app)
    
    try:
        db.execute('DELETE FROM plate_templates WHERE id = ?', (template_id,))
        db.commit()
        return jsonify({'message': '删除成功'})
    except Exception as e:
        return jsonify({'error': str(e)}), 400
