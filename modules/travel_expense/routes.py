import datetime
from flask import render_template, request, redirect, url_for, flash, jsonify, send_from_directory, abort
from modules.travel_expense import travel_expense_bp
from shared import get_db, get_active_staff, log_to_markdown, to_thai_date
from shared.xlsx_engine import generate_travel_expense_xlsx
from shared.thai_amount import amount_to_thai_text
from config import Config

# ==========================================
# HELPER: Fetch vehicle info + per-diem rate
# ==========================================

def _get_vehicle_info(conn, vehicle_id):
    """Returns dict with plate_number, type_name, rate_per_km, or None."""
    row = conn.execute(
        """
        SELECT v.plate_number, vt.type_name, vt.rate_per_km
        FROM vehicles v
        JOIN vehicle_types vt ON v.vehicle_type_id = vt.id
        WHERE v.id = ?
        """,
        (vehicle_id,)
    ).fetchone()
    return dict(row) if row else None


def _get_expense_rates(conn, position_id, reference_date=None):
    """Returns dict with per_diem_rate and accommodation_rate for a position, or defaults (240.0, 1200.0)."""
    params = [position_id]
    date_clause = ""
    if reference_date:
        date_clause = "AND (effective_date <= ? OR effective_date IS NULL)"
        params.append(reference_date)
    row = conn.execute(
        f"""
        SELECT per_diem_rate, accommodation_rate FROM expense_rates
        WHERE position_id = ? {date_clause}
        ORDER BY effective_date DESC LIMIT 1
        """,
        params
    ).fetchone()
    if row:
        return {
            'per_diem_rate': row['per_diem_rate'],
            'accommodation_rate': row['accommodation_rate']
        }
    return {
        'per_diem_rate': 240.0,
        'accommodation_rate': 1200.0
    }


def _get_approval_by_doc_number(conn, doc_number):
    """Resolves a document_number to the approval row, or None."""
    return conn.execute(
        "SELECT id, document_number, staff_id FROM travel_approvals WHERE document_number = ?",
        (doc_number,)
    ).fetchone()


# ==========================================
# API: Approval autocomplete
# ==========================================

