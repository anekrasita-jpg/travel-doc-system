from flask import render_template, request, redirect, url_for, flash
from modules._template import template_bp

# Import shared modules as needed for a new feature:
# from shared import get_db, get_active_staff, generate_docx, log_to_markdown, to_thai_date

@template_bp.route('/', methods=['GET', 'POST'])
def form():
    """
    Template route handler. Developers can copy this blueprint directory
    to create new document modules.
    """
    errors = {}
    form_data = {}
    
    if request.method == 'POST':
        # TODO: Implement manual form validation or use a custom validator
        # validation_success = True
        
        # Example validation check:
        # if not request.form.get('some_field'):
        #     errors['some_field'] = 'This field is required'
        
        # If valid:
        #   1. Save to Database:
        #      with get_db() as conn:
        #          conn.execute("INSERT INTO ...")
        #   2. Generate Docx Document:
        #      generate_docx('template_name.docx', 'output_name.docx', data)
        #   3. Log Summary to Markdown Log Table:
        #      log_to_markdown('module_type', log_data)
        
        flash('บันทึกแบบฟอร์มสำเร็จ (นี่คือโมดูลตัวอย่าง)', 'success')
        return redirect(url_for('_template.form'))
        
    return render_template('_template/form.html', errors=errors, form_data=form_data)
