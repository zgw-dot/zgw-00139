import json
import csv
import io
import os
from datetime import datetime, date

from app.services.unit_converter import UnitConverter


MAX_LIMIT = 5000
DEFAULT_LIMIT = 100


def _parse_iso_date(date_str, field_name):
    if not date_str:
        return None, None
    s = str(date_str).strip()
    if not s:
        return None, None
    for fmt in (
        '%Y-%m-%dT%H:%M:%S',
        '%Y-%m-%d %H:%M:%S',
        '%Y-%m-%dT%H:%M',
        '%Y-%m-%d %H:%M',
        '%Y-%m-%d',
    ):
        try:
            return datetime.strptime(s, fmt), None
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(s), None
    except (ValueError, TypeError):
        pass
    return None, f'{field_name} 格式不合法，请使用 YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS'


class HistoryService:

    ACTION_TYPES = [
        'task_created', 'plan_generated', 'task_approved', 'task_rejected',
        'approval_revoked', 'deviation_note_added', 'task_edited',
        'task_copied', 'task_copied_from', 'task_exported',
        'task_imported', 'task_import_failed',
        'snapshot_created', 'snapshot_rollback',
        'template_imported', 'template_exported_json', 'template_exported_csv',
        'template_copied', 'template_deleted', 'template_overwritten',
        'history_exported_json', 'history_exported_csv',
        'history_exported_empty',
        'filter_preset_created', 'filter_preset_updated',
        'filter_preset_deleted', 'filter_preset_default_changed',
    ]

    ACTION_LABELS = {
        'create': '创建',
        'generate': '生成方案',
        'approve': '批准',
        'reject': '驳回',
        'revoke': '撤销',
        'deviation': '偏差备注',
        'edit': '编辑',
        'snapshot': '快照',
        'rollback': '回滚',
        'copy': '复制',
        'export': '导出',
        'import': '导入',
    }

    ACTION_TYPE_LABELS = {
        'task_created': '创建任务',
        'plan_generated': '生成配液方案',
        'task_approved': '批准任务',
        'task_rejected': '驳回任务',
        'approval_revoked': '撤销批准',
        'deviation_note_added': '添加偏差备注',
        'task_edited': '编辑任务',
        'task_copied': '复制为新任务',
        'task_copied_from': '被复制为新任务',
        'task_exported': '导出任务方案',
        'task_imported': '导入任务方案',
        'task_import_failed': '任务方案导入失败',
        'snapshot_created': '创建快照',
        'snapshot_rollback': '回滚快照',
        'template_imported': '导入模板',
        'template_exported_json': '导出模板 JSON',
        'template_exported_csv': '导出模板 CSV',
        'template_copied': '复制模板',
        'template_deleted': '删除模板',
        'template_overwritten': '覆盖模板',
        'history_exported_json': '导出历史 JSON',
        'history_exported_csv': '导出历史 CSV',
        'history_exported_empty': '导出空结果',
        'filter_preset_created': '创建筛选方案',
        'filter_preset_updated': '更新筛选方案',
        'filter_preset_deleted': '删除筛选方案',
        'filter_preset_default_changed': '切换默认筛选方案',
    }

    def __init__(self, db, data_dir):
        self.db = db
        self.data_dir = data_dir

    def validate_filters(self, task_id=None, action_type=None, start_date=None,
                         end_date=None, keyword=None, limit=DEFAULT_LIMIT):
        errors = []
        warnings = []
        parsed = {}

        if task_id is not None:
            try:
                parsed['task_id'] = int(task_id)
            except (ValueError, TypeError):
                errors.append('task_id 必须是整数')
        else:
            parsed['task_id'] = None

        if action_type:
            at = str(action_type).strip()
            if at and at not in self.ACTION_TYPES:
                warnings.append(f'未知的操作类型: {at}，结果可能为空')
            parsed['action_type'] = at
        else:
            parsed['action_type'] = None

        sd, sd_err = _parse_iso_date(start_date, 'start_date')
        parsed['start_date'] = sd
        if sd_err:
            errors.append(sd_err)

        ed, ed_err = _parse_iso_date(end_date, 'end_date')
        if ed and ed_err is None and ed.time() == datetime.min.time():
            ed = ed.replace(hour=23, minute=59, second=59)
        parsed['end_date'] = ed
        if ed_err:
            errors.append(ed_err)

        if parsed['start_date'] and parsed['end_date']:
            if parsed['start_date'] > parsed['end_date']:
                errors.append('start_date 不能晚于 end_date')

        if keyword:
            kw = str(keyword).strip()
            parsed['keyword'] = kw if kw else None
        else:
            parsed['keyword'] = None

        try:
            lim = int(limit)
        except (ValueError, TypeError):
            errors.append('limit 必须是整数')
            lim = DEFAULT_LIMIT
        if lim < 1:
            errors.append('limit 必须大于 0')
            lim = DEFAULT_LIMIT
        if lim > MAX_LIMIT:
            warnings.append(f'limit 超过上限 {MAX_LIMIT}，已自动截断为 {MAX_LIMIT}')
            lim = MAX_LIMIT
        parsed['limit'] = lim

        return parsed, errors, warnings

    def _build_query(self, parsed, count_only=False):
        select_clause = 'SELECT COUNT(*) AS cnt' if count_only else 'SELECT *'
        query = f'{select_clause} FROM history WHERE 1=1'
        params = []

        if parsed.get('task_id') is not None:
            query += ' AND task_id = ?'
            params.append(parsed['task_id'])

        if parsed.get('action_type'):
            query += ' AND action_type = ?'
            params.append(parsed['action_type'])

        if parsed.get('start_date'):
            query += ' AND created_at >= ?'
            params.append(parsed['start_date'].strftime('%Y-%m-%d %H:%M:%S'))

        if parsed.get('end_date'):
            query += ' AND created_at <= ?'
            params.append(parsed['end_date'].strftime('%Y-%m-%d %H:%M:%S'))

        if parsed.get('keyword'):
            kw = f"%{parsed['keyword']}%"
            query += ' AND (action LIKE ? OR action_type LIKE ? OR detail LIKE ? OR operator LIKE ? OR COALESCE(task_id, "") LIKE ?)'
            params.extend([kw, kw, kw, kw, kw])

        return query, params

    def query_history(self, task_id=None, action_type=None, start_date=None,
                      end_date=None, keyword=None, limit=DEFAULT_LIMIT,
                      include_total=True):
        parsed, errors, warnings = self.validate_filters(
            task_id=task_id, action_type=action_type,
            start_date=start_date, end_date=end_date,
            keyword=keyword, limit=limit,
        )

        result = {
            'records': [],
            'total': 0,
            'filters': self._filters_summary(parsed),
            'errors': errors,
            'warnings': warnings,
        }

        if errors:
            return result

        query, params = self._build_query(parsed, count_only=False)
        query += ' ORDER BY created_at DESC LIMIT ?'
        params.append(parsed['limit'])

        try:
            rows = self.db.execute(query, params).fetchall()
            result['records'] = [dict(r) for r in rows]
        except Exception as e:
            result['errors'].append(f'查询失败: {str(e)}')
            return result

        if include_total:
            try:
                cnt_q, cnt_p = self._build_query(parsed, count_only=True)
                total_row = self.db.execute(cnt_q, cnt_p).fetchone()
                result['total'] = int(total_row['cnt']) if total_row else 0
            except Exception as e:
                result['warnings'].append(f'统计总数失败: {str(e)}')
                result['total'] = len(result['records'])

        return result

    def get_history(self, task_id=None, action_type=None, start_date=None,
                    end_date=None, keyword=None, limit=DEFAULT_LIMIT):
        result = self.query_history(
            task_id=task_id, action_type=action_type,
            start_date=start_date, end_date=end_date,
            keyword=keyword, limit=limit, include_total=False,
        )
        return result['records']

    def _filters_summary(self, parsed):
        parts = []
        if parsed.get('task_id'):
            parts.append(f"任务#{parsed['task_id']}")
        if parsed.get('action_type'):
            label = self.ACTION_TYPE_LABELS.get(parsed['action_type'], parsed['action_type'])
            parts.append(f"操作类型:{label}")
        if parsed.get('start_date'):
            parts.append(f"起始:{parsed['start_date'].strftime('%Y-%m-%d %H:%M:%S')}")
        if parsed.get('end_date'):
            parts.append(f"结束:{parsed['end_date'].strftime('%Y-%m-%d %H:%M:%S')}")
        if parsed.get('keyword'):
            parts.append(f"关键词:\"{parsed['keyword']}\"")
        parts.append(f"条数上限:{parsed.get('limit', DEFAULT_LIMIT)}")
        return ' | '.join(parts) if parts else '无筛选条件（全部）'

    def _filters_dict(self, parsed):
        return {
            'task_id': parsed.get('task_id'),
            'action_type': parsed.get('action_type'),
            'start_date': parsed['start_date'].isoformat() if parsed.get('start_date') else None,
            'end_date': parsed['end_date'].isoformat() if parsed.get('end_date') else None,
            'keyword': parsed.get('keyword'),
            'limit': parsed.get('limit'),
        }

    def export_history_json(self, task_id=None, action_type=None, start_date=None,
                            end_date=None, keyword=None, limit=MAX_LIMIT):
        parsed, errors, warnings = self.validate_filters(
            task_id=task_id, action_type=action_type,
            start_date=start_date, end_date=end_date,
            keyword=keyword, limit=limit,
        )

        if errors:
            raise ValueError('; '.join(errors))

        result = self.query_history(
            task_id=parsed['task_id'], action_type=parsed['action_type'],
            start_date=start_date, end_date=end_date,
            keyword=parsed['keyword'], limit=parsed['limit'],
            include_total=True,
        )

        history_records = result['records']
        inventory_logs = self.get_inventory_logs(limit=1000)

        tasks_q = 'SELECT * FROM tasks'
        tasks_params = []
        if parsed.get('task_id'):
            tasks_q += ' WHERE id = ?'
            tasks_params.append(parsed['task_id'])
        tasks_q += ' ORDER BY created_at'
        tasks = self.db.execute(tasks_q, tasks_params).fetchall()

        reagents = self.db.execute('SELECT * FROM reagents ORDER BY id').fetchall()
        primers = self.db.execute('SELECT * FROM primers ORDER BY id').fetchall()
        samples = self.db.execute('SELECT * FROM samples ORDER BY id').fetchall()

        export_data = {
            'export_time': datetime.now().isoformat(),
            'export_format': 'json',
            'filter_summary': self._filters_summary(parsed),
            'filters': self._filters_dict(parsed),
            'warnings': result.get('warnings', []) + warnings,
            'matched_count': result['total'],
            'exported_count': len(history_records),
            'tasks': [dict(t) for t in tasks],
            'samples': [dict(s) for s in samples],
            'primers': [dict(p) for p in primers],
            'reagents': [dict(r) for r in reagents],
            'history': history_records,
            'inventory_logs': inventory_logs,
        }

        self._log_export(
            export_type='json',
            parsed=parsed,
            count=len(history_records),
            total=result['total'],
        )

        return json.dumps(export_data, ensure_ascii=False, indent=2)

    def export_history_csv(self, task_id=None, action_type=None, start_date=None,
                           end_date=None, keyword=None, limit=MAX_LIMIT):
        parsed, errors, warnings = self.validate_filters(
            task_id=task_id, action_type=action_type,
            start_date=start_date, end_date=end_date,
            keyword=keyword, limit=limit,
        )

        if errors:
            raise ValueError('; '.join(errors))

        result = self.query_history(
            task_id=parsed['task_id'], action_type=parsed['action_type'],
            start_date=start_date, end_date=end_date,
            keyword=parsed['keyword'], limit=parsed['limit'],
            include_total=True,
        )

        history_records = result['records']

        output = io.StringIO()
        output.write(f'# 导出时间: {datetime.now().isoformat()}\n')
        output.write(f'# 筛选条件: {self._filters_summary(parsed)}\n')
        output.write(f'# 匹配总数: {result["total"]} / 导出条数: {len(history_records)}\n')
        if warnings or result.get('warnings'):
            all_warn = list(warnings) + list(result.get('warnings', []))
            output.write(f'# 警告: {"; ".join(all_warn)}\n')
        output.write('\n')

        fieldnames = ['id', 'task_id', 'action', 'action_type',
                      'detail', 'operator', 'created_at']
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(history_records)

        self._log_export(
            export_type='csv',
            parsed=parsed,
            count=len(history_records),
            total=result['total'],
        )

        return output.getvalue()

    def _log_export(self, export_type, parsed, count, total):
        try:
            if total == 0:
                action_type_key = 'history_exported_empty'
            else:
                action_type_key = f'history_exported_{export_type}'
            detail = (
                f'导出历史记录 {export_type.upper()} | '
                f'{self._filters_summary(parsed)} | '
                f'匹配:{total} 导出:{count}'
            )
            self.db.execute(
                'INSERT INTO history (task_id, action, action_type, detail, operator) VALUES (?, ?, ?, ?, ?)',
                (None, 'export', action_type_key, detail, 'system')
            )
            self.db.commit()
        except Exception:
            pass

    def _log_filter_preset_action(self, action_type, detail, task_id=None):
        try:
            self.db.execute(
                'INSERT INTO history (task_id, action, action_type, detail, operator) VALUES (?, ?, ?, ?, ?)',
                (task_id, 'filter_preset', action_type, detail, 'system')
            )
            self.db.commit()
        except Exception:
            pass

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

    def save_history_export(self, task_id=None, action_type=None, start_date=None,
                            end_date=None, keyword=None, limit=MAX_LIMIT):
        json_data = self.export_history_json(
            task_id=task_id, action_type=action_type,
            start_date=start_date, end_date=end_date,
            keyword=keyword, limit=limit,
        )
        csv_data = self.export_history_csv(
            task_id=task_id, action_type=action_type,
            start_date=start_date, end_date=end_date,
            keyword=keyword, limit=limit,
        )

        export_dir = os.path.join(self.data_dir, 'exports')
        os.makedirs(export_dir, exist_ok=True)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        task_suffix = f'_task_{task_id}' if task_id else ''

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

    def list_tasks(self):
        rows = self.db.execute(
            'SELECT id, name, status FROM tasks ORDER BY id DESC'
        ).fetchall()
        return [dict(r) for r in rows]

    def list_filter_presets(self):
        rows = self.db.execute(
            'SELECT * FROM history_filter_presets ORDER BY is_default DESC, name ASC'
        ).fetchall()
        return [dict(r) for r in rows]

    def get_filter_preset(self, preset_id):
        row = self.db.execute(
            'SELECT * FROM history_filter_presets WHERE id = ?',
            (preset_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_default_filter_preset(self):
        row = self.db.execute(
            'SELECT * FROM history_filter_presets WHERE is_default = 1 LIMIT 1'
        ).fetchone()
        return dict(row) if row else None

    def _validate_preset_name(self, name, exclude_id=None):
        name = str(name).strip() if name else ''
        if not name:
            raise ValueError('方案名称不能为空')
        if len(name) > 100:
            raise ValueError('方案名称不能超过 100 个字符')
        query = 'SELECT id FROM history_filter_presets WHERE name = ?'
        params = [name]
        if exclude_id is not None:
            query += ' AND id != ?'
            params.append(exclude_id)
        existing = self.db.execute(query, params).fetchone()
        if existing:
            raise ValueError(f'方案名称 "{name}" 已存在，请使用其他名称')
        return name

    def save_filter_preset(self, name, description=None, task_id=None,
                           action_type=None, start_date=None, end_date=None,
                           keyword=None, limit=DEFAULT_LIMIT, is_default=False,
                           preset_id=None):
        name = self._validate_preset_name(name, exclude_id=preset_id)

        parsed, errors, _ = self.validate_filters(
            task_id=task_id, action_type=action_type,
            start_date=start_date, end_date=end_date,
            keyword=keyword, limit=limit,
        )
        if errors:
            raise ValueError('筛选条件不合法: ' + '; '.join(errors))

        if preset_id is not None:
            existing = self.get_filter_preset(preset_id)
            if not existing:
                raise ValueError(f'筛选方案 #{preset_id} 不存在')

            was_default = existing['is_default'] == 1
            if is_default and not was_default:
                self.db.execute(
                    'UPDATE history_filter_presets SET is_default = 0 WHERE is_default = 1'
                )
            elif not is_default and was_default:
                is_default = True

            self.db.execute(
                '''UPDATE history_filter_presets
                   SET name = ?, description = ?, task_id = ?, action_type = ?,
                       start_date = ?, end_date = ?, keyword = ?, "limit" = ?,
                       is_default = ?, updated_at = CURRENT_TIMESTAMP
                   WHERE id = ?''',
                (name, description, parsed['task_id'], parsed['action_type'],
                 parsed['start_date'].isoformat() if parsed['start_date'] else None,
                 parsed['end_date'].isoformat() if parsed['end_date'] else None,
                 parsed['keyword'], parsed['limit'], 1 if is_default else 0,
                 preset_id)
            )
            self.db.commit()
            updated_preset = self.get_filter_preset(preset_id)
            self._log_filter_preset_action(
                'filter_preset_updated',
                f'更新筛选方案 "{name}" | {self._filters_summary(parsed)}' + (' | 设为默认' if is_default else '')
            )
            return updated_preset
        else:
            if is_default:
                self.db.execute(
                    'UPDATE history_filter_presets SET is_default = 0 WHERE is_default = 1'
                )

            cursor = self.db.execute(
                '''INSERT INTO history_filter_presets
                   (name, description, task_id, action_type, start_date,
                    end_date, keyword, "limit", is_default)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (name, description, parsed['task_id'], parsed['action_type'],
                 parsed['start_date'].isoformat() if parsed['start_date'] else None,
                 parsed['end_date'].isoformat() if parsed['end_date'] else None,
                 parsed['keyword'], parsed['limit'], 1 if is_default else 0)
            )
            self.db.commit()
            new_preset = self.get_filter_preset(cursor.lastrowid)
            self._log_filter_preset_action(
                'filter_preset_created',
                f'创建筛选方案 "{name}" | {self._filters_summary(parsed)}' + (' | 设为默认' if is_default else '')
            )
            return new_preset

    def set_default_filter_preset(self, preset_id):
        preset = self.get_filter_preset(preset_id)
        if not preset:
            raise ValueError(f'筛选方案 #{preset_id} 不存在')

        old_default = self.get_default_filter_preset()
        self.db.execute(
            'UPDATE history_filter_presets SET is_default = 0 WHERE is_default = 1'
        )
        self.db.execute(
            'UPDATE history_filter_presets SET is_default = 1, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
            (preset_id,)
        )
        self.db.commit()
        updated_preset = self.get_filter_preset(preset_id)
        old_name = old_default['name'] if old_default else '(无)'
        self._log_filter_preset_action(
            'filter_preset_default_changed',
            f'默认筛选方案切换: "{old_name}" → "{preset["name"]}"'
        )
        return updated_preset

    def delete_filter_preset(self, preset_id):
        preset = self.get_filter_preset(preset_id)
        if not preset:
            raise ValueError(f'筛选方案 #{preset_id} 不存在')

        was_default = preset['is_default'] == 1

        self.db.execute(
            'DELETE FROM history_filter_presets WHERE id = ?',
            (preset_id,)
        )
        self.db.commit()

        preset_name = preset['name']

        if was_default:
            remaining = self.db.execute(
                'SELECT id FROM history_filter_presets ORDER BY created_at ASC LIMIT 1'
            ).fetchone()
            if remaining:
                self.db.execute(
                    'UPDATE history_filter_presets SET is_default = 1 WHERE id = ?',
                    (remaining['id'],)
                )
                self.db.commit()

        self._log_filter_preset_action(
            'filter_preset_deleted',
            f'删除筛选方案 "{preset_name}"' + (' | 原默认方案已删除' if was_default else '')
        )

        return {'deleted': True, 'was_default': was_default}
