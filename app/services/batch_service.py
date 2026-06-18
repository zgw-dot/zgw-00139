from datetime import datetime, date
from app.services.unit_converter import UnitConverter


class BatchService:

    def __init__(self, db):
        self.db = db

    def _is_expired(self, expiry_date_str):
        if not expiry_date_str:
            return False
        try:
            for fmt in ('%Y-%m-%d', '%Y/%m/%d', '%Y.%m.%d'):
                try:
                    exp = datetime.strptime(expiry_date_str.strip(), fmt).date()
                    return exp < date.today()
                except ValueError:
                    continue
            return False
        except Exception:
            return False

    def _get_usable_volume_ul(self, batch):
        vol_ul = UnitConverter.convert_volume(batch['volume'], batch['volume_unit'], 'ul')
        min_usable = batch.get('min_usable_volume')
        if min_usable is not None:
            min_unit = batch.get('min_usable_unit', 'ul')
            min_ul = UnitConverter.convert_volume(min_usable, min_unit, 'ul')
            if vol_ul < min_ul:
                return 0.0
        return max(0.0, vol_ul)

    def _is_batch_usable(self, batch):
        if batch.get('is_frozen'):
            return False
        if self._is_expired(batch.get('expiry_date')):
            return False
        if self._get_usable_volume_ul(batch) <= 0:
            return False
        return True

    def get_usable_batches(self, reagent_id):
        rows = self.db.execute(
            '''SELECT * FROM reagent_batches 
               WHERE reagent_id = ? 
               ORDER BY CASE WHEN expiry_date IS NULL THEN 1 ELSE 0 END, 
                        expiry_date ASC, id ASC''',
            (reagent_id,)
        ).fetchall()
        batches = [dict(r) for r in rows]
        usable = []
        unusable_details = []
        for b in batches:
            if self._is_batch_usable(b):
                usable.append(b)
            else:
                reasons = []
                if b.get('is_frozen'):
                    reasons.append('已冻结')
                if self._is_expired(b.get('expiry_date')):
                    reasons.append(f'已过期 ({b.get("expiry_date")})')
                vol_ul = UnitConverter.convert_volume(b['volume'], b['volume_unit'], 'ul')
                min_usable = b.get('min_usable_volume')
                if min_usable is not None:
                    min_unit = b.get('min_usable_unit', 'ul')
                    min_ul = UnitConverter.convert_volume(min_usable, min_unit, 'ul')
                    if vol_ul < min_ul:
                        reasons.append(f'低于最小可用量 ({vol_ul:.2f} µL < {min_ul:.2f} µL)')
                elif vol_ul <= 0:
                    reasons.append('库存为 0')
                unusable_details.append({
                    'batch_id': b['id'],
                    'batch_number': b['batch_number'],
                    'reasons': reasons,
                    'volume': b['volume'],
                    'volume_unit': b['volume_unit'],
                })
        return usable, unusable_details

    def allocate_batches(self, reagent_id, required_volume_ul, exclude_batch_ids=None):
        exclude = set(exclude_batch_ids or [])
        usable, unusable = self.get_usable_batches(reagent_id)
        usable = [b for b in usable if b['id'] not in exclude]

        total_available_ul = sum(self._get_usable_volume_ul(b) for b in usable)

        if total_available_ul < required_volume_ul:
            reagent = self.db.execute(
                'SELECT name FROM reagents WHERE id = ?', (reagent_id,)
            ).fetchone()
            reagent_name = reagent['name'] if reagent else f'#{reagent_id}'
            error_parts = [f'试剂 {reagent_name} 库存不足: 需要 {required_volume_ul:.2f} µL, 全部可用批次仅 {total_available_ul:.2f} µL']
            if unusable:
                detail = '; '.join(
                    f"{u['batch_number']} ({', '.join(u['reasons'])})" for u in unusable
                )
                error_parts.append(f'不可用批次: {detail}')
            raise ValueError('. '.join(error_parts))

        allocations = []
        remaining = required_volume_ul

        for batch in usable:
            if remaining <= 0:
                break
            avail = self._get_usable_volume_ul(batch)
            if avail <= 0:
                continue
            take = min(avail, remaining)
            allocations.append({
                'batch_id': batch['id'],
                'batch_number': batch['batch_number'],
                'allocated_volume_ul': take,
                'expiry_date': batch.get('expiry_date'),
            })
            remaining -= take

        if remaining > 1e-6:
            raise ValueError('批次分配计算异常，仍有未分配用量')

        return allocations

    def deduct_batch_volume(self, batch_id, deduct_volume_ul, task_id=None, note=None):
        batch = self.db.execute(
            'SELECT * FROM reagent_batches WHERE id = ?', (batch_id,)
        ).fetchone()
        if not batch:
            raise ValueError(f'批次不存在 (id={batch_id})')

        current_ul = UnitConverter.convert_volume(batch['volume'], batch['volume_unit'], 'ul')
        if current_ul < deduct_volume_ul - 1e-6:
            reagent = self.db.execute(
                'SELECT name FROM reagents WHERE id = ?', (batch['reagent_id'],)
            ).fetchone()
            reagent_name = reagent['name'] if reagent else ''
            raise ValueError(
                f'批次 {batch["batch_number"]} ({reagent_name}) 库存不足: '
                f'当前 {current_ul:.2f} µL, 需要扣减 {deduct_volume_ul:.2f} µL'
            )

        new_vol_ul = current_ul - deduct_volume_ul
        new_vol = UnitConverter.convert_volume(new_vol_ul, 'ul', batch['volume_unit'])

        self.db.execute(
            'UPDATE reagent_batches SET volume = ? WHERE id = ?',
            (new_vol, batch_id)
        )

        self.db.execute('''
            INSERT INTO reagent_inventory_log 
            (reagent_id, batch_id, batch_number, change_type, change_volume, change_volume_unit,
             balance_volume, balance_volume_unit, task_id, note)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            batch['reagent_id'],
            batch_id,
            batch['batch_number'],
            'deduct',
            deduct_volume_ul, 'ul',
            new_vol_ul, 'ul',
            task_id,
            note or f'批次 {batch["batch_number"]} 扣减 {deduct_volume_ul:.2f} µL'
        ))

        return new_vol_ul

    def refund_batch_volume(self, batch_id, refund_volume_ul, task_id=None, note=None):
        batch = self.db.execute(
            'SELECT * FROM reagent_batches WHERE id = ?', (batch_id,)
        ).fetchone()
        if not batch:
            raise ValueError(f'批次不存在 (id={batch_id})')

        current_ul = UnitConverter.convert_volume(batch['volume'], batch['volume_unit'], 'ul')
        new_vol_ul = current_ul + refund_volume_ul
        new_vol = UnitConverter.convert_volume(new_vol_ul, 'ul', batch['volume_unit'])

        self.db.execute(
            'UPDATE reagent_batches SET volume = ? WHERE id = ?',
            (new_vol, batch_id)
        )

        self.db.execute('''
            INSERT INTO reagent_inventory_log 
            (reagent_id, batch_id, batch_number, change_type, change_volume, change_volume_unit,
             balance_volume, balance_volume_unit, task_id, note)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            batch['reagent_id'],
            batch_id,
            batch['batch_number'],
            'refund',
            refund_volume_ul, 'ul',
            new_vol_ul, 'ul',
            task_id,
            note or f'批次 {batch["batch_number"]} 退回 {refund_volume_ul:.2f} µL'
        ))

        return new_vol_ul

    def check_batch_occupied_by_later_tasks(self, batch_id, current_task_id):
        rows = self.db.execute(
            '''SELECT DISTINCT tru.task_id, t.name, t.status, tru.used_volume, tru.used_volume_unit
               FROM task_reagent_usage tru
               JOIN tasks t ON t.id = tru.task_id
               WHERE tru.batch_id = ? AND tru.task_id > ?
               ORDER BY tru.task_id ASC''',
            (batch_id, current_task_id)
        ).fetchall()
        if not rows:
            return []
        result = []
        for r in rows:
            d = dict(r)
            if d['status'] == 'approved':
                result.append(d)
        return result

    def check_revoke_conflicts(self, task_id):
        usages = [dict(u) for u in self.db.execute(
            'SELECT * FROM task_reagent_usage WHERE task_id = ? AND batch_id IS NOT NULL',
            (task_id,)
        ).fetchall()]
        conflicts = []
        for u in usages:
            if u['batch_id'] is None:
                continue
            later = self.check_batch_occupied_by_later_tasks(u['batch_id'], task_id)
            if later:
                conflicts.append({
                    'reagent_name': u['reagent_name'],
                    'batch_id': u['batch_id'],
                    'batch_number': u.get('batch_number') or '',
                    'conflicting_tasks': [
                        {
                            'task_id': l['task_id'],
                            'task_name': l['name'],
                            'status': l['status'],
                            'used_volume': l['used_volume'],
                            'used_volume_unit': l['used_volume_unit'],
                        } for l in later
                    ]
                })
        return conflicts
