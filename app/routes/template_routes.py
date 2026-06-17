import json
import csv
import io
from flask import Blueprint, request, jsonify, current_app, send_file
from app.services.data_importer import DataImporter

template_bp = Blueprint('templates', __name__)


def _add_template_history(db, action, action_type, detail, template_id=None):
    db.execute('''
        INSERT INTO history (task_id, action, action_type, detail, operator)
        VALUES (?, ?, ?, ?, ?)
    ''', (None, action, action_type, detail, 'system'))


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

        _add_template_history(db, 'create', 'template_created',
                              f'创建模板: {name}', template_id=template_id)
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


@template_bp.route('/<int:template_id>/export/json', methods=['GET'])
def export_template_json(template_id):
    from app.database import get_db
    db = get_db(current_app)

    template = db.execute('SELECT * FROM plate_templates WHERE id = ?', (template_id,)).fetchone()
    if not template:
        return jsonify({'error': '模板不存在'}), 404

    wells = db.execute(
        'SELECT well_row, well_col, well_type, sample_name, note '
        'FROM template_wells WHERE template_id = ? ORDER BY well_row, well_col',
        (template_id,)
    ).fetchall()

    export_data = {
        'name': template['name'],
        'rows': template['rows'],
        'cols': template['cols'],
        'description': template['description'],
        'wells': [dict(w) for w in wells],
    }

    _add_template_history(db, 'export', 'template_exported',
                          f'导出模板为JSON: {template["name"]}', template_id=template_id)
    db.commit()

    json_bytes = json.dumps(export_data, ensure_ascii=False, indent=2).encode('utf-8')
    output = io.BytesIO(json_bytes)
    output.seek(0)

    return send_file(
        output,
        mimetype='application/json',
        as_attachment=True,
        download_name=f'{template["name"]}.json'
    )


@template_bp.route('/<int:template_id>/export/csv', methods=['GET'])
def export_template_csv(template_id):
    from app.database import get_db
    db = get_db(current_app)

    template = db.execute('SELECT * FROM plate_templates WHERE id = ?', (template_id,)).fetchone()
    if not template:
        return jsonify({'error': '模板不存在'}), 404

    wells = db.execute(
        'SELECT well_row, well_col, well_type, sample_name, note '
        'FROM template_wells WHERE template_id = ? ORDER BY well_row, well_col',
        (template_id,)
    ).fetchall()

    grid = {}
    for w in wells:
        cell_value = ''
        if w['well_type'] == 'positive_control':
            cell_value = 'PC'
        elif w['well_type'] == 'negative_control':
            cell_value = 'NC'
        elif w['well_type'] == 'empty':
            cell_value = 'EMPTY'
        elif w['sample_name']:
            cell_value = w['sample_name']
        else:
            cell_value = 'S'
        grid[(w['well_row'], w['well_col'])] = cell_value

    output = io.StringIO()
    writer = csv.writer(output)

    header = [''] + [str(c) for c in range(1, template['cols'] + 1)]
    writer.writerow(header)

    for r in range(1, template['rows'] + 1):
        row_label = chr(64 + r)
        row_data = [row_label]
        for c in range(1, template['cols'] + 1):
            row_data.append(grid.get((r, c), 'EMPTY'))
        writer.writerow(row_data)

    _add_template_history(db, 'export', 'template_exported',
                          f'导出模板为CSV: {template["name"]}', template_id=template_id)
    db.commit()

    csv_bytes = output.getvalue().encode('utf-8-sig')
    bytes_output = io.BytesIO(csv_bytes)
    bytes_output.seek(0)

    return send_file(
        bytes_output,
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'{template["name"]}.csv'
    )


