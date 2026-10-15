import datetime
from flask import render_template, request, redirect, url_for, flash, jsonify, send_from_directory, abort
from config import Config
from modules.medical_expense import medical_expense_bp
from modules.medical_expense.forms import MedicalExpenseForm
from shared import get_db, get_active_staff, get_staff_details, generate_docx, log_to_markdown, to_thai_date, checkbox, generate_medical_expense_docx, convert_docx_to_pdf
from shared.thai_amount import amount_to_thai_text

@medical_expense_bp.route('/', methods=['GET', 'POST'])
def form():
    errors = {}
    form_data = {}
    
    if request.method == 'POST':
        form_validator = MedicalExpenseForm(request.form)
        if form_validator.validate():
            staff_id = int(form_validator.staff_id)
            facility_id = int(form_validator.facility_id)
            beneficiary_type = form_validator.beneficiary_type
            
            staff = get_staff_details(staff_id)
            
            # Fetch facility info
            facility = None
            with get_db() as conn:
                cursor = conn.execute("SELECT id, facility_name, facility_type FROM medical_facilities WHERE id = ?", (facility_id,))
                f_row = cursor.fetchone()
                if f_row:
                    facility = dict(f_row)

            # Fetch dependent info if beneficiary is dependent
            dependent = None
            if beneficiary_type == 'dependent':
                dependent_id = int(form_validator.dependent_id)
                with get_db() as conn:
                    cursor = conn.execute("SELECT id, full_name, relationship FROM medical_dependents WHERE id = ? AND staff_id = ?", (dependent_id, staff_id))
                    d_row = cursor.fetchone()
                    if d_row:
                        dependent = dict(d_row)

            if not staff:
                errors['staff_id'] = 'ไม่พบข้อมูลพนักงานในระบบ'
            elif not facility:
                errors['facility_id'] = 'ไม่พบข้อมูลสถานพยาบาลในระบบ'
            elif beneficiary_type == 'dependent' and not dependent:
                errors['dependent_id'] = 'ไม่พบข้อมูลบุตรที่ระบุสำหรับพนักงานท่านนี้'
            else:
                amount_requested = float(form_validator.amount_requested)
                receipt_count = int(form_validator.receipt_count)
                is_full_amount = 1 if form_validator.is_full_amount else 0
                
                # Logic: if full amount, approved = requested
                if is_full_amount:
                    amount_approved = amount_requested
                else:
                    amount_approved = float(form_validator.amount_approved)
                
                treatment_date_start = form_validator.treatment_date_start
                treatment_date_end = form_validator.treatment_date_end
                
                # Format Thai date
                treatment_date_start_thai = to_thai_date(treatment_date_start)
                treatment_date_end_thai = to_thai_date(treatment_date_end)
                if treatment_date_start == treatment_date_end:
                    treatment_date_thai_range = treatment_date_start_thai
                else:
                    treatment_date_thai_range = f"{treatment_date_start_thai} - {treatment_date_end_thai}"
                
                # 1. Database insertion and document generation in a single transaction
                try:
                    with get_db() as conn:
                        cursor = conn.execute(
                            """
                            INSERT INTO medical_expenses (
                                staff_id, beneficiary_type, dependent_id, facility_id, 
                                treatment_date_start, treatment_date_end, amount_requested, 
                                receipt_count, is_full_amount, amount_approved
                            )
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                staff_id, beneficiary_type, 
                                dependent['id'] if dependent else None,
                                facility_id, treatment_date_start, treatment_date_end,
                                amount_requested, receipt_count, is_full_amount, amount_approved
                            )
                        )
                        inserted_id = cursor.lastrowid
                        
                        # 2. Document generation
                        docx_filename = f"medical_expense_{inserted_id}.docx"
                        
                        beneficiary_name = "" if beneficiary_type == 'self' else dependent['full_name']
                        beneficiary_rel = 'ตนเอง' if beneficiary_type == 'self' else (dependent['relationship'] or 'บุตร')
                        
                        doc_data = {
                            'full_name': staff['full_name'],
                            'position': staff['position'] or '-',
                            'department': f"{staff['department']} (กอง {staff['division_name']})" if staff['division_name'] else staff['department'],
                            'beneficiary_name': beneficiary_name,
                            'beneficiary_type': beneficiary_rel,
                            'amount': f"{amount_requested:,.2f}", # compatibility key
                            'amount_text': amount_to_thai_text(amount_requested),
                            'amount_requested': f"{amount_requested:,.2f}",
                            'amount_requested_text': amount_to_thai_text(amount_requested),
                            'amount_approved': f"{amount_approved:,.2f}",
                            'amount_approved_text': amount_to_thai_text(amount_approved),
                            'receipt_count': str(receipt_count),
                            'is_full_amount': 'ใช่' if is_full_amount else 'ไม่ใช่',
                            'treatment_date': treatment_date_thai_range, # compatibility key
                            'treatment_date_range': treatment_date_thai_range,
                            'hospital_name': facility['facility_name'],
                            'hospital_type': facility['facility_type'] or '-',
                            'checkbox_self': checkbox(beneficiary_type == 'self'),
                            'checkbox_child': checkbox(beneficiary_type == 'dependent'),
                            'checkbox_gov': checkbox(facility.get('facility_type') in ['รัฐบาล', 'ราชการ']),
                            'checkbox_private': checkbox(facility.get('facility_type') == 'เอกชน'),
                            'checkbox_full': checkbox(bool(is_full_amount)),
                            'checkbox_partial': checkbox(not bool(is_full_amount)),
                            
                            # Real Template Placeholders
                            'staff_name': staff['full_name'],
                            'staff_id': str(staff['id']),
                            'position_name': staff['position'] or '-',
                            'grade': str(staff['grade'] or '-'),
                            'section_name': staff['department'] or '-',
                            'division_name': staff['division_name'] or '-',
                            'facility_name': facility['facility_name'],
                            'treatment_date_start_thai': treatment_date_start_thai,
                            'treatment_date_end_thai': treatment_date_end_thai
                        }
                        
                        # Generate Word file
                        docx_path = generate_medical_expense_docx('medical_expense_template.docx', docx_filename, doc_data)
                        
                        # Convert to PDF
                        pdf_filename = f"medical_expense_{inserted_id}.pdf"
                        pdf_path = convert_docx_to_pdf(docx_path, Config.OUTPUT_DOCX_DIR)
                        
                        # Update path in DB inside the same transaction
                        conn.execute(
                            "UPDATE medical_expenses SET docx_path = ?, pdf_path = ? WHERE id = ?",
                            (docx_filename, pdf_filename if pdf_path else None, inserted_id)
                        )
                except Exception as e:
                    flash(f'เกิดข้อผิดพลาดในการบันทึกข้อมูลหรือสร้างเอกสาร: {str(e)}', 'danger')
                    return redirect(url_for('medical_expense.form'))
 
                # 3. Log to markdown
                log_data = {
                    'id': inserted_id,
                    'staff_name': staff['full_name'],
                    'beneficiary_type': 'ตนเอง' if beneficiary_type == 'self' else f"บุตร ({dependent['full_name']})",
                    'dependent_name': dependent['full_name'] if dependent else '-',
                    'amount': f"{amount_requested:,.2f}", # compatibility
                    'amount_requested': f"{amount_requested:,.2f}",
                    'amount_approved': f"{amount_approved:,.2f}",
                    'receipt_count': str(receipt_count),
                    'is_full_amount': 'ใช่' if is_full_amount else 'ไม่ใช่',
                    'treatment_date_thai': treatment_date_thai_range, # compatibility
                    'treatment_date_start_thai': treatment_date_start_thai,
                    'treatment_date_end_thai': treatment_date_end_thai,
                    'hospital_name': facility['facility_name'],
                    'created_at': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
                try:
                    log_to_markdown('medical_expense', log_data)
                except Exception as e:
                    flash(f'เกิดข้อผิดพลาดในการบันทึก Log ลงไฟล์ Markdown: {str(e)}', 'danger')
 
                flash('บันทึกคำขอเบิกจ่ายค่ารักษาพยาบาลและสร้างเอกสารราชการสำเร็จ', 'success')
                return redirect(url_for('medical_expense.success_view', expense_id=inserted_id))
        else:
            errors = form_validator.errors
            form_data = request.form
 
    # Load active staff members for dropdown
    staff_members = get_active_staff()
    
    # Load medical facilities
    facilities = []
    with get_db() as conn:
        cursor = conn.execute("SELECT id, facility_name, facility_type FROM medical_facilities ORDER BY facility_name")
        facilities = [dict(row) for row in cursor.fetchall()]
 
    return render_template(
        'medical_expense/form.html', 
        staff_members=staff_members, 
        facilities=facilities,
        errors=errors, 
        form_data=form_data
    )

@medical_expense_bp.route('/edit/<int:expense_id>', methods=['GET', 'POST'])
def edit(expense_id):
    errors = {}
    with get_db() as conn:
        existing = conn.execute("SELECT * FROM medical_expenses WHERE id = ? AND (is_deleted = 0 OR is_deleted IS NULL)", (expense_id,)).fetchone()
        if not existing:
            abort(404, "ไม่พบข้อมูลคำร้องเบิกจ่ายค่ารักษาพยาบาลที่ระบุ")

    if request.method == 'POST':
        form_validator = MedicalExpenseForm(request.form)
        if form_validator.validate():
            staff_id = int(form_validator.staff_id)
            facility_id = int(form_validator.facility_id)
            beneficiary_type = form_validator.beneficiary_type

            staff = get_staff_details(staff_id)
            
            facility = None
            dependent = None
            with get_db() as conn:
                f_row = conn.execute("SELECT * FROM medical_facilities WHERE id = ?", (facility_id,)).fetchone()
                facility = dict(f_row) if f_row else None
                if beneficiary_type == 'dependent':
                    dep_row = conn.execute(
                        "SELECT * FROM medical_dependents WHERE id = ? AND staff_id = ?",
                        (int(form_validator.dependent_id), staff_id)
                    ).fetchone()
                    dependent = dict(dep_row) if dep_row else None

            if not staff:
                errors['staff_id'] = 'ไม่พบข้อมูลพนักงานในระบบ'
            elif not facility:
                errors['facility_id'] = 'ไม่พบข้อมูลสถานพยาบาลในระบบ'
            elif beneficiary_type == 'dependent' and not dependent:
                errors['dependent_id'] = 'ไม่พบข้อมูลผู้พึ่งพิง/บุตร ของพนักงานท่านนี้'
            else:
                try:
                    amount_requested = float(form_validator.amount_requested)
                    is_full_amount = bool(form_validator.is_full_amount)
                    amount_approved = amount_requested if is_full_amount else float(form_validator.amount_approved)
                    receipt_count = int(form_validator.receipt_count)
                    treatment_date_start = form_validator.treatment_date_start
                    treatment_date_end = form_validator.treatment_date_end
                    now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

                    # 1. Update in DB and regenerate docs in transaction
                    with get_db() as conn:
                        conn.execute("""
                            UPDATE medical_expenses SET
                                staff_id = ?,
                                beneficiary_type = ?,
                                dependent_id = ?,
                                facility_id = ?,
                                treatment_date_start = ?,
                                treatment_date_end = ?,
                                amount_requested = ?,
                                receipt_count = ?,
                                is_full_amount = ?,
                                amount_approved = ?,
                                updated_at = ?
                            WHERE id = ?
                        """, (
                            staff_id, beneficiary_type,
                            dependent['id'] if dependent else None,
                            facility_id, treatment_date_start, treatment_date_end,
                            amount_requested, receipt_count, is_full_amount, amount_approved,
                            now_str, expense_id
                        ))

                        # 2. Document generation
                        docx_filename = f"medical_expense_{expense_id}.docx"
                        beneficiary_name = "" if beneficiary_type == 'self' else (dependent['full_name'] if dependent else "")
                        beneficiary_rel = 'ตนเอง' if beneficiary_type == 'self' else ((dependent['relationship'] if dependent else None) or 'บุตร')
                        
                        treatment_date_start_thai = to_thai_date(treatment_date_start)
                        treatment_date_end_thai = to_thai_date(treatment_date_end)
                        treatment_date_thai_range = f"{treatment_date_start_thai} - {treatment_date_end_thai}" if treatment_date_start != treatment_date_end else treatment_date_start_thai

                        doc_data = {
                            'full_name': staff['full_name'],
                            'position': staff['position'] or '-',
                            'department': f"{staff['department']} (กอง {staff['division_name']})" if staff['division_name'] else staff['department'],
                            'beneficiary_name': beneficiary_name,
                            'beneficiary_type': beneficiary_rel,
                            'amount': f"{amount_requested:,.2f}",
                            'amount_text': amount_to_thai_text(amount_requested),
                            'amount_requested': f"{amount_requested:,.2f}",
                            'amount_requested_text': amount_to_thai_text(amount_requested),
                            'amount_approved': f"{amount_approved:,.2f}",
                            'amount_approved_text': amount_to_thai_text(amount_approved),
                            'receipt_count': str(receipt_count),
                            'is_full_amount': 'ใช่' if is_full_amount else 'ไม่ใช่',
                            'treatment_date': treatment_date_thai_range,
                            'treatment_date_range': treatment_date_thai_range,
                            'hospital_name': facility['facility_name'],
                            'hospital_type': facility['facility_type'] or '-',
                            'checkbox_self': checkbox(beneficiary_type == 'self'),
                            'checkbox_child': checkbox(beneficiary_type == 'dependent'),
                            'checkbox_gov': checkbox(facility.get('facility_type') in ['รัฐบาล', 'ราชการ']),
                            'checkbox_private': checkbox(facility.get('facility_type') == 'เอกชน'),
                            'checkbox_full': checkbox(bool(is_full_amount)),
                            'checkbox_partial': checkbox(not bool(is_full_amount)),
                            'staff_name': staff['full_name'],
                            'staff_id': str(staff['id']),
                            'position_name': staff['position'] or '-',
                            'grade': str(staff['grade'] or '-'),
                            'section_name': staff['department'] or '-',
                            'division_name': staff['division_name'] or '-',
                            'facility_name': facility['facility_name'],
                            'treatment_date_start_thai': treatment_date_start_thai,
                            'treatment_date_end_thai': treatment_date_end_thai
                        }

                        docx_path = generate_medical_expense_docx('medical_expense_template.docx', docx_filename, doc_data)
                        pdf_filename = f"medical_expense_{expense_id}.pdf"
                        pdf_path = convert_docx_to_pdf(docx_path, Config.OUTPUT_DOCX_DIR)
                        conn.execute(
                            "UPDATE medical_expenses SET docx_path = ?, pdf_path = ? WHERE id = ?",
                            (docx_filename, pdf_filename if pdf_path else None, expense_id)
                        )

                    flash(f'แก้ไขใบเบิกค่ารักษาพยาบาล #{expense_id} และอัปเดตเอกสารสำเร็จ', 'success')
                    return redirect(url_for('medical_expense.success_view', expense_id=expense_id))
                except Exception as e:
                    flash(f'เกิดข้อผิดพลาดในการบันทึกการแก้ไข: {str(e)}', 'danger')
        else:
            errors = form_validator.errors
        form_data = request.form
    else:
        form_data = dict(existing)
        form_data['is_full_amount'] = '1' if existing['is_full_amount'] else '0'

    staff_members = get_active_staff()
    facilities = []
    with get_db() as conn:
        cursor = conn.execute("SELECT id, facility_name, facility_type FROM medical_facilities ORDER BY facility_name")
        facilities = [dict(row) for row in cursor.fetchall()]

    return render_template(
        'medical_expense/form.html',
        staff_members=staff_members,
        facilities=facilities,
        errors=errors,
        form_data=form_data,
        is_edit=True,
        edit_id=expense_id
    )

# --- AJAX APIs ---

@medical_expense_bp.route('/api/dependents/<int:staff_id>', methods=['GET'])
def get_dependents(staff_id):
    """
    Returns a list of dependents for a specific staff member.
    """
    dependents = []
    try:
        with get_db() as conn:
            cursor = conn.execute(
                "SELECT id, full_name, relationship FROM medical_dependents WHERE staff_id = ? ORDER BY full_name",
                (staff_id,)
            )
            dependents = [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
        
    return jsonify({"success": True, "dependents": dependents})

@medical_expense_bp.route('/api/dependents/add', methods=['POST'])
def add_dependent_api():
    """
    Adds a new dependent via AJAX.
    """
    staff_id = request.form.get('staff_id')
    full_name = request.form.get('full_name', '').strip()
    relationship = request.form.get('relationship', 'บุตร').strip() or 'บุตร'
    
    if not staff_id or not full_name:
        return jsonify({"success": False, "error": "กรุณากรอกข้อมูลให้ครบถ้วน"}), 400
        
    try:
        with get_db() as conn:
            # Check if staff exists
            staff_check = conn.execute("SELECT id FROM staff WHERE id = ?", (staff_id,)).fetchone()
            if not staff_check:
                return jsonify({"success": False, "error": "ไม่พบพนักงานในระบบ"}), 400
                
            cursor = conn.execute(
                "INSERT INTO medical_dependents (staff_id, full_name, relationship) VALUES (?, ?, ?)",
                (staff_id, full_name, relationship)
            )
            inserted_id = cursor.lastrowid
            
        return jsonify({
            "success": True, 
            "dependent": {
                "id": inserted_id,
                "full_name": full_name,
                "relationship": relationship
            }
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@medical_expense_bp.route('/success/<int:expense_id>')
def success_view(expense_id):
    with get_db() as conn:
        cursor = conn.execute("""
            SELECT m.id, m.beneficiary_type, m.amount_requested, m.amount_approved,
                   m.treatment_date_start, m.treatment_date_end, m.docx_path, m.pdf_path,
                   s.full_name as staff_name, dep.full_name as dependent_name
            FROM medical_expenses m
            LEFT JOIN staff s ON m.staff_id = s.id
            LEFT JOIN medical_dependents dep ON m.dependent_id = dep.id
            WHERE m.id = ?
        """, (expense_id,))
        row = cursor.fetchone()
        if not row:
            abort(404)
        expense = dict(row)
        
    return render_template('medical_expense/success.html', expense=expense)

@medical_expense_bp.route('/download/<filename>')
def download_file(filename):
    if not filename.endswith('.docx') or not filename.startswith('medical_expense_'):
        abort(400, "ชื่อไฟล์ไม่ถูกต้อง")
    return send_from_directory(Config.OUTPUT_DOCX_DIR, filename, as_attachment=True)

@medical_expense_bp.route('/view-pdf/<filename>')
def view_pdf(filename):
    if not filename.endswith('.pdf') or not filename.startswith('medical_expense_'):
        abort(400, "ชื่อไฟล์ไม่ถูกต้อง")
    return send_from_directory(Config.OUTPUT_DOCX_DIR, filename, as_attachment=False, mimetype='application/pdf')

