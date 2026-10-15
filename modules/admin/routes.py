import os
import re
from flask import render_template, request, redirect, url_for, session, flash, send_from_directory, abort
from werkzeug.security import check_password_hash
from config import Config
from modules.admin import admin_bp
from modules.admin.auth import admin_required
from shared.db import get_db
from shared.date_utils import to_thai_date

@admin_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        # Verify credentials
        if username == Config.ADMIN_USERNAME and check_password_hash(Config.ADMIN_PASSWORD_HASH, password):
            session['admin_logged_in'] = True
            flash('เข้าสู่ระบบสำเร็จ', 'success')
            return redirect(url_for('admin.dashboard'))
        else:
            flash('ชื่อผู้ใช้งานหรือรหัสผ่านไม่ถูกต้อง', 'danger')
            
    return render_template('login.html')

@admin_bp.route('/logout')
def logout():
    session.pop('admin_logged_in', None)
    flash('ออกจากระบบเรียบร้อยแล้ว', 'success')
    return redirect(url_for('index'))

PER_PAGE = 20

def _paginate_query(conn, base_sql, count_sql, params, page):
    """Helper: returns (rows_list, total_count, total_pages)."""
    total = conn.execute(count_sql, params).fetchone()[0]
    total_pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
    page = max(1, min(page, total_pages))
    offset = (page - 1) * PER_PAGE
    rows = conn.execute(base_sql + f" LIMIT {PER_PAGE} OFFSET {offset}", params).fetchall()
    return [dict(r) for r in rows], total, total_pages, page

