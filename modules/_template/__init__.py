from flask import Blueprint

template_bp = Blueprint(
    '_template', 
    __name__, 
    template_folder='templates', 
    url_prefix='/_template'
)

from modules._template import routes
