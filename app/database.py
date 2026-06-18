import sqlite3
import os
from flask import g

def get_db(app):
    if 'db' not in g:
        g.db = sqlite3.connect(app.config['DATABASE'])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db

def close_db(e=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db(app):
    db_path = app.config['DATABASE']
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS samples (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            concentration REAL NOT NULL,
            concentration_unit TEXT NOT NULL,
            volume REAL NOT NULL,
            volume_unit TEXT NOT NULL,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS primers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            sequence TEXT,
            concentration REAL NOT NULL,
            concentration_unit TEXT NOT NULL,
            volume REAL NOT NULL,
            volume_unit TEXT NOT NULL,
            melting_temp REAL,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS reagents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            type TEXT NOT NULL,
            concentration REAL,
            concentration_unit TEXT,
            volume REAL NOT NULL,
            volume_unit TEXT NOT NULL,
            min_pipette_volume REAL,
            min_pipette_unit TEXT,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS reagent_batches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reagent_id INTEGER NOT NULL,
            batch_number TEXT NOT NULL,
            volume REAL NOT NULL,
            volume_unit TEXT NOT NULL,
            expiry_date TEXT,
            is_frozen INTEGER NOT NULL DEFAULT 0,
            min_usable_volume REAL,
            min_usable_unit TEXT,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (reagent_id) REFERENCES reagents(id) ON DELETE CASCADE,
            UNIQUE(reagent_id, batch_number)
        );

        CREATE TABLE IF NOT EXISTS plate_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            rows INTEGER NOT NULL,
            cols INTEGER NOT NULL,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS template_wells (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            template_id INTEGER NOT NULL,
            well_row INTEGER NOT NULL,
            well_col INTEGER NOT NULL,
            well_type TEXT NOT NULL DEFAULT 'sample',
            sample_name TEXT,
            sample_id INTEGER,
            reagent_id INTEGER,
            note TEXT,
            FOREIGN KEY (template_id) REFERENCES plate_templates(id) ON DELETE CASCADE,
            FOREIGN KEY (sample_id) REFERENCES samples(id),
            FOREIGN KEY (reagent_id) REFERENCES reagents(id),
            UNIQUE(template_id, well_row, well_col)
        );

        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft',
            template_id INTEGER NOT NULL,
            total_volume REAL NOT NULL,
            volume_unit TEXT NOT NULL,
            deviation_note TEXT,
            rejected_reason TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (template_id) REFERENCES plate_templates(id)
        );

        CREATE TABLE IF NOT EXISTS task_wells (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL,
            well_row INTEGER NOT NULL,
            well_col INTEGER NOT NULL,
            well_type TEXT NOT NULL,
            sample_name TEXT,
            sample_volume REAL,
            sample_volume_unit TEXT,
            sample_concentration REAL,
            sample_concentration_unit TEXT,
            primer_name TEXT,
            primer_volume REAL,
            primer_volume_unit TEXT,
            primer_concentration REAL,
            primer_concentration_unit TEXT,
            master_mix_volume REAL,
            master_mix_unit TEXT,
            water_volume REAL,
            water_unit TEXT,
            total_volume REAL,
            total_volume_unit TEXT,
            note TEXT,
            FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE,
            UNIQUE(task_id, well_row, well_col)
        );

        CREATE TABLE IF NOT EXISTS task_reagent_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL,
            reagent_id INTEGER NOT NULL,
            reagent_name TEXT NOT NULL,
            batch_id INTEGER,
            batch_number TEXT,
            used_volume REAL NOT NULL,
            used_volume_unit TEXT NOT NULL,
            source TEXT,
            FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE,
            FOREIGN KEY (reagent_id) REFERENCES reagents(id),
            FOREIGN KEY (batch_id) REFERENCES reagent_batches(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS task_primer_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL,
            primer_id INTEGER NOT NULL,
            primer_name TEXT NOT NULL,
            used_volume REAL NOT NULL,
            used_volume_unit TEXT NOT NULL,
            source TEXT,
            FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE,
            FOREIGN KEY (primer_id) REFERENCES primers(id)
        );

        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER,
            action TEXT NOT NULL,
            action_type TEXT NOT NULL,
            detail TEXT,
            operator TEXT DEFAULT 'system',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS task_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL,
            version INTEGER NOT NULL,
            snapshot_type TEXT NOT NULL,
            status TEXT NOT NULL,
            task_data TEXT NOT NULL,
            wells_data TEXT NOT NULL,
            reagent_usage_data TEXT NOT NULL,
            primer_usage_data TEXT NOT NULL,
            template_id INTEGER,
            template_name TEXT,
            total_volume REAL,
            volume_unit TEXT,
            note TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE,
            UNIQUE(task_id, version)
        );

        CREATE TABLE IF NOT EXISTS reagent_inventory_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reagent_id INTEGER NOT NULL,
            batch_id INTEGER,
            batch_number TEXT,
            change_type TEXT NOT NULL,
            change_volume REAL NOT NULL,
            change_volume_unit TEXT NOT NULL,
            balance_volume REAL NOT NULL,
            balance_volume_unit TEXT NOT NULL,
            task_id INTEGER,
            note TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (reagent_id) REFERENCES reagents(id),
            FOREIGN KEY (batch_id) REFERENCES reagent_batches(id) ON DELETE SET NULL,
            FOREIGN KEY (task_id) REFERENCES tasks(id)
        );

        CREATE TABLE IF NOT EXISTS primer_inventory_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            primer_id INTEGER NOT NULL,
            change_type TEXT NOT NULL,
            change_volume REAL NOT NULL,
            change_volume_unit TEXT NOT NULL,
            balance_volume REAL NOT NULL,
            balance_volume_unit TEXT NOT NULL,
            task_id INTEGER,
            note TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (primer_id) REFERENCES primers(id),
            FOREIGN KEY (task_id) REFERENCES tasks(id)
        );

        CREATE TABLE IF NOT EXISTS history_filter_presets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            description TEXT,
            task_id INTEGER,
            action_type TEXT,
            start_date TEXT,
            end_date TEXT,
            keyword TEXT,
            "limit" INTEGER NOT NULL DEFAULT 100,
            is_default INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    ''')
    
    # schema 迁移：补齐旧库缺少的列
    cur = conn.execute("PRAGMA table_info(template_wells)")
    existing_cols = {row[1] for row in cur.fetchall()}
    if 'sample_name' not in existing_cols:
        conn.execute("ALTER TABLE template_wells ADD COLUMN sample_name TEXT")
    
    cur = conn.execute("PRAGMA table_info(task_reagent_usage)")
    existing_cols = {row[1] for row in cur.fetchall()}
    if 'batch_id' not in existing_cols:
        conn.execute("ALTER TABLE task_reagent_usage ADD COLUMN batch_id INTEGER")
    if 'batch_number' not in existing_cols:
        conn.execute("ALTER TABLE task_reagent_usage ADD COLUMN batch_number TEXT")
    
    cur = conn.execute("PRAGMA table_info(reagent_inventory_log)")
    existing_cols = {row[1] for row in cur.fetchall()}
    if 'batch_id' not in existing_cols:
        conn.execute("ALTER TABLE reagent_inventory_log ADD COLUMN batch_id INTEGER")
    if 'batch_number' not in existing_cols:
        conn.execute("ALTER TABLE reagent_inventory_log ADD COLUMN batch_number TEXT")
    
    conn.commit()
    conn.close()
    
    app.teardown_appcontext(close_db)