@travel_expense_bp.route('/api/approval-search')
def api_approval_search():
    """
    JSON endpoint for autocomplete on document_number.
    GET /travel-expense/api/approval-search?q=<query>
    Returns [{id, document_number, full_name, purpose, date_start, date_end}]
    """
    q = request.args.get('q', '').strip()
    results = []
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT ta.id, ta.document_number, ta.purpose,
                   ta.date_start, ta.date_end,
                   s.full_name
            FROM travel_approvals ta
            LEFT JOIN staff s ON ta.staff_id = s.id
            WHERE (ta.is_deleted = 0 OR ta.is_deleted IS NULL)
              AND ta.document_number LIKE ?
            ORDER BY ta.id DESC
            LIMIT 15
            """,
            (f"%{q}%",)
        ).fetchall()
        for r in rows:
            results.append({
                'id': r['id'],
                'document_number': r['document_number'] or '',
                'full_name': r['full_name'] or '-',
                'purpose': r['purpose'] or '-',
                'date_start': r['date_start'] or '',
                'date_end': r['date_end'] or '',
                # Compatibility aliases
                'destination': r['purpose'] or '-',
                'travel_date_start': r['date_start'] or '',
                'travel_date_end': r['date_end'] or '',
            })
    return jsonify(results)


# ==========================================
# MAIN FORM: GET + POST
# ==========================================

@travel_expense_bp.route('/', methods=['GET', 'POST'])
def form():
    form_data = request.form if request.method == 'POST' else {}
    errors = {}

    if request.method == 'POST':
        errors, redirect_response = _handle_post(form_data)
        if redirect_response:
            return redirect_response
        # If errors, fall through to re-render form with errors

    # Load dropdown data
    staff_members = get_active_staff()
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

    return render_template(
        'travel_expense/form.html',
        staff_members=staff_members,
        vehicles=vehicles,
        errors=errors,
        form_data=form_data
    )


def _handle_post(form_data, edit_id=None):
    """
    Processes the POST submission.
    Returns (errors_dict, redirect_response).
    If errors_dict is non-empty, redirect_response is None.
    If successful, errors_dict is {} and redirect_response is a redirect.
    """
    errors = {}

    # --- 1. Parse and validate header fields ---
    doc_number = form_data.get('approval_doc_number', '').strip()
    staff_id_raw = form_data.get('staff_id', '').strip()
    vehicle_id_raw = form_data.get('vehicle_id', '').strip()
    depart_date = form_data.get('depart_date', '').strip()
    depart_time = form_data.get('depart_time', '').strip()
    return_date = form_data.get('return_date', '').strip()
    return_time = form_data.get('return_time', '').strip()
    fuel_cost_raw = form_data.get('fuel_cost', '0').strip() or '0'
    toll_cost_raw = form_data.get('toll_cost', '0').strip() or '0'

    if not doc_number:
        errors['approval_doc_number'] = 'กรุณากรอกเลขที่อนุมัติเดินทาง'
    if not staff_id_raw:
        errors['staff_id'] = 'กรุณาเลือกชื่อผู้เบิก'
    if not vehicle_id_raw:
        errors['vehicle_id'] = 'กรุณาเลือกยานพาหนะ'
    if not depart_date:
        errors['depart_date'] = 'กรุณากรอกวันที่เดินทางออก'
    if not return_date:
        errors['return_date'] = 'กรุณากรอกวันที่เดินทางกลับ'

    if errors:
        return errors, None

    # Date order validation
    if return_date < depart_date:
        errors['return_date'] = 'วันที่เดินทางกลับต้องไม่มาก่อนวันที่เดินทางออก'
        return errors, None

    try:
        staff_id = int(staff_id_raw)
        vehicle_id = int(vehicle_id_raw)
        fuel_cost = float(fuel_cost_raw)
        toll_cost = float(toll_cost_raw)
    except ValueError:
        errors['general'] = 'ข้อมูลตัวเลขไม่ถูกต้อง'
        return errors, None

    # --- 2. Process legs ---
    with get_db() as conn:
        from_locations = form_data.getlist('leg_from_location[]')
        depart_dates = form_data.getlist('leg_depart_date[]')
        depart_times = form_data.getlist('leg_depart_time[]')
        to_locations = form_data.getlist('leg_to_location[]')
        arrive_dates = form_data.getlist('leg_arrive_date[]')
        arrive_times = form_data.getlist('leg_arrive_time[]')
        work_reports = form_data.getlist('leg_work_report[]')
        distance_kms = form_data.getlist('leg_distance_km[]')
        multipliers = form_data.getlist('leg_per_diem_multiplier[]')
        has_accommodations_checked = form_data.getlist('leg_has_accommodation_check[]')

        n_legs = len(from_locations)
        if n_legs == 0:
            errors['legs'] = 'ต้องมีอย่างน้อย 1 รายการเส้นทาง'
            return errors, None

        # Build leg objects
        legs = []
        for i in range(n_legs):
            try:
                dist = float(distance_kms[i]) if distance_kms[i].strip() else None
            except (IndexError, ValueError):
                dist = None
            try:
                mult_str = multipliers[i].strip() if i < len(multipliers) else ''
                mult = float(mult_str) if mult_str else 0.0
            except (IndexError, ValueError):
                mult = 0.0

            has_accomm = 1 if str(i) in has_accommodations_checked else 0

            legs.append({
                'leg_order': i + 1,
                'from_location': from_locations[i] if i < len(from_locations) else '',
                'depart_date': depart_dates[i] if i < len(depart_dates) else '',
                'depart_time': depart_times[i] if i < len(depart_times) else '',
                'to_location': to_locations[i] if i < len(to_locations) else '',
                'arrive_date': arrive_dates[i] if i < len(arrive_dates) else '',
                'arrive_time': arrive_times[i] if i < len(arrive_times) else '',
                'work_report': work_reports[i] if i < len(work_reports) else '',
                'distance_km': dist,
                'per_diem_multiplier': mult,
                'has_accommodation': has_accomm
            })

        # --- 3. Fetch vehicle + rates ---
        vehicle_info = _get_vehicle_info(conn, vehicle_id)
        if not vehicle_info:
            errors['vehicle_id'] = 'ไม่พบข้อมูลยานพาหนะที่เลือก'
            return errors, None

        vehicle_type_name = vehicle_info['type_name']
        rate_per_km = vehicle_info['rate_per_km'] or 0.0
        plate_number = vehicle_info['plate_number']

        # Validate: personal car must have at least one distance
        is_personal = 'ส่วนตัว' in vehicle_type_name
        if is_personal:
            if not any(lg['distance_km'] and lg['distance_km'] > 0 for lg in legs):
                errors['legs'] = 'รถยนต์ส่วนตัว: ต้องกรอกระยะทาง (กม.) อย่างน้อย 1 รายการเส้นทาง'
                return errors, None

        # Fetch staff position for rates
        staff_row = conn.execute(
            "SELECT position_id FROM staff WHERE id = ?", (staff_id,)
        ).fetchone()
        position_id = staff_row['position_id'] if staff_row else None

        rates = _get_expense_rates(conn, position_id, depart_date)
        per_diem_rate = rates['per_diem_rate']
        accommodation_rate = rates['accommodation_rate']

        # --- 4. Calculate totals ---
        total_per_diem = sum(
            per_diem_rate * lg['per_diem_multiplier']
            for lg in legs
        )

        accommodation_nights = sum(1 for lg in legs if lg['has_accommodation'])
        total_accommodation = accommodation_nights * accommodation_rate

        if is_personal:
            total_distance = sum(
                lg['distance_km'] for lg in legs if lg['distance_km']
            )
            vehicle_cost = total_distance * rate_per_km
        else:
            vehicle_cost = fuel_cost + toll_cost

        total_amount = total_per_diem + total_accommodation + vehicle_cost

        # --- 5. Persist to DB (Insert or Update) ---
        now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        try:
            if edit_id:
                expense_id = edit_id
                conn.execute(
                    """
                    UPDATE travel_expenses SET
                        approval_document_number = ?, staff_id = ?, vehicle_id = ?,
                        depart_date = ?, depart_time = ?, return_date = ?, return_time = ?,
                        fuel_cost = ?, toll_cost = ?, total_amount = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (doc_number, staff_id, vehicle_id,
                     depart_date, depart_time, return_date, return_time,
                     fuel_cost, toll_cost, total_amount, now_str, edit_id)
                )
                conn.execute("DELETE FROM travel_expense_legs WHERE travel_expense_id = ?", (edit_id,))
            else:
                cursor = conn.execute(
                    """
                    INSERT INTO travel_expenses
                    (approval_document_number, staff_id, vehicle_id, depart_date, depart_time,
                     return_date, return_time, fuel_cost, toll_cost, total_amount)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (doc_number, staff_id, vehicle_id,
                     depart_date, depart_time, return_date, return_time,
                     fuel_cost, toll_cost, total_amount)
                )
                expense_id = cursor.lastrowid

            # Insert legs
            for leg in legs:
                conn.execute(
                    """
                    INSERT INTO travel_expense_legs
                    (travel_expense_id, leg_order, from_location, depart_date, depart_time,
                     to_location, arrive_date, arrive_time, work_report,
                     distance_km, per_diem_multiplier, has_accommodation)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (expense_id, leg['leg_order'],
                     leg['from_location'], leg['depart_date'], leg['depart_time'],
                     leg['to_location'], leg['arrive_date'], leg['arrive_time'],
                     leg['work_report'], leg['distance_km'], leg['per_diem_multiplier'],
                     leg['has_accommodation'])
                )

            # --- 6. Generate xlsx ---
            xlsx_filename = generate_travel_expense_xlsx(expense_id, conn)
            conn.execute(
                "UPDATE travel_expenses SET docx_path = ? WHERE id = ?",
                (xlsx_filename, expense_id)
            )
            
            # Fetch staff info for logging
            staff_full = conn.execute(
                "SELECT s.full_name FROM staff s WHERE s.id = ?",
                (staff_id,)
            ).fetchone()
            staff_name_logged = staff_full['full_name'] if staff_full else '-'

        except Exception as e:
            flash(f'เกิดข้อผิดพลาดในการบันทึกหรือสร้างเอกสาร Excel: {str(e)}', 'danger')
            return {}, None

        # --- 7. Log to markdown ---
        log_data = {
            'id': expense_id,
            'staff_name': staff_name_logged,
            'approval_id': doc_number,
            'amount': f"{total_amount:,.2f}",
            'expense_date_thai': to_thai_date(depart_date),
            'created_at': now_str,
        }
        try:
            log_to_markdown('travel_expense', log_data)
        except Exception as e:
            flash(f'บันทึก Log Markdown ล้มเหลว: {str(e)}', 'warning')

    action_text = "แก้ไข" if edit_id else "บันทึก"
    flash(f'{action_text}ใบเบิกค่าเดินทาง #{expense_id} และสร้างเอกสารสำเร็จ — ยอดรวม {total_amount:,.2f} บาท', 'success')
    return {}, redirect(url_for('travel_expense.success_view', expense_id=expense_id))


