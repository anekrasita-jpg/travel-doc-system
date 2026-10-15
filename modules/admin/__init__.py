from flask import Blueprint

admin_bp = Blueprint('admin', __name__, template_folder='templates')

from modules.admin import routes