@admin_bp.route('/')
@admin_required
def dashboard():
    # ── Approval filters ──────────────────────────────────────────────────────
    app_search   = request.args.get('app_search', '').strip()
    app_date_from = request.args.get('app_date_from', '').strip()
    app_date_to   = request.args.get('app_date_to', '').strip()
    app_status    = request.args.get('app_status', '').strip()
    app_page      = int(request.args.get('app_page', 1))

    # ── Expense filters ───────────────────────────────────────────────────────
    exp_search    = request.args.get('exp_search', '').strip()
    exp_date_from = request.args.get('exp_date_from', '').strip()
    exp_date_to   = request.args.get('exp_date_to', '').strip()
    exp_page      = int(request.args.get('exp_page', 1))

    # ── Medical filters ───────────────────────────────────────────────────────
    med_search    = request.args.get('med_search', '').strip()
    med_date_from = request.args.get('med_date_from', '').strip()
    med_date_to   = request.args.get('med_date_to', '').strip()
    med_page      = int(request.args.get('med_page', 1))

    with get_db() as conn:

        # ── Travel Approvals ──────────────────────────────────────────────────
        app_where = ["t.is_deleted = 0"]
        app_params = []
        if app_search:
            app_where.append("(s.full_name LIKE ? OR t.document_number LIKE ? OR t.purpose LIKE ?)")
            app_params += [f"%{app_search}%"] * 3
        if app_date_from:
            app_where.append("t.date_start >= ?")
            app_params.append(app_date_from)
        if app_date_to:
            app_where.append("t.date_end <= ?")
            app_params.append(app_date_to)
        if app_status:
            app_where.append("t.status = ?")
            app_params.append(app_status)

        app_where_sql = " AND ".join(app_where)
        app_base_sql = f"""
            SELECT t.id, t.document_number, t.date_start, t.date_end, t.purpose,
                   t.status, t.docx_path, t.pdf_path, t.created_at, s.full_name AS staff_name
            FROM travel_approvals t
            LEFT JOIN staff s ON t.staff_id = s.id
            WHERE {app_where_sql}
            ORDER BY t.id DESC
        """
        app_count_sql = f"""
            SELECT COUNT(*) FROM travel_approvals t
            LEFT JOIN staff s ON t.staff_id = s.id
            WHERE {app_where_sql}
        """
        raw_approvals, app_total, app_total_pages, app_page = _paginate_query(
            conn, app_base_sql, app_count_sql, app_params, app_page
        )
        approvals = []
        for d in raw_approvals:
            d['travel_date_thai'] = f"{to_thai_date(d.get('date_start'))} – {to_thai_date(d.get('date_end'))}"
            approvals.append(d)

        # ── Travel Expenses ───────────────────────────────────────────────────
        exp_where = ["e.is_deleted = 0"]
        exp_params = []
        if exp_search:
            exp_where.append("(s.full_name LIKE ? OR e.approval_document_number LIKE ?)")
            exp_params += [f"%{exp_search}%"] * 2
        if exp_date_from:
            exp_where.append("e.depart_date >= ?")
            exp_params.append(exp_date_from)
        if exp_date_to:
            exp_where.append("e.depart_date <= ?")
            exp_params.append(exp_date_to)

        exp_where_sql = " AND ".join(exp_where)
        exp_base_sql = f"""
            SELECT e.id, e.approval_document_number, e.total_amount AS amount,
                   e.depart_date AS expense_date, e.return_date, e.docx_path, e.created_at,
                   s.full_name AS staff_name
            FROM travel_expenses e
            LEFT JOIN staff s ON e.staff_id = s.id
            WHERE {exp_where_sql}
            ORDER BY e.id DESC
        """
        exp_count_sql = f"""
            SELECT COUNT(*) FROM travel_expenses e
            LEFT JOIN staff s ON e.staff_id = s.id
            WHERE {exp_where_sql}
        """
        raw_expenses, exp_total, exp_total_pages, exp_page = _paginate_query(
            conn, exp_base_sql, exp_count_sql, exp_params, exp_page
        )
        expenses = []
        for d in raw_expenses:
            d['expense_date_thai'] = to_thai_date(d.get('expense_date'))
            expenses.append(d)

        # ── Medical Expenses ──────────────────────────────────────────────────
        med_where = ["m.is_deleted = 0"]
        med_params = []
        if med_search:
            med_where.append("(s.full_name LIKE ? OR fac.facility_name LIKE ? OR dep.full_name LIKE ?)")
            med_params += [f"%{med_search}%"] * 3
        if med_date_from:
            med_where.append("m.treatment_date_start >= ?")
            med_params.append(med_date_from)
        if med_date_to:
            med_where.append("m.treatment_date_end <= ?")
            med_params.append(med_date_to)

        med_where_sql = " AND ".join(med_where)
        med_base_sql = f"""
            SELECT m.id, m.beneficiary_type, m.amount_requested, m.amount_approved,
                   m.receipt_count, m.treatment_date_start, m.treatment_date_end,
                   m.docx_path, m.pdf_path, m.created_at,
                   s.full_name AS staff_name, dep.full_name AS dependent_name,
                   fac.facility_name AS hospital_name
            FROM medical_expenses m
            LEFT JOIN staff s ON m.staff_id = s.id
            LEFT JOIN medical_dependents dep ON m.dependent_id = dep.id
            LEFT JOIN medical_facilities fac ON m.facility_id = fac.id
            WHERE {med_where_sql}
            ORDER BY m.id DESC
        """
        med_count_sql = f"""
            SELECT COUNT(*) FROM medical_expenses m
            LEFT JOIN staff s ON m.staff_id = s.id
            LEFT JOIN medical_dependents dep ON m.dependent_id = dep.id
            LEFT JOIN medical_facilities fac ON m.facility_id = fac.id
            WHERE {med_where_sql}
        """
        raw_medicals, med_total, med_total_pages, med_page = _paginate_query(
            conn, med_base_sql, med_count_sql, med_params, med_page
        )
        medicals = []
        for d in raw_medicals:
            start_date = d.get('treatment_date_start')
            end_date   = d.get('treatment_date_end')
            d['treatment_date_thai'] = (
                to_thai_date(start_date) if start_date == end_date
                else f"{to_thai_date(start_date)} – {to_thai_date(end_date)}"
            )
            medicals.append(d)

    return render_template(
        'dashboard.html',
        # data
        approvals=approvals, expenses=expenses, medicals=medicals,
        # approval pagination/filter
        app_search=app_search, app_date_from=app_date_from, app_date_to=app_date_to,
        app_status=app_status, app_page=app_page, app_total_pages=app_total_pages,
        app_total=app_total,
        # expense pagination/filter
        exp_search=exp_search, exp_date_from=exp_date_from, exp_date_to=exp_date_to,
        exp_page=exp_page, exp_total_pages=exp_total_pages, exp_total=exp_total,
        # medical pagination/filter
        med_search=med_search, med_date_from=med_date_from, med_date_to=med_date_to,
        med_page=med_page, med_total_pages=med_total_pages, med_total=med_total,
    )


