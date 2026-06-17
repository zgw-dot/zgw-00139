import json
from datetime import datetime

from app.services.unit_converter import UnitConverter
from app.services.liquid_handling_engine import LiquidHandlingEngine


class TaskService:
    
    def __init__(self, db):
        self.db = db
        self.engine = LiquidHandlingEngine()
    
    def create_task(self, name, template_id, total_volume, volume_unit='ul'):
        if not UnitConverter.is_volume_unit(volume_unit):
            raise ValueError(f"无效的体积单位: {volume_unit}")
        
        cursor = self.db.execute(
            'INSERT INTO tasks (name, template_id, total_volume, volume_unit, status) VALUES (?, ?, ?, ?, ?)',
            (name, template_id, total_volume, volume_unit, 'draft')
        )
        task_id = cursor.lastrowid
        self.db.commit()
        
        self._add_history(task_id, 'create', 'task_created', f'创建任务: {name}')
        
        return task_id
    
    def generate_plan(self, task_id, sample_assignments=None, primer_id=None, 
                      master_mix_id=None, water_id=None):
        task = self.db.execute(
            'SELECT * FROM tasks WHERE id = ?', (task_id,)
        ).fetchone()
        
        if not task:
            raise ValueError('任务不存在')
        
        if task['status'] not in ['draft', 'rejected']:
            raise ValueError('只有草稿或已驳回状态的任务才能生成方案')
        
        if not UnitConverter.is_volume_unit(task['volume_unit']):
            raise ValueError(f"任务的体积单位无效: {task['volume_unit']}")
        
        template = self.db.execute(
            'SELECT * FROM plate_templates WHERE id = ?', (task['template_id'],)
        ).fetchone()
        
        template_wells = self.db.execute(
            'SELECT * FROM template_wells WHERE template_id = ? ORDER BY well_row, well_col',
            (task['template_id'],)
        ).fetchall()
        
        all_primers = self.db.execute('SELECT * FROM primers').fetchall()
        all_reagents = self.db.execute('SELECT * FROM reagents').fetchall()
        all_samples = self.db.execute('SELECT * FROM samples').fetchall()
        
        for s in all_samples:
            if not UnitConverter.is_volume_unit(s['volume_unit']):
                raise ValueError(f"样本 {s['name']} 的体积单位无效: {s['volume_unit']}")
        for p in all_primers:
            if not UnitConverter.is_volume_unit(p['volume_unit']):
                raise ValueError(f"引物 {p['name']} 的体积单位无效: {p['volume_unit']}")
        for r in all_reagents:
            if not UnitConverter.is_volume_unit(r['volume_unit']):
                raise ValueError(f"试剂 {r['name']} 的体积单位无效: {r['volume_unit']}")
        
        primer = None
        if primer_id:
            primer = self.db.execute('SELECT * FROM primers WHERE id = ?', (primer_id,)).fetchone()
        elif all_primers:
            primer = all_primers[0]
        
        master_mix = None
        if master_mix_id:
            master_mix = self.db.execute('SELECT * FROM reagents WHERE id = ?', (master_mix_id,)).fetchone()
        else:
            for r in all_reagents:
                if r['type'] == 'master_mix':
                    master_mix = r
                    break
        
        water = None
        if water_id:
            water = self.db.execute('SELECT * FROM reagents WHERE id = ?', (water_id,)).fetchone()
        else:
            for r in all_reagents:
                if r['type'] == 'water':
                    water = r
                    break
        
        if not primer:
            raise ValueError('未找到引物，请先导入引物')
        if not master_mix:
            raise ValueError('未找到 Master Mix 试剂')
        if not water:
            raise ValueError('未找到水试剂')
        
        sample_map = {s['name']: s for s in all_samples}
        
        conflicts = self._check_well_conflicts([dict(w) for w in template_wells])
        if conflicts:
            raise ValueError(f'孔位冲突: {json.dumps(conflicts, ensure_ascii=False)}')
        
        min_pipette = master_mix['min_pipette_volume'] if master_mix['min_pipette_volume'] else None
        
        self.db.execute('DELETE FROM task_wells WHERE task_id = ?', (task_id,))
        self.db.execute('DELETE FROM task_reagent_usage WHERE task_id = ?', (task_id,))
        self.db.execute('DELETE FROM task_primer_usage WHERE task_id = ?', (task_id,))
        
        reagent_usage = {}
        primer_usage = {'total': 0, 'unit': 'ul'}
        all_warnings = []
        below_min_pipette = False
        
        for well in template_wells:
            well_dict = dict(well)
            well_type = well_dict['well_type']
            
            sample_name = None
            sample = None
            sample_vol = 0
            sample_conc = None
            sample_conc_unit = None
            
            if well_type == 'sample':
                if sample_assignments:
                    well_key = f"{well_dict['well_row']}_{well_dict['well_col']}"
                    sample_name = sample_assignments.get(well_key)
                elif well_dict.get('sample_name'):
                    sample_name = well_dict['sample_name']
                
                if sample_name and sample_name in sample_map:
                    sample = sample_map[sample_name]
                elif not sample_name and all_samples:
                    sample = all_samples[0]
                    sample_name = sample['name']
            
            if well_type in ['sample', 'positive_control']:
                if well_type == 'positive_control':
                    recipe = self.engine.calculate_control_well(
                        'positive', primer, master_mix, water,
                        task['total_volume'], task['volume_unit'], min_pipette
                    )
                    sample_name = 'Positive Control'
                else:
                    recipe = self.engine.calculate_well_recipe(
                        sample, primer, master_mix, water,
                        task['total_volume'], task['volume_unit'], min_pipette
                    )
                
                if sample:
                    sample_vol = recipe['sample_volume']
                    sample_conc = sample['concentration']
                    sample_conc_unit = sample['concentration_unit']
                
                if recipe.get('warnings'):
                    for w in recipe['warnings']:
                        if w.get('type') == 'min_pipette':
                            below_min_pipette = True
                    all_warnings.append({
                        'well': f"{chr(64 + well_dict['well_row'])}{well_dict['well_col']}",
                        'warnings': recipe['warnings']
                    })
                
                self.db.execute('''
                    INSERT INTO task_wells 
                    (task_id, well_row, well_col, well_type, sample_name, 
                     sample_volume, sample_volume_unit, sample_concentration, sample_concentration_unit,
                     primer_name, primer_volume, primer_volume_unit, primer_concentration, primer_concentration_unit,
                     master_mix_volume, master_mix_unit, water_volume, water_unit,
                     total_volume, total_volume_unit, note)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    task_id, well_dict['well_row'], well_dict['well_col'], well_type,
                    sample_name or '',
                    sample_vol, 'ul', sample_conc, sample_conc_unit,
                    primer['name'], recipe['primer_volume'], 'ul', 
                    primer['concentration'], primer['concentration_unit'],
                    recipe['master_mix_volume'], 'ul',
                    recipe['water_volume'], 'ul',
                    recipe['total_volume'], 'ul',
                    well_dict.get('note', '')
                ))
                
                primer_usage['total'] += recipe['primer_volume']
                
                mm_key = ('reagent', master_mix['id'])
                if mm_key not in reagent_usage:
                    reagent_usage[mm_key] = {
                        'id': master_mix['id'],
                        'name': master_mix['name'],
                        'volume': 0,
                        'unit': 'ul',
                        'source': 'master_mix'
                    }
                reagent_usage[mm_key]['volume'] += recipe['master_mix_volume']
                
                water_key = ('reagent', water['id'])
                if water_key not in reagent_usage:
                    reagent_usage[water_key] = {
                        'id': water['id'],
                        'name': water['name'],
                        'volume': 0,
                        'unit': 'ul',
                        'source': 'water'
                    }
                reagent_usage[water_key]['volume'] += recipe['water_volume']
            
            elif well_type == 'negative_control':
                recipe = self.engine.calculate_control_well(
                    'negative', primer, master_mix, water,
                    task['total_volume'], task['volume_unit'], min_pipette
                )
                
                if recipe.get('warnings'):
                    all_warnings.append({
                        'well': f"{chr(64 + well_dict['well_row'])}{well_dict['well_col']}",
                        'warnings': recipe['warnings']
                    })
                
                self.db.execute('''
                    INSERT INTO task_wells 
                    (task_id, well_row, well_col, well_type, sample_name, 
                     sample_volume, sample_volume_unit,
                     primer_name, primer_volume, primer_volume_unit, primer_concentration, primer_concentration_unit,
                     master_mix_volume, master_mix_unit, water_volume, water_unit,
                     total_volume, total_volume_unit, note)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    task_id, well_dict['well_row'], well_dict['well_col'], well_type,
                    'Negative Control',
                    0, 'ul',
                    primer['name'], recipe['primer_volume'], 'ul', 
                    primer['concentration'], primer['concentration_unit'],
                    recipe['master_mix_volume'], 'ul',
                    recipe['water_volume'], 'ul',
                    recipe['total_volume'], 'ul',
                    well_dict.get('note', '')
                ))
                
                primer_usage['total'] += recipe['primer_volume']
                
                mm_key = ('reagent', master_mix['id'])
                if mm_key not in reagent_usage:
                    reagent_usage[mm_key] = {
                        'id': master_mix['id'],
                        'name': master_mix['name'],
                        'volume': 0,
                        'unit': 'ul',
                        'source': 'master_mix'
                    }
                reagent_usage[mm_key]['volume'] += recipe['master_mix_volume']
                
                water_key = ('reagent', water['id'])
                if water_key not in reagent_usage:
                    reagent_usage[water_key] = {
                        'id': water['id'],
                        'name': water['name'],
                        'volume': 0,
                        'unit': 'ul',
                        'source': 'water'
                    }
                reagent_usage[water_key]['volume'] += recipe['water_volume']
            
            else:
                self.db.execute('''
                    INSERT INTO task_wells 
                    (task_id, well_row, well_col, well_type, total_volume, total_volume_unit, note)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    task_id, well_dict['well_row'], well_dict['well_col'], well_type,
                    0, 'ul', well_dict.get('note', '')
                ))
        
        for key, usage in reagent_usage.items():
            self.db.execute('''
                INSERT INTO task_reagent_usage (task_id, reagent_id, reagent_name, used_volume, used_volume_unit, source)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (task_id, usage['id'], usage['name'], usage['volume'], usage['unit'], usage['source']))
        
        self.db.execute('''
            INSERT INTO task_primer_usage (task_id, primer_id, primer_name, used_volume, used_volume_unit, source)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (task_id, primer['id'], primer['name'], primer_usage['total'], primer_usage['unit'], 'primer'))
        
        self.db.execute(
            "UPDATE tasks SET status = 'pending_review', updated_at = ? WHERE id = ?",
            (datetime.now().isoformat(), task_id)
        )
        self.db.commit()

        from app.services.snapshot_service import SnapshotService
        snapshot_service = SnapshotService(self.db)
        snapshot_info = snapshot_service.create_snapshot(task_id, 'generate', '生成配液方案')

        self._add_history(task_id, 'generate', 'plan_generated',
                          f'生成配液方案，{len(template_wells)} 个孔位，{len(all_warnings)} 个警告，快照 v{snapshot_info["version"]}')

        return {
            'task_id': task_id,
            'status': 'pending_review',
            'warnings': all_warnings,
            'below_min_pipette': below_min_pipette,
            'snapshot_version': snapshot_info['version'],
            'reagent_usage': [{'name': v['name'], 'volume': v['volume'], 'unit': v['unit'], 'source': v['source']}
                             for v in reagent_usage.values()],
            'primer_usage': {'name': primer['name'], 'volume': primer_usage['total'], 'unit': 'ul'},
        }
    
    def approve_task(self, task_id, operator='user', ignore_min_pipette=False):
        task = self.db.execute('SELECT * FROM tasks WHERE id = ?', (task_id,)).fetchone()
        if not task:
            raise ValueError('任务不存在')

        if task['status'] != 'pending_review':
            raise ValueError('只有待复核状态的任务才能批准')

        from app.services.snapshot_service import SnapshotService
        snapshot_service = SnapshotService(self.db)
        snapshot_info = snapshot_service.create_snapshot(task_id, 'pre_approve', '批准前快照')
        
        task_wells = self.db.execute(
            'SELECT * FROM task_wells WHERE task_id = ?', (task_id,)
        ).fetchall()
        
        has_min_pipette_warning = False
        for well in task_wells:
            if well['primer_volume'] and well['primer_volume'] < 0.5:
                has_min_pipette_warning = True
                break
            if well['master_mix_volume'] and well['master_mix_volume'] < 0.5:
                has_min_pipette_warning = True
                break
            if well['sample_volume'] and well['sample_volume'] < 0.5:
                has_min_pipette_warning = True
                break
        
        if has_min_pipette_warning and not ignore_min_pipette:
            raise ValueError('存在低于最小移液体积的孔，不能直接批准。如有偏差，请添加偏差备注后再批准。')
        
        reagent_usage = self.db.execute(
            'SELECT * FROM task_reagent_usage WHERE task_id = ?', (task_id,)
        ).fetchall()
        
        primer_usage = self.db.execute(
            'SELECT * FROM task_primer_usage WHERE task_id = ?', (task_id,)
        ).fetchall()
        
        for usage in reagent_usage:
            reagent = self.db.execute(
                'SELECT * FROM reagents WHERE id = ?', (usage['reagent_id'],)
            ).fetchone()
            
            if not reagent:
                raise ValueError(f'试剂不存在: {usage["reagent_name"]}')
            
            available_vol = UnitConverter.convert_volume(
                reagent['volume'], reagent['volume_unit'], 'ul'
            )
            used_vol = UnitConverter.convert_volume(
                usage['used_volume'], usage['used_volume_unit'], 'ul'
            )
            
            if available_vol < used_vol:
                raise ValueError(f'试剂库存不足: {reagent["name"]}, 可用 {available_vol:.2f} µL, 需要 {used_vol:.2f} µL')
        
        for usage in primer_usage:
            primer = self.db.execute(
                'SELECT * FROM primers WHERE id = ?', (usage['primer_id'],)
            ).fetchone()
            
            if not primer:
                raise ValueError(f'引物不存在: {usage["primer_name"]}')
            
            available_vol = UnitConverter.convert_volume(
                primer['volume'], primer['volume_unit'], 'ul'
            )
            used_vol = UnitConverter.convert_volume(
                usage['used_volume'], usage['used_volume_unit'], 'ul'
            )
            
            if available_vol < used_vol:
                raise ValueError(f'引物库存不足: {primer["name"]}, 可用 {available_vol:.2f} µL, 需要 {used_vol:.2f} µL')
        
        for usage in reagent_usage:
            reagent = self.db.execute(
                'SELECT * FROM reagents WHERE id = ?', (usage['reagent_id'],)
            ).fetchone()
            
            current_vol_ul = UnitConverter.convert_volume(
                reagent['volume'], reagent['volume_unit'], 'ul'
            )
            used_vol_ul = UnitConverter.convert_volume(
                usage['used_volume'], usage['used_volume_unit'], 'ul'
            )
            new_vol_ul = current_vol_ul - used_vol_ul
            
            new_vol = UnitConverter.convert_volume(new_vol_ul, 'ul', reagent['volume_unit'])
            
            self.db.execute(
                'UPDATE reagents SET volume = ? WHERE id = ?',
                (new_vol, usage['reagent_id'])
            )
            
            self.db.execute('''
                INSERT INTO reagent_inventory_log 
                (reagent_id, change_type, change_volume, change_volume_unit, 
                 balance_volume, balance_volume_unit, task_id, note)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                usage['reagent_id'], 'deduct', 
                usage['used_volume'], usage['used_volume_unit'],
                new_vol_ul, 'ul',
                task_id, f'任务 #{task_id} 扣减'
            ))
        
        for usage in primer_usage:
            primer = self.db.execute(
                'SELECT * FROM primers WHERE id = ?', (usage['primer_id'],)
            ).fetchone()
            
            current_vol_ul = UnitConverter.convert_volume(
                primer['volume'], primer['volume_unit'], 'ul'
            )
            used_vol_ul = UnitConverter.convert_volume(
                usage['used_volume'], usage['used_volume_unit'], 'ul'
            )
            new_vol_ul = current_vol_ul - used_vol_ul
            
            new_vol = UnitConverter.convert_volume(new_vol_ul, 'ul', primer['volume_unit'])
            
            self.db.execute(
                'UPDATE primers SET volume = ? WHERE id = ?',
                (new_vol, usage['primer_id'])
            )
            
            self.db.execute('''
                INSERT INTO primer_inventory_log 
                (primer_id, change_type, change_volume, change_volume_unit, 
                 balance_volume, balance_volume_unit, task_id, note)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                usage['primer_id'], 'deduct', 
                usage['used_volume'], usage['used_volume_unit'],
                new_vol_ul, 'ul',
                task_id, f'任务 #{task_id} 扣减'
            ))
        
        self.db.execute(
            "UPDATE tasks SET status = 'approved', updated_at = ? WHERE id = ?",
            (datetime.now().isoformat(), task_id)
        )
        self.db.commit()
        
        self._add_history(task_id, 'approve', 'task_approved', 
                          f'任务已批准，扣减库存。操作人: {operator}')
        
        return True
    
    def reject_task(self, task_id, reason, operator='user'):
        task = self.db.execute('SELECT * FROM tasks WHERE id = ?', (task_id,)).fetchone()
        if not task:
            raise ValueError('任务不存在')
        
        if task['status'] != 'pending_review':
            raise ValueError('只有待复核状态的任务才能驳回')
        
        self.db.execute(
            "UPDATE tasks SET status = 'rejected', rejected_reason = ?, updated_at = ? WHERE id = ?",
            (reason, datetime.now().isoformat(), task_id)
        )
        self.db.commit()
        
        self._add_history(task_id, 'reject', 'task_rejected', 
                          f'任务被驳回，原因: {reason}。操作人: {operator}')
        
        return True
    
    def revoke_approval(self, task_id, operator='user'):
        task = self.db.execute('SELECT * FROM tasks WHERE id = ?', (task_id,)).fetchone()
        if not task:
            raise ValueError('任务不存在')
        
        if task['status'] != 'approved':
            raise ValueError('只有已批准的任务才能撤销确认')
        
        reagent_usage = self.db.execute(
            'SELECT * FROM task_reagent_usage WHERE task_id = ?', (task_id,)
        ).fetchall()
        
        primer_usage = self.db.execute(
            'SELECT * FROM task_primer_usage WHERE task_id = ?', (task_id,)
        ).fetchall()
        
        for usage in reagent_usage:
            reagent = self.db.execute(
                'SELECT * FROM reagents WHERE id = ?', (usage['reagent_id'],)
            ).fetchone()
            
            current_vol_ul = UnitConverter.convert_volume(
                reagent['volume'], reagent['volume_unit'], 'ul'
            )
            used_vol_ul = UnitConverter.convert_volume(
                usage['used_volume'], usage['used_volume_unit'], 'ul'
            )
            new_vol_ul = current_vol_ul + used_vol_ul
            
            new_vol = UnitConverter.convert_volume(new_vol_ul, 'ul', reagent['volume_unit'])
            
            self.db.execute(
                'UPDATE reagents SET volume = ? WHERE id = ?',
                (new_vol, usage['reagent_id'])
            )
            
            self.db.execute('''
                INSERT INTO reagent_inventory_log 
                (reagent_id, change_type, change_volume, change_volume_unit, 
                 balance_volume, balance_volume_unit, task_id, note)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                usage['reagent_id'], 'refund', 
                usage['used_volume'], usage['used_volume_unit'],
                new_vol_ul, 'ul',
                task_id, f'任务 #{task_id} 撤销确认，退回库存'
            ))
        
        for usage in primer_usage:
            primer = self.db.execute(
                'SELECT * FROM primers WHERE id = ?', (usage['primer_id'],)
            ).fetchone()
            
            current_vol_ul = UnitConverter.convert_volume(
                primer['volume'], primer['volume_unit'], 'ul'
            )
            used_vol_ul = UnitConverter.convert_volume(
                usage['used_volume'], usage['used_volume_unit'], 'ul'
            )
            new_vol_ul = current_vol_ul + used_vol_ul
            
            new_vol = UnitConverter.convert_volume(new_vol_ul, 'ul', primer['volume_unit'])
            
            self.db.execute(
                'UPDATE primers SET volume = ? WHERE id = ?',
                (new_vol, usage['primer_id'])
            )
            
            self.db.execute('''
                INSERT INTO primer_inventory_log 
                (primer_id, change_type, change_volume, change_volume_unit, 
                 balance_volume, balance_volume_unit, task_id, note)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                usage['primer_id'], 'refund', 
                usage['used_volume'], usage['used_volume_unit'],
                new_vol_ul, 'ul',
                task_id, f'任务 #{task_id} 撤销确认，退回库存'
            ))
        
        self.db.execute(
            "UPDATE tasks SET status = 'revoked', updated_at = ? WHERE id = ?",
            (datetime.now().isoformat(), task_id)
        )
        self.db.commit()
        
        self._add_history(task_id, 'revoke', 'approval_revoked', 
                          f'撤销确认，库存已退回。操作人: {operator}')
        
        return True
    
    def add_deviation_note(self, task_id, note, operator='user'):
        task = self.db.execute('SELECT * FROM tasks WHERE id = ?', (task_id,)).fetchone()
        if not task:
            raise ValueError('任务不存在')
        
        self.db.execute(
            "UPDATE tasks SET deviation_note = ?, updated_at = ? WHERE id = ?",
            (note, datetime.now().isoformat(), task_id)
        )
        self.db.commit()
        
        self._add_history(task_id, 'deviation', 'deviation_note_added', 
                          f'添加偏差备注: {note}。操作人: {operator}')
        
        return True
    
    def get_task(self, task_id):
        task = self.db.execute('SELECT * FROM tasks WHERE id = ?', (task_id,)).fetchone()
        if not task:
            return None
        
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
        
        return {
            'task': dict(task),
            'wells': [dict(w) for w in wells],
            'reagent_usage': [dict(r) for r in reagent_usage],
            'primer_usage': [dict(p) for p in primer_usage],
        }
    
    def list_tasks(self, status=None):
        if status:
            tasks = self.db.execute(
                'SELECT * FROM tasks WHERE status = ? ORDER BY created_at DESC',
                (status,)
            ).fetchall()
        else:
            tasks = self.db.execute(
                'SELECT * FROM tasks ORDER BY created_at DESC'
            ).fetchall()
        
        return [dict(t) for t in tasks]
    
    def _check_well_conflicts(self, wells):
        well_map = {}
        conflicts = []
        
        for well in wells:
            key = (well['well_row'], well['well_col'])
            if key in well_map:
                conflicts.append({
                    'well': f"{chr(64 + well['well_row'])}{well['well_col']}",
                    'existing_type': well_map[key].get('well_type'),
                    'new_type': well.get('well_type')
                })
            else:
                well_map[key] = well
        
        return conflicts
    
    def _add_history(self, task_id, action, action_type, detail):
        self.db.execute('''
            INSERT INTO history (task_id, action, action_type, detail, operator)
            VALUES (?, ?, ?, ?, ?)
        ''', (task_id, action, action_type, detail, 'system'))
        self.db.commit()
    
    def copy_task(self, task_id, new_name=None):
        task = self.db.execute('SELECT * FROM tasks WHERE id = ?', (task_id,)).fetchone()
        if not task:
            raise ValueError('任务不存在')
        
        if task['status'] not in ['draft', 'pending_review', 'approved']:
            raise ValueError('只有草稿、待复核、已批准状态的任务才能复制')
        
        if not UnitConverter.is_volume_unit(task['volume_unit']):
            raise ValueError(f"任务的体积单位无效: {task['volume_unit']}")
        
        base_name = new_name if new_name else task['name']
        final_name = f'{base_name}_副本'
        suffix = 1
        while self.db.execute('SELECT id FROM tasks WHERE name = ?', (final_name,)).fetchone():
            suffix += 1
            final_name = f'{base_name}_副本{suffix}'
        
        cursor = self.db.execute(
            'INSERT INTO tasks (name, template_id, total_volume, volume_unit, status) VALUES (?, ?, ?, ?, ?)',
            (final_name, task['template_id'], task['total_volume'], task['volume_unit'], 'draft')
        )
        new_task_id = cursor.lastrowid
        
        task_wells = self.db.execute(
            'SELECT * FROM task_wells WHERE task_id = ? ORDER BY well_row, well_col',
            (task_id,)
        ).fetchall()
        
        if task_wells:
            for well in task_wells:
                self.db.execute('''
                    INSERT INTO task_wells 
                    (task_id, well_row, well_col, well_type, sample_name, 
                     sample_volume, sample_volume_unit, sample_concentration, sample_concentration_unit,
                     primer_name, primer_volume, primer_volume_unit, primer_concentration, primer_concentration_unit,
                     master_mix_volume, master_mix_unit, water_volume, water_unit,
                     total_volume, total_volume_unit, note)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    new_task_id, well['well_row'], well['well_col'], well['well_type'],
                    well['sample_name'],
                    well['sample_volume'], well['sample_volume_unit'],
                    well['sample_concentration'], well['sample_concentration_unit'],
                    well['primer_name'], well['primer_volume'], well['primer_volume_unit'],
                    well['primer_concentration'], well['primer_concentration_unit'],
                    well['master_mix_volume'], well['master_mix_unit'],
                    well['water_volume'], well['water_unit'],
                    well['total_volume'], well['total_volume_unit'],
                    well['note']
                ))
        
        reagent_usage = self.db.execute(
            'SELECT * FROM task_reagent_usage WHERE task_id = ?',
            (task_id,)
        ).fetchall()
        
        if reagent_usage:
            for usage in reagent_usage:
                self.db.execute('''
                    INSERT INTO task_reagent_usage (task_id, reagent_id, reagent_name, used_volume, used_volume_unit, source)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (
                    new_task_id, usage['reagent_id'], usage['reagent_name'],
                    usage['used_volume'], usage['used_volume_unit'], usage['source']
                ))
        
        primer_usage = self.db.execute(
            'SELECT * FROM task_primer_usage WHERE task_id = ?',
            (task_id,)
        ).fetchall()
        
        if primer_usage:
            for usage in primer_usage:
                self.db.execute('''
                    INSERT INTO task_primer_usage (task_id, primer_id, primer_name, used_volume, used_volume_unit, source)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (
                    new_task_id, usage['primer_id'], usage['primer_name'],
                    usage['used_volume'], usage['used_volume_unit'], usage['source']
                ))
        
        self.db.commit()

        from app.services.snapshot_service import SnapshotService
        snapshot_service = SnapshotService(self.db)
        snapshot_info = snapshot_service.create_snapshot(new_task_id, 'copy', f'从任务 #{task_id} 复制')

        self._add_history(new_task_id, 'copy', 'task_copied',
                          f'从任务 #{task_id} ({task["name"]}) 复制为新草稿，快照 v{snapshot_info["version"]}')
        self._add_history(task_id, 'copy', 'task_copied_from',
                          f'被复制为新任务 #{new_task_id} ({final_name})')

        return new_task_id
    
    def export_task_json(self, task_id):
        task = self.db.execute('SELECT * FROM tasks WHERE id = ?', (task_id,)).fetchone()
        if not task:
            raise ValueError('任务不存在')

        template = self.db.execute(
            'SELECT * FROM plate_templates WHERE id = ?', (task['template_id'],)
        ).fetchone()

        task_wells = self.db.execute(
            'SELECT well_row, well_col, well_type, sample_name, note FROM task_wells WHERE task_id = ? ORDER BY well_row, well_col',
            (task_id,)
        ).fetchall()

        reagent_usage = self.db.execute(
            'SELECT reagent_name, source, used_volume, used_volume_unit FROM task_reagent_usage WHERE task_id = ?',
            (task_id,)
        ).fetchall()

        primer_usage = self.db.execute(
            'SELECT primer_name, source, used_volume, used_volume_unit FROM task_primer_usage WHERE task_id = ?',
            (task_id,)
        ).fetchall()

        from app.services.snapshot_service import SnapshotService
        snapshot_service = SnapshotService(self.db)
        snapshots_summary = snapshot_service.get_snapshot_summary_for_export(task_id)

        export_data = {
            'schema_version': '1.1',
            'task': {
                'name': task['name'],
                'total_volume': task['total_volume'],
                'volume_unit': task['volume_unit'],
                'status': task['status'],
            },
            'template': {
                'name': template['name'] if template else None,
                'rows': template['rows'] if template else None,
                'cols': template['cols'] if template else None,
            },
            'wells': [dict(w) for w in task_wells],
            'reagent_usage': [dict(r) for r in reagent_usage],
            'primer_usage': [dict(p) for p in primer_usage],
            'snapshots': snapshots_summary,
        }

        self._add_history(task_id, 'export', 'task_exported',
                          f'导出任务方案为 JSON: {task["name"]}，包含 {snapshots_summary["snapshot_count"]} 个快照')

        return json.dumps(export_data, ensure_ascii=False, indent=2)
    
    def import_task_json(self, json_content, conflict_mode='reject'):
        task_name = '未知任务'
        try:
            try:
                data = json.loads(json_content)
            except json.JSONDecodeError as e:
                raise ValueError(f'JSON 解析失败: {str(e)}')

            if not data.get('task'):
                raise ValueError('JSON 缺少 task 字段')
            if not data.get('template'):
                raise ValueError('JSON 缺少 template 字段')

            from app.services.snapshot_service import SnapshotService
            snapshot_service = SnapshotService(self.db)

            task_name = data['task'].get('name', '导入任务')
            total_volume = data['task'].get('total_volume')
            volume_unit = data['task'].get('volume_unit', 'ul')
            template_name = data['template'].get('name')
            template_rows = data['template'].get('rows')
            template_cols = data['template'].get('cols')
            wells = data.get('wells', [])
            reagent_usage = data.get('reagent_usage', [])
            primer_usage = data.get('primer_usage', [])

            check_name_dup = (conflict_mode == 'reject')
            snapshot_errors = snapshot_service.validate_import_snapshots(
                task_name, data, check_name_duplicate=check_name_dup
            )
            if snapshot_errors:
                raise ValueError('导入校验失败: ' + '; '.join(snapshot_errors))

            if total_volume is None:
                raise ValueError('任务缺少 total_volume')
            if not template_name:
                raise ValueError('模板缺少 name')
            if template_rows is None or template_cols is None:
                raise ValueError('模板缺少 rows 或 cols')

            if not UnitConverter.is_volume_unit(volume_unit):
                raise ValueError(f'无效的体积单位: {volume_unit}')

            template = self.db.execute(
                'SELECT * FROM plate_templates WHERE name = ?', (template_name,)
            ).fetchone()

            if not template:
                raise ValueError(f'模板不存在: {template_name}。请先导入对应模板。')

            if template['rows'] != template_rows or template['cols'] != template_cols:
                raise ValueError(
                    f'模板尺寸不匹配: 导入期望 {template_rows}×{template_cols}，'
                    f'实际模板 {template["rows"]}×{template["cols"]}'
                )

            existing_task = self.db.execute(
                'SELECT id FROM tasks WHERE name = ?', (task_name,)
            ).fetchone()

            if existing_task:
                if conflict_mode == 'reject':
                    raise ValueError(f'任务名称已存在: {task_name}')
                elif conflict_mode == 'rename':
                    suffix = 2
                    while self.db.execute(
                        'SELECT id FROM tasks WHERE name = ?', (f'{task_name}_{suffix}',)
                    ).fetchone():
                        suffix += 1
                    task_name = f'{task_name}_{suffix}'
                elif conflict_mode == 'overwrite':
                    raise ValueError('任务不支持覆盖模式，请使用 rename 或 reject')
                else:
                    raise ValueError(f'无效的冲突处理模式: {conflict_mode}')

            missing_reagents = []
            for usage in reagent_usage:
                reagent = self.db.execute(
                    'SELECT * FROM reagents WHERE name = ?', (usage['reagent_name'],)
                ).fetchone()
                if not reagent:
                    missing_reagents.append(usage['reagent_name'])

            if missing_reagents:
                raise ValueError(f'缺少试剂: {", ".join(missing_reagents)}。请先导入对应试剂。')

            missing_primers = []
            for usage in primer_usage:
                primer = self.db.execute(
                    'SELECT * FROM primers WHERE name = ?', (usage['primer_name'],)
                ).fetchone()
                if not primer:
                    missing_primers.append(usage['primer_name'])

            if missing_primers:
                raise ValueError(f'缺少引物: {", ".join(missing_primers)}。请先导入对应引物。')

            self.db.execute('BEGIN')

            cursor = self.db.execute(
                'INSERT INTO tasks (name, template_id, total_volume, volume_unit, status) VALUES (?, ?, ?, ?, ?)',
                (task_name, template['id'], total_volume, volume_unit, 'draft')
            )
            new_task_id = cursor.lastrowid

            if wells:
                for well in wells:
                    self.db.execute('''
                        INSERT INTO task_wells
                        (task_id, well_row, well_col, well_type, sample_name, note)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (
                        new_task_id,
                        well.get('well_row'),
                        well.get('well_col'),
                        well.get('well_type', 'sample'),
                        well.get('sample_name'),
                        well.get('note', '')
                    ))

            if reagent_usage:
                for usage in reagent_usage:
                    reagent = self.db.execute(
                        'SELECT id FROM reagents WHERE name = ?', (usage['reagent_name'],)
                    ).fetchone()
                    if reagent:
                        self.db.execute('''
                            INSERT INTO task_reagent_usage (task_id, reagent_id, reagent_name, used_volume, used_volume_unit, source)
                            VALUES (?, ?, ?, ?, ?, ?)
                        ''', (
                            new_task_id, reagent['id'], usage['reagent_name'],
                            usage.get('used_volume', 0),
                            usage.get('used_volume_unit', 'ul'),
                            usage.get('source', '')
                        ))

            if primer_usage:
                for usage in primer_usage:
                    primer = self.db.execute(
                        'SELECT id FROM primers WHERE name = ?', (usage['primer_name'],)
                    ).fetchone()
                    if primer:
                        self.db.execute('''
                            INSERT INTO task_primer_usage (task_id, primer_id, primer_name, used_volume, used_volume_unit, source)
                            VALUES (?, ?, ?, ?, ?, ?)
                        ''', (
                            new_task_id, primer['id'], usage['primer_name'],
                            usage.get('used_volume', 0),
                            usage.get('used_volume_unit', 'ul'),
                            usage.get('source', '')
                        ))

            self.db.commit()

            snapshot_info = snapshot_service.create_snapshot(new_task_id, 'import', '从 JSON 导入任务')
            imported_snap_count = snapshot_service.import_snapshots(new_task_id, data)

            self._add_history(new_task_id, 'import', 'task_imported',
                              f'从 JSON 导入任务: {task_name}，导入 {imported_snap_count} 个历史快照，当前快照 v{snapshot_info["version"]}')

            return new_task_id
        except Exception as e:
            try:
                self.db.rollback()
            except Exception:
                pass
            self._add_history(None, 'import', 'task_import_failed',
                              f'导入任务失败: {task_name}，原因: {str(e)}')
            raise e