@template_bp.route('/<int:template_id>/copy', methods=['POST'])
def copy_template(template_id):
    from app.database import get_db
    db = get_db(current_app)

    template = db.execute('SELECT * FROM plate_templates WHERE id = ?', (template_id,)).fetchone()
    if not template:
        return jsonify({'error': '模板不存在'}), 404

    data = request.get_json() or {}
    new_name = data.get('name', f'{template["name"]}_副本')

    existing = db.execute('SELECT id FROM plate_templates WHERE name = ?', (new_name,)).fetchone()
    if existing:
        suffix = 1
        while db.execute('SELECT id FROM plate_templates WHERE name = ?',
                         (f'{template["name"]}_副本{suffix}',)).fetchone():
            suffix += 1
        new_name = f'{template["name"]}_副本{suffix}'

    cursor = db.execute('''
        INSERT INTO plate_templates (name, rows, cols, description)
        VALUES (?, ?, ?, ?)
    ''', (new_name, template['rows'], template['cols'],
          data.get('description', template['description'])))
    new_id = cursor.lastrowid

    wells = db.execute(
        'SELECT well_row, well_col, well_type, sample_name, note '
        'FROM template_wells WHERE template_id = ? ORDER BY well_row, well_col',
        (template_id,)
    ).fetchall()

    for w in wells:
        db.execute('''
            INSERT INTO template_wells (template_id, well_row, well_col, well_type, sample_name, note)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (new_id, w['well_row'], w['well_col'], w['well_type'],
              w['sample_name'], w['note']))

    db.commit()

    _add_template_history(db, 'copy', 'template_copied',
                          f'复制模板: {template["name"]} → {new_name}',
                          template_id=new_id)
    db.commit()

    new_template = db.execute('SELECT * FROM plate_templates WHERE id = ?', (new_id,)).fetchone()
    new_wells = db.execute(
        'SELECT * FROM template_wells WHERE template_id = ? ORDER BY well_row, well_col',
        (new_id,)
    ).fetchall()

    result = dict(new_template)
    result['wells'] = [dict(w) for w in new_wells]

    return jsonify(result), 201


@template_bp.route('/import', methods=['POST'])
def import_template():
    from app.database import get_db
    db = get_db(current_app)

    conflict_mode = (request.form.get('conflict_mode')
                     or request.args.get('conflict_mode')
                     or 'reject')

    json_body = request.get_json(silent=True)

    if 'file' not in request.files:
        if json_body and 'wells' in json_body:
            name = json_body.get('name', '')
            description = json_body.get('description', '')
            rows = json_body.get('rows', 8)
            cols = json_body.get('cols', 12)
            wells = json_body.get('wells', [])
            template_data = {'rows': rows, 'cols': cols, 'wells': wells}
            if not conflict_mode or conflict_mode == 'reject':
                conflict_mode = json_body.get('conflict_mode', 'reject')
        else:
            return jsonify({'error': '未上传文件且未提供JSON数据'}), 400
    else:
        file = request.files['file']
        filename = file.filename or ''
        content = file.read().decode('utf-8')
        name = request.form.get('name', filename)
        description = request.form.get('description', '')

        if filename.lower().endswith('.json'):
            try:
                json_data = json.loads(content)
                template_data = {
                    'rows': json_data.get('rows', 8),
                    'cols': json_data.get('cols', 12),
                    'wells': json_data.get('wells', []),
                }
                if not name or name.lower().endswith('.json'):
                    name = json_data.get('name', name)
                if not description:
                    description = json_data.get('description', '')
            except json.JSONDecodeError as e:
                return jsonify({'error': f'JSON 解析失败: {str(e)}'}), 400
        else:
            try:
                template_data = DataImporter.parse_template_csv(content)
            except Exception as e:
                return jsonify({'error': f'CSV 解析失败: {str(e)}'}), 400

    if not template_data:
        return jsonify({'error': '模板数据为空'}), 400

    existing = db.execute('SELECT id FROM plate_templates WHERE name = ?', (name,)).fetchone()

    if existing:
        existing_id = existing['id']
        if conflict_mode == 'reject':
            return jsonify({
                'error': f'模板名称已存在: {name}',
                'conflict': 'name_exists',
                'existing_id': existing_id
            }), 409
        elif conflict_mode == 'rename':
            suffix = 2
            while db.execute('SELECT id FROM plate_templates WHERE name = ?',
                             (f'{name}_{suffix}',)).fetchone():
                suffix += 1
            name = f'{name}_{suffix}'
        elif conflict_mode == 'overwrite':
            db.execute('DELETE FROM template_wells WHERE template_id = ?', (existing_id,))
            for well in template_data.get('wells', []):
                db.execute('''
                    INSERT INTO template_wells
                    (template_id, well_row, well_col, well_type, sample_name, note)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (
                    existing_id,
                    well['well_row'],
                    well['well_col'],
                    well.get('well_type', 'sample'),
                    well.get('sample_name'),
                    well.get('note', '')
                ))
            db.execute('''
                UPDATE plate_templates SET rows = ?, cols = ?, description = ? WHERE id = ?
            ''', (template_data['rows'], template_data['cols'], description, existing_id))
            db.commit()

            _add_template_history(db, 'import', 'template_imported',
                                  f'覆盖导入模板: {name}', template_id=existing_id)
            db.commit()

            template = db.execute('SELECT * FROM plate_templates WHERE id = ?', (existing_id,)).fetchone()
            wells = db.execute(
                'SELECT * FROM template_wells WHERE template_id = ? ORDER BY well_row, well_col',
                (existing_id,)
            ).fetchall()

            result = dict(template)
            result['wells'] = [dict(w) for w in wells]
            result['overwritten'] = True

            return jsonify(result), 200
        else:
            return jsonify({'error': f'无效的冲突处理模式: {conflict_mode}'}), 400

    try:
        cursor = db.execute('''
            INSERT INTO plate_templates (name, rows, cols, description)
            VALUES (?, ?, ?, ?)
        ''', (name, template_data['rows'], template_data['cols'], description))
        template_id = cursor.lastrowid

        for well in template_data.get('wells', []):
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

        _add_template_history(db, 'import', 'template_imported',
                              f'导入模板: {name}', template_id=template_id)
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
        db.rollback()
        return jsonify({'error': str(e)}), 400


@template_bp.route('/<int:template_id>', methods=['DELETE'])
def delete_template(template_id):
    from app.database import get_db
    db = get_db(current_app)

    template = db.execute('SELECT * FROM plate_templates WHERE id = ?', (template_id,)).fetchone()
    if not template:
        return jsonify({'error': '模板不存在'}), 404

    referencing_tasks = db.execute(
        'SELECT id, name, status FROM tasks WHERE template_id = ?', (template_id,)
    ).fetchall()

    if referencing_tasks:
        task_list = [{'id': t['id'], 'name': t['name'], 'status': t['status']}
                     for t in referencing_tasks]
        return jsonify({
            'error': '该模板已被任务引用，无法删除',
            'reason': 'template_in_use',
            'referencing_tasks': task_list,
            'task_count': len(referencing_tasks)
        }), 409

    template_name = template['name']
    well_count = db.execute(
        'SELECT COUNT(*) as cnt FROM template_wells WHERE template_id = ?', (template_id,)
    ).fetchone()['cnt']

    db.execute('DELETE FROM template_wells WHERE template_id = ?', (template_id,))
    db.execute('DELETE FROM plate_templates WHERE id = ?', (template_id,))
    db.commit()

    _add_template_history(db, 'delete', 'template_deleted',
                          f'删除模板: {template_name} ({well_count} 孔位)')
    db.commit()

    return jsonify({'message': '删除成功', 'name': template_name})