@admin_bp.route('/update-status/<int:approval_id>', methods=['POST'])
@admin_required
def update_status(approval_id):
    status = request.form.get('status')
    if status not in ['approved', 'rejected', 'pending']:
        flash('สถานะไม่ถูกต้อง', 'danger')
        return redirect(url_for('admin.dashboard'))
        
    with get_db() as conn:
        conn.execute(
            "UPDATE travel_approvals SET status = ? WHERE id = ?",
            (status, approval_id)
        )
    flash(f"อัปเดตสถานะคำขออนุมัติเดินทางเป็น '{status}' เรียบร้อยแล้ว", "success")
    return redirect(url_for('admin.dashboard'))

@admin_bp.route('/soft-delete/<string:doc_type>/<int:doc_id>', methods=['POST'])
@admin_required
def soft_delete(doc_type, doc_id):
    table_map = {
        'travel_approval': 'travel_approvals',
        'travel_expense': 'travel_expenses',
        'medical_expense': 'medical_expenses'
    }
    table_name = table_map.get(doc_type)
    if not table_name:
        flash('ประเภทเอกสารไม่ถูกต้อง', 'danger')
        return redirect(url_for('admin.dashboard'))
        
    try:
        with get_db() as conn:
            conn.execute(f"UPDATE {table_name} SET is_deleted = 1 WHERE id = ?", (doc_id,))
        flash('ย้ายเอกสารไปที่ถังขยะเรียบร้อยแล้ว', 'success')
    except Exception as e:
        flash(f'เกิดข้อผิดพลาดในการลบเอกสาร: {str(e)}', 'danger')
        
    return redirect(url_for('admin.dashboard'))

@admin_bp.route('/restore/<string:doc_type>/<int:doc_id>', methods=['POST'])
@admin_required
def restore(doc_type, doc_id):
    table_map = {
        'travel_approval': 'travel_approvals',
        'travel_expense': 'travel_expenses',
        'medical_expense': 'medical_expenses'
    }
    table_name = table_map.get(doc_type)
    if not table_name:
        flash('ประเภทเอกสารไม่ถูกต้อง', 'danger')
        return redirect(url_for('admin.trash'))
        
    try:
        with get_db() as conn:
            conn.execute(f"UPDATE {table_name} SET is_deleted = 0 WHERE id = ?", (doc_id,))
        flash('กู้คืนเอกสารเรียบร้อยแล้ว', 'success')
    except Exception as e:
        flash(f'เกิดข้อผิดพลาดในการกู้คืนเอกสาร: {str(e)}', 'danger')
        
    return redirect(url_for('admin.trash'))

@admin_bp.route('/trash')
@admin_required
def trash():
    with get_db() as conn:
        # Fetch deleted approvals
        cursor = conn.execute("""
            SELECT t.id, t.document_number, t.date_start, t.date_end, t.purpose, t.status, t.docx_path, t.created_at, s.full_name as staff_name 
            FROM travel_approvals t 
            LEFT JOIN staff s ON t.staff_id = s.id 
            WHERE t.is_deleted = 1
            ORDER BY t.id DESC
        """)
        approvals = []
        for r in cursor.fetchall():
            d = dict(r)
            d['travel_date_thai'] = f"{to_thai_date(d.get('date_start'))} – {to_thai_date(d.get('date_end'))}"
            approvals.append(d)

        # Fetch deleted travel expenses
        cursor = conn.execute("""
            SELECT e.id, e.approval_document_number, e.total_amount AS amount,
                   e.depart_date AS expense_date, e.docx_path, e.created_at,
                   s.full_name as staff_name 
            FROM travel_expenses e 
            LEFT JOIN staff s ON e.staff_id = s.id 
            WHERE e.is_deleted = 1
            ORDER BY e.id DESC
        """)
        expenses = []
        for r in cursor.fetchall():
            d = dict(r)
            d['expense_date_thai'] = to_thai_date(d.get('expense_date'))
            expenses.append(d)

        # Fetch deleted medical expenses
        cursor = conn.execute("""
            SELECT m.id, m.beneficiary_type, m.amount_requested, m.amount_approved,
                   m.treatment_date_start, m.treatment_date_end, m.docx_path, m.pdf_path, m.created_at,
                   s.full_name as staff_name, dep.full_name as dependent_name,
                   fac.facility_name as hospital_name
            FROM medical_expenses m 
            LEFT JOIN staff s ON m.staff_id = s.id 
            LEFT JOIN medical_dependents dep ON m.dependent_id = dep.id
            LEFT JOIN medical_facilities fac ON m.facility_id = fac.id
            WHERE m.is_deleted = 1
            ORDER BY m.id DESC
        """)
        medicals = []
        for r in cursor.fetchall():
            d = dict(r)
            start_date = d.get('treatment_date_start')
            end_date = d.get('treatment_date_end')
            if start_date == end_date:
                d['treatment_date_thai'] = to_thai_date(start_date)
            else:
                d['treatment_date_thai'] = f"{to_thai_date(start_date)} – {to_thai_date(end_date)}"
            medicals.append(d)

    return render_template('trash.html', approvals=approvals, expenses=expenses, medicals=medicals)

