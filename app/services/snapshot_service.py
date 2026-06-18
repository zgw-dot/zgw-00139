import json
from datetime import datetime


class SnapshotService:

    SNAPSHOT_SCHEMA_VERSION = '1.0'

    def __init__(self, db):
        self.db = db

    def create_snapshot(self, task_id, snapshot_type, note=None):
        task = self.db.execute('SELECT * FROM tasks WHERE id = ?', (task_id,)).fetchone()
        if not task:
            raise ValueError('任务不存在')

        last_snapshot = self.db.execute(
            'SELECT MAX(version) as max_ver FROM task_snapshots WHERE task_id = ?',
            (task_id,)
        ).fetchone()
        next_version = (last_snapshot['max_ver'] or 0) + 1

        wells = self.db.execute(
            'SELECT * FROM task_wells WHERE task_id = ? ORDER BY well_row, well_col',
            (task_id,)
        ).fetchall()

        reagent_usage = self.db.execute(
            'SELECT * FROM task_reagent_usage WHERE task_id = ?',
            (task_id,)
        ).fetchall()

        primer_usage = self.db.execute(
            'SELECT * FROM task_primer_usage WHERE task_id = ?',
            (task_id,)
        ).fetchall()

        template = None
        template_name = None
        if task['template_id']:
            template = self.db.execute(
                'SELECT * FROM plate_templates WHERE id = ?',
                (task['template_id'],)
            ).fetchone()
            if template:
                template_name = template['name']

        task_dict = dict(task)
        wells_list = [dict(w) for w in wells]
        reagent_list = [dict(r) for r in reagent_usage]
        primer_list = [dict(p) for p in primer_usage]

        self.db.execute('''
            INSERT INTO task_snapshots
            (task_id, version, snapshot_type, status, task_data, wells_data,
             reagent_usage_data, primer_usage_data, template_id, template_name,
             total_volume, volume_unit, note)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            task_id, next_version, snapshot_type, task['status'],
            json.dumps(task_dict, ensure_ascii=False),
            json.dumps(wells_list, ensure_ascii=False),
            json.dumps(reagent_list, ensure_ascii=False),
            json.dumps(primer_list, ensure_ascii=False),
            task['template_id'], template_name,
            task['total_volume'], task['volume_unit'],
            note or ''
        ))
        self.db.commit()

        self._add_history(task_id, 'snapshot', 'snapshot_created',
                          f'创建版本快照 v{next_version}，类型: {snapshot_type}')

        return {
            'snapshot_id': self.db.execute('SELECT last_insert_rowid() as id').fetchone()['id'],
            'version': next_version,
            'snapshot_type': snapshot_type,
            'status': task['status'],
            'created_at': datetime.now().isoformat()
        }

    def list_snapshots(self, task_id):
        task = self.db.execute('SELECT id FROM tasks WHERE id = ?', (task_id,)).fetchone()
        if not task:
            raise ValueError('任务不存在')

        snapshots = self.db.execute(
            '''SELECT id, task_id, version, snapshot_type, status, template_id, template_name,
                      total_volume, volume_unit, note, created_at
               FROM task_snapshots WHERE task_id = ? ORDER BY version DESC''',
            (task_id,)
        ).fetchall()

        result = []
        for s in snapshots:
            d = dict(s)
            wells_data = self.db.execute(
                'SELECT wells_data FROM task_snapshots WHERE id = ?', (s['id'],)
            ).fetchone()
            if wells_data and wells_data['wells_data']:
                wells = json.loads(wells_data['wells_data'])
                d['well_count'] = len(wells)
            else:
                d['well_count'] = 0
            result.append(d)

        return result

    def get_snapshot(self, snapshot_id):
        snapshot = self.db.execute(
            'SELECT * FROM task_snapshots WHERE id = ?', (snapshot_id,)
        ).fetchone()
        if not snapshot:
            raise ValueError('快照不存在')

        return self._parse_snapshot(snapshot)

    def get_snapshot_by_version(self, task_id, version):
        snapshot = self.db.execute(
            'SELECT * FROM task_snapshots WHERE task_id = ? AND version = ?',
            (task_id, version)
        ).fetchone()
        if not snapshot:
            raise ValueError(f'任务 #{task_id} 不存在版本 v{version} 的快照')

        return self._parse_snapshot(snapshot)

    def _parse_snapshot(self, snapshot_row):
        d = dict(snapshot_row)
        d['task_data'] = json.loads(d['task_data']) if d['task_data'] else {}
        d['wells_data'] = json.loads(d['wells_data']) if d['wells_data'] else []
        d['reagent_usage_data'] = json.loads(d['reagent_usage_data']) if d['reagent_usage_data'] else []
        d['primer_usage_data'] = json.loads(d['primer_usage_data']) if d['primer_usage_data'] else []
        return d

    def compare_snapshots(self, task_id, version_a, version_b):
        snap_a = self.get_snapshot_by_version(task_id, version_a)
        snap_b = self.get_snapshot_by_version(task_id, version_b)

        task_a = snap_a['task_data']
        task_b = snap_b['task_data']

        differences = {
            'version_a': version_a,
            'version_b': version_b,
            'task_differences': {},
            'template_differences': {},
            'well_differences': {},
            'reagent_differences': {},
            'primer_differences': {},
            'summary': {
                'wells_added': 0,
                'wells_removed': 0,
                'wells_modified': 0,
                'reagents_added': 0,
                'reagents_removed': 0,
                'reagents_modified': 0,
                'primers_added': 0,
                'primers_removed': 0,
                'primers_modified': 0
            }
        }

        for key in ['status', 'total_volume', 'volume_unit', 'deviation_note']:
            val_a = task_a.get(key)
            val_b = task_b.get(key)
            if val_a != val_b:
                differences['task_differences'][key] = {'old': val_a, 'new': val_b}

        if snap_a.get('template_name') != snap_b.get('template_name'):
            differences['template_differences']['template_name'] = {
                'old': snap_a.get('template_name'),
                'new': snap_b.get('template_name')
            }

        wells_a = {(w['well_row'], w['well_col']): w for w in snap_a['wells_data']}
        wells_b = {(w['well_row'], w['well_col']): w for w in snap_b['wells_data']}

        all_keys = set(wells_a.keys()) | set(wells_b.keys())
        for key in sorted(all_keys):
            well_label = f"{chr(64 + key[0])}{key[1]}"
            if key not in wells_a:
                differences['well_differences'][well_label] = {'change': 'added', 'well': wells_b[key]}
                differences['summary']['wells_added'] += 1
            elif key not in wells_b:
                differences['well_differences'][well_label] = {'change': 'removed', 'well': wells_a[key]}
                differences['summary']['wells_removed'] += 1
            else:
                wa, wb = wells_a[key], wells_b[key]
                diff_fields = {}
                for f in ['well_type', 'sample_name', 'sample_volume', 'primer_name',
                          'primer_volume', 'master_mix_volume', 'water_volume', 'total_volume']:
                    if wa.get(f) != wb.get(f):
                        diff_fields[f] = {'old': wa.get(f), 'new': wb.get(f)}
                if diff_fields:
                    differences['well_differences'][well_label] = {'change': 'modified', 'fields': diff_fields}
                    differences['summary']['wells_modified'] += 1

        reagents_a = {r['reagent_name']: r for r in snap_a['reagent_usage_data']}
        reagents_b = {r['reagent_name']: r for r in snap_b['reagent_usage_data']}

        all_reagents = set(reagents_a.keys()) | set(reagents_b.keys())
        for name in sorted(all_reagents):
            if name not in reagents_a:
                differences['reagent_differences'][name] = {'change': 'added', 'data': reagents_b[name]}
                differences['summary']['reagents_added'] += 1
            elif name not in reagents_b:
                differences['reagent_differences'][name] = {'change': 'removed', 'data': reagents_a[name]}
                differences['summary']['reagents_removed'] += 1
            else:
                ra, rb = reagents_a[name], reagents_b[name]
                diff_fields = {}
                for f in ['used_volume', 'used_volume_unit', 'source', 'batch_id', 'batch_number']:
                    if ra.get(f) != rb.get(f):
                        diff_fields[f] = {'old': ra.get(f), 'new': rb.get(f)}
                if diff_fields:
                    differences['reagent_differences'][name] = {'change': 'modified', 'fields': diff_fields}
                    differences['summary']['reagents_modified'] += 1

        primers_a = {p['primer_name']: p for p in snap_a['primer_usage_data']}
        primers_b = {p['primer_name']: p for p in snap_b['primer_usage_data']}

        all_primers = set(primers_a.keys()) | set(primers_b.keys())
        for name in sorted(all_primers):
            if name not in primers_a:
                differences['primer_differences'][name] = {'change': 'added', 'data': primers_b[name]}
                differences['summary']['primers_added'] += 1
            elif name not in primers_b:
                differences['primer_differences'][name] = {'change': 'removed', 'data': primers_a[name]}
                differences['summary']['primers_removed'] += 1
            else:
                pa, pb = primers_a[name], primers_b[name]
                diff_fields = {}
                for f in ['used_volume', 'used_volume_unit', 'source']:
                    if pa.get(f) != pb.get(f):
                        diff_fields[f] = {'old': pa.get(f), 'new': pb.get(f)}
                if diff_fields:
                    differences['primer_differences'][name] = {'change': 'modified', 'fields': diff_fields}
                    differences['summary']['primers_modified'] += 1

        return differences

    def rollback_to_snapshot(self, task_id, version, operator='user'):
        task = self.db.execute('SELECT * FROM tasks WHERE id = ?', (task_id,)).fetchone()
        if not task:
            raise ValueError('任务不存在')

        if task['status'] in ['approved', 'revoked']:
            raise ValueError(f'当前状态为「{task["status"]}」的任务不能回滚，只能回滚未批准的任务')

        snapshot = self.db.execute(
            'SELECT * FROM task_snapshots WHERE task_id = ? AND version = ?',
            (task_id, version)
        ).fetchone()
        if not snapshot:
            raise ValueError(f'任务 #{task_id} 不存在版本 v{version} 的快照')

        snap_data = self._parse_snapshot(snapshot)
        snap_task = snap_data['task_data']
        snap_wells = snap_data['wells_data']
        snap_reagents = snap_data['reagent_usage_data']
        snap_primers = snap_data['primer_usage_data']

        previous_status = task['status']

        try:
            self.db.execute('BEGIN')

            self.db.execute('''
                UPDATE tasks SET status = ?, total_volume = ?, volume_unit = ?,
                       deviation_note = ?, rejected_reason = ?, updated_at = ?
                WHERE id = ?
            ''', (
                snap_task.get('status', 'draft'),
                snap_task.get('total_volume', task['total_volume']),
                snap_task.get('volume_unit', task['volume_unit']),
                snap_task.get('deviation_note'),
                snap_task.get('rejected_reason'),
                datetime.now().isoformat(),
                task_id
            ))

            self.db.execute('DELETE FROM task_wells WHERE task_id = ?', (task_id,))
            for w in snap_wells:
                self.db.execute('''
                    INSERT INTO task_wells
                    (task_id, well_row, well_col, well_type, sample_name,
                     sample_volume, sample_volume_unit, sample_concentration, sample_concentration_unit,
                     primer_name, primer_volume, primer_volume_unit, primer_concentration, primer_concentration_unit,
                     master_mix_volume, master_mix_unit, water_volume, water_unit,
                     total_volume, total_volume_unit, note)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    task_id, w['well_row'], w['well_col'], w.get('well_type', 'sample'),
                    w.get('sample_name'),
                    w.get('sample_volume'), w.get('sample_volume_unit'),
                    w.get('sample_concentration'), w.get('sample_concentration_unit'),
                    w.get('primer_name'),
                    w.get('primer_volume'), w.get('primer_volume_unit'),
                    w.get('primer_concentration'), w.get('primer_concentration_unit'),
                    w.get('master_mix_volume'), w.get('master_mix_unit'),
                    w.get('water_volume'), w.get('water_unit'),
                    w.get('total_volume'), w.get('total_volume_unit'),
                    w.get('note', '')
                ))

            self.db.execute('DELETE FROM task_reagent_usage WHERE task_id = ?', (task_id,))
            for r in snap_reagents:
                self.db.execute('''
                    INSERT INTO task_reagent_usage 
                    (task_id, reagent_id, reagent_name, batch_id, batch_number,
                     used_volume, used_volume_unit, source)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    task_id, r.get('reagent_id'), r.get('reagent_name'),
                    r.get('batch_id'), r.get('batch_number'),
                    r.get('used_volume', 0), r.get('used_volume_unit', 'ul'),
                    r.get('source', '')
                ))

            self.db.execute('DELETE FROM task_primer_usage WHERE task_id = ?', (task_id,))
            for p in snap_primers:
                self.db.execute('''
                    INSERT INTO task_primer_usage (task_id, primer_id, primer_name, used_volume, used_volume_unit, source)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (
                    task_id, p.get('primer_id'), p.get('primer_name'),
                    p.get('used_volume', 0), p.get('used_volume_unit', 'ul'),
                    p.get('source', '')
                ))

            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

        new_status = snap_task.get('status', 'draft')
        self._add_history(task_id, 'rollback', 'snapshot_rollback',
                          f'回滚到版本 v{version}，状态从 {previous_status} 变为 {new_status}。操作人: {operator}')

        return {
            'task_id': task_id,
            'rolled_back_to': version,
            'previous_status': previous_status,
            'new_status': new_status
        }

    def get_snapshot_summary_for_export(self, task_id):
        snapshots = self.list_snapshots(task_id)
        return {
            'schema_version': self.SNAPSHOT_SCHEMA_VERSION,
            'snapshot_count': len(snapshots),
            'snapshots': [
                {
                    'version': s['version'],
                    'snapshot_type': s['snapshot_type'],
                    'status': s['status'],
                    'created_at': s['created_at'],
                    'note': s.get('note', '')
                }
                for s in snapshots
            ]
        }

    def validate_import_snapshots(self, task_name, import_data, check_name_duplicate=True):
        errors = []

        if 'snapshots' in import_data:
            snapshots_info = import_data['snapshots']
            schema_ver = snapshots_info.get('schema_version', '')
            if schema_ver and schema_ver != self.SNAPSHOT_SCHEMA_VERSION:
                errors.append(f'快照 schema 版本不支持: {schema_ver}，当前支持: {self.SNAPSHOT_SCHEMA_VERSION}')

        if check_name_duplicate:
            existing = self.db.execute(
                'SELECT id FROM tasks WHERE name = ?', (task_name,)
            ).fetchone()
            if existing:
                errors.append(f'任务名称已存在: {task_name}')

        return errors

    def import_snapshots(self, new_task_id, import_data):
        if 'snapshots' not in import_data or 'snapshots' not in import_data['snapshots']:
            return 0

        snapshot_list = import_data['snapshots']['snapshots']
        if not snapshot_list:
            return 0

        task = self.db.execute('SELECT * FROM tasks WHERE id = ?', (new_task_id,)).fetchone()
        if not task:
            raise ValueError('任务不存在')

        last_snapshot = self.db.execute(
            'SELECT MAX(version) as max_ver FROM task_snapshots WHERE task_id = ?',
            (new_task_id,)
        ).fetchone()
        start_version = (last_snapshot['max_ver'] or 0) + 1

        wells = self.db.execute(
            'SELECT * FROM task_wells WHERE task_id = ? ORDER BY well_row, well_col',
            (new_task_id,)
        ).fetchall()
        reagent_usage = self.db.execute(
            'SELECT * FROM task_reagent_usage WHERE task_id = ?', (new_task_id,)
        ).fetchall()
        primer_usage = self.db.execute(
            'SELECT * FROM task_primer_usage WHERE task_id = ?', (new_task_id,)
        ).fetchall()

        template = None
        template_name = None
        if task['template_id']:
            template = self.db.execute(
                'SELECT * FROM plate_templates WHERE id = ?', (task['template_id'],)
            ).fetchone()
            if template:
                template_name = template['name']

        task_dict = dict(task)
        wells_list = [dict(w) for w in wells]
        reagent_list = [dict(r) for r in reagent_usage]
        primer_list = [dict(p) for p in primer_usage]

        version = start_version
        for snap_info in snapshot_list:
            self.db.execute('''
                INSERT INTO task_snapshots
                (task_id, version, snapshot_type, status, task_data, wells_data,
                 reagent_usage_data, primer_usage_data, template_id, template_name,
                 total_volume, volume_unit, note)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                new_task_id, version,
                snap_info.get('snapshot_type', 'imported'),
                snap_info.get('status', task['status']),
                json.dumps(task_dict, ensure_ascii=False),
                json.dumps(wells_list, ensure_ascii=False),
                json.dumps(reagent_list, ensure_ascii=False),
                json.dumps(primer_list, ensure_ascii=False),
                task['template_id'], template_name,
                task['total_volume'], task['volume_unit'],
                snap_info.get('note', '导入快照')
            ))
            version += 1

        self.db.commit()
        return len(snapshot_list)

    def _add_history(self, task_id, action, action_type, detail):
        self.db.execute('''
            INSERT INTO history (task_id, action, action_type, detail, operator)
            VALUES (?, ?, ?, ?, ?)
        ''', (task_id, action, action_type, detail, 'system'))
        self.db.commit()
