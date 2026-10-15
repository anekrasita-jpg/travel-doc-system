from flask import Blueprint

travel_expense_bp = Blueprint(
    'travel_expense', 
    __name__, 
    template_folder='templates', 
    url_prefix='/travel-expense'
)

from modules.travel_expense import routes