# ==========================================
# STAFF CRUD
# ==========================================
@admin_bp.route('/staff')
@admin_required
def staff_manage():
    with get_db() as conn:
        cursor = conn.execute("""
            SELECT s.id, s.full_name, s.grade, s.phone, s.is_active, 
                   p.position_name as position, sec.section_name as department
            FROM staff s
            LEFT JOIN positions p ON s.position_id = p.id
            LEFT JOIN sections sec ON s.section_id = sec.id
            ORDER BY s.id DESC
        """)
        staff_list = [dict(r) for r in cursor.fetchall()]
        
        # Load positions and sections for the dropdowns
        pos_cursor = conn.execute("SELECT id, position_name FROM positions ORDER BY position_name")
        positions = [dict(r) for r in pos_cursor.fetchall()]
        
        sec_cursor = conn.execute("SELECT id, section_name FROM sections ORDER BY section_name")
        sections = [dict(r) for r in sec_cursor.fetchall()]

    return render_template(
        'staff_manage.html', 
        staff_list=staff_list, 
        positions=positions, 
        sections=sections
    )

@admin_bp.route('/staff/add', methods=['POST'])
@admin_required
def add_staff():
    staff_id_raw = request.form.get('staff_id', '').strip()
    full_name = request.form.get('full_name', '').strip()
    position_id = request.form.get('position_id')
    grade = request.form.get('grade', '').strip()
    section_id = request.form.get('section_id')
    phone = request.form.get('phone', '').strip()

    # --- Validate staff_id ---
    if not staff_id_raw:
        flash('กรุณากรอกรหัสพนักงาน', 'danger')
        return redirect(url_for('admin.staff_manage'))
    try:
        staff_id = int(staff_id_raw)
        if staff_id <= 0:
            raise ValueError()
    except ValueError:
        flash('รหัสพนักงานต้องเป็นตัวเลขจำนวนเต็มบวกเท่านั้น', 'danger')
        return redirect(url_for('admin.staff_manage'))

    if not full_name:
        flash('กรุณากรอกชื่อ-นามสกุลพนักงาน', 'danger')
        return redirect(url_for('admin.staff_manage'))

    try:
        with get_db() as conn:
            # Check for duplicate employee ID
            existing = conn.execute("SELECT id FROM staff WHERE id = ?", (staff_id,)).fetchone()
            if existing:
                flash(f'รหัสพนักงาน {staff_id} มีอยู่ในระบบแล้ว กรุณาใช้รหัสอื่น', 'danger')
                return redirect(url_for('admin.staff_manage'))

            conn.execute(
                "INSERT INTO staff (id, full_name, position_id, grade, section_id, phone) VALUES (?, ?, ?, ?, ?, ?)",
                (staff_id, full_name, position_id or None, grade or None, section_id or None, phone or None)
            )
        flash(f"เพิ่มพนักงาน '{full_name}' (รหัส {staff_id}) สำเร็จ", "success")
    except Exception as e:
        flash(f'เกิดข้อผิดพลาดในการเพิ่มพนักงาน: {str(e)}', 'danger')

    return redirect(url_for('admin.staff_manage'))

@admin_bp.route('/staff/toggle/<int:staff_id>', methods=['POST'])
@admin_required
def toggle_staff_status(staff_id):
    with get_db() as conn:
        cursor = conn.execute("SELECT is_active, full_name FROM staff WHERE id = ?", (staff_id,))
        row = cursor.fetchone()
        if not row:
            flash('ไม่พบข้อมูลพนักงาน', 'danger')
            return redirect(url_for('admin.staff_manage'))
            
        new_status = 0 if row['is_active'] else 1
        conn.execute("UPDATE staff SET is_active = ? WHERE id = ?", (new_status, staff_id))
        flash(f"เปลี่ยนสถานะพนักงาน '{row['full_name']}' เรียบร้อยแล้ว", "success")
        
    return redirect(url_for('admin.staff_manage'))

