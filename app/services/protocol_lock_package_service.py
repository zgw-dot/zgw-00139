import json
import csv
import io
from datetime import datetime


class ProtocolLockPackageService:

    def __init__(self, db):
        self.db = db

    def _log_history(self, package_id, action, action_type, detail=None,
                     operator='system', snapshot=None):
        self.db.execute('''
            INSERT INTO lock_package_history
            (package_id, action, action_type, detail, operator, snapshot)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            package_id,
            action,
            action_type,
            detail,
            operator,
            json.dumps(snapshot, ensure_ascii=False) if snapshot and not isinstance(snapshot, str) else (snapshot or None),
        ))
        self.db.commit()

    def _package_snapshot(self, row):
        if not row:
            return None
        d = dict(row)
        return d

    def _get_package(self, package_id):
        row = self.db.execute(
            'SELECT * FROM protocol_lock_packages WHERE id = ?', (package_id,)
        ).fetchone()
        return dict(row) if row else None

    def _check_name_conflict(self, name, exclude_id=None):
        q = 'SELECT id FROM protocol_lock_packages WHERE name = ?'
        params = [name]
        if exclude_id:
            q += ' AND id != ?'
            params.append(exclude_id)
        return self.db.execute(q, params).fetchone()

    def validate_dependencies(self, package_id):
        pkg = self._get_package(package_id)
        if not pkg:
            return {'valid': False, 'missing': [], 'disabled': [], 'error': '锁定包不存在'}

        missing = []
        disabled = []

        if pkg.get('template_id'):
            t = self.db.execute(
                'SELECT id, name FROM plate_templates WHERE id = ?',
                (pkg['template_id'],)
            ).fetchone()
            if not t:
                missing.append({
                    'type': 'template',
                    'id': pkg['template_id'],
                    'name': pkg.get('template_name', ''),
                    'field': 'template_id',
                    'message': f'板位模板 #{pkg["template_id"]} ({pkg.get("template_name", "")}) 已被删除',
                })

        if pkg.get('primer_id'):
            p = self.db.execute(
                'SELECT id, name FROM primers WHERE id = ?',
                (pkg['primer_id'],)
            ).fetchone()
            if not p:
                missing.append({
                    'type': 'primer',
                    'id': pkg['primer_id'],
                    'name': pkg.get('primer_name', ''),
                    'field': 'primer_id',
                    'message': f'引物 #{pkg["primer_id"]} ({pkg.get("primer_name", "")}) 已被删除',
                })

        if pkg.get('master_mix_id'):
            r = self.db.execute(
                'SELECT id, name, type FROM reagents WHERE id = ?',
                (pkg['master_mix_id'],)
            ).fetchone()
            if not r:
                missing.append({
                    'type': 'reagent',
                    'id': pkg['master_mix_id'],
                    'name': pkg.get('master_mix_name', ''),
                    'field': 'master_mix_id',
                    'message': f'Master Mix #{pkg["master_mix_id"]} ({pkg.get("master_mix_name", "")}) 已被删除',
                })

        if pkg.get('water_id'):
            r = self.db.execute(
                'SELECT id, name, type FROM reagents WHERE id = ?',
                (pkg['water_id'],)
            ).fetchone()
            if not r:
                missing.append({
                    'type': 'reagent',
                    'id': pkg['water_id'],
                    'name': pkg.get('water_name', ''),
                    'field': 'water_id',
                    'message': f'水试剂 #{pkg["water_id"]} ({pkg.get("water_name", "")}) 已被删除',
                })

        return {'valid': len(missing) == 0 and len(disabled) == 0, 'missing': missing, 'disabled': disabled}

    def create_from_task(self, task_id, name, description=None, operator='system'):
        if not name or not name.strip():
            raise ValueError('锁定包名称不能为空')

        task_row = self.db.execute(
            'SELECT * FROM tasks WHERE id = ?', (task_id,)
        ).fetchone()
        if not task_row:
            raise ValueError('任务不存在')

        task = dict(task_row)

        existing = self._check_name_conflict(name.strip())
        if existing:
            raise ValueError(f'锁定包名称已存在: {name}', 'name_conflict')

        template = None
        template_name = None
        template_rows = None
        template_cols = None
        if task['template_id']:
            t = self.db.execute(
                'SELECT * FROM plate_templates WHERE id = ?', (task['template_id'],)
            ).fetchone()
            if t:
                template = dict(t)
                template_name = t['name']
                template_rows = t['rows']
                template_cols = t['cols']

        primer_id = None
        primer_name = None
        primer_usage = self.db.execute(
            'SELECT * FROM task_primer_usage WHERE task_id = ?', (task_id,)
        ).fetchall()
        if primer_usage:
            primer_id = primer_usage[0]['primer_id']
            primer_name = primer_usage[0]['primer_name']

        master_mix_id = None
        master_mix_name = None
        water_id = None
        water_name = None
        reagent_usage = self.db.execute(
            'SELECT * FROM task_reagent_usage WHERE task_id = ?', (task_id,)
        ).fetchall()
        for ru in reagent_usage:
            if ru['source'] == 'master_mix':
                master_mix_id = ru['reagent_id']
                master_mix_name = ru['reagent_name']
            elif ru['source'] == 'water':
                water_id = ru['reagent_id']
                water_name = ru['reagent_name']

        frozen_params = {
            'template_id': task['template_id'],
            'template_name': template_name,
            'total_volume': task['total_volume'],
            'volume_unit': task['volume_unit'],
            'primer_id': primer_id,
            'primer_name': primer_name,
            'master_mix_id': master_mix_id,
            'master_mix_name': master_mix_name,
            'water_id': water_id,
            'water_name': water_name,
            'deviation_note': task.get('deviation_note'),
        }

        cursor = self.db.execute('''
            INSERT INTO protocol_lock_packages
            (name, description, template_id, template_name, template_rows, template_cols,
             total_volume, volume_unit, primer_id, primer_name,
             master_mix_id, master_mix_name, water_id, water_name,
             deviation_note, frozen_params,
             source_task_id, source_task_name, source_task_status,
             is_enabled, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
        ''', (
            name.strip(),
            description or f'从任务 #{task_id} "{task["name"]}" 生成锁定包',
            task['template_id'],
            template_name,
            template_rows,
            template_cols,
            task['total_volume'],
            task['volume_unit'],
            primer_id,
            primer_name,
            master_mix_id,
            master_mix_name,
            water_id,
            water_name,
            task.get('deviation_note'),
            json.dumps(frozen_params, ensure_ascii=False),
            task_id,
            task['name'],
            task['status'],
            datetime.now().isoformat(),
        ))
        package_id = cursor.lastrowid
        self.db.commit()

        pkg = self._get_package(package_id)
        self._log_history(
            package_id, 'create_from_task', 'package_created',
            detail=f'从任务 #{task_id} "{task["name"]}" 生成锁定包: {name}',
            operator=operator,
            snapshot=pkg,
        )

        return pkg

    def create_manual(self, name, description=None, template_id=None,
                      total_volume=None, volume_unit='ul',
                      primer_id=None, master_mix_id=None, water_id=None,
                      deviation_note=None, operator='system'):
        if not name or not name.strip():
            raise ValueError('锁定包名称不能为空')

        existing = self._check_name_conflict(name.strip())
        if existing:
            raise ValueError(f'锁定包名称已存在: {name}', 'name_conflict')

        template_name = None
        template_rows = None
        template_cols = None
        if template_id:
            t = self.db.execute(
                'SELECT * FROM plate_templates WHERE id = ?', (template_id,)
            ).fetchone()
            if t:
                template_name = t['name']
                template_rows = t['rows']
                template_cols = t['cols']

        primer_name = None
        if primer_id:
            p = self.db.execute(
                'SELECT name FROM primers WHERE id = ?', (primer_id,)
            ).fetchone()
            if p:
                primer_name = p['name']

        master_mix_name = None
        if master_mix_id:
            r = self.db.execute(
                'SELECT name FROM reagents WHERE id = ?', (master_mix_id,)
            ).fetchone()
            if r:
                master_mix_name = r['name']

        water_name = None
        if water_id:
            r = self.db.execute(
                'SELECT name FROM reagents WHERE id = ?', (water_id,)
            ).fetchone()
            if r:
                water_name = r['name']

        frozen_params = {
            'template_id': template_id,
            'template_name': template_name,
            'total_volume': total_volume,
            'volume_unit': volume_unit or 'ul',
            'primer_id': primer_id,
            'primer_name': primer_name,
            'master_mix_id': master_mix_id,
            'master_mix_name': master_mix_name,
            'water_id': water_id,
            'water_name': water_name,
            'deviation_note': deviation_note,
        }

        cursor = self.db.execute('''
            INSERT INTO protocol_lock_packages
            (name, description, template_id, template_name, template_rows, template_cols,
             total_volume, volume_unit, primer_id, primer_name,
             master_mix_id, master_mix_name, water_id, water_name,
             deviation_note, frozen_params,
             is_enabled, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
        ''', (
            name.strip(),
            description,
            template_id,
            template_name,
            template_rows,
            template_cols,
            total_volume,
            volume_unit or 'ul',
            primer_id,
            primer_name,
            master_mix_id,
            master_mix_name,
            water_id,
            water_name,
            deviation_note,
            json.dumps(frozen_params, ensure_ascii=False),
            datetime.now().isoformat(),
        ))
        package_id = cursor.lastrowid
        self.db.commit()

        pkg = self._get_package(package_id)
        self._log_history(
            package_id, 'create', 'package_created',
            detail=f'手动创建锁定包: {name}',
            operator=operator,
            snapshot=pkg,
        )

        return pkg

    def update_package(self, package_id, name=None, description=None,
                       template_id=None, total_volume=None, volume_unit=None,
                       primer_id=None, master_mix_id=None, water_id=None,
                       deviation_note=None, operator='system'):
        pkg = self._get_package(package_id)
        if not pkg:
            raise ValueError('锁定包不存在')

        new_name = (name or pkg['name']).strip()
        if not new_name:
            raise ValueError('锁定包名称不能为空')

        existing = self._check_name_conflict(new_name, exclude_id=package_id)
        if existing:
            raise ValueError(f'锁定包名称已存在: {new_name}', 'name_conflict')

        new_template_id = template_id if template_id is not None else pkg['template_id']
        new_total_volume = total_volume if total_volume is not None else pkg['total_volume']
        new_volume_unit = volume_unit if volume_unit is not None else pkg['volume_unit']
        new_primer_id = primer_id if primer_id is not None else pkg['primer_id']
        new_master_mix_id = master_mix_id if master_mix_id is not None else pkg['master_mix_id']
        new_water_id = water_id if water_id is not None else pkg['water_id']
        new_deviation_note = deviation_note if deviation_note is not None else pkg['deviation_note']
        new_description = description if description is not None else pkg['description']

        template_name = pkg.get('template_name')
        template_rows = pkg.get('template_rows')
        template_cols = pkg.get('template_cols')
        if new_template_id != pkg.get('template_id'):
            t = self.db.execute(
                'SELECT * FROM plate_templates WHERE id = ?', (new_template_id,)
            ).fetchone()
            if t:
                template_name = t['name']
                template_rows = t['rows']
                template_cols = t['cols']
            else:
                template_name = None
                template_rows = None
                template_cols = None

        primer_name = pkg.get('primer_name')
        if new_primer_id != pkg.get('primer_id'):
            p = self.db.execute('SELECT name FROM primers WHERE id = ?', (new_primer_id,)).fetchone()
            primer_name = p['name'] if p else None

        master_mix_name = pkg.get('master_mix_name')
        if new_master_mix_id != pkg.get('master_mix_id'):
            r = self.db.execute('SELECT name FROM reagents WHERE id = ?', (new_master_mix_id,)).fetchone()
            master_mix_name = r['name'] if r else None

        water_name = pkg.get('water_name')
        if new_water_id != pkg.get('water_id'):
            r = self.db.execute('SELECT name FROM reagents WHERE id = ?', (new_water_id,)).fetchone()
            water_name = r['name'] if r else None

        new_frozen_params = {
            'template_id': new_template_id,
            'template_name': template_name,
            'total_volume': new_total_volume,
            'volume_unit': new_volume_unit,
            'primer_id': new_primer_id,
            'primer_name': primer_name,
            'master_mix_id': new_master_mix_id,
            'master_mix_name': master_mix_name,
            'water_id': new_water_id,
            'water_name': water_name,
            'deviation_note': new_deviation_note,
        }

        self.db.execute('''
            UPDATE protocol_lock_packages SET
                name = ?, description = ?,
                template_id = ?, template_name = ?, template_rows = ?, template_cols = ?,
                total_volume = ?, volume_unit = ?,
                primer_id = ?, primer_name = ?,
                master_mix_id = ?, master_mix_name = ?,
                water_id = ?, water_name = ?,
                deviation_note = ?, frozen_params = ?,
                updated_at = ?
            WHERE id = ?
        ''', (
            new_name, new_description,
            new_template_id, template_name, template_rows, template_cols,
            new_total_volume, new_volume_unit,
            new_primer_id, primer_name,
            new_master_mix_id, master_mix_name,
            new_water_id, water_name,
            new_deviation_note, json.dumps(new_frozen_params, ensure_ascii=False),
            datetime.now().isoformat(),
            package_id,
        ))
        self.db.commit()

        updated = self._get_package(package_id)
        self._log_history(
            package_id, 'update', 'package_updated',
            detail=f'更新锁定包: {new_name}',
            operator=operator,
            snapshot=updated,
        )

        return updated

    def delete_package(self, package_id, operator='system'):
        pkg = self._get_package(package_id)
        if not pkg:
            raise ValueError('锁定包不存在')

        ref_count = self.db.execute(
            'SELECT COUNT(*) as cnt FROM lock_package_task_references WHERE package_id = ?',
            (package_id,)
        ).fetchone()['cnt']

        if ref_count > 0:
            raise ValueError(
                f'该锁定包已被 {ref_count} 个任务引用，无法删除。'
                '可停用锁定包以禁止新建任务引用，历史任务查看和导出不受影响。',
                'package_referenced'
            )

        snapshot = dict(pkg)
        self._log_history(
            package_id, 'delete', 'package_deleted',
            detail=f'删除锁定包: {pkg["name"]}',
            operator=operator,
            snapshot=snapshot,
        )

        self.db.execute(
            'DELETE FROM protocol_lock_packages WHERE id = ?', (package_id,)
        )
        self.db.commit()

        return {'deleted': True, 'name': pkg['name']}

    def get_package(self, package_id):
        pkg = self._get_package(package_id)
        if not pkg:
            return None

        dep_result = self.validate_dependencies(package_id)
        pkg['dependency_check'] = dep_result

        ref_count = self.db.execute(
            'SELECT COUNT(*) as cnt FROM lock_package_task_references WHERE package_id = ?',
            (package_id,)
        ).fetchone()['cnt']
        pkg['task_reference_count'] = ref_count

        if pkg.get('frozen_params') and isinstance(pkg['frozen_params'], str):
            try:
                pkg['frozen_params'] = json.loads(pkg['frozen_params'])
            except (json.JSONDecodeError, TypeError):
                pass

        return pkg

    def list_packages(self, is_enabled=None, keyword=None):
        query = 'SELECT * FROM protocol_lock_packages WHERE 1=1'
        params = []

        if is_enabled is not None:
            query += ' AND is_enabled = ?'
            params.append(1 if is_enabled else 0)

        if keyword:
            kw = f'%{keyword}%'
            query += ' AND (name LIKE ? OR description LIKE ? OR deviation_note LIKE ?)'
            params.extend([kw, kw, kw])

        query += ' ORDER BY updated_at DESC'
        rows = self.db.execute(query, params).fetchall()
        packages = [dict(r) for r in rows]

        for p in packages:
            dep_result = self.validate_dependencies(p['id'])
            p['dependency_check'] = dep_result
            ref_count = self.db.execute(
                'SELECT COUNT(*) as cnt FROM lock_package_task_references WHERE package_id = ?',
                (p['id'],)
            ).fetchone()['cnt']
            p['task_reference_count'] = ref_count

            if p.get('frozen_params') and isinstance(p['frozen_params'], str):
                try:
                    p['frozen_params'] = json.loads(p['frozen_params'])
                except (json.JSONDecodeError, TypeError):
                    pass

        return packages

    def copy_package(self, package_id, new_name=None, operator='system'):
        pkg = self._get_package(package_id)
        if not pkg:
            raise ValueError('锁定包不存在')

        name = new_name or f'{pkg["name"]}_副本'
        existing = self._check_name_conflict(name)
        if existing:
            suffix = 2
            while self._check_name_conflict(f'{pkg["name"]}_副本{suffix}'):
                suffix += 1
            name = f'{pkg["name"]}_副本{suffix}'

        frozen_params = pkg.get('frozen_params', '{}')
        if isinstance(frozen_params, dict):
            frozen_params = json.dumps(frozen_params, ensure_ascii=False)

        cursor = self.db.execute('''
            INSERT INTO protocol_lock_packages
            (name, description, template_id, template_name, template_rows, template_cols,
             total_volume, volume_unit, primer_id, primer_name,
             master_mix_id, master_mix_name, water_id, water_name,
             deviation_note, frozen_params,
             source_task_id, source_task_name, source_task_status,
             is_enabled, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
        ''', (
            name,
            pkg['description'],
            pkg['template_id'],
            pkg['template_name'],
            pkg['template_rows'],
            pkg['template_cols'],
            pkg['total_volume'],
            pkg['volume_unit'],
            pkg['primer_id'],
            pkg['primer_name'],
            pkg['master_mix_id'],
            pkg['master_mix_name'],
            pkg['water_id'],
            pkg['water_name'],
            pkg['deviation_note'],
            frozen_params,
            pkg.get('source_task_id'),
            pkg.get('source_task_name'),
            pkg.get('source_task_status'),
            datetime.now().isoformat(),
        ))
        new_id = cursor.lastrowid
        self.db.commit()

        new_pkg = self._get_package(new_id)
        self._log_history(
            new_id, 'copy', 'package_copied',
            detail=f'从锁定包 #{package_id} "{pkg["name"]}" 复制为 "{name}"',
            operator=operator,
        )

        return new_pkg

    def enable_package(self, package_id, operator='system'):
        pkg = self._get_package(package_id)
        if not pkg:
            raise ValueError('锁定包不存在')
        if pkg['is_enabled']:
            return pkg

        self.db.execute(
            'UPDATE protocol_lock_packages SET is_enabled = 1, updated_at = ? WHERE id = ?',
            (datetime.now().isoformat(), package_id)
        )
        self.db.commit()

        updated = self._get_package(package_id)
        self._log_history(
            package_id, 'enable', 'package_enabled',
            detail=f'启用锁定包: {pkg["name"]}',
            operator=operator,
            snapshot=updated,
        )
        return updated

    def disable_package(self, package_id, operator='system'):
        pkg = self._get_package(package_id)
        if not pkg:
            raise ValueError('锁定包不存在')
        if not pkg['is_enabled']:
            return pkg

        self.db.execute(
            'UPDATE protocol_lock_packages SET is_enabled = 0, updated_at = ? WHERE id = ?',
            (datetime.now().isoformat(), package_id)
        )
        self.db.commit()

        updated = self._get_package(package_id)
        self._log_history(
            package_id, 'disable', 'package_disabled',
            detail=f'停用锁定包: {pkg["name"]}',
            operator=operator,
            snapshot=updated,
        )
        return updated

    def apply_package_to_task(self, package_id, task_name=None, operator='system'):
        pkg = self._get_package(package_id)
        if not pkg:
            raise ValueError('锁定包不存在')

        if not pkg['is_enabled']:
            raise ValueError(
                f'锁定包 "{pkg["name"]}" 已停用，无法用于创建新任务',
                'package_disabled'
            )

        dep_result = self.validate_dependencies(package_id)
        if not dep_result['valid']:
            all_issues = dep_result.get('missing', []) + dep_result.get('disabled', [])
            desc = '; '.join(m['message'] for m in all_issues)
            raise ValueError(
                f'锁定包依赖项缺失或已停用，无法创建任务: {desc}',
                'dependency_missing'
            )

        from app.services.task_service import TaskService
        task_service = TaskService(self.db)

        if not task_name:
            task_name = f'{pkg["name"]}_{datetime.now().strftime("%Y%m%d_%H%M%S")}'

        template_id = pkg['template_id']
        total_volume = pkg['total_volume'] or 20
        volume_unit = pkg['volume_unit'] or 'ul'

        task_id = task_service.create_task(
            name=task_name,
            template_id=template_id,
            total_volume=total_volume,
            volume_unit=volume_unit,
        )

        if pkg.get('deviation_note'):
            task_service.add_deviation_note(
                task_id, pkg['deviation_note'], operator=operator,
            )

        pkg_snapshot = dict(pkg)
        if isinstance(pkg_snapshot.get('frozen_params'), dict):
            pass
        elif isinstance(pkg_snapshot.get('frozen_params'), str):
            try:
                pkg_snapshot['frozen_params'] = json.loads(pkg_snapshot['frozen_params'])
            except (json.JSONDecodeError, TypeError):
                pass

        self.db.execute('''
            INSERT INTO lock_package_task_references
            (task_id, package_id, package_name, package_snapshot)
            VALUES (?, ?, ?, ?)
        ''', (
            task_id,
            package_id,
            pkg['name'],
            json.dumps(pkg_snapshot, ensure_ascii=False),
        ))
        self.db.commit()

        self._log_history(
            package_id, 'apply', 'package_applied',
            detail=f'从锁定包 "{pkg["name"]}" 创建任务 #{task_id} "{task_name}"',
            operator=operator,
        )

        return {
            'task_id': task_id,
            'package_id': package_id,
            'package_name': pkg['name'],
            'template_id': template_id,
            'total_volume': total_volume,
            'volume_unit': volume_unit,
            'primer_id': pkg.get('primer_id'),
            'master_mix_id': pkg.get('master_mix_id'),
            'water_id': pkg.get('water_id'),
        }

    def get_task_package_reference(self, task_id):
        rows = self.db.execute(
            'SELECT * FROM lock_package_task_references WHERE task_id = ? ORDER BY created_at DESC',
            (task_id,)
        ).fetchall()
        refs = []
        for r in rows:
            ref = dict(r)
            if ref.get('package_snapshot') and isinstance(ref['package_snapshot'], str):
                try:
                    ref['package_snapshot'] = json.loads(ref['package_snapshot'])
                except (json.JSONDecodeError, TypeError):
                    pass
            refs.append(ref)
        return refs

    def get_package_referenced_tasks(self, package_id):
        rows = self.db.execute('''
            SELECT lptr.*, t.name AS task_name, t.status AS task_status
            FROM lock_package_task_references lptr
            LEFT JOIN tasks t ON t.id = lptr.task_id
            WHERE lptr.package_id = ?
            ORDER BY lptr.created_at DESC
        ''', (package_id,)).fetchall()
        return [dict(r) for r in rows]

    def get_package_history(self, package_id, limit=200):
        rows = self.db.execute('''
            SELECT * FROM lock_package_history
            WHERE package_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT ?
        ''', (package_id, int(limit))).fetchall()
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

    def import_packages_json(self, json_content, conflict_mode='reject',
                             operator='system'):
        try:
            data = json.loads(json_content)
        except json.JSONDecodeError as e:
            raise ValueError(f'JSON 解析失败: {str(e)}')

        packages_data = data if isinstance(data, list) else data.get('packages', [data])

        imported = 0
        skipped = 0
        renamed = 0
        overwritten = 0
        errors = []

        for pkg_data in packages_data:
            try:
                name = pkg_data.get('name', '').strip()
                if not name:
                    errors.append('缺少锁定包名称，跳过')
                    skipped += 1
                    continue

                resolved_name, action, existing_id = self._resolve_import_conflict(
                    name, conflict_mode
                )

                if action == 'name_conflict':
                    errors.append(f'锁定包名称已存在: {name}，已跳过')
                    skipped += 1
                    continue
                elif action == 'invalid_conflict_mode':
                    errors.append(f'无效的冲突处理模式: {conflict_mode}')
                    skipped += 1
                    continue

                if action == 'overwrite' and existing_id:
                    self.update_package(
                        existing_id,
                        name=resolved_name,
                        description=pkg_data.get('description'),
                        template_id=pkg_data.get('template_id'),
                        total_volume=pkg_data.get('total_volume'),
                        volume_unit=pkg_data.get('volume_unit', 'ul'),
                        primer_id=pkg_data.get('primer_id'),
                        master_mix_id=pkg_data.get('master_mix_id'),
                        water_id=pkg_data.get('water_id'),
                        deviation_note=pkg_data.get('deviation_note'),
                        operator=operator,
                    )
                    overwritten += 1
                    self._log_history(
                        existing_id, 'import', 'package_imported_overwrite',
                        detail=f'覆盖导入锁定包: {resolved_name}',
                        operator=operator,
                    )
                elif action == 'renamed':
                    self.create_manual(
                        name=resolved_name,
                        description=pkg_data.get('description'),
                        template_id=pkg_data.get('template_id'),
                        total_volume=pkg_data.get('total_volume'),
                        volume_unit=pkg_data.get('volume_unit', 'ul'),
                        primer_id=pkg_data.get('primer_id'),
                        master_mix_id=pkg_data.get('master_mix_id'),
                        water_id=pkg_data.get('water_id'),
                        deviation_note=pkg_data.get('deviation_note'),
                        operator=operator,
                    )
                    renamed += 1
                else:
                    self.create_manual(
                        name=resolved_name,
                        description=pkg_data.get('description'),
                        template_id=pkg_data.get('template_id'),
                        total_volume=pkg_data.get('total_volume'),
                        volume_unit=pkg_data.get('volume_unit', 'ul'),
                        primer_id=pkg_data.get('primer_id'),
                        master_mix_id=pkg_data.get('master_mix_id'),
                        water_id=pkg_data.get('water_id'),
                        deviation_note=pkg_data.get('deviation_note'),
                        operator=operator,
                    )
                    imported += 1

            except Exception as e:
                errors.append(f'导入锁定包 {pkg_data.get("name", "?")}: {str(e)}')
                skipped += 1

        return {
            'imported': imported,
            'renamed': renamed,
            'overwritten': overwritten,
            'skipped': skipped,
            'errors': errors,
            'total': len(packages_data),
        }

    def import_packages_csv(self, csv_content, conflict_mode='reject',
                            operator='system'):
        try:
            reader = csv.DictReader(io.StringIO(csv_content))
            packages_data = []
            for row in reader:
                pkg = {
                    'name': row.get('name', '').strip(),
                    'description': row.get('description', '').strip() or None,
                    'template_id': int(row['template_id']) if row.get('template_id') and row['template_id'].strip() else None,
                    'total_volume': float(row['total_volume']) if row.get('total_volume') and row['total_volume'].strip() else None,
                    'volume_unit': row.get('volume_unit', 'ul').strip() or 'ul',
                    'primer_id': int(row['primer_id']) if row.get('primer_id') and row['primer_id'].strip() else None,
                    'master_mix_id': int(row['master_mix_id']) if row.get('master_mix_id') and row['master_mix_id'].strip() else None,
                    'water_id': int(row['water_id']) if row.get('water_id') and row['water_id'].strip() else None,
                    'deviation_note': row.get('deviation_note', '').strip() or None,
                }
                packages_data.append(pkg)
        except Exception as e:
            raise ValueError(f'CSV 解析失败: {str(e)}')

        return self.import_packages_json(
            json.dumps(packages_data, ensure_ascii=False),
            conflict_mode=conflict_mode,
            operator=operator,
        )

    def export_packages_json(self, package_ids=None, is_enabled=None):
        if package_ids:
            placeholders = ','.join('?' * len(package_ids))
            rows = self.db.execute(
                f'SELECT * FROM protocol_lock_packages WHERE id IN ({placeholders}) ORDER BY name',
                [int(pid) for pid in package_ids]
            ).fetchall()
        else:
            query = 'SELECT * FROM protocol_lock_packages WHERE 1=1'
            params = []
            if is_enabled is not None:
                query += ' AND is_enabled = ?'
                params.append(1 if is_enabled else 0)
            query += ' ORDER BY name'
            rows = self.db.execute(query, params).fetchall()

        packages = []
        for r in rows:
            d = dict(r)
            if d.get('frozen_params') and isinstance(d['frozen_params'], str):
                try:
                    d['frozen_params'] = json.loads(d['frozen_params'])
                except (json.JSONDecodeError, TypeError):
                    pass
            packages.append(d)

        export_data = {
            'export_time': datetime.now().isoformat(),
            'export_format': 'protocol_lock_packages',
            'package_count': len(packages),
            'packages': packages,
        }
        return json.dumps(export_data, ensure_ascii=False, indent=2)

    def export_packages_csv(self, package_ids=None, is_enabled=None):
        if package_ids:
            placeholders = ','.join('?' * len(package_ids))
            rows = self.db.execute(
                f'SELECT * FROM protocol_lock_packages WHERE id IN ({placeholders}) ORDER BY name',
                [int(pid) for pid in package_ids]
            ).fetchall()
        else:
            query = 'SELECT * FROM protocol_lock_packages WHERE 1=1'
            params = []
            if is_enabled is not None:
                query += ' AND is_enabled = ?'
                params.append(1 if is_enabled else 0)
            query += ' ORDER BY name'
            rows = self.db.execute(query, params).fetchall()

        output = io.StringIO()
        fieldnames = [
            'id', 'name', 'description', 'template_id', 'template_name',
            'template_rows', 'template_cols',
            'total_volume', 'volume_unit',
            'primer_id', 'primer_name',
            'master_mix_id', 'master_mix_name',
            'water_id', 'water_name',
            'deviation_note', 'is_enabled',
            'source_task_id', 'source_task_name', 'source_task_status',
            'created_at', 'updated_at',
        ]
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow({k: r[k] if k in r.keys() else '' for k in fieldnames})

        return output.getvalue()
