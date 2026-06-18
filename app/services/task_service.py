import json
from datetime import datetime

from app.services.unit_converter import UnitConverter
from app.services.liquid_handling_engine import LiquidHandlingEngine
from app.services.batch_service import BatchService


class TaskService:
    
    def __init__(self, db):
        self.db = db
        self.engine = LiquidHandlingEngine()
        self.batch_service = BatchService(db)
        from app.services.batch_trace_service import BatchTraceService
        self._trace_service = BatchTraceService(db)
    
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
        
        batch_allocations_summary = []
        for key, usage in reagent_usage.items():
            required_ul = UnitConverter.convert_volume(
                usage['volume'], usage['unit'], 'ul'
            )
            try:
                allocations = self.batch_service.allocate_batches(usage['id'], required_ul)
            except ValueError as e:
                raise ValueError(f'试剂 {usage["name"]} 批次分配失败: {str(e)}')
            
            for alloc in allocations:
                self.db.execute('''
                    INSERT INTO task_reagent_usage 
                    (task_id, reagent_id, reagent_name, batch_id, batch_number, 
                     used_volume, used_volume_unit, source)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    task_id, usage['id'], usage['name'],
                    alloc['batch_id'], alloc['batch_number'],
                    alloc['allocated_volume_ul'], 'ul',
                    usage['source']
                ))
                batch_allocations_summary.append({
                    'reagent_name': usage['name'],
                    'batch_number': alloc['batch_number'],
                    'volume': alloc['allocated_volume_ul'],
                    'unit': 'ul',
                    'expiry_date': alloc.get('expiry_date'),
                    'source': usage['source'],
                })
                if alloc.get('batch_id'):
                    try:
                        self._trace_service.log_allocate(
                            batch_id=alloc['batch_id'],
                            task_id=task_id,
                            allocated_volume_ul=alloc['allocated_volume_ul'],
                            source='plan',
                        )
                    except Exception:
                        pass
        
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

        batch_desc_parts = []
        by_reagent = {}
        for b in batch_allocations_summary:
            key = b['reagent_name']
            if key not in by_reagent:
                by_reagent[key] = []
            by_reagent[key].append(f"{b['batch_number']}({b['volume']:.1f}{b['unit']})")
        for name, batches in by_reagent.items():
            batch_desc_parts.append(f"{name}: {', '.join(batches)}")
        batch_desc = '; '.join(batch_desc_parts) if batch_desc_parts else '无'

        self._add_history(task_id, 'generate', 'plan_generated',
                          f'生成配液方案，{len(template_wells)} 个孔位，{len(all_warnings)} 个警告，'
                          f'批次分配: {batch_desc}，快照 v{snapshot_info["version"]}')

        return {
            'task_id': task_id,
            'status': 'pending_review',
            'warnings': all_warnings,
            'below_min_pipette': below_min_pipette,
            'snapshot_version': snapshot_info['version'],
            'reagent_usage': [{'name': v['name'], 'volume': v['volume'], 'unit': v['unit'], 'source': v['source']}
                             for v in reagent_usage.values()],
            'batch_allocations': batch_allocations_summary,
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
        
        reagent_usage = [dict(r) for r in self.db.execute(
            'SELECT * FROM task_reagent_usage WHERE task_id = ?', (task_id,)
        ).fetchall()]
        
        primer_usage = [dict(r) for r in self.db.execute(
            'SELECT * FROM task_primer_usage WHERE task_id = ?', (task_id,)
        ).fetchall()]
        
        for usage in reagent_usage:
            reagent = self.db.execute(
                'SELECT * FROM reagents WHERE id = ?', (usage['reagent_id'],)
            ).fetchone()
            
            if not reagent:
                raise ValueError(f'试剂不存在: {usage["reagent_name"]}')
            
            used_vol = UnitConverter.convert_volume(
                usage['used_volume'], usage['used_volume_unit'], 'ul'
            )
            
            if usage.get('batch_id'):
                batch = self.db.execute(
                    'SELECT * FROM reagent_batches WHERE id = ?', (usage['batch_id'],)
                ).fetchone()
                if not batch:
                    raise ValueError(
                        f'试剂 {usage["reagent_name"]} 的批次 {usage.get("batch_number", "")} 不存在，可能已被删除'
                    )
                available_vol = UnitConverter.convert_volume(
                    batch['volume'], batch['volume_unit'], 'ul'
                )
                if available_vol < used_vol:
                    raise ValueError(
                        f'试剂 {reagent["name"]} 批次 {batch["batch_number"]} 库存不足: '
                        f'可用 {available_vol:.2f} µL, 需要 {used_vol:.2f} µL'
                    )
            else:
                available_vol = UnitConverter.convert_volume(
                    reagent['volume'], reagent['volume_unit'], 'ul'
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
        
        batch_deduct_details = []
        for usage in reagent_usage:
            reagent = self.db.execute(
                'SELECT * FROM reagents WHERE id = ?', (usage['reagent_id'],)
            ).fetchone()
            
            used_vol_ul = UnitConverter.convert_volume(
                usage['used_volume'], usage['used_volume_unit'], 'ul'
            )
            
            if usage.get('batch_id'):
                new_vol_ul = self.batch_service.deduct_batch_volume(
                    usage['batch_id'], used_vol_ul, task_id=task_id,
                    note=f'任务 #{task_id} 批准扣减'
                )
                batch_deduct_details.append(
                    f'{reagent["name"]}-{usage.get("batch_number", "")}: -{used_vol_ul:.1f}ul (余 {new_vol_ul:.1f}ul)'
                )
                try:
                    self._trace_service.log_deduct(
                        batch_id=usage['batch_id'],
                        task_id=task_id,
                        deducted_volume_ul=used_vol_ul,
                        operator=operator,
                    )
                except Exception:
                    pass
            else:
                current_vol_ul = UnitConverter.convert_volume(
                    reagent['volume'], reagent['volume_unit'], 'ul'
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
                batch_deduct_details.append(f'{reagent["name"]}: -{used_vol_ul:.1f}ul')
            
            current_vol_ul = UnitConverter.convert_volume(
                reagent['volume'], reagent['volume_unit'], 'ul'
            )
            new_reagent_total_ul = max(0.0, current_vol_ul - used_vol_ul)
            new_reagent_total = UnitConverter.convert_volume(
                new_reagent_total_ul, 'ul', reagent['volume_unit']
            )
            self.db.execute(
                'UPDATE reagents SET volume = ? WHERE id = ?',
                (new_reagent_total, usage['reagent_id'])
            )
        
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
        
        batch_desc = '; '.join(batch_deduct_details) if batch_deduct_details else '无批次明细'
        self._add_history(task_id, 'approve', 'task_approved', 
                          f'任务已批准，扣减库存（批次: {batch_desc}）。操作人: {operator}')
        
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
    
    def revoke_approval(self, task_id, operator='user', force=False):
        task = self.db.execute('SELECT * FROM tasks WHERE id = ?', (task_id,)).fetchone()
        if not task:
            raise ValueError('任务不存在')
        
        if task['status'] != 'approved':
            raise ValueError('只有已批准的任务才能撤销确认')
        
        conflicts = self.batch_service.check_revoke_conflicts(task_id)
        if conflicts and not force:
            conflict_msgs = []
            for c in conflicts:
                task_refs = ', '.join(
                    f'任务 #{t["task_id"]} ({t["task_name"]})' for t in c['conflicting_tasks']
                )
                conflict_msgs.append(
                    f'试剂 {c["reagent_name"]} 批次 {c["batch_number"]} 已被后续已批准任务占用: {task_refs}'
                )
            raise ValueError(
                '撤销失败：以下批次已被后续已批准的任务占用，无法直接退回。'
                '如需强制撤销请使用 force 参数，但请注意这可能导致后续任务库存为负。'
                ' 具体: ' + ' | '.join(conflict_msgs)
            )
        
        reagent_usage = [dict(r) for r in self.db.execute(
            'SELECT * FROM task_reagent_usage WHERE task_id = ?', (task_id,)
        ).fetchall()]
        
        primer_usage = [dict(r) for r in self.db.execute(
            'SELECT * FROM task_primer_usage WHERE task_id = ?', (task_id,)
        ).fetchall()]
        
        batch_refund_details = []
        for usage in reagent_usage:
            reagent = self.db.execute(
                'SELECT * FROM reagents WHERE id = ?', (usage['reagent_id'],)
            ).fetchone()
            
            used_vol_ul = UnitConverter.convert_volume(
                usage['used_volume'], usage['used_volume_unit'], 'ul'
            )
            
            if usage.get('batch_id'):
                new_vol_ul = self.batch_service.refund_batch_volume(
                    usage['batch_id'], used_vol_ul, task_id=task_id,
                    note=f'任务 #{task_id} 撤销确认，退回库存'
                )
                batch_refund_details.append(
                    f'{reagent["name"]}-{usage.get("batch_number", "")}: +{used_vol_ul:.1f}ul (现 {new_vol_ul:.1f}ul)'
                )
                try:
                    self._trace_service.log_refund(
                        batch_id=usage['batch_id'],
                        task_id=task_id,
                        refund_volume_ul=used_vol_ul,
                        force=force,
                        operator=operator,
                    )
                except Exception:
                    pass
            else:
                current_vol_ul = UnitConverter.convert_volume(
                    reagent['volume'], reagent['volume_unit'], 'ul'
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
                batch_refund_details.append(f'{reagent["name"]}: +{used_vol_ul:.1f}ul')
            
            current_vol_ul = UnitConverter.convert_volume(
                reagent['volume'], reagent['volume_unit'], 'ul'
            )
            new_reagent_total_ul = current_vol_ul + used_vol_ul
            new_reagent_total = UnitConverter.convert_volume(
                new_reagent_total_ul, 'ul', reagent['volume_unit']
            )
            self.db.execute(
                'UPDATE reagents SET volume = ? WHERE id = ?',
                (new_reagent_total, usage['reagent_id'])
            )
        
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
        
        batch_desc = '; '.join(batch_refund_details) if batch_refund_details else '无批次明细'
        force_note = '（强制撤销，后续任务可能出现负库存）' if force else ''
        self._add_history(task_id, 'revoke', 'approval_revoked', 
                          f'撤销确认，库存已退回{force_note}（批次: {batch_desc}）。操作人: {operator}')
        
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
    
    def get_edit_preview(self, task_id):
        task = self.db.execute('SELECT * FROM tasks WHERE id = ?', (task_id,)).fetchone()
        if not task:
            raise ValueError('任务不存在')

        if task['status'] in ['approved', 'revoked']:
            raise ValueError(f'当前状态为「{task["status"]}」的任务不能编辑，已批准和已撤销的任务只读')

        template = self.db.execute(
            'SELECT * FROM plate_templates WHERE id = ?', (task['template_id'],)
        ).fetchone()

        template_wells = self.db.execute(
            'SELECT * FROM template_wells WHERE template_id = ? ORDER BY well_row, well_col',
            (task['template_id'],)
        ).fetchall()

        task_wells = self.db.execute(
            'SELECT * FROM task_wells WHERE task_id = ? ORDER BY well_row, well_col',
            (task_id,)
        ).fetchall()

        all_templates = self.db.execute(
            'SELECT id, name, rows, cols FROM plate_templates ORDER BY id'
        ).fetchall()

        all_samples = self.db.execute(
            'SELECT id, name, concentration, concentration_unit, volume, volume_unit FROM samples ORDER BY id'
        ).fetchall()

        return {
            'task': {
                'id': task['id'],
                'name': task['name'],
                'status': task['status'],
                'total_volume': task['total_volume'],
                'volume_unit': task['volume_unit'],
            },
            'current_template': {
                'id': template['id'],
                'name': template['name'],
                'rows': template['rows'],
                'cols': template['cols'],
            } if template else None,
            'current_wells': [dict(w) for w in (task_wells if task_wells else template_wells)],
            'available_templates': [dict(t) for t in all_templates],
            'available_samples': [dict(s) for s in all_samples],
        }

    def validate_edit(self, task_id, edit_data):
        task = self.db.execute('SELECT * FROM tasks WHERE id = ?', (task_id,)).fetchone()
        if not task:
            raise ValueError('任务不存在')

        if task['status'] in ['approved', 'revoked']:
            raise ValueError(f'当前状态为「{task["status"]}」的任务不能编辑，已批准和已撤销的任务只读')

        errors = []
        warnings = []

        new_template_id = edit_data.get('template_id', task['template_id'])
        new_total_volume = edit_data.get('total_volume', task['total_volume'])
        new_volume_unit = edit_data.get('volume_unit', task['volume_unit'])
        new_wells = edit_data.get('wells', None)

        if not UnitConverter.is_volume_unit(new_volume_unit):
            errors.append(f'无效的体积单位: {new_volume_unit}')

        if new_total_volume is None or new_total_volume <= 0:
            errors.append('总体积必须大于 0')

        template = self.db.execute(
            'SELECT * FROM plate_templates WHERE id = ?', (new_template_id,)
        ).fetchone()
        if not template:
            errors.append(f'模板不存在 (id={new_template_id})')
            return {'valid': False, 'errors': errors, 'warnings': warnings}

        template_wells = self.db.execute(
            'SELECT * FROM template_wells WHERE template_id = ? ORDER BY well_row, well_col',
            (new_template_id,)
        ).fetchall()

        wells_to_validate = new_wells if new_wells is not None else [dict(w) for w in template_wells]

        if wells_to_validate:
            well_conflicts = self._check_well_conflicts(wells_to_validate)
            if well_conflicts:
                errors.append(f'孔位冲突: {json.dumps(well_conflicts, ensure_ascii=False)}')

            for well in wells_to_validate:
                wr = well.get('well_row')
                wc = well.get('well_col')
                if wr is None or wc is None:
                    errors.append(f'孔位缺少行/列信息: {json.dumps(well, ensure_ascii=False)}')
                    continue
                if wr < 1 or wr > template['rows'] or wc < 1 or wc > template['cols']:
                    errors.append(
                        f'孔位 {chr(64 + wr)}{wc} 超出模板范围 '
                        f'({template["rows"]}行×{template["cols"]}列)'
                    )

                well_type = well.get('well_type', 'sample')
                if well_type not in ['sample', 'positive_control', 'negative_control', 'empty']:
                    errors.append(f'孔位 {chr(64 + wr)}{wc} 的类型无效: {well_type}')

                if well_type == 'sample' and well.get('sample_name'):
                    sample = self.db.execute(
                        'SELECT * FROM samples WHERE name = ?', (well['sample_name'],)
                    ).fetchone()
                    if not sample:
                        errors.append(f'孔位 {chr(64 + wr)}{wc} 引用的样本不存在: {well["sample_name"]}')

        all_primers = self.db.execute('SELECT * FROM primers').fetchall()
        all_reagents = self.db.execute('SELECT * FROM reagents').fetchall()
        all_samples = self.db.execute('SELECT * FROM samples').fetchall()

        has_primer = len(all_primers) > 0
        has_master_mix = any(r['type'] == 'master_mix' for r in all_reagents)
        has_water = any(r['type'] == 'water' for r in all_reagents)

        if not has_primer:
            errors.append('缺少引物，请先导入引物')
        if not has_master_mix:
            errors.append('缺少 Master Mix 试剂')
        if not has_water:
            errors.append('缺少水试剂')

        if not errors and has_primer and has_master_mix and has_water:
            primer = all_primers[0]
            master_mix = next(r for r in all_reagents if r['type'] == 'master_mix')
            water = next(r for r in all_reagents if r['type'] == 'water')

            sample_count = sum(1 for w in wells_to_validate if w.get('well_type') in ['sample', 'positive_control'])
            nc_count = sum(1 for w in wells_to_validate if w.get('well_type') == 'negative_control')
            total_wells_for_reagent = sample_count + nc_count

            if total_wells_for_reagent > 0:
                total_vol_ul = UnitConverter.convert_volume(new_total_volume, new_volume_unit, 'ul')
                mm_vol_per_well = total_vol_ul * self.engine.DEFAULT_MASTER_MIX_VOLUME_RATIO
                primer_vol_per_well = total_vol_ul * self.engine.DEFAULT_PRIMER_VOLUME_RATIO
                sample_vol_per_well = total_vol_ul * self.engine.DEFAULT_SAMPLE_VOLUME_RATIO

                mm_total = mm_vol_per_well * total_wells_for_reagent
                primer_total = primer_vol_per_well * total_wells_for_reagent

                mm_available = UnitConverter.convert_volume(
                    master_mix['volume'], master_mix['volume_unit'], 'ul'
                )
                if mm_available < mm_total:
                    errors.append(
                        f'Master Mix 库存不足: {master_mix["name"]}, '
                        f'可用 {mm_available:.2f} µL, 需要 {mm_total:.2f} µL'
                    )
                elif mm_available < mm_total * 1.1:
                    warnings.append(
                        f'Master Mix 库存接近耗尽: {master_mix["name"]}, '
                        f'可用 {mm_available:.2f} µL, 需要 {mm_total:.2f} µL'
                    )

                primer_available = UnitConverter.convert_volume(
                    primer['volume'], primer['volume_unit'], 'ul'
                )
                if primer_available < primer_total:
                    errors.append(
                        f'引物库存不足: {primer["name"]}, '
                        f'可用 {primer_available:.2f} µL, 需要 {primer_total:.2f} µL'
                    )
                elif primer_available < primer_total * 1.1:
                    warnings.append(
                        f'引物库存接近耗尽: {primer["name"]}, '
                        f'可用 {primer_available:.2f} µL, 需要 {primer_total:.2f} µL'
                    )

                if mm_vol_per_well < 0.5:
                    warnings.append(
                        f'单孔 Master Mix 体积 ({mm_vol_per_well:.2f} µL) 低于最小移液体积 0.5 µL'
                    )
                if primer_vol_per_well < 0.5:
                    warnings.append(
                        f'单孔引物体积 ({primer_vol_per_well:.2f} µL) 低于最小移液体积 0.5 µL'
                    )
                if sample_count > 0 and sample_vol_per_well < 0.5:
                    warnings.append(
                        f'单孔样本体积 ({sample_vol_per_well:.2f} µL) 低于最小移液体积 0.5 µL'
                    )

        return {
            'valid': len(errors) == 0,
            'errors': errors,
            'warnings': warnings,
            'template_info': {
                'id': template['id'],
                'name': template['name'],
                'rows': template['rows'],
                'cols': template['cols'],
            } if template else None,
            'total_volume': new_total_volume,
            'volume_unit': new_volume_unit,
            'well_count': len(wells_to_validate),
        }

    def calculate_edit_diff(self, task_id, edit_data):
        task = self.db.execute('SELECT * FROM tasks WHERE id = ?', (task_id,)).fetchone()
        if not task:
            raise ValueError('任务不存在')

        old_template = self.db.execute(
            'SELECT * FROM plate_templates WHERE id = ?', (task['template_id'],)
        ).fetchone()

        old_task_wells = self.db.execute(
            'SELECT * FROM task_wells WHERE task_id = ? ORDER BY well_row, well_col',
            (task_id,)
        ).fetchall()
        old_template_wells = self.db.execute(
            'SELECT * FROM template_wells WHERE template_id = ? ORDER BY well_row, well_col',
            (task['template_id'],)
        ).fetchall()
        old_wells = [dict(w) for w in (old_task_wells if old_task_wells else old_template_wells)]

        new_template_id = edit_data.get('template_id', task['template_id'])
        new_total_volume = edit_data.get('total_volume', task['total_volume'])
        new_volume_unit = edit_data.get('volume_unit', task['volume_unit'])
        new_wells_input = edit_data.get('wells', None)

        new_template = self.db.execute(
            'SELECT * FROM plate_templates WHERE id = ?', (new_template_id,)
        ).fetchone()

        new_template_wells = self.db.execute(
            'SELECT * FROM template_wells WHERE template_id = ? ORDER BY well_row, well_col',
            (new_template_id,)
        ).fetchall()
        new_wells = new_wells_input if new_wells_input is not None else [dict(w) for w in new_template_wells]

        diff = {
            'task_changes': {},
            'template_changes': {},
            'well_changes': {
                'added': [],
                'removed': [],
                'modified': [],
            },
            'summary': {
                'wells_added': 0,
                'wells_removed': 0,
                'wells_modified': 0,
            }
        }

        if task['total_volume'] != new_total_volume:
            diff['task_changes']['total_volume'] = {
                'old': task['total_volume'],
                'new': new_total_volume
            }
        if task['volume_unit'] != new_volume_unit:
            diff['task_changes']['volume_unit'] = {
                'old': task['volume_unit'],
                'new': new_volume_unit
            }

        if old_template and new_template and old_template['id'] != new_template['id']:
            diff['template_changes'] = {
                'old': {'id': old_template['id'], 'name': old_template['name'],
                        'rows': old_template['rows'], 'cols': old_template['cols']},
                'new': {'id': new_template['id'], 'name': new_template['name'],
                        'rows': new_template['rows'], 'cols': new_template['cols']}
            }
        elif (old_template and not new_template) or (not old_template and new_template):
            diff['template_changes'] = {
                'old': {'id': old_template['id'], 'name': old_template['name']} if old_template else None,
                'new': {'id': new_template['id'], 'name': new_template['name']} if new_template else None
            }

        old_well_map = {(w['well_row'], w['well_col']): w for w in old_wells}
        new_well_map = {(w['well_row'], w['well_col']): w for w in new_wells}

        all_keys = set(old_well_map.keys()) | set(new_well_map.keys())
        for key in sorted(all_keys):
            well_label = f"{chr(64 + key[0])}{key[1]}"
            if key not in old_well_map:
                diff['well_changes']['added'].append({
                    'well': well_label,
                    'data': new_well_map[key]
                })
                diff['summary']['wells_added'] += 1
            elif key not in new_well_map:
                diff['well_changes']['removed'].append({
                    'well': well_label,
                    'data': old_well_map[key]
                })
                diff['summary']['wells_removed'] += 1
            else:
                ow, nw = old_well_map[key], new_well_map[key]
                diff_fields = {}
                for f in ['well_type', 'sample_name']:
                    ov = ow.get(f)
                    nv = nw.get(f)
                    if f == 'sample_name':
                        ov = ov if ov is not None else ''
                        nv = nv if nv is not None else ''
                    if ov != nv:
                        diff_fields[f] = {'old': ov, 'new': nv}
                if diff_fields:
                    diff['well_changes']['modified'].append({
                        'well': well_label,
                        'fields': diff_fields
                    })
                    diff['summary']['wells_modified'] += 1

        return diff

    def apply_edit(self, task_id, edit_data, operator='user'):
        task = self.db.execute('SELECT * FROM tasks WHERE id = ?', (task_id,)).fetchone()
        if not task:
            raise ValueError('任务不存在')

        if task['status'] in ['approved', 'revoked']:
            raise ValueError(f'当前状态为「{task["status"]}」的任务不能编辑，已批准和已撤销的任务只读')

        validation = self.validate_edit(task_id, edit_data)
        if not validation['valid']:
            raise ValueError('编辑校验失败: ' + '; '.join(validation['errors']))

        diff = self.calculate_edit_diff(task_id, edit_data)

        new_template_id = edit_data.get('template_id', task['template_id'])
        new_total_volume = edit_data.get('total_volume', task['total_volume'])
        new_volume_unit = edit_data.get('volume_unit', task['volume_unit'])
        new_wells_input = edit_data.get('wells', None)

        new_template = self.db.execute(
            'SELECT * FROM plate_templates WHERE id = ?', (new_template_id,)
        ).fetchone()

        new_template_wells = self.db.execute(
            'SELECT * FROM template_wells WHERE template_id = ? ORDER BY well_row, well_col',
            (new_template_id,)
        ).fetchall()
        wells_to_use = new_wells_input if new_wells_input is not None else [dict(w) for w in new_template_wells]

        from app.services.snapshot_service import SnapshotService
        snapshot_service = SnapshotService(self.db)
        pre_edit_snapshot = snapshot_service.create_snapshot(
            task_id, 'pre_edit', '编辑前快照'
        )

        try:
            self.db.execute('BEGIN')

            self.db.execute(
                "UPDATE tasks SET template_id = ?, total_volume = ?, volume_unit = ?, "
                "status = 'draft', updated_at = ? WHERE id = ?",
                (new_template_id, new_total_volume, new_volume_unit,
                 datetime.now().isoformat(), task_id)
            )

            old_usages = [dict(u) for u in self.db.execute(
                'SELECT * FROM task_reagent_usage WHERE task_id = ? AND batch_id IS NOT NULL',
                (task_id,)
            ).fetchall()]
            for u in old_usages:
                try:
                    cleared_ul = UnitConverter.convert_volume(
                        u['used_volume'], u['used_volume_unit'], 'ul'
                    )
                    self._trace_service.log_edit_clear(
                        batch_id=u['batch_id'],
                        task_id=task_id,
                        cleared_volume_ul=cleared_ul,
                    )
                except Exception:
                    pass

            self.db.execute('DELETE FROM task_wells WHERE task_id = ?', (task_id,))
            self.db.execute('DELETE FROM task_reagent_usage WHERE task_id = ?', (task_id,))
            self.db.execute('DELETE FROM task_primer_usage WHERE task_id = ?', (task_id,))

            all_samples = {s['name']: s for s in self.db.execute(
                'SELECT * FROM samples'
            ).fetchall()}

            for well in wells_to_use:
                sample_name = well.get('sample_name', '')
                sample_vol = 0
                sample_conc = None
                sample_conc_unit = None
                if sample_name and sample_name in all_samples:
                    s = all_samples[sample_name]
                    sample_conc = s['concentration']
                    sample_conc_unit = s['concentration_unit']

                self.db.execute('''
                    INSERT INTO task_wells
                    (task_id, well_row, well_col, well_type, sample_name,
                     sample_volume, sample_volume_unit, sample_concentration, sample_concentration_unit,
                     total_volume, total_volume_unit, note)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    task_id,
                    well.get('well_row'),
                    well.get('well_col'),
                    well.get('well_type', 'sample'),
                    sample_name,
                    sample_vol, 'ul',
                    sample_conc, sample_conc_unit,
                    0, 'ul',
                    well.get('note', '')
                ))

            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

        post_edit_snapshot = snapshot_service.create_snapshot(
            task_id, 'edit',
            f'编辑后快照: 模板={new_template["name"]}, 体积={new_total_volume}{new_volume_unit}'
        )

        diff_summary_parts = []
        if diff['task_changes']:
            for k, v in diff['task_changes'].items():
                label_map = {'total_volume': '总体积', 'volume_unit': '体积单位'}
                diff_summary_parts.append(f"{label_map.get(k, k)}: {v['old']}→{v['new']}")
        if diff['template_changes']:
            old_name = diff['template_changes']['old']['name'] if diff['template_changes'].get('old') else '无'
            new_name = diff['template_changes']['new']['name'] if diff['template_changes'].get('new') else '无'
            diff_summary_parts.append(f'模板: {old_name}→{new_name}')
        s = diff['summary']
        if s['wells_added'] or s['wells_removed'] or s['wells_modified']:
            diff_summary_parts.append(
                f'孔位: +{s["wells_added"]}/-{s["wells_removed"]}/~{s["wells_modified"]}'
            )
        diff_summary = '; '.join(diff_summary_parts) if diff_summary_parts else '无实质变更'

        detail = (
            f'编辑并重算任务配置，编辑前快照 v{pre_edit_snapshot["version"]}，'
            f'编辑后快照 v{post_edit_snapshot["version"]}。变更: {diff_summary}。操作人: {operator}'
        )
        self._add_history(task_id, 'edit', 'task_edited', detail)

        return {
            'task_id': task_id,
            'status': 'draft',
            'pre_edit_version': pre_edit_snapshot['version'],
            'post_edit_version': post_edit_snapshot['version'],
            'diff': diff,
            'validation_warnings': validation.get('warnings', []),
        }

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
            reagent_usage_by_id = {}
            for usage in reagent_usage:
                key = usage['reagent_id']
                if key not in reagent_usage_by_id:
                    reagent_usage_by_id[key] = {
                        'id': usage['reagent_id'],
                        'name': usage['reagent_name'],
                        'volume': 0.0,
                        'unit': usage['used_volume_unit'],
                        'source': usage['source'],
                    }
                add_ul = UnitConverter.convert_volume(
                    usage['used_volume'], usage['used_volume_unit'], 'ul'
                )
                cur_ul = UnitConverter.convert_volume(
                    reagent_usage_by_id[key]['volume'],
                    reagent_usage_by_id[key]['unit'],
                    'ul'
                )
                new_total_ul = cur_ul + add_ul
                reagent_usage_by_id[key]['volume'] = UnitConverter.convert_volume(
                    new_total_ul, 'ul', reagent_usage_by_id[key]['unit']
                )
            
            for key, usage in reagent_usage_by_id.items():
                required_ul = UnitConverter.convert_volume(
                    usage['volume'], usage['unit'], 'ul'
                )
                try:
                    allocations = self.batch_service.allocate_batches(usage['id'], required_ul)
                except ValueError as e:
                    allocations = [{
                        'batch_id': None,
                        'batch_number': None,
                        'allocated_volume_ul': required_ul,
                    }]
                
                for alloc in allocations:
                    self.db.execute('''
                        INSERT INTO task_reagent_usage 
                        (task_id, reagent_id, reagent_name, batch_id, batch_number,
                         used_volume, used_volume_unit, source)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        new_task_id, usage['id'], usage['name'],
                        alloc.get('batch_id'), alloc.get('batch_number'),
                        alloc['allocated_volume_ul'], 'ul',
                        usage['source']
                    ))
                    if alloc.get('batch_id'):
                        try:
                            self._trace_service.log_allocate(
                                batch_id=alloc['batch_id'],
                                task_id=new_task_id,
                                allocated_volume_ul=alloc['allocated_volume_ul'],
                                source='copy',
                            )
                        except Exception:
                            pass
        
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
            '''SELECT reagent_name, source, used_volume, used_volume_unit, 
                      batch_id, batch_number 
               FROM task_reagent_usage WHERE task_id = ?''',
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
                usage_by_reagent = {}
                for usage in reagent_usage:
                    name = usage['reagent_name']
                    if name not in usage_by_reagent:
                        usage_by_reagent[name] = {
                            'name': name,
                            'volume_ul': 0.0,
                            'source': usage.get('source', ''),
                        }
                    add_ul = UnitConverter.convert_volume(
                        usage.get('used_volume', 0),
                        usage.get('used_volume_unit', 'ul'),
                        'ul'
                    )
                    usage_by_reagent[name]['volume_ul'] += add_ul
                
                for name, summary in usage_by_reagent.items():
                    reagent = self.db.execute(
                        'SELECT * FROM reagents WHERE name = ?', (name,)
                    ).fetchone()
                    if not reagent:
                        continue
                    try:
                        allocations = self.batch_service.allocate_batches(
                            reagent['id'], summary['volume_ul']
                        )
                    except ValueError:
                        allocations = [{
                            'batch_id': None,
                            'batch_number': usage.get('batch_number'),
                            'allocated_volume_ul': summary['volume_ul'],
                        }]
                    for alloc in allocations:
                        self.db.execute('''
                            INSERT INTO task_reagent_usage 
                            (task_id, reagent_id, reagent_name, batch_id, batch_number,
                             used_volume, used_volume_unit, source)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (
                            new_task_id, reagent['id'], name,
                            alloc.get('batch_id'), alloc.get('batch_number'),
                            alloc['allocated_volume_ul'], 'ul',
                            summary['source']
                        ))
                        if alloc.get('batch_id'):
                            try:
                                self._trace_service.log_allocate(
                                    batch_id=alloc['batch_id'],
                                    task_id=new_task_id,
                                    allocated_volume_ul=alloc['allocated_volume_ul'],
                                    source='import',
                                )
                            except Exception:
                                pass

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