@admin_bp.route('/staff/delete/<int:staff_id>', methods=['POST'])
@admin_required
def delete_staff(staff_id):
    try:
        with get_db() as conn:
            cursor = conn.execute("SELECT full_name FROM staff WHERE id = ?", (staff_id,))
            row = cursor.fetchone()
            if not row:
                flash('ไม่พบข้อมูลพนักงาน', 'danger')
                return redirect(url_for('admin.staff_manage'))
                
            conn.execute("DELETE FROM staff WHERE id = ?", (staff_id,))
            flash(f"ลบข้อมูลพนักงาน '{row['full_name']}' สำเร็จ", "success")
    except Exception as e:
        flash(f"ไม่สามารถลบพนักงานได้: {str(e)}", "danger")
        
    return redirect(url_for('admin.staff_manage'))

# ==========================================
# DEPENDENT CRUD (จัดการสิทธิ์ครอบครัวพนักงาน)
# ==========================================
@admin_bp.route('/dependents')
@admin_required
def dependents_manage():
    edit_id = request.args.get('edit_id')
    edit_dep = None
    
    with get_db() as conn:
        # Load all dependents with their staff details
        cursor = conn.execute("""
            SELECT d.id, d.full_name, d.relationship, d.staff_id, d.created_at,
                   s.full_name as staff_name
            FROM medical_dependents d
            LEFT JOIN staff s ON d.staff_id = s.id
            ORDER BY d.id DESC
        """)
        dependents_list = [dict(r) for r in cursor.fetchall()]
        
        # Load active staff for selection in form
        staff_cursor = conn.execute("SELECT id, full_name FROM staff WHERE is_active = 1 ORDER BY full_name")
        staff_members = [dict(r) for r in staff_cursor.fetchall()]
        
        # Fetch dependent for edit mode if requested
        if edit_id:
            try:
                edit_cursor = conn.execute(
                    "SELECT id, full_name, relationship, staff_id FROM medical_dependents WHERE id = ?",
                    (int(edit_id),)
                )
                row = edit_cursor.fetchone()
                if row:
                    edit_dep = dict(row)
            except ValueError:
                pass

    return render_template(
        'dependent_manage.html',
        dependents_list=dependents_list,
        staff_members=staff_members,
        edit_dep=edit_dep
    )

@admin_bp.route('/dependents/add', methods=['POST'])
@admin_required
def add_dependent():
    staff_id = request.form.get('staff_id')
    full_name = request.form.get('full_name', '').strip()
    relationship = request.form.get('relationship', 'บุตร').strip() or 'บุตร'
    
    if not staff_id or not full_name:
        flash('กรุณากรอกข้อมูลที่จำเป็นให้ครบถ้วน', 'danger')
        return redirect(url_for('admin.dependents_manage'))
        
    try:
        with get_db() as conn:
            conn.execute(
                "INSERT INTO medical_dependents (staff_id, full_name, relationship) VALUES (?, ?, ?)",
                (int(staff_id), full_name, relationship)
            )
        flash(f"เพิ่มข้อมูลบุตร '{full_name}' สำเร็จ", "success")
    except Exception as e:
        flash(f"เกิดข้อผิดพลาดในการบันทึกข้อมูล: {str(e)}", "danger")
        
    return redirect(url_for('admin.dependents_manage'))

@admin_bp.route('/dependents/edit/<int:id>', methods=['POST'])
@admin_required
def edit_dependent(id):
    staff_id = request.form.get('staff_id')
    full_name = request.form.get('full_name', '').strip()
    relationship = request.form.get('relationship', 'บุตร').strip() or 'บุตร'
    
    if not staff_id or not full_name:
        flash('กรุณากรอกข้อมูลให้ครบถ้วน', 'danger')
        return redirect(url_for('admin.dependents_manage', edit_id=id))
        
    try:
        with get_db() as conn:
            conn.execute(
                "UPDATE medical_dependents SET staff_id = ?, full_name = ?, relationship = ? WHERE id = ?",
                (int(staff_id), full_name, relationship, id)
            )
        flash(f"แก้ไขข้อมูลบุตร '{full_name}' เรียบร้อยแล้ว", "success")
    except Exception as e:
        flash(f"เกิดข้อผิดพลาดในการแก้ไขข้อมูล: {str(e)}", "danger")
        
    return redirect(url_for('admin.dependents_manage'))

