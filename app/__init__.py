import os
from flask import Flask, send_from_directory
from flask_cors import CORS

from app.database import init_db

def create_app():
    app = Flask(__name__, static_folder='../static', static_url_path='/static')
    app.config['SECRET_KEY'] = 'pcr-planner-secret-key'
    app.config['DATABASE'] = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'pcr_planner.db')
    app.config['DATA_DIR'] = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
    
    CORS(app)
    
    init_db(app)
    
    from app.routes.main_routes import main_bp
    from app.routes.sample_routes import sample_bp
    from app.routes.primer_routes import primer_bp
    from app.routes.reagent_routes import reagent_bp
    from app.routes.template_routes import template_bp
    from app.routes.task_routes import task_bp
    from app.routes.history_routes import history_bp
    from app.routes.report_routes import report_bp
    from app.routes.batch_trace_routes import batch_trace_bp

    @app.route('/data/<path:filename>')
    def serve_data_file(filename):
        return send_from_directory(app.config['DATA_DIR'], filename)

    app.register_blueprint(main_bp)
    app.register_blueprint(sample_bp, url_prefix='/api/samples')
    app.register_blueprint(primer_bp, url_prefix='/api/primers')
    app.register_blueprint(reagent_bp, url_prefix='/api/reagents')
    app.register_blueprint(template_bp, url_prefix='/api/templates')
    app.register_blueprint(task_bp, url_prefix='/api/tasks')
    app.register_blueprint(history_bp, url_prefix='/api/history')
    app.register_blueprint(report_bp, url_prefix='/api/reports')
    app.register_blueprint(batch_trace_bp, url_prefix='/api/batch-trace')
    
    return app
