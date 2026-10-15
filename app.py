import os
from flask import Flask, render_template
from config import Config
from shared import init_db, to_thai_date

# Import blueprints
from modules.admin import admin_bp
from modules.travel_approval import travel_approval_bp
from modules.travel_expense import travel_expense_bp
from modules.medical_expense import medical_expense_bp
from modules._template import template_bp

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Ensure required folders exist
    os.makedirs(app.config['TEMPLATE_DOCX_DIR'], exist_ok=True)
    os.makedirs(app.config['OUTPUT_DOCX_DIR'], exist_ok=True)
    os.makedirs(app.config['KNOWLEDGE_BASE_DIR'], exist_ok=True)

    # Initialize Database
    init_db()

    # Register Jinja Filters
    app.jinja_env.filters['basename'] = os.path.basename
    app.jinja_env.filters['thai_date'] = to_thai_date

    # Register Blueprints
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(travel_approval_bp)
    app.register_blueprint(travel_expense_bp)
    app.register_blueprint(medical_expense_bp)
    app.register_blueprint(template_bp)

    # Module definitions for dynamic Landing Page generation
    # Adding a new module here automatically generates card links on the index route!
    app.config['REGISTERED_MODULES'] = [
        {
            'name': 'travel_approval',
            'title': 'ขออนุมัติเดินทาง',
            'url_prefix': '/travel-approval',
            'icon': 'flight_takeoff',
            'description': 'ยื่นขออนุมัติเดินทางไปราชการ/ปฏิบัติงานนอกสถานที่ พร้อมสร้างไฟล์เอกสารนำส่งในรูปแบบ พ.ศ.'
        },
        {
            'name': 'travel_expense',
            'title': 'เบิกจ่ายค่าเดินทาง',
            'url_prefix': '/travel-expense',
            'icon': 'payments',
            'description': 'ยื่นหลักฐานเบิกจ่ายเงินค่าเดินทางและเบี้ยเลี้ยง โดยเชื่อมโยงประวัติผ่านใบขออนุมัติเดิมที่ได้รับอนุมัติ'
        },
        {
            'name': 'medical_expense',
            'title': 'เบิกจ่ายค่ารักษาพยาบาล',
            'url_prefix': '/medical-expense',
            'icon': 'medical_services',
            'description': 'ยื่นเอกสารคำร้องและใบเสร็จการรักษาพยาบาล สำหรับเบิกสวัสดิการของพนักงานในส่วนงาน'
        }
    ]

    @app.route('/')
    def index():
        """
        Landing Page displaying registered document modules dynamically.
        """
        modules = app.config['REGISTERED_MODULES']
        return render_template('landing.html', modules=modules)

    return app

if __name__ == '__main__':
    app = create_app()
    # Runs on localhost for development, can bind to 0.0.0.0 for Tailscale access
    app.run(host='0.0.0.0', port=5000, debug=True)