@admin_bp.route('/dependents/delete/<int:id>', methods=['POST'])
@admin_required
def delete_dependent(id):
    try:
        with get_db() as conn:
            cursor = conn.execute("SELECT full_name FROM medical_dependents WHERE id = ?", (id,))
            row = cursor.fetchone()
            if not row:
                flash('ไม่พบข้อมูลบุตรที่ต้องการลบ', 'danger')
                return redirect(url_for('admin.dependents_manage'))
                
            conn.execute("DELETE FROM medical_dependents WHERE id = ?", (id,))
            flash(f"ลบข้อมูลบุตร '{row['full_name']}' สำเร็จ", "success")
    except Exception as e:
        flash(f"เกิดข้อผิดพลาดในการลบข้อมูล: {str(e)}", "danger")
        
    return redirect(url_for('admin.dependents_manage'))

# ==========================================
# MASTER DATA CRUD
# ==========================================
@admin_bp.route('/master')
@admin_required
def master_manage():
    with get_db() as conn:
        # Fetch Divisions
        divisions = [dict(r) for r in conn.execute("SELECT * FROM divisions ORDER BY id DESC").fetchall()]
        
        # Fetch Sections joining Division
        sections = [dict(r) for r in conn.execute("""
            SELECT s.id, s.section_name, s.division_id, d.division_name
            FROM sections s
            LEFT JOIN divisions d ON s.division_id = d.id
            ORDER BY s.id DESC
        """).fetchall()]
        
        # Fetch Positions
        positions = [dict(r) for r in conn.execute("SELECT * FROM positions ORDER BY id DESC").fetchall()]
        
        # Fetch Vehicle Types
        vehicle_types = [dict(r) for r in conn.execute("SELECT * FROM vehicle_types ORDER BY id DESC").fetchall()]
        
        # Fetch Medical Facilities
        facilities = [dict(r) for r in conn.execute("SELECT * FROM medical_facilities ORDER BY id DESC").fetchall()]
        
        # Fetch Expense Rates joining Position
        rates = [dict(r) for r in conn.execute("""
            SELECT r.id, r.per_diem_rate, r.accommodation_rate, r.effective_date, p.position_name
            FROM expense_rates r
            LEFT JOIN positions p ON r.position_id = p.id
            ORDER BY r.id DESC
        """).fetchall()]
        for rate in rates:
            rate['effective_date_thai'] = to_thai_date(rate.get('effective_date'))

        # Fetch Vehicles joining Type and Staff
        vehicles = [dict(r) for r in conn.execute("""
            SELECT v.id, v.plate_number, v.contract_year, vt.type_name, s.full_name as staff_name
            FROM vehicles v
            LEFT JOIN vehicle_types vt ON v.vehicle_type_id = vt.id
            LEFT JOIN staff s ON v.staff_id = s.id
            ORDER BY v.id DESC
        """).fetchall()]

        # Load active staff for vehicles CRUD
        staff_members = [dict(r) for r in conn.execute("SELECT id, full_name FROM staff WHERE is_active=1 ORDER BY full_name").fetchall()]

    return render_template(
        'master_manage.html',
        divisions=divisions,
        sections=sections,
        positions=positions,
        vehicle_types=vehicle_types,
        facilities=facilities,
        rates=rates,
        vehicles=vehicles,
        staff_members=staff_members
    )

# 1. Divisions
@admin_bp.route('/master/divisions/add', methods=['POST'])
@admin_required
def add_division():
    name = request.form.get('division_name')
    if name:
        try:
            with get_db() as conn:
                conn.execute("INSERT INTO divisions (division_name) VALUES (?)", (name,))
            flash(f"เพิ่มกอง '{name}' สำเร็จ", "success")
        except Exception as e:
            flash(f"ข้อผิดพลาด: {str(e)}", "danger")
    return redirect(url_for('admin.master_manage') + '#tab-divisions')

@admin_bp.route('/master/divisions/delete/<int:id>', methods=['POST'])
@admin_required
def delete_division(id):
    try:
        with get_db() as conn:
            conn.execute("DELETE FROM divisions WHERE id = ?", (id,))
        flash("ลบกองสำเร็จ", "success")
    except Exception as e:
        flash(f"ไม่สามารถลบกองได้: {str(e)}", "danger")
    return redirect(url_for('admin.master_manage') + '#tab-divisions')

