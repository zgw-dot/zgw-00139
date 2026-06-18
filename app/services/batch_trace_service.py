import json
import csv
import io
from datetime import datetime, date

from app.services.unit_converter import UnitConverter


class BatchTraceService:

    EVENT_TYPES = [
        'import',
        'allocate',
        'deduct',
        'refund',
        'freeze',
        'unfreeze',
        'copy_allocate',
        'recalculate',
        'edit_clear',
        'manual_create',
        'manual_update',
    ]

    EVENT_TYPE_LABELS = {
        'import': '导入登记',
        'allocate': '方案分配',
        'deduct': '批准扣减',
        'refund': '撤销退回',
        'freeze': '冻结',
        'unfreeze': '解冻',
        'copy_allocate': '复制分配',
        'recalculate': '编辑重算分配',
        'edit_clear': '编辑清空旧分配',
        'manual_create': '手工新增批次',
        'manual_update': '手工更新批次',
    }

    CONFLICT_TYPES = [
        'duplicate_batch',
        'batch_occupied',
        'revoke_incomplete',
        'reimport_duplicate',
    ]

    CONFLICT_TYPE_LABELS = {
        'duplicate_batch': '同名批次重复导入',
        'batch_occupied': '批次被后续任务占用',
        'revoke_incomplete': '撤销回滚不完整',
        'reimport_duplicate': '同一文件重复导入',
    }

    def __init__(self, db):
        self.db = db

    def _get_reagent_name(self, reagent_id):
        row = self.db.execute(
            'SELECT name FROM reagents WHERE id = ?', (reagent_id,)
        ).fetchone()
        return row['name'] if row else f'#{reagent_id}'

    def _get_batch_info(self, batch_id):
        row = self.db.execute(
            'SELECT * FROM reagent_batches WHERE id = ?', (batch_id,)
        ).fetchone()
        return dict(row) if row else None

    def _get_task_info(self, task_id):
        if task_id is None:
            return None, None
        row = self.db.execute(
            'SELECT name, status FROM tasks WHERE id = ?', (task_id,)
        ).fetchone()
        if row:
            return row['name'], row['status']
        return None, None

    def log_event(self, batch_id, event_type, event_subtype=None,
                  task_id=None, volume_change=0, volume_unit='ul',
                  source_file=None, freeze_reason=None, operator='system',
                  detail=None, raw_data=None):
        batch = self._get_batch_info(batch_id)
        if not batch:
            raise ValueError(f'批次不存在 (id={batch_id})，无法记录台账')

        if event_type not in self.EVENT_TYPES:
            raise ValueError(f'未知的台账事件类型: {event_type}')

        reagent_name = self._get_reagent_name(batch['reagent_id'])
        task_name, task_status = self._get_task_info(task_id)

        balance_ul = UnitConverter.convert_volume(
            batch['volume'], batch['volume_unit'], 'ul'
        )

        cursor = self.db.execute('''
            INSERT INTO batch_trace_ledger
            (batch_id, batch_number, reagent_id, reagent_name,
             event_type, event_subtype, task_id, task_name, task_status,
             volume_change, volume_unit, balance_volume, balance_unit,
             source_file, freeze_reason, operator, detail, raw_data)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            batch_id,
            batch['batch_number'],
            batch['reagent_id'],
            reagent_name,
            event_type,
            event_subtype,
            task_id,
            task_name,
            task_status,
            volume_change,
            volume_unit,
            balance_ul,
            'ul',
            source_file or batch.get('source_file'),
            freeze_reason or batch.get('freeze_reason'),
            operator,
            detail,
            json.dumps(raw_data, ensure_ascii=False) if raw_data and not isinstance(raw_data, str) else (raw_data or None),
        ))
        self.db.commit()
        return cursor.lastrowid

    def log_import(self, batch_id, source_file=None, operator='system',
                   import_note=None):
        batch = self._get_batch_info(batch_id)
        if source_file:
            self.db.execute(
                'UPDATE reagent_batches SET source_file = ? WHERE id = ?',
                (source_file, batch_id)
            )
            self.db.commit()
            batch = self._get_batch_info(batch_id)
        initial_vol_ul = UnitConverter.convert_volume(
            batch['volume'], batch['volume_unit'], 'ul'
        )
        return self.log_event(
            batch_id=batch_id,
            event_type='import',
            volume_change=initial_vol_ul,
            volume_unit='ul',
            source_file=source_file,
            operator=operator,
            detail=import_note or f'导入批次 {batch["batch_number"]}，初始库存 {initial_vol_ul:.2f} µL',
        )

    def log_manual_create(self, batch_id, operator='user', note=None):
        batch = self._get_batch_info(batch_id)
        initial_vol_ul = UnitConverter.convert_volume(
            batch['volume'], batch['volume_unit'], 'ul'
        )
        return self.log_event(
            batch_id=batch_id,
            event_type='manual_create',
            volume_change=initial_vol_ul,
            volume_unit='ul',
            operator=operator,
            detail=note or f'手工新增批次 {batch["batch_number"]}，初始库存 {initial_vol_ul:.2f} µL',
        )

    def log_manual_update(self, batch_id, changes=None, operator='user', note=None):
        change_desc = ''
        if changes:
            parts = []
            label_map = {
                'batch_number': '批次号',
                'volume': '体积',
                'volume_unit': '单位',
                'expiry_date': '有效期',
                'is_frozen': '冻结状态',
                'min_usable_volume': '最小可用量',
            }
            for k, v in changes.items():
                label = label_map.get(k, k)
                parts.append(f'{label}: {v.get("old")} → {v.get("new")}')
            change_desc = '; '.join(parts)
        detail_parts = []
        if note:
            detail_parts.append(note)
        if change_desc:
            detail_parts.append(f'变更项: {change_desc}')
        return self.log_event(
            batch_id=batch_id,
            event_type='manual_update',
            operator=operator,
            detail=' | '.join(detail_parts) or '手工更新批次信息',
            raw_data={'changes': changes},
        )

    def log_allocate(self, batch_id, task_id, allocated_volume_ul, source='plan'):
        batch = self._get_batch_info(batch_id)
        event_type = 'allocate'
        event_subtype = source
        if source == 'copy':
            event_type = 'copy_allocate'
        elif source == 'recalculate':
            event_type = 'recalculate'
        return self.log_event(
            batch_id=batch_id,
            event_type=event_type,
            event_subtype=event_subtype,
            task_id=task_id,
            volume_change=0,
            volume_unit='ul',
            detail=f'任务方案分配 {allocated_volume_ul:.2f} µL (来源: {source})',
            raw_data={'allocated_volume_ul': allocated_volume_ul, 'source': source},
        )

    def log_edit_clear(self, batch_id, task_id, cleared_volume_ul=None):
        return self.log_event(
            batch_id=batch_id,
            event_type='edit_clear',
            task_id=task_id,
            volume_change=0,
            detail=f'任务编辑，清空旧方案分配 {cleared_volume_ul:.2f} µL' if cleared_volume_ul else '任务编辑，清空旧方案分配',
        )

    def log_deduct(self, batch_id, task_id, deducted_volume_ul, operator='system'):
        return self.log_event(
            batch_id=batch_id,
            event_type='deduct',
            task_id=task_id,
            volume_change=-abs(deducted_volume_ul),
            volume_unit='ul',
            operator=operator,
            detail=f'任务批准扣减 {abs(deducted_volume_ul):.2f} µL',
            raw_data={'deducted_volume_ul': deducted_volume_ul},
        )

    def log_refund(self, batch_id, task_id, refund_volume_ul, force=False, operator='system'):
        note = '强制撤销' if force else '撤销'
        return self.log_event(
            batch_id=batch_id,
            event_type='refund',
            task_id=task_id,
            volume_change=abs(refund_volume_ul),
            volume_unit='ul',
            operator=operator,
            detail=f'{note}回滚，退回库存 {abs(refund_volume_ul):.2f} µL',
            raw_data={'refund_volume_ul': refund_volume_ul, 'force': force},
        )

    def log_freeze(self, batch_id, reason=None, operator='user'):
        if reason:
            self.db.execute(
                'UPDATE reagent_batches SET freeze_reason = ? WHERE id = ?',
                (reason, batch_id)
            )
            self.db.commit()
        return self.log_event(
            batch_id=batch_id,
            event_type='freeze',
            freeze_reason=reason,
            operator=operator,
            detail=reason and f'冻结批次，原因: {reason}' or '冻结批次',
        )

    def log_unfreeze(self, batch_id, operator='user', note=None):
        return self.log_event(
            batch_id=batch_id,
            event_type='unfreeze',
            operator=operator,
            detail=note and f'解除冻结: {note}' or '解除冻结',
        )

    def record_conflict(self, reagent_name, batch_number, conflict_type='duplicate_batch',
                        source_file=None, incoming=None, existing=None,
                        detail=None, resolution_note=None):
        if conflict_type not in self.CONFLICT_TYPES:
            raise ValueError(f'未知的冲突类型: {conflict_type}')

        incoming = incoming or {}
        existing = existing or {}

        cursor = self.db.execute('''
            INSERT INTO batch_import_conflicts
            (reagent_name, batch_number, source_file, conflict_type,
             incoming_volume, incoming_volume_unit, incoming_expiry_date, incoming_is_frozen,
             existing_batch_id, existing_volume, existing_volume_unit,
             existing_expiry_date, existing_is_frozen,
             resolved, resolution_note, detail)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            reagent_name,
            batch_number,
            source_file,
            conflict_type,
            incoming.get('volume'),
            incoming.get('volume_unit', 'ul'),
            incoming.get('expiry_date'),
            1 if incoming.get('is_frozen') else 0,
            existing.get('batch_id'),
            existing.get('volume'),
            existing.get('volume_unit', 'ul'),
            existing.get('expiry_date'),
            1 if existing.get('is_frozen') else 0,
            0,
            resolution_note,
            detail,
        ))
        self.db.commit()
        return cursor.lastrowid

    def list_conflicts(self, reagent_name=None, batch_number=None,
                       conflict_type=None, resolved=None, limit=500):
        query = 'SELECT * FROM batch_import_conflicts WHERE 1=1'
        params = []
        if reagent_name:
            query += ' AND reagent_name = ?'
            params.append(reagent_name)
        if batch_number:
            query += ' AND batch_number = ?'
            params.append(batch_number)
        if conflict_type:
            query += ' AND conflict_type = ?'
            params.append(conflict_type)
        if resolved is not None:
            query += ' AND resolved = ?'
            params.append(1 if resolved else 0)
        query += ' ORDER BY created_at DESC LIMIT ?'
        params.append(int(limit))
        rows = self.db.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def get_conflict(self, conflict_id):
        row = self.db.execute(
            'SELECT * FROM batch_import_conflicts WHERE id = ?', (conflict_id,)
        ).fetchone()
        return dict(row) if row else None

    def resolve_conflict(self, conflict_id, resolution_note, operator='user'):
        self.db.execute(
            'UPDATE batch_import_conflicts SET resolved = 1, resolution_note = ? WHERE id = ?',
            (f'{resolution_note} (操作人: {operator})', conflict_id)
        )
        self.db.commit()
        return self.get_conflict(conflict_id)

    def trace_by_batch(self, batch_id, limit=500):
        batch = self._get_batch_info(batch_id)
        if not batch:
            raise ValueError(f'批次不存在 (id={batch_id})')

        rows = self.db.execute(
            '''SELECT * FROM batch_trace_ledger
               WHERE batch_id = ? ORDER BY created_at ASC, id ASC LIMIT ?''',
            (batch_id, int(limit))
        ).fetchall()
        ledger = [dict(r) for r in rows]

        task_ids = sorted(set(
            r['task_id'] for r in ledger if r.get('task_id') is not None
        ))
        task_details = []
        for tid in task_ids:
            task_row = self.db.execute(
                'SELECT id, name, status, created_at, updated_at FROM tasks WHERE id = ?',
                (tid,)
            ).fetchone()
            if task_row:
                usages = [dict(u) for u in self.db.execute(
                    '''SELECT * FROM task_reagent_usage
                       WHERE task_id = ? AND batch_id = ?''',
                    (tid, batch_id)
                ).fetchall()]
                task_details.append({
                    'task': dict(task_row),
                    'usages': usages,
                })

        return {
            'batch': dict(batch),
            'ledger': ledger,
            'related_tasks': task_details,
        }

    def trace_by_task(self, task_id, limit=500):
        task_name, task_status = self._get_task_info(task_id)
        if task_name is None:
            raise ValueError(f'任务不存在 (id={task_id})')

        task_row = self.db.execute(
            'SELECT * FROM tasks WHERE id = ?', (task_id,)
        ).fetchone()

        usages = [dict(u) for u in self.db.execute(
            'SELECT * FROM task_reagent_usage WHERE task_id = ? ORDER BY id',
            (task_id,)
        ).fetchall()]

        batch_ids = sorted(set(
            u['batch_id'] for u in usages if u.get('batch_id') is not None
        ))

        ledger = []
        if batch_ids:
            placeholders = ','.join('?' * len(batch_ids))
            rows = self.db.execute(
                f'''SELECT * FROM batch_trace_ledger
                    WHERE task_id = ? OR batch_id IN ({placeholders})
                    ORDER BY created_at ASC, id ASC LIMIT ?''',
                [task_id] + batch_ids + [int(limit)]
            ).fetchall()
            ledger = [dict(r) for r in rows]

        batch_details = []
        for bid in batch_ids:
            b = self._get_batch_info(bid)
            if b:
                batch_ledger = [l for l in ledger if l['batch_id'] == bid]
                batch_details.append({
                    'batch': dict(b),
                    'ledger': batch_ledger,
                })

        return {
            'task': dict(task_row),
            'reagent_usages': usages,
            'ledger': ledger,
            'related_batches': batch_details,
        }

    def query_ledger(self, batch_id=None, reagent_id=None, task_id=None,
                     event_type=None, start_date=None, end_date=None,
                     keyword=None, limit=1000):
        query = 'SELECT * FROM batch_trace_ledger WHERE 1=1'
        params = []
        if batch_id:
            query += ' AND batch_id = ?'
            params.append(int(batch_id))
        if reagent_id:
            query += ' AND reagent_id = ?'
            params.append(int(reagent_id))
        if task_id:
            query += ' AND task_id = ?'
            params.append(int(task_id))
        if event_type:
            query += ' AND event_type = ?'
            params.append(event_type)
        if start_date:
            query += ' AND created_at >= ?'
            params.append(start_date)
        if end_date:
            query += ' AND created_at <= ?'
            params.append(end_date)
        if keyword:
            kw = f'%{keyword}%'
            query += ''' AND (batch_number LIKE ? OR reagent_name LIKE ?
                              OR event_type LIKE ? OR detail LIKE ?
                              OR COALESCE(task_name, '') LIKE ?)'''
            params.extend([kw, kw, kw, kw, kw])
        query += ' ORDER BY created_at DESC, id DESC LIMIT ?'
        params.append(int(limit))
        rows = self.db.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def check_batch_occupied_safety(self, batch_id, current_task_id=None):
        result = {
            'batch_id': batch_id,
            'safe': True,
            'approved_later_tasks': [],
            'warning': None,
        }
        batch = self._get_batch_info(batch_id)
        if not batch:
            result['safe'] = False
            result['warning'] = '批次不存在'
            return result

        q = '''SELECT DISTINCT tru.task_id, t.name AS task_name, t.status,
                      tru.used_volume, tru.used_volume_unit
               FROM task_reagent_usage tru
               JOIN tasks t ON t.id = tru.task_id
               WHERE tru.batch_id = ?'''
        params = [batch_id]
        if current_task_id is not None:
            q += ' AND tru.task_id != ?'
            params.append(current_task_id)
        q += ' ORDER BY tru.task_id ASC'
        rows = self.db.execute(q, params).fetchall()

        approved = []
        for r in rows:
            d = dict(r)
            if d['status'] == 'approved':
                approved.append(d)

        if approved:
            result['safe'] = False
            result['approved_later_tasks'] = approved
            refs = ', '.join(
                f"#{t['task_id']}({t['task_name']})" for t in approved
            )
            result['warning'] = (
                f'批次 {batch["batch_number"]} 已被以下已批准任务占用，无法直接退回: {refs}'
            )
        return result

    def check_revoke_completeness(self, task_id):
        task_name, task_status = self._get_task_info(task_id)
        result = {
            'task_id': task_id,
            'complete': True,
            'issues': [],
            'details': [],
        }

        if task_status != 'revoked':
            refund_events = self.db.execute(
                '''SELECT * FROM batch_trace_ledger
                   WHERE task_id = ? AND event_type = 'refund' ''',
                (task_id,)
            ).fetchall()
            deduct_events = self.db.execute(
                '''SELECT * FROM batch_trace_ledger
                   WHERE task_id = ? AND event_type = 'deduct' ''',
                (task_id,)
            ).fetchall()
            if len(refund_events) < len(deduct_events):
                result['complete'] = False
                result['issues'].append(
                    f'撤销回滚不完整: 扣减 {len(deduct_events)} 次，仅退回 {len(refund_events)} 次'
                )

        usages = [dict(u) for u in self.db.execute(
            'SELECT * FROM task_reagent_usage WHERE task_id = ? AND batch_id IS NOT NULL',
            (task_id,)
        ).fetchall()]

        for u in usages:
            bid = u['batch_id']
            if bid is None:
                continue
            used_ul = UnitConverter.convert_volume(
                u['used_volume'], u['used_volume_unit'], 'ul'
            )
            safety = self.check_batch_occupied_safety(bid, task_id)
            if not safety['safe']:
                result['complete'] = False
                for t in safety['approved_later_tasks']:
                    result['details'].append({
                        'reagent_name': u['reagent_name'],
                        'batch_id': bid,
                        'batch_number': u.get('batch_number'),
                        'issue': '被后续批准任务占用',
                        'conflicting_task_id': t['task_id'],
                        'conflicting_task_name': t['task_name'],
                        'task_used_volume': used_ul,
                    })
        if not result['complete'] and not result['issues']:
            result['issues'].append('存在批次占用问题，强制撤销后可能导致后续任务负库存')
        return result

    def export_ledger_json(self, batch_id=None, reagent_id=None, task_id=None,
                           event_type=None, start_date=None, end_date=None,
                           keyword=None, limit=5000):
        records = self.query_ledger(
            batch_id=batch_id, reagent_id=reagent_id, task_id=task_id,
            event_type=event_type, start_date=start_date, end_date=end_date,
            keyword=keyword, limit=limit,
        )
        conflicts = self.list_conflicts(limit=limit)
        export_data = {
            'export_time': datetime.now().isoformat(),
            'export_format': 'json',
            'filter': {
                'batch_id': batch_id,
                'reagent_id': reagent_id,
                'task_id': task_id,
                'event_type': event_type,
                'start_date': start_date,
                'end_date': end_date,
                'keyword': keyword,
                'limit': limit,
            },
            'ledger_count': len(records),
            'conflict_count': len(conflicts),
            'event_type_labels': self.EVENT_TYPE_LABELS,
            'conflict_type_labels': self.CONFLICT_TYPE_LABELS,
            'ledger': records,
            'conflicts': conflicts,
        }
        return json.dumps(export_data, ensure_ascii=False, indent=2)

    def export_ledger_csv(self, batch_id=None, reagent_id=None, task_id=None,
                          event_type=None, start_date=None, end_date=None,
                          keyword=None, limit=5000):
        records = self.query_ledger(
            batch_id=batch_id, reagent_id=reagent_id, task_id=task_id,
            event_type=event_type, start_date=start_date, end_date=end_date,
            keyword=keyword, limit=limit,
        )
        output = io.StringIO()
        fieldnames = [
            'id', 'created_at', 'batch_id', 'batch_number',
            'reagent_id', 'reagent_name', 'event_type', 'event_type_label',
            'event_subtype', 'task_id', 'task_name', 'task_status',
            'volume_change', 'volume_unit', 'balance_volume', 'balance_unit',
            'source_file', 'freeze_reason', 'operator', 'detail',
        ]
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        for r in records:
            row = {k: r.get(k, '') for k in fieldnames}
            row['event_type_label'] = self.EVENT_TYPE_LABELS.get(
                r.get('event_type', ''), r.get('event_type', '')
            )
            writer.writerow(row)
        return output.getvalue()

    def export_conflicts_csv(self, limit=5000):
        records = self.list_conflicts(limit=limit)
        output = io.StringIO()
        fieldnames = [
            'id', 'created_at', 'reagent_name', 'batch_number',
            'conflict_type', 'conflict_type_label',
            'source_file',
            'incoming_volume', 'incoming_volume_unit',
            'incoming_expiry_date', 'incoming_is_frozen',
            'existing_batch_id', 'existing_volume', 'existing_volume_unit',
            'existing_expiry_date', 'existing_is_frozen',
            'resolved', 'resolution_note', 'detail',
        ]
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        for r in records:
            row = {k: r.get(k, '') for k in fieldnames}
            row['conflict_type_label'] = self.CONFLICT_TYPE_LABELS.get(
                r.get('conflict_type', ''), r.get('conflict_type', '')
            )
            writer.writerow(row)
        return output.getvalue()

    def export_conflicts_json(self, limit=5000):
        records = self.list_conflicts(limit=limit)
        export_data = {
            'export_time': datetime.now().isoformat(),
            'export_format': 'json',
            'conflict_count': len(records),
            'conflict_type_labels': self.CONFLICT_TYPE_LABELS,
            'conflicts': records,
        }
        return json.dumps(export_data, ensure_ascii=False, indent=2)

    def enrich_history_with_batch_filter(self, history_records, batch_number=None):
        if not batch_number:
            return history_records
        batch_rows = self.db.execute(
            'SELECT id, batch_number, reagent_id FROM reagent_batches WHERE batch_number = ?',
            (batch_number,)
        ).fetchall()
        if not batch_rows:
            return []
        batch_ids = [b['id'] for b in batch_rows]
        placeholders = ','.join('?' * len(batch_ids))
        task_rows = self.db.execute(
            f'''SELECT DISTINCT task_id FROM task_reagent_usage
                WHERE batch_id IN ({placeholders})''',
            batch_ids
        ).fetchall()
        relevant_task_ids = set(t['task_id'] for t in task_rows if t['task_id'])

        placeholders2 = ','.join('?' * len(batch_ids))
        event_task_rows = self.db.execute(
            f'''SELECT DISTINCT task_id FROM batch_trace_ledger
                WHERE batch_id IN ({placeholders2}) AND task_id IS NOT NULL''',
            batch_ids
        ).fetchall()
        for t in event_task_rows:
            if t['task_id']:
                relevant_task_ids.add(t['task_id'])

        enriched = []
        for h in history_records:
            hid = h.get('task_id')
            if hid is None or hid in relevant_task_ids:
                detail = (h.get('detail') or '').lower()
                for b in batch_rows:
                    if b['batch_number'].lower() in detail:
                        enriched.append(h)
                        break
                else:
                    if hid in relevant_task_ids:
                        enriched.append(h)
        return enriched