@travel_expense_bp.route('/edit/<int:expense_id>', methods=['GET', 'POST'])
def edit(expense_id):
    with get_db() as conn:
        existing = conn.execute("SELECT * FROM travel_expenses WHERE id = ? AND (is_deleted = 0 OR is_deleted IS NULL)", (expense_id,)).fetchone()
        if not existing:
            abort(404, "ไม่พบข้อมูลคำร้องเบิกจ่ายค่าเดินทางที่ระบุ")
        
        existing_legs = conn.execute("""
            SELECT from_location, depart_date, depart_time, to_location, arrive_date, arrive_time,
                   work_report, distance_km, per_diem_multiplier, has_accommodation
            FROM travel_expense_legs
            WHERE travel_expense_id = ?
            ORDER BY leg_order ASC
        """, (expense_id,)).fetchall()
        existing_legs = [dict(r) for r in existing_legs]

    form_data = request.form if request.method == 'POST' else {}
    errors = {}

    if request.method == 'POST':
        errors, redirect_response = _handle_post(form_data, edit_id=expense_id)
        if redirect_response:
            return redirect_response
    else:
        form_data = {
            'approval_doc_number': existing['approval_document_number'],
            'staff_id': str(existing['staff_id']),
            'vehicle_id': str(existing['vehicle_id']),
            'depart_date': existing['depart_date'],
            'depart_time': existing['depart_time'],
            'return_date': existing['return_date'],
            'return_time': existing['return_time'],
            'fuel_cost': existing['fuel_cost'],
            'toll_cost': existing['toll_cost'],
        }

    staff_members = get_active_staff()
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

    return render_template(
        'travel_expense/form.html',
        staff_members=staff_members,
        vehicles=vehicles,
        errors=errors,
        form_data=form_data,
        existing_legs=existing_legs if request.method == 'GET' else None,
        is_edit=True,
        edit_id=expense_id
    )


@travel_expense_bp.route('/success/<int:expense_id>')
def success_view(expense_id):
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT e.id, e.approval_document_number, e.docx_path as xlsx_path, e.total_amount,
                   s.full_name as staff_name
            FROM travel_expenses e
            LEFT JOIN staff s ON e.staff_id = s.id
            WHERE e.id = ?
            """,
            (expense_id,)
        ).fetchone()
        if not row:
            abort(404)
        expense = dict(row)
    return render_template('travel_expense/success.html', expense=expense)


@travel_expense_bp.route('/download/<filename>')
def download_file(filename):
    if not filename.endswith('.xlsx') or not filename.startswith('travel_expense_'):
        abort(400, "ชื่อไฟล์ไม่ถูกต้อง")
    return send_from_directory(Config.OUTPUT_DOCX_DIR, filename, as_attachment=True)
