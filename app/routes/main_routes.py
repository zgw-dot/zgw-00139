import os
from flask import Blueprint, jsonify, current_app, send_from_directory

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():
    return send_from_directory(
        os.path.join(current_app.root_path, '..', 'static'),
        'index.html'
    )

@main_bp.route('/api/health')
def health():
    return jsonify({'status': 'ok', 'message': 'PCR 板位配液规划工具运行中'})

@main_bp.route('/api/stats')
def stats():
    from app.database import get_db
    db = get_db(current_app)
    
    stats = {}
    
    stats['samples'] = db.execute('SELECT COUNT(*) as cnt FROM samples').fetchone()['cnt']
    stats['primers'] = db.execute('SELECT COUNT(*) as cnt FROM primers').fetchone()['cnt']
    stats['reagents'] = db.execute('SELECT COUNT(*) as cnt FROM reagents').fetchone()['cnt']
    stats['templates'] = db.execute('SELECT COUNT(*) as cnt FROM plate_templates').fetchone()['cnt']
    stats['tasks'] = db.execute('SELECT COUNT(*) as cnt FROM tasks').fetchone()['cnt']
    stats['approved_tasks'] = db.execute("SELECT COUNT(*) as cnt FROM tasks WHERE status = 'approved'").fetchone()['cnt']
    stats['history'] = db.execute('SELECT COUNT(*) as cnt FROM history').fetchone()['cnt']
    
    return jsonify(stats)
