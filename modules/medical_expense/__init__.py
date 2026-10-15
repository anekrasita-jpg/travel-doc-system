from flask import Blueprint

medical_expense_bp = Blueprint(
    'medical_expense', 
    __name__, 
    template_folder='templates', 
    url_prefix='/medical-expense'
)

from modules.medical_expense import routes
