import json
import csv
import io
import os
from datetime import datetime

from app.services.unit_converter import UnitConverter


class HistoryService:
    
    def __init__(self, db, data_dir):
        self.db = db
        self.data_dir = data_dir
    
    def get_history(self, task_id=None, action_type=None, limit=100):
        query = 'SELECT * FROM history WHERE 1=1'
        params = []
        
        if task_id:
            query += ' AND task_id = ?'
            params.append(task_id)
        
        if action_type:
            query += ' AND action_type = ?'
            params.append(action_type)
        
        query += ' ORDER BY created_at DESC LIMIT ?'
        params.append(limit)
        
        records = self.db.execute(query, params).fetchall()
        return [dict(r) for r in records]
    
    def get_inventory_logs(self, reagent_id=None, primer_id=None, limit=100):
        logs = []
        
        if reagent_id:
            reagent_logs = self.db.execute(
                'SELECT * FROM reagent_inventory_log WHERE reagent_id = ? ORDER BY created_at DESC LIMIT ?',
                (reagent_id, limit)
            ).fetchall()
            for log in reagent_logs:
                d = dict(log)
                d['type'] = 'reagent'
                logs.append(d)
        
        if primer_id:
            primer_logs = self.db.execute(
                'SELECT * FROM primer_inventory_log WHERE primer_id = ? ORDER BY created_at DESC LIMIT ?',
                (primer_id, limit)
            ).fetchall()
            for log in primer_logs:
                d = dict(log)
                d['type'] = 'primer'
                logs.append(d)
        
        if not reagent_id and not primer_id:
            reagent_logs = self.db.execute(
                'SELECT * FROM reagent_inventory_log ORDER BY created_at DESC LIMIT ?',
                (limit,)
            ).fetchall()
            for log in reagent_logs:
                d = dict(log)
                d['log_type'] = 'reagent'
                logs.append(d)
            
            primer_logs = self.db.execute(
                'SELECT * FROM primer_inventory_log ORDER BY created_at DESC LIMIT ?',
                (limit,)
            ).fetchall()
            for log in primer_logs:
                d = dict(log)
                d['log_type'] = 'primer'
                logs.append(d)
        
        logs.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        return logs[:limit]
    
    def export_history_json(self, task_id=None):
        history = self.get_history(task_id=task_id, limit=1000)
        inventory_logs = self.get_inventory_logs(limit=1000)
        tasks = self.db.execute('SELECT * FROM tasks ORDER BY created_at').fetchall()
        reagents = self.db.execute('SELECT * FROM reagents ORDER BY id').fetchall()
        primers = self.db.execute('SELECT * FROM primers ORDER BY id').fetchall()
        samples = self.db.execute('SELECT * FROM samples ORDER BY id').fetchall()
        
        export_data = {
            'export_time': datetime.now().isoformat(),
            'tasks': [dict(t) for t in tasks],
            'samples': [dict(s) for s in samples],
            'primers': [dict(p) for p in primers],
            'reagents': [dict(r) for r in reagents],
            'history': history,
            'inventory_logs': inventory_logs,
        }
        
        return json.dumps(export_data, ensure_ascii=False, indent=2)
    
    def export_history_csv(self, task_id=None):
        history = self.get_history(task_id=task_id, limit=1000)
        
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=['id', 'task_id', 'action', 'action_type', 
                                                    'detail', 'operator', 'created_at'])
        writer.writeheader()
        writer.writerows(history)
        
        return output.getvalue()
    
    def save_history_export(self, task_id=None):
        json_data = self.export_history_json(task_id)
        csv_data = self.export_history_csv(task_id)
        
        export_dir = os.path.join(self.data_dir, 'exports')
        os.makedirs(export_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        task_suffix = f'_task_{task_id}' if task_id else '_all'
        
        json_path = os.path.join(export_dir, f'history{task_suffix}_{timestamp}.json')
        csv_path = os.path.join(export_dir, f'history{task_suffix}_{timestamp}.csv')
        
        with open(json_path, 'w', encoding='utf-8') as f:
            f.write(json_data)
        
        with open(csv_path, 'w', encoding='utf-8') as f:
            f.write(csv_data)
        
        return {
            'json_path': json_path,
            'csv_path': csv_path,
        }
