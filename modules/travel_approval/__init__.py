from flask import Blueprint

travel_approval_bp = Blueprint(
    'travel_approval', 
    __name__, 
    template_folder='templates', 
    url_prefix='/travel-approval'
)

from modules.travel_approval import routes
