import json
import csv
import io
import os
from datetime import datetime


class ReportService:
    
    def __init__(self, db):
        self.db = db
    
    def generate_task_report(self, task_id):
        task = self.db.execute('SELECT * FROM tasks WHERE id = ?', (task_id,)).fetchone()
        if not task:
            raise ValueError('任务不存在')
        
        template = self.db.execute(
            'SELECT * FROM plate_templates WHERE id = ?', (task['template_id'],)
        ).fetchone()
        
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
        
        control_wells = [w for w in wells if w['well_type'] in ['positive_control', 'negative_control']]
        sample_wells = [w for w in wells if w['well_type'] == 'sample']
        empty_wells = [w for w in wells if w['well_type'] == 'empty']
        
        well_grid = {}
        for well in wells:
            key = f"{chr(64 + well['well_row'])}{well['well_col']}"
            well_grid[key] = dict(well)
        
        report = {
            'task': dict(task),
            'template': dict(template),
            'summary': {
                'total_wells': len(wells),
                'sample_wells': len(sample_wells),
                'positive_controls': len([w for w in control_wells if w['well_type'] == 'positive_control']),
                'negative_controls': len([w for w in control_wells if w['well_type'] == 'negative_control']),
                'empty_wells': len(empty_wells),
                'total_volume_per_well': f"{task['total_volume']} {task['volume_unit']}",
            },
            'wells': [dict(w) for w in wells],
            'well_grid': well_grid,
            'reagent_usage': [dict(r) for r in reagent_usage],
            'primer_usage': [dict(p) for p in primer_usage],
            'inventory_deduction': {
                'reagents': [],
                'primers': [],
            }
        }
        
        for usage in reagent_usage:
            reagent = self.db.execute(
                'SELECT * FROM reagents WHERE id = ?', (usage['reagent_id'],)
            ).fetchone()
            if reagent:
                batch_info = None
                if usage.get('batch_id'):
                    batch = self.db.execute(
                        'SELECT * FROM reagent_batches WHERE id = ?', (usage['batch_id'],)
                    ).fetchone()
                    if batch:
                        batch_info = {
                            'batch_id': batch['id'],
                            'batch_number': batch['batch_number'],
                            'expiry_date': batch.get('expiry_date'),
                            'is_frozen': bool(batch.get('is_frozen')),
                            'remaining_volume': f"{batch['volume']} {batch['volume_unit']}",
                        }
                report['inventory_deduction']['reagents'].append({
                    'name': usage['reagent_name'],
                    'source': usage['source'],
                    'used_volume': f"{usage['used_volume']} {usage['used_volume_unit']}",
                    'remaining_volume': f"{reagent['volume']} {reagent['volume_unit']}",
                    'batch_id': usage.get('batch_id'),
                    'batch_number': usage.get('batch_number'),
                    'batch': batch_info,
                })
        
        for usage in primer_usage:
            primer = self.db.execute(
                'SELECT * FROM primers WHERE id = ?', (usage['primer_id'],)
            ).fetchone()
            if primer:
                report['inventory_deduction']['primers'].append({
                    'name': usage['primer_name'],
                    'source': usage['source'],
                    'used_volume': f"{usage['used_volume']} {usage['used_volume_unit']}",
                    'remaining_volume': f"{primer['volume']} {primer['volume_unit']}",
                })
        
        return report
    
    def export_report_csv(self, task_id):
        report = self.generate_task_report(task_id)
        
        output = io.StringIO()
        writer = csv.writer(output)
        
        writer.writerow(['PCR 板位配液方案报告'])
        writer.writerow(['任务名称', report['task']['name']])
        writer.writerow(['任务状态', report['task']['status']])
        writer.writerow(['总体系', f"{report['task']['total_volume']} {report['task']['volume_unit']}"])
        writer.writerow([])
        
        writer.writerow(['孔位用量明细'])
        writer.writerow(['孔位', '类型', '样本', '样本体积(µL)', '引物', '引物体积(µL)', 
                         'Master Mix(µL)', '水(µL)', '总体系(µL)', '备注'])
        
        for well in report['wells']:
            well_name = f"{chr(64 + well['well_row'])}{well['well_col']}"
            well_type_map = {
                'sample': '样本',
                'positive_control': '阳性对照',
                'negative_control': '阴性对照',
                'empty': '空孔',
            }
            writer.writerow([
                well_name,
                well_type_map.get(well['well_type'], well['well_type']),
                well.get('sample_name', ''),
                well.get('sample_volume', '') or '',
                well.get('primer_name', ''),
                well.get('primer_volume', '') or '',
                well.get('master_mix_volume', '') or '',
                well.get('water_volume', '') or '',
                well.get('total_volume', '') or '',
                well.get('note', '') or '',
            ])
        
        writer.writerow([])
        writer.writerow(['试剂库存扣减明细'])
        writer.writerow(['试剂名称', '批次号', '有效期', '来源', '用量', '批次剩余库存', '总剩余库存'])
        
        for item in report['inventory_deduction']['reagents']:
            batch_number = item.get('batch_number') or ''
            expiry = ''
            batch_remaining = ''
            if item.get('batch'):
                expiry = item['batch'].get('expiry_date') or ''
                batch_remaining = item['batch'].get('remaining_volume') or ''
            writer.writerow([
                item['name'],
                batch_number,
                expiry,
                item['source'],
                item['used_volume'],
                batch_remaining,
                item['remaining_volume'],
            ])
        
        writer.writerow([])
        writer.writerow(['引物库存扣减明细'])
        writer.writerow(['引物名称', '来源', '用量', '剩余库存'])
        
        for item in report['inventory_deduction']['primers']:
            writer.writerow([
                item['name'],
                item['source'],
                item['used_volume'],
                item['remaining_volume'],
            ])
        
        return output.getvalue()
    
    def export_report_json(self, task_id):
        report = self.generate_task_report(task_id)
        return json.dumps(report, ensure_ascii=False, indent=2)
