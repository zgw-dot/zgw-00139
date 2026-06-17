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
            used_volume REAL NOT NULL,
            used_volume_unit TEXT NOT NULL,
            source TEXT,
            FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE,
            FOREIGN KEY (reagent_id) REFERENCES reagents(id)
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

        CREATE TABLE IF NOT EXISTS reagent_inventory_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reagent_id INTEGER NOT NULL,
            change_type TEXT NOT NULL,
            change_volume REAL NOT NULL,
            change_volume_unit TEXT NOT NULL,
            balance_volume REAL NOT NULL,
            balance_volume_unit TEXT NOT NULL,
            task_id INTEGER,
            note TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (reagent_id) REFERENCES reagents(id),
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
    ''')
    
    conn.commit()
    conn.close()
    
    app.teardown_appcontext(close_db)
