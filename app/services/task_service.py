import json
from datetime import datetime

from app.services.unit_converter import UnitConverter
from app.services.liquid_handling_engine import LiquidHandlingEngine


class TaskService:
    
    def __init__(self, db):
        self.db = db
        self.engine = LiquidHandlingEngine()
    
    def create_task(self, name, template_id, total_volume, volume_unit='ul'):
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
        
        self._add_history(task_id, 'generate', 'plan_generated', 
                          f'生成配液方案，{len(template_wells)} 个孔位，{len(all_warnings)} 个警告')
        
        return {
            'task_id': task_id,
            'status': 'pending_review',
            'warnings': all_warnings,
            'below_min_pipette': below_min_pipette,
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