# 2. Sections
@admin_bp.route('/master/sections/add', methods=['POST'])
@admin_required
def add_section():
    name = request.form.get('section_name')
    div_id = request.form.get('division_id')
    if name and div_id:
        try:
            with get_db() as conn:
                conn.execute("INSERT INTO sections (section_name, division_id) VALUES (?, ?)", (name, div_id))
            flash(f"เพิ่มงาน '{name}' สำเร็จ", "success")
        except Exception as e:
            flash(f"ข้อผิดพลาด: {str(e)}", "danger")
    return redirect(url_for('admin.master_manage') + '#tab-sections')

@admin_bp.route('/master/sections/delete/<int:id>', methods=['POST'])
@admin_required
def delete_section(id):
    try:
        with get_db() as conn:
            conn.execute("DELETE FROM sections WHERE id = ?", (id,))
        flash("ลบงานสำเร็จ", "success")
    except Exception as e:
        flash(f"ไม่สามารถลบงานได้: {str(e)}", "danger")
    return redirect(url_for('admin.master_manage') + '#tab-sections')

# 3. Positions
@admin_bp.route('/master/positions/add', methods=['POST'])
@admin_required
def add_position():
    name = request.form.get('position_name')
    if name:
        try:
            with get_db() as conn:
                conn.execute("INSERT INTO positions (position_name) VALUES (?)", (name,))
            flash(f"เพิ่มตำแหน่ง '{name}' สำเร็จ", "success")
        except Exception as e:
            flash(f"ข้อผิดพลาด: {str(e)}", "danger")
    return redirect(url_for('admin.master_manage') + '#tab-positions')

@admin_bp.route('/master/positions/delete/<int:id>', methods=['POST'])
@admin_required
def delete_position(id):
    try:
        with get_db() as conn:
            conn.execute("DELETE FROM positions WHERE id = ?", (id,))
        flash("ลบตำแหน่งสำเร็จ", "success")
    except Exception as e:
        flash(f"ไม่สามารถลบตำแหน่งได้: {str(e)}", "danger")
    return redirect(url_for('admin.master_manage') + '#tab-positions')

# 4. Vehicle Types
@admin_bp.route('/master/vehicle-types/add', methods=['POST'])
@admin_required
def add_vehicle_type():
    name = request.form.get('type_name')
    rate = request.form.get('rate_per_km')
    rate_val = float(rate) if rate else None
    if name:
        try:
            with get_db() as conn:
                conn.execute("INSERT INTO vehicle_types (type_name, rate_per_km) VALUES (?, ?)", (name, rate_val))
            flash(f"เพิ่มประเภทรถ '{name}' สำเร็จ", "success")
        except Exception as e:
            flash(f"ข้อผิดพลาด: {str(e)}", "danger")
    return redirect(url_for('admin.master_manage') + '#tab-vehicle-types')

@admin_bp.route('/master/vehicle-types/delete/<int:id>', methods=['POST'])
@admin_required
def delete_vehicle_type(id):
    try:
        with get_db() as conn:
            conn.execute("DELETE FROM vehicle_types WHERE id = ?", (id,))
        flash("ลบประเภทรถสำเร็จ", "success")
    except Exception as e:
        flash(f"ไม่สามารถลบประเภทรถได้: {str(e)}", "danger")
    return redirect(url_for('admin.master_manage') + '#tab-vehicle-types')

# 5. Medical Facilities
@admin_bp.route('/master/facilities/add', methods=['POST'])
@admin_required
def add_facility():
    name = request.form.get('facility_name')
    fac_type = request.form.get('facility_type')
    if name:
        try:
            with get_db() as conn:
                conn.execute("INSERT INTO medical_facilities (facility_name, facility_type) VALUES (?, ?)", (name, fac_type))
            flash(f"เพิ่มสถานพยาบาล '{name}' สำเร็จ", "success")
        except Exception as e:
            flash(f"ข้อผิดพลาด: {str(e)}", "danger")
    return redirect(url_for('admin.master_manage') + '#tab-facilities')

@admin_bp.route('/master/facilities/delete/<int:id>', methods=['POST'])
@admin_required
def delete_facility(id):
    try:
        with get_db() as conn:
            conn.execute("DELETE FROM medical_facilities WHERE id = ?", (id,))
        flash("ลบสถานพยาบาลสำเร็จ", "success")
    except Exception as e:
        flash(f"ไม่สามารถลบสถานพยาบาลได้: {str(e)}", "danger")
    return redirect(url_for('admin.master_manage') + '#tab-facilities')

