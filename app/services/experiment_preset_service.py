import json
import csv
import io
from datetime import datetime


class ExperimentPresetService:

    def __init__(self, db):
        self.db = db

    def _log_history(self, preset_id, action, action_type, detail=None,
                     operator='system', snapshot=None):
        self.db.execute('''
            INSERT INTO experiment_preset_history
            (preset_id, action, action_type, detail, operator, snapshot)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            preset_id,
            action,
            action_type,
            detail,
            operator,
            json.dumps(snapshot, ensure_ascii=False) if snapshot and not isinstance(snapshot, str) else (snapshot or None),
        ))
        self.db.commit()

    def _preset_snapshot(self, preset_row):
        if not preset_row:
            return None
        d = dict(preset_row)
        return d

    def _get_preset(self, preset_id):
        row = self.db.execute(
            'SELECT * FROM experiment_presets WHERE id = ?', (preset_id,)
        ).fetchone()
        return dict(row) if row else None

    def _check_name_conflict(self, name, exclude_id=None):
        q = 'SELECT id FROM experiment_presets WHERE name = ?'
        params = [name]
        if exclude_id:
            q += ' AND id != ?'
            params.append(exclude_id)
        return self.db.execute(q, params).fetchone()

    def validate_dependencies(self, preset_id):
        preset = self._get_preset(preset_id)
        if not preset:
            return {'valid': False, 'missing': [], 'error': '预设不存在'}

        missing = []

        if preset.get('template_id'):
            t = self.db.execute(
                'SELECT id, name FROM plate_templates WHERE id = ?',
                (preset['template_id'],)
            ).fetchone()
            if not t:
                missing.append({
                    'type': 'template',
                    'id': preset['template_id'],
                    'field': 'template_id',
                    'message': f'板位模板 #{preset["template_id"]} 已被删除',
                })

        if preset.get('primer_id'):
            p = self.db.execute(
                'SELECT id, name FROM primers WHERE id = ?',
                (preset['primer_id'],)
            ).fetchone()
            if not p:
                missing.append({
                    'type': 'primer',
                    'id': preset['primer_id'],
                    'field': 'primer_id',
                    'message': f'引物 #{preset["primer_id"]} 已被删除',
                })

        if preset.get('master_mix_id'):
            r = self.db.execute(
                'SELECT id, name, type FROM reagents WHERE id = ?',
                (preset['master_mix_id'],)
            ).fetchone()
            if not r:
                missing.append({
                    'type': 'reagent',
                    'id': preset['master_mix_id'],
                    'field': 'master_mix_id',
                    'message': f'Master Mix 试剂 #{preset["master_mix_id"]} 已被删除',
                })

        if preset.get('water_id'):
            r = self.db.execute(
                'SELECT id, name, type FROM reagents WHERE id = ?',
                (preset['water_id'],)
            ).fetchone()
            if not r:
                missing.append({
                    'type': 'reagent',
                    'id': preset['water_id'],
                    'field': 'water_id',
                    'message': f'水试剂 #{preset["water_id"]} 已被删除',
                })

        return {'valid': len(missing) == 0, 'missing': missing}

    def create_preset(self, name, description=None, template_id=None,
                      total_volume=None, volume_unit='ul', primer_id=None,
                      master_mix_id=None, water_id=None,
                      deviation_note_template=None, operator='system'):
        if not name or not name.strip():
            raise ValueError('预设名称不能为空')

        existing = self._check_name_conflict(name)
        if existing:
            raise ValueError(f'预设名称已存在: {name}', 'name_conflict')

        cursor = self.db.execute('''
            INSERT INTO experiment_presets
            (name, description, template_id, total_volume, volume_unit,
             primer_id, master_mix_id, water_id, deviation_note_template,
             is_enabled, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
        ''', (
            name.strip(),
            description,
            template_id,
            total_volume,
            volume_unit or 'ul',
            primer_id,
            master_mix_id,
            water_id,
            deviation_note_template,
            datetime.now().isoformat(),
        ))
        preset_id = cursor.lastrowid
        self.db.commit()

        preset = self._get_preset(preset_id)
        self._log_history(
            preset_id, 'create', 'preset_created',
            detail=f'创建预设: {name}',
            operator=operator,
            snapshot=preset,
        )

        return preset

    def update_preset(self, preset_id, name=None, description=None,
                      template_id=None, total_volume=None, volume_unit=None,
                      primer_id=None, master_mix_id=None, water_id=None,
                      deviation_note_template=None, operator='system'):
        preset = self._get_preset(preset_id)
        if not preset:
            raise ValueError('预设不存在')

        new_name = (name or preset['name']).strip()
        if not new_name:
            raise ValueError('预设名称不能为空')

        existing = self._check_name_conflict(new_name, exclude_id=preset_id)
        if existing:
            raise ValueError(f'预设名称已存在: {new_name}', 'name_conflict')

        changes = {}
        fields = {
            'name': new_name,
            'description': description if description is not None else preset['description'],
            'template_id': template_id if template_id is not None else preset['template_id'],
            'total_volume': total_volume if total_volume is not None else preset['total_volume'],
            'volume_unit': volume_unit if volume_unit is not None else preset['volume_unit'],
            'primer_id': primer_id if primer_id is not None else preset['primer_id'],
            'master_mix_id': master_mix_id if master_mix_id is not None else preset['master_mix_id'],
            'water_id': water_id if water_id is not None else preset['water_id'],
            'deviation_note_template': deviation_note_template if deviation_note_template is not None else preset['deviation_note_template'],
        }

        for key, new_val in fields.items():
            old_val = preset.get(key)
            if new_val != old_val:
                changes[key] = {'old': old_val, 'new': new_val}

        if not changes:
            return preset

        self.db.execute('''
            UPDATE experiment_presets SET
                name = ?, description = ?, template_id = ?,
                total_volume = ?, volume_unit = ?,
                primer_id = ?, master_mix_id = ?, water_id = ?,
                deviation_note_template = ?, updated_at = ?
            WHERE id = ?
        ''', (
            fields['name'], fields['description'], fields['template_id'],
            fields['total_volume'], fields['volume_unit'],
            fields['primer_id'], fields['master_mix_id'], fields['water_id'],
            fields['deviation_note_template'],
            datetime.now().isoformat(),
            preset_id,
        ))
        self.db.commit()

        updated = self._get_preset(preset_id)
        change_desc = '; '.join(
            f'{k}: {v["old"]} → {v["new"]}' for k, v in changes.items()
        )
        self._log_history(
            preset_id, 'update', 'preset_updated',
            detail=f'更新预设 {fields["name"]}: {change_desc}',
            operator=operator,
            snapshot=updated,
        )

        return updated

    def delete_preset(self, preset_id, operator='system'):
        preset = self._get_preset(preset_id)
        if not preset:
            raise ValueError('预设不存在')

        ref_count = self.db.execute(
            'SELECT COUNT(*) as cnt FROM task_preset_references WHERE preset_id = ?',
            (preset_id,)
        ).fetchone()['cnt']

        if ref_count > 0:
            raise ValueError(
                f'该预设已被 {ref_count} 个任务引用，无法删除。'
                '可停用预设以禁止新建任务引用，历史任务查看和导出不受影响。',
                'preset_referenced'
            )

        snapshot = dict(preset)
        self._log_history(
            preset_id, 'delete', 'preset_deleted',
            detail=f'删除预设: {preset["name"]}',
            operator=operator,
            snapshot=snapshot,
        )

        self.db.execute(
            'DELETE FROM experiment_presets WHERE id = ?', (preset_id,)
        )
        self.db.commit()

        return {'deleted': True, 'name': preset['name']}

    def get_preset(self, preset_id):
        preset = self._get_preset(preset_id)
        if not preset:
            return None

        dep_result = self.validate_dependencies(preset_id)
        preset['dependency_check'] = dep_result

        ref_count = self.db.execute(
            'SELECT COUNT(*) as cnt FROM task_preset_references WHERE preset_id = ?',
            (preset_id,)
        ).fetchone()['cnt']
        preset['task_reference_count'] = ref_count

        return preset

    def list_presets(self, is_enabled=None, keyword=None):
        query = 'SELECT * FROM experiment_presets WHERE 1=1'
        params = []

        if is_enabled is not None:
            query += ' AND is_enabled = ?'
            params.append(1 if is_enabled else 0)

        if keyword:
            kw = f'%{keyword}%'
            query += ' AND (name LIKE ? OR description LIKE ? OR deviation_note_template LIKE ?)'
            params.extend([kw, kw, kw])

        query += ' ORDER BY updated_at DESC'
        rows = self.db.execute(query, params).fetchall()
        presets = [dict(r) for r in rows]

        for p in presets:
            dep_result = self.validate_dependencies(p['id'])
            p['dependency_check'] = dep_result
            ref_count = self.db.execute(
                'SELECT COUNT(*) as cnt FROM task_preset_references WHERE preset_id = ?',
                (p['id'],)
            ).fetchone()['cnt']
            p['task_reference_count'] = ref_count

        return presets

    def copy_preset(self, preset_id, new_name=None, operator='system'):
        preset = self._get_preset(preset_id)
        if not preset:
            raise ValueError('预设不存在')

        name = new_name or f'{preset["name"]}_副本'
        existing = self._check_name_conflict(name)
        if existing:
            suffix = 2
            while self._check_name_conflict(f'{preset["name"]}_副本{suffix}'):
                suffix += 1
            name = f'{preset["name"]}_副本{suffix}'

        new_preset = self.create_preset(
            name=name,
            description=preset['description'],
            template_id=preset['template_id'],
            total_volume=preset['total_volume'],
            volume_unit=preset['volume_unit'],
            primer_id=preset['primer_id'],
            master_mix_id=preset['master_mix_id'],
            water_id=preset['water_id'],
            deviation_note_template=preset['deviation_note_template'],
            operator=operator,
        )

        self._log_history(
            new_preset['id'], 'copy', 'preset_copied',
            detail=f'从预设 #{preset_id} "{preset["name"]}" 复制为 "{name}"',
            operator=operator,
        )

        return new_preset

    def enable_preset(self, preset_id, operator='system'):
        preset = self._get_preset(preset_id)
        if not preset:
            raise ValueError('预设不存在')
        if preset['is_enabled']:
            return preset

        self.db.execute(
            'UPDATE experiment_presets SET is_enabled = 1, updated_at = ? WHERE id = ?',
            (datetime.now().isoformat(), preset_id)
        )
        self.db.commit()

        updated = self._get_preset(preset_id)
        self._log_history(
            preset_id, 'enable', 'preset_enabled',
            detail=f'启用预设: {preset["name"]}',
            operator=operator,
            snapshot=updated,
        )
        return updated

    def disable_preset(self, preset_id, operator='system'):
        preset = self._get_preset(preset_id)
        if not preset:
            raise ValueError('预设不存在')
        if not preset['is_enabled']:
            return preset

        self.db.execute(
            'UPDATE experiment_presets SET is_enabled = 0, updated_at = ? WHERE id = ?',
            (datetime.now().isoformat(), preset_id)
        )
        self.db.commit()

        updated = self._get_preset(preset_id)
        self._log_history(
            preset_id, 'disable', 'preset_disabled',
            detail=f'停用预设: {preset["name"]}',
            operator=operator,
            snapshot=updated,
        )
        return updated

    def apply_preset_to_task(self, preset_id, task_name=None, operator='system'):
        preset = self._get_preset(preset_id)
        if not preset:
            raise ValueError('预设不存在')

        if not preset['is_enabled']:
            raise ValueError(f'预设 "{preset["name"]}" 已停用，无法用于创建新任务')

        dep_result = self.validate_dependencies(preset_id)
        if not dep_result['valid']:
            missing_desc = '; '.join(
                m['message'] for m in dep_result['missing']
            )
            raise ValueError(
                f'预设依赖项缺失，无法创建任务: {missing_desc}',
                'dependency_missing'
            )

        from app.services.task_service import TaskService
        task_service = TaskService(self.db)

        if not task_name:
            task_name = f'{preset["name"]}_{datetime.now().strftime("%Y%m%d_%H%M%S")}'

        task_id = task_service.create_task(
            name=task_name,
            template_id=preset['template_id'],
            total_volume=preset['total_volume'] or 20,
            volume_unit=preset['volume_unit'] or 'ul',
        )

        if preset.get('deviation_note_template'):
            task_service.add_deviation_note(
                task_id, preset['deviation_note_template'], operator=operator,
            )

        preset_snapshot = dict(preset)
        self.db.execute('''
            INSERT INTO task_preset_references
            (task_id, preset_id, preset_name, preset_snapshot)
            VALUES (?, ?, ?, ?)
        ''', (
            task_id,
            preset_id,
            preset['name'],
            json.dumps(preset_snapshot, ensure_ascii=False),
        ))
        self.db.commit()

        self._log_history(
            preset_id, 'apply', 'preset_applied',
            detail=f'从预设 "{preset["name"]}" 创建任务 #{task_id} "{task_name}"',
            operator=operator,
        )

        return {
            'task_id': task_id,
            'preset_id': preset_id,
            'preset_name': preset['name'],
            'primer_id': preset.get('primer_id'),
            'master_mix_id': preset.get('master_mix_id'),
            'water_id': preset.get('water_id'),
        }

    def save_task_as_preset(self, task_id, preset_name, description=None,
                            operator='system'):
        task_row = self.db.execute(
            'SELECT * FROM tasks WHERE id = ?', (task_id,)
        ).fetchone()
        if not task_row:
            raise ValueError('任务不存在')

        task = dict(task_row)
        deviation_note = task.get('deviation_note_template') or task.get('deviation_note')

        preset = self.create_preset(
            name=preset_name,
            description=description or f'从任务 #{task_id} "{task["name"]}" 另存为预设',
            template_id=task['template_id'],
            total_volume=task['total_volume'],
            volume_unit=task['volume_unit'],
            deviation_note_template=deviation_note,
            operator=operator,
        )

        self.db.execute('''
            INSERT INTO task_preset_references
            (task_id, preset_id, preset_name, preset_snapshot)
            VALUES (?, ?, ?, ?)
        ''', (
            task_id,
            preset['id'],
            preset['name'],
            json.dumps(dict(preset), ensure_ascii=False),
        ))
        self.db.commit()

        self._log_history(
            preset['id'], 'save_from_task', 'preset_saved_from_task',
            detail=f'从任务 #{task_id} "{task["name"]}" 另存为预设 "{preset_name}"',
            operator=operator,
        )

        return preset

    def get_task_preset_reference(self, task_id):
        rows = self.db.execute(
            'SELECT * FROM task_preset_references WHERE task_id = ? ORDER BY created_at DESC',
            (task_id,)
        ).fetchall()
        refs = []
        for r in rows:
            ref = dict(r)
            if ref.get('preset_snapshot') and isinstance(ref['preset_snapshot'], str):
                try:
                    ref['preset_snapshot'] = json.loads(ref['preset_snapshot'])
                except (json.JSONDecodeError, TypeError):
                    pass
            refs.append(ref)
        return refs

    def get_preset_referenced_tasks(self, preset_id):
        rows = self.db.execute('''
            SELECT tpr.*, t.name AS task_name, t.status AS task_status
            FROM task_preset_references tpr
            LEFT JOIN tasks t ON t.id = tpr.task_id
            WHERE tpr.preset_id = ?
            ORDER BY tpr.created_at DESC
        ''', (preset_id,)).fetchall()
        return [dict(r) for r in rows]

    def get_preset_history(self, preset_id, limit=200):
        rows = self.db.execute('''
            SELECT * FROM experiment_preset_history
            WHERE preset_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT ?
        ''', (preset_id, int(limit))).fetchall()
        records = []
        for r in rows:
            rec = dict(r)
            if rec.get('snapshot') and isinstance(rec['snapshot'], str):
                try:
                    rec['snapshot'] = json.loads(rec['snapshot'])
                except (json.JSONDecodeError, TypeError):
                    pass
            records.append(rec)
        return records

    def _resolve_import_conflict(self, name, conflict_mode):
        existing = self._check_name_conflict(name)
        if not existing:
            return name, None, None

        if conflict_mode == 'reject':
            return None, 'name_conflict', existing['id']
        elif conflict_mode == 'rename':
            suffix = 2
            while self._check_name_conflict(f'{name}_{suffix}'):
                suffix += 1
            return f'{name}_{suffix}', 'renamed', existing['id']
        elif conflict_mode == 'overwrite':
            return name, 'overwrite', existing['id']
        else:
            return None, 'invalid_conflict_mode', None

    def import_presets_json(self, json_content, conflict_mode='reject',
                            operator='system'):
        try:
            data = json.loads(json_content)
        except json.JSONDecodeError as e:
            raise ValueError(f'JSON 解析失败: {str(e)}')

        presets_data = data if isinstance(data, list) else data.get('presets', [data])

        imported = 0
        skipped = 0
        renamed = 0
        overwritten = 0
        errors = []

        for preset_data in presets_data:
            try:
                name = preset_data.get('name', '').strip()
                if not name:
                    errors.append('缺少预设名称，跳过')
                    skipped += 1
                    continue

                resolved_name, action, existing_id = self._resolve_import_conflict(
                    name, conflict_mode
                )

                if action == 'name_conflict':
                    errors.append(f'预设名称已存在: {name}，已跳过')
                    skipped += 1
                    continue
                elif action == 'invalid_conflict_mode':
                    errors.append(f'无效的冲突处理模式: {conflict_mode}')
                    skipped += 1
                    continue

                if action == 'overwrite' and existing_id:
                    self.update_preset(
                        existing_id,
                        name=resolved_name,
                        description=preset_data.get('description'),
                        template_id=preset_data.get('template_id'),
                        total_volume=preset_data.get('total_volume'),
                        volume_unit=preset_data.get('volume_unit', 'ul'),
                        primer_id=preset_data.get('primer_id'),
                        master_mix_id=preset_data.get('master_mix_id'),
                        water_id=preset_data.get('water_id'),
                        deviation_note_template=preset_data.get('deviation_note_template'),
                        operator=operator,
                    )
                    overwritten += 1
                    self._log_history(
                        existing_id, 'import', 'preset_imported_overwrite',
                        detail=f'覆盖导入预设: {resolved_name}',
                        operator=operator,
                    )
                elif action == 'renamed':
                    self.create_preset(
                        name=resolved_name,
                        description=preset_data.get('description'),
                        template_id=preset_data.get('template_id'),
                        total_volume=preset_data.get('total_volume'),
                        volume_unit=preset_data.get('volume_unit', 'ul'),
                        primer_id=preset_data.get('primer_id'),
                        master_mix_id=preset_data.get('master_mix_id'),
                        water_id=preset_data.get('water_id'),
                        deviation_note_template=preset_data.get('deviation_note_template'),
                        operator=operator,
                    )
                    renamed += 1
                else:
                    self.create_preset(
                        name=resolved_name,
                        description=preset_data.get('description'),
                        template_id=preset_data.get('template_id'),
                        total_volume=preset_data.get('total_volume'),
                        volume_unit=preset_data.get('volume_unit', 'ul'),
                        primer_id=preset_data.get('primer_id'),
                        master_mix_id=preset_data.get('master_mix_id'),
                        water_id=preset_data.get('water_id'),
                        deviation_note_template=preset_data.get('deviation_note_template'),
                        operator=operator,
                    )
                    imported += 1

            except Exception as e:
                errors.append(f'导入预设 {preset_data.get("name", "?")}: {str(e)}')
                skipped += 1

        return {
            'imported': imported,
            'renamed': renamed,
            'overwritten': overwritten,
            'skipped': skipped,
            'errors': errors,
            'total': len(presets_data),
        }

    def import_presets_csv(self, csv_content, conflict_mode='reject',
                           operator='system'):
        try:
            reader = csv.DictReader(io.StringIO(csv_content))
            presets_data = []
            for row in reader:
                preset = {
                    'name': row.get('name', '').strip(),
                    'description': row.get('description', '').strip() or None,
                    'template_id': int(row['template_id']) if row.get('template_id') and row['template_id'].strip() else None,
                    'total_volume': float(row['total_volume']) if row.get('total_volume') and row['total_volume'].strip() else None,
                    'volume_unit': row.get('volume_unit', 'ul').strip() or 'ul',
                    'primer_id': int(row['primer_id']) if row.get('primer_id') and row['primer_id'].strip() else None,
                    'master_mix_id': int(row['master_mix_id']) if row.get('master_mix_id') and row['master_mix_id'].strip() else None,
                    'water_id': int(row['water_id']) if row.get('water_id') and row['water_id'].strip() else None,
                    'deviation_note_template': row.get('deviation_note_template', '').strip() or None,
                }
                presets_data.append(preset)
        except Exception as e:
            raise ValueError(f'CSV 解析失败: {str(e)}')

        return self.import_presets_json(
            json.dumps(presets_data, ensure_ascii=False),
            conflict_mode=conflict_mode,
            operator=operator,
        )

    def export_presets_json(self, preset_ids=None, is_enabled=None):
        if preset_ids:
            placeholders = ','.join('?' * len(preset_ids))
            rows = self.db.execute(
                f'SELECT * FROM experiment_presets WHERE id IN ({placeholders}) ORDER BY name',
                [int(pid) for pid in preset_ids]
            ).fetchall()
        else:
            query = 'SELECT * FROM experiment_presets WHERE 1=1'
            params = []
            if is_enabled is not None:
                query += ' AND is_enabled = ?'
                params.append(1 if is_enabled else 0)
            query += ' ORDER BY name'
            rows = self.db.execute(query, params).fetchall()

        presets = []
        for r in rows:
            d = dict(r)
            presets.append(d)

        export_data = {
            'export_time': datetime.now().isoformat(),
            'export_format': 'experiment_presets',
            'preset_count': len(presets),
            'presets': presets,
        }
        return json.dumps(export_data, ensure_ascii=False, indent=2)

    def export_presets_csv(self, preset_ids=None, is_enabled=None):
        if preset_ids:
            placeholders = ','.join('?' * len(preset_ids))
            rows = self.db.execute(
                f'SELECT * FROM experiment_presets WHERE id IN ({placeholders}) ORDER BY name',
                [int(pid) for pid in preset_ids]
            ).fetchall()
        else:
            query = 'SELECT * FROM experiment_presets WHERE 1=1'
            params = []
            if is_enabled is not None:
                query += ' AND is_enabled = ?'
                params.append(1 if is_enabled else 0)
            query += ' ORDER BY name'
            rows = self.db.execute(query, params).fetchall()

        output = io.StringIO()
        fieldnames = [
            'id', 'name', 'description', 'template_id', 'total_volume',
            'volume_unit', 'primer_id', 'master_mix_id', 'water_id',
            'deviation_note_template', 'is_enabled', 'created_at', 'updated_at',
        ]
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow({k: r[k] if k in r.keys() else '' for k in fieldnames})

        return output.getvalue()
