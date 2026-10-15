import datetime
import os
from flask import render_template, request, redirect, url_for, flash, jsonify, send_from_directory, abort
from modules.travel_approval import travel_approval_bp
from modules.travel_approval.forms import TravelApprovalForm
from shared import get_db, get_active_staff, get_staff_details, log_to_markdown, to_thai_date, checkbox, generate_travel_approval_docx, convert_docx_to_pdf
from config import Config

@travel_approval_bp.route('/', methods=['GET', 'POST'])
def form():
    errors = {}
    form_data = {}
    
    if request.method == 'POST':
        form_validator = TravelApprovalForm(request.form)
        if form_validator.validate():
            staff_id = int(form_validator.staff_id)
            staff = get_staff_details(staff_id)
            
            if not staff:
                errors['staff_id'] = 'ไม่พบข้อมูลพนักงานในระบบ'
            else:
                date_start = form_validator.date_start
                date_end = form_validator.date_end
                purpose = form_validator.purpose
                vehicle_id = int(form_validator.vehicle_id)
                acting_replacement = form_validator.acting_replacement
                acting_replacement_position = form_validator.acting_replacement_position
                
                # Fetch vehicle info
                with get_db() as conn:
                    vehicle_row = conn.execute(
                        """
                        SELECT v.plate_number, vt.type_name 
                        FROM vehicles v 
                        JOIN vehicle_types vt ON v.vehicle_type_id = vt.id 
                        WHERE v.id = ?
                        """, (vehicle_id,)
                    ).fetchone()
                vehicle_info = dict(vehicle_row) if vehicle_row else None
                
                if vehicle_info is None:
                    errors['vehicle_id'] = 'ไม่พบข้อมูลยานพาหนะในระบบ'
                else:
                    # Calculate total days in backend
                    try:
                        d1 = datetime.datetime.strptime(date_start, "%Y-%m-%d")
                        d2 = datetime.datetime.strptime(date_end, "%Y-%m-%d")
                        total_days = (d2 - d1).days + 1
                    except Exception:
                        total_days = 1
                    
                    companion_staff_ids = form_validator.companion_staff_ids
                    
                    date_start_thai = to_thai_date(date_start)
                    date_end_thai = to_thai_date(date_end)
                    
                    # 1. Database insertion and document generation
                    try:
                        with get_db() as conn:
                            cursor = conn.execute(
                                """
                                INSERT INTO travel_approvals 
                                (document_number, staff_id, date_start, date_end, total_days, purpose, vehicle_id, acting_replacement, acting_replacement_position, status) 
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
                                """,
                                (
                                    form_validator.document_number or None,
                                    staff_id,
                                    date_start,
                                    date_end,
                                    total_days,
                                    purpose,
                                    vehicle_id,
                                    acting_replacement or None,
                                    acting_replacement_position or None
                                )
                            )
                            inserted_id = cursor.lastrowid
                            
                            # Save companions
                            for comp_id in companion_staff_ids:
                                conn.execute(
                                    """
                                    INSERT INTO travel_approval_companions (travel_approval_id, staff_id)
                                    VALUES (?, ?)
                                    """,
                                    (inserted_id, comp_id)
                                )
                            
                            # 2. Document generation using docxtpl
                            docx_path = generate_travel_approval_docx(inserted_id, conn)
                            docx_filename = f"travel_approval_{inserted_id}.docx"
                            
                            # Convert to PDF
                            pdf_filename = f"travel_approval_{inserted_id}.pdf"
                            pdf_path = convert_docx_to_pdf(docx_path, Config.OUTPUT_DOCX_DIR)
                            
                            # Update docx_path and pdf_path in DB
                            conn.execute(
                                "UPDATE travel_approvals SET docx_path = ?, pdf_path = ? WHERE id = ?",
                                (docx_filename, pdf_filename if pdf_path else None, inserted_id)
                            )
                            
                            # Fetch companions from DB for logging
                            companions_rows = conn.execute(
                                """
                                SELECT s.full_name 
                                FROM travel_approval_companions tac
                                JOIN staff s ON tac.staff_id = s.id
                                WHERE tac.travel_approval_id = ?
                                ORDER BY tac.id ASC
                                """, (inserted_id,)
                            ).fetchall()
                            companions_str = ", ".join([r['full_name'] for r in companions_rows]) if companions_rows else "ไม่มี"
                    except Exception as e:
                        flash(f'เกิดข้อผิดพลาดในการบันทึกข้อมูลหรือสร้างเอกสาร: {str(e)}', 'danger')
                        return redirect(url_for('travel_approval.form'))
                    
                    # 3. Log to markdown
                    log_data = {
                        'id': inserted_id,
                        'staff_name': staff['full_name'],
                        'document_number': form_validator.document_number or '-',
                        'date_start': date_start_thai,
                        'date_end': date_end_thai,
                        'total_days': f"{total_days} วัน",
                        'purpose': purpose,
                        'vehicle': f"{vehicle_info['plate_number']} ({vehicle_info['type_name']})",
                        'acting_replacement': f"{acting_replacement} ({acting_replacement_position})" if (acting_replacement and acting_replacement_position) else (acting_replacement or 'ไม่มี'),
                        'companions': companions_str,
                        'status': 'pending',
                        'created_at': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    }
                    try:
                        log_to_markdown('travel_approval', log_data)
                    except Exception as e:
                        flash(f'เกิดข้อผิดพลาดในการบันทึก Log ลงไฟล์ Markdown: {str(e)}', 'danger')
                    
                    flash(f'บันทึกใบขออนุมัติเดินทาง #{inserted_id} และสร้างเอกสารสำเร็จ', 'success')
                    return redirect(url_for('travel_approval.success_view', approval_id=inserted_id))
        else:
            errors = form_validator.errors
            form_data = request.form
            
    # Load active staff members for dropdown
    staff_members = get_active_staff()
    
    # Load vehicles
    vehicles = []
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT v.id, v.plate_number, vt.type_name, vt.rate_per_km,
                   s.full_name as owner_name
            FROM vehicles v
            JOIN vehicle_types vt ON v.vehicle_type_id = vt.id
            LEFT JOIN staff s ON v.staff_id = s.id
            ORDER BY vt.type_name, v.plate_number
            """
        ).fetchall()
        vehicles = [dict(r) for r in rows]
        
    # Preserve companion selections when re-rendering on validation error
    if request.method == 'POST' and 'form_validator' in dir():
        companion_staff_ids = form_validator.companion_staff_ids
    else:
        companion_staff_ids = []
            
    return render_template(
        'travel_approval/form.html', 
        staff_members=staff_members, 
        vehicles=vehicles,
        errors=errors, 
        form_data=form_data,
        companion_staff_ids=companion_staff_ids
    )

@travel_approval_bp.route('/edit/<int:approval_id>', methods=['GET', 'POST'])
def edit(approval_id):
    errors = {}
    with get_db() as conn:
        existing = conn.execute("SELECT * FROM travel_approvals WHERE id = ? AND (is_deleted = 0 OR is_deleted IS NULL)", (approval_id,)).fetchone()
        if not existing:
            abort(404, "ไม่พบข้อมูลคำร้องขออนุมัติเดินทางที่ระบุ")

    if request.method == 'POST':
        form_validator = TravelApprovalForm(request.form)
        if form_validator.validate():
            with get_db() as conn:
                staff = conn.execute("SELECT id, full_name FROM staff WHERE id = ?", (form_validator.staff_id,)).fetchone()
                vehicle_info = conn.execute("""
                    SELECT v.id, v.plate_number, vt.type_name 
                    FROM vehicles v 
                    JOIN vehicle_types vt ON v.vehicle_type_id = vt.id 
                    WHERE v.id = ?
                """, (form_validator.vehicle_id,)).fetchone()
                
                if not staff:
                    errors['staff_id'] = 'ไม่พบข้อมูลพนักงานที่เลือกในระบบ'
                elif not vehicle_info:
                    errors['vehicle_id'] = 'ไม่พบข้อมูลยานพาหนะที่เลือกในระบบ'
                else:
                    try:
                        date_start = form_validator.date_start
                        date_end = form_validator.date_end
                        dt_start = datetime.datetime.strptime(date_start, "%Y-%m-%d")
                        dt_end = datetime.datetime.strptime(date_end, "%Y-%m-%d")
                        total_days = (dt_end - dt_start).days + 1
                        
                        purpose = form_validator.purpose
                        acting_replacement = form_validator.acting_replacement
                        acting_replacement_position = form_validator.acting_replacement_position
                        now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

                        # 1. Update DB
                        conn.execute("""
                            UPDATE travel_approvals SET
                                document_number = ?,
                                staff_id = ?,
                                date_start = ?,
                                date_end = ?,
                                total_days = ?,
                                purpose = ?,
                                vehicle_id = ?,
                                acting_replacement = ?,
                                acting_replacement_position = ?,
                                updated_at = ?
                            WHERE id = ?
                        """, (
                            form_validator.document_number or None,
                            form_validator.staff_id,
                            date_start,
                            date_end,
                            total_days,
                            purpose,
                            form_validator.vehicle_id,
                            acting_replacement or None,
                            acting_replacement_position or None,
                            now_str,
                            approval_id
                        ))

                        # 2. Update companions
                        conn.execute("DELETE FROM travel_approval_companions WHERE travel_approval_id = ?", (approval_id,))
                        for comp_id in form_validator.companion_staff_ids:
                            conn.execute("INSERT INTO travel_approval_companions (travel_approval_id, staff_id) VALUES (?, ?)", (approval_id, comp_id))

                        # 3. Regenerate documents overwriting existing files
                        docx_path = generate_travel_approval_docx(approval_id, conn)
                        docx_filename = f"travel_approval_{approval_id}.docx"
                        pdf_filename = f"travel_approval_{approval_id}.pdf"
                        pdf_path = convert_docx_to_pdf(docx_path, Config.OUTPUT_DOCX_DIR)
                        conn.execute(
                            "UPDATE travel_approvals SET docx_path = ?, pdf_path = ? WHERE id = ?",
                            (docx_filename, pdf_filename if pdf_path else None, approval_id)
                        )

                        flash(f'แก้ไขใบขออนุมัติเดินทาง #{approval_id} และอัปเดตเอกสารสำเร็จ', 'success')
                        return redirect(url_for('travel_approval.success_view', approval_id=approval_id))
                    except Exception as e:
                        flash(f'เกิดข้อผิดพลาดในการบันทึกการแก้ไข: {str(e)}', 'danger')
        else:
            errors = form_validator.errors
        form_data = request.form
        companion_staff_ids = form_validator.companion_staff_ids
    else:
        form_data = dict(existing)
        with get_db() as conn:
            comp_rows = conn.execute("SELECT staff_id FROM travel_approval_companions WHERE travel_approval_id = ?", (approval_id,)).fetchall()
            companion_staff_ids = [r['staff_id'] for r in comp_rows]

    staff_members = get_active_staff()
    vehicles = []
    with get_db() as conn:
        rows = conn.execute("""
            SELECT v.id, v.plate_number, vt.type_name, vt.rate_per_km, s.full_name as owner_name
            FROM vehicles v
            JOIN vehicle_types vt ON v.vehicle_type_id = vt.id
            LEFT JOIN staff s ON v.staff_id = s.id
            ORDER BY vt.type_name, v.plate_number
        """).fetchall()
        vehicles = [dict(r) for r in rows]

    return render_template(
        'travel_approval/form.html',
        staff_members=staff_members,
        vehicles=vehicles,
        errors=errors,
        form_data=form_data,
        companion_staff_ids=companion_staff_ids,
        is_edit=True,
        edit_id=approval_id
    )

@travel_approval_bp.route('/success/<int:approval_id>')
def success_view(approval_id):
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT ta.id, ta.document_number, ta.docx_path, ta.pdf_path, s.full_name as staff_name
            FROM travel_approvals ta
            LEFT JOIN staff s ON ta.staff_id = s.id
            WHERE ta.id = ?
            """,
            (approval_id,)
        ).fetchone()
        if not row:
            abort(404)
        approval = dict(row)
        
    return render_template('travel_approval/success.html', approval=approval)

@travel_approval_bp.route('/download/<filename>')
def download_file(filename):
    if not filename.endswith('.docx') or not filename.startswith('travel_approval_'):
        abort(400, "ชื่อไฟล์ไม่ถูกต้อง")
    return send_from_directory(Config.OUTPUT_DOCX_DIR, filename, as_attachment=True)

@travel_approval_bp.route('/view-pdf/<filename>')
def view_pdf(filename):
    if not filename.endswith('.pdf') or not filename.startswith('travel_approval_'):
        abort(400, "ชื่อไฟล์ไม่ถูกต้อง")
    return send_from_directory(Config.OUTPUT_DOCX_DIR, filename, as_attachment=False, mimetype='application/pdf')
