# 确保 data 目录可以通过 /data/ 访问
import os
from flask import send_from_directory, Blueprint, current_app

data_bp = Blueprint('data', __name__)

@data_bp.route('/data/<path:filename>')
def serve_data(filename):
    data_dir = current_app.config['DATA_DIR']
    return send_from_directory(data_dir, filename)