# 6. Expense Rates
@admin_bp.route('/master/rates/add', methods=['POST'])
@admin_required
def add_rate():
    pos_id = request.form.get('position_id')
    diem = request.form.get('per_diem_rate')
    accom = request.form.get('accommodation_rate')
    eff_date = request.form.get('effective_date')
    if pos_id and diem and accom:
        try:
            with get_db() as conn:
                conn.execute(
                    "INSERT INTO expense_rates (position_id, per_diem_rate, accommodation_rate, effective_date) VALUES (?, ?, ?, ?)",
                    (pos_id, float(diem), float(accom), eff_date or None)
                )
            flash("เพิ่มอัตราค่าใช้จ่ายสำเร็จ", "success")
        except Exception as e:
            flash(f"ข้อผิดพลาด: {str(e)}", "danger")
    return redirect(url_for('admin.master_manage') + '#tab-rates')

@admin_bp.route('/master/rates/delete/<int:id>', methods=['POST'])
@admin_required
def delete_rate(id):
    try:
        with get_db() as conn:
            conn.execute("DELETE FROM expense_rates WHERE id = ?", (id,))
        flash("ลบอัตราค่าใช้จ่ายสำเร็จ", "success")
    except Exception as e:
        flash(f"ไม่สามารถลบอัตราค่าใช้จ่ายได้: {str(e)}", "danger")
    return redirect(url_for('admin.master_manage') + '#tab-rates')

# 7. Vehicles
@admin_bp.route('/master/vehicles/add', methods=['POST'])
@admin_required
def add_vehicle():
    plate = request.form.get('plate_number')
    vt_id = request.form.get('vehicle_type_id')
    staff_id = request.form.get('staff_id')
    year = request.form.get('contract_year')
    if plate and vt_id:
        try:
            with get_db() as conn:
                conn.execute(
                    "INSERT INTO vehicles (plate_number, vehicle_type_id, staff_id, contract_year) VALUES (?, ?, ?, ?)",
                    (plate, vt_id, staff_id or None, year or None)
                )
            flash(f"เพิ่มยานพาหนะทะเบียน '{plate}' สำเร็จ", "success")
        except Exception as e:
            flash(f"ข้อผิดพลาด: {str(e)}", "danger")
    return redirect(url_for('admin.master_manage') + '#tab-vehicles')

@admin_bp.route('/master/vehicles/delete/<int:id>', methods=['POST'])
@admin_required
def delete_vehicle(id):
    try:
        with get_db() as conn:
            conn.execute("DELETE FROM vehicles WHERE id = ?", (id,))
        flash("ลบยานพาหนะสำเร็จ", "success")
    except Exception as e:
        flash(f"ไม่สามารถลบยานพาหนะได้: {str(e)}", "danger")
    return redirect(url_for('admin.master_manage') + '#tab-vehicles')

# ==========================================
# DOWNLOAD / VIEW-PDF ROUTES
# ==========================================
@admin_bp.route('/download/<file_type>/<filename>')
@admin_required
def download_file(file_type, filename):
    """
    Serves generated documents (both .docx and .xlsx) as file downloads.
    """
    if file_type not in ['travel_approval', 'travel_expense', 'medical_expense']:
        abort(404)

    # Strictly validate filename depending on file type:
    if file_type == 'travel_expense':
        # travel_expense documents are in .xlsx format
        pattern = r'^travel_expense_\d+\.xlsx$'
    else:
        # travel_approval and medical_expense documents are in .docx format
        pattern = r'^(travel_approval|medical_expense)_\d+\.docx$'

    if not re.match(pattern, filename):
        abort(400, "ชื่อไฟล์ไม่ถูกต้อง")

    return send_from_directory(Config.OUTPUT_DOCX_DIR, filename, as_attachment=True)


@admin_bp.route('/view-pdf/<file_type>/<filename>')
@admin_required
def view_pdf(file_type, filename):
    """
    Serves generated .pdf documents for inline viewing in the browser.
    """
    if file_type not in ['travel_approval', 'travel_expense', 'medical_expense']:
        abort(404)

    # Strictly validate filename: only allow <type>_<id>.pdf to prevent path traversal
    pattern = r'^(travel_approval|travel_expense|medical_expense)_\d+\.pdf$'
    if not re.match(pattern, filename):
        abort(400, "ชื่อไฟล์ไม่ถูกต้อง")

    return send_from_directory(Config.OUTPUT_DOCX_DIR, filename, as_attachment=False, mimetype='application/pdf')
