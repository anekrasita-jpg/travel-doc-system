import os
from docx import Document
from config import Config

def checkbox(is_checked: bool) -> str:
    return "☒" if is_checked else "☐"

def replace_text_in_paragraph(paragraph, placeholder, value):
    """
    Replaces a placeholder in a paragraph's runs to preserve formatting.
    Falls back to paragraph-level replacement if placeholder is split across runs.
    """
    if placeholder in paragraph.text:
        replaced = False
        for run in paragraph.runs:
            if placeholder in run.text:
                run.text = run.text.replace(placeholder, str(value))
                replaced = True
        
        # Fallback if placeholder is split across multiple runs
        if not replaced and placeholder in paragraph.text:
            paragraph.text = paragraph.text.replace(placeholder, str(value))

def replace_placeholders(doc, data):
    """
    Replaces keys from the data dictionary formatted as {{KEY}}
    in paragraphs and table cells of a python-docx Document.
    """
    # 1. Replace in body paragraphs
    for paragraph in doc.paragraphs:
        for key, val in data.items():
            placeholder = f"{{{{{key}}}}}"
            replace_text_in_paragraph(paragraph, placeholder, val)

    # 2. Replace in tables
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    for key, val in data.items():
                        placeholder = f"{{{{{key}}}}}"
                        replace_text_in_paragraph(paragraph, placeholder, val)

def create_mock_template(template_path, module_name):
    """
    Generates a basic template file if it does not exist,
    so that python-docx does not fail.
    """
    doc = Document()
    doc.add_heading(f"แบบฟอร์มเอกสารราชการ: {module_name.upper()}", level=1)
    doc.add_paragraph("นี่คือไฟล์เทมเพลตจำลองสำหรับการทดสอบระบบ (เวอร์ชันปรับปรุงความสัมพันธ์ข้อมูล)")
    
    doc.add_paragraph("ข้อมูลผู้ยื่นคำร้อง:")
    doc.add_paragraph("ชื่อ-นามสกุล: {{full_name}}")
    doc.add_paragraph("ตำแหน่ง: {{position}}")
    doc.add_paragraph("ฝ่าย/แผนก: {{department}}")
    
    if module_name == "travel_approval":
        doc.add_paragraph("เลขที่หนังสือ: {{document_number}}")
        doc.add_paragraph("วันที่เริ่มเดินทาง: {{date_start_thai}}")
        doc.add_paragraph("วันที่สิ้นสุดเดินทาง: {{date_end_thai}}")
        doc.add_paragraph("วัตถุประสงค์: {{purpose}}")
    elif module_name == "travel_expense":
        doc.add_paragraph("อ้างอิงใบอนุมัติเดินทาง: {{approval_id}}")
        doc.add_paragraph("จำนวนวันเบี้ยเลี้ยง (เต็มวัน): {{per_diem_full_days}} วัน | อัตรา: {{per_diem_rate}} บาท/วัน | รวม: {{total_per_diem}} บาท")
        doc.add_paragraph("จำนวนวันเบี้ยเลี้ยง (จัดอาหารกลางวัน): {{per_diem_partial_days}} วัน | รวมสิทธิ์หักลด: {{total_per_diem}} บาท")
        doc.add_paragraph("จำนวนคืนที่พัก: {{accommodation_nights}} คืน | อัตรา: {{accommodation_rate}} บาท/คืน | รวม: {{total_accommodation}} บาท")
        doc.add_paragraph("พาหนะเดินทางทะเบียน: {{plate_number}} (ประเภท: {{vehicle_type}})")
        doc.add_paragraph("ระยะทางสะสม: {{distance_km}} กม. | อัตรากิโลเมตรละ: {{rate_per_km}} บาท")
        doc.add_paragraph("ค่าน้ำมัน (ถ้าเป็นรถเช่า): {{fuel_cost}} บาท")
        doc.add_paragraph("ค่าทางพิเศษ: {{toll_cost}} บาท")
        doc.add_paragraph("รวมค่าพาหนะรวมทางด่วน: {{total_vehicle_cost}} บาท")
        doc.add_paragraph("ค่าใช้จ่ายอื่น ๆ: {{other_expenses}} บาท")
        doc.add_paragraph("ยอดเบิกเงินรวมสุทธิ: {{total_amount}} บาท ({{total_amount_text}})")
    elif module_name == "medical_expense":
        doc.add_paragraph("ผู้รับสิทธิ์สวัสดิการ: {{checkbox_self}} ตนเอง | {{checkbox_child}} บุตร (ผู้รับสิทธิ์สวัสดิการ: {{beneficiary_name}} ความสัมพันธ์: {{beneficiary_type}})")
        doc.add_paragraph("วันที่เข้ารับการรักษา: {{treatment_date_range}}")
        doc.add_paragraph("สถานพยาบาล: {{checkbox_gov}} รัฐบาล/ราชการ | {{checkbox_private}} เอกชน (สถานพยาบาล: {{hospital_name}} ประเภท: {{hospital_type}})")
        doc.add_paragraph("จำนวนเงินที่ขอเบิก: {{amount_requested}} บาท ({{amount_requested_text}})")
        doc.add_paragraph("จำนวนใบเสร็จ: {{receipt_count}} ใบ")
        doc.add_paragraph("เบิกเต็มจำนวนหรือไม่: {{checkbox_full}} ใช่ | {{checkbox_partial}} ไม่ใช่ (เต็มจำนวน: {{is_full_amount}})")
        doc.add_paragraph("จำนวนเงินที่อนุมัติเบิกจ่ายจริง: {{amount_approved}} บาท ({{amount_approved_text}})")
        
        # Compatibility keys
        doc.add_paragraph("(อ้างอิง) วันที่รักษา: {{treatment_date}}")
        doc.add_paragraph("(อ้างอิง) จำนวนเงิน: {{amount}} บาท ({{amount_text}})")

    doc.add_paragraph("\nลงชื่อ.......................................................... ผู้ยื่นขออนุมัติ")
    doc.add_paragraph("ลงชื่อ.......................................................... ผู้อนุมัติ (หัวหน้างาน)")
    
    # Ensure directory exists
    os.makedirs(os.path.dirname(template_path), exist_ok=True)
    doc.save(template_path)

def generate_docx(template_name, output_filename, data):
    """
    Generates a .docx file based on a template, replacing all data placeholders.
    Returns the absolute path to the generated document.
    """
    template_path = os.path.join(Config.TEMPLATE_DOCX_DIR, template_name)
    output_path = os.path.join(Config.OUTPUT_DOCX_DIR, output_filename)
    
    # If the template file doesn't exist, create a mock template
    if not os.path.exists(template_path):
        module_name = template_name.replace("_template.docx", "")
        create_mock_template(template_path, module_name)
        
    doc = Document(template_path)
    replace_placeholders(doc, data)
    
    # Ensure parent output directory exists
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    doc.save(output_path)
    return output_path

def generate_medical_expense_docx(template_name, output_filename, data):
    """
    Renders medical_expense_template.docx using docxtpl.
    """
    from docxtpl import DocxTemplate
    template_path = os.path.join(Config.TEMPLATE_DOCX_DIR, template_name)
    output_path = os.path.join(Config.OUTPUT_DOCX_DIR, output_filename)
    
    # If the template file doesn't exist, create a mock template
    if not os.path.exists(template_path):
        module_name = template_name.replace("_template.docx", "")
        create_mock_template(template_path, module_name)
        
    doc = DocxTemplate(template_path)
    doc.render(data)
    
    # Ensure parent output directory exists
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    doc.save(output_path)
    return output_path

def convert_docx_to_pdf(docx_path, output_dir):
    """
    Converts a docx file to pdf using LibreOffice headless command.
    Checks PATH and common installation directories.
    """
    import subprocess
    import shutil
    libreoffice_bin = 'libreoffice'
    if not shutil.which(libreoffice_bin):
        # Fallback to local Windows path
        win_path = r"C:\Program Files\LibreOffice\program\soffice.exe"
        if os.path.exists(win_path):
            libreoffice_bin = win_path
        elif shutil.which('soffice'):
            libreoffice_bin = 'soffice'
            
    print(f"[PDF] Converting {docx_path} to PDF using {libreoffice_bin}...")
    try:
        # Run conversion
        subprocess.run(
            [libreoffice_bin, '--headless', '--convert-to', 'pdf', '--outdir', output_dir, docx_path],
            capture_output=True,
            text=True,
            check=True
        )
        base_name = os.path.splitext(os.path.basename(docx_path))[0]
        pdf_path = os.path.join(output_dir, f"{base_name}.pdf")
        if os.path.exists(pdf_path):
            print(f"[PDF] Successfully generated PDF: {pdf_path}")
            return pdf_path
        else:
            print("[PDF] Conversion finished but PDF file not found.")
            return None
    except Exception as e:
        print(f"[PDF] Conversion failed with error: {str(e)}")
        return None

def generate_travel_approval_docx(approval_id, conn=None):
    """
    Renders travel_approval_template.docx using docxtpl by fetching data from database.
    """
    from docxtpl import DocxTemplate
    from shared.date_utils import to_thai_date, to_thai_date_full
    import sqlite3
    
    close_conn = False
    if conn is None:
        conn = sqlite3.connect(Config.DATABASE_PATH)
        conn.row_factory = sqlite3.Row
        close_conn = True
        
    try:
        approval_row = conn.execute("""
            SELECT ta.id, ta.document_number, ta.date_start, ta.date_end, ta.total_days, ta.purpose, 
                   ta.acting_replacement, ta.acting_replacement_position, ta.created_at,
                   s.full_name as staff_name, s.id as staff_id, s.grade,
                   p.position_name, sec.section_name, div.division_name,
                   v.plate_number as vehicle_plate, vt.type_name as vehicle_type
            FROM travel_approvals ta
            LEFT JOIN staff s ON ta.staff_id = s.id
            LEFT JOIN positions p ON s.position_id = p.id
            LEFT JOIN sections sec ON s.section_id = sec.id
            LEFT JOIN divisions div ON sec.division_id = div.id
            LEFT JOIN vehicles v ON ta.vehicle_id = v.id
            LEFT JOIN vehicle_types vt ON v.vehicle_type_id = vt.id
            WHERE ta.id = ?
        """, (approval_id,)).fetchone()
        
        if not approval_row:
            raise ValueError(f"Travel approval record #{approval_id} not found.")
            
        # Fetch companions
        companions_rows = conn.execute("""
            SELECT s.id as staff_id, s.full_name, p.position_name
            FROM travel_approval_companions tac
            JOIN staff s ON tac.staff_id = s.id
            LEFT JOIN positions p ON s.position_id = p.id
            WHERE tac.travel_approval_id = ?
            ORDER BY tac.id ASC
        """, (approval_id,)).fetchall()
    finally:
        if close_conn:
            conn.close()
        
    # Process vehicle type and plates
    vehicle_type_name = approval_row['vehicle_type'] or ""
    vehicle_plate = approval_row['vehicle_plate'] or ""
    
    is_gov = vehicle_type_name.startswith("รถเช่า")
    is_personal = (vehicle_type_name == "รถยนต์ส่วนตัว")
    
    checkbox_vehicle_gov = checkbox(is_gov)
    vehicle_gov_plate = vehicle_plate if is_gov else ""
    
    checkbox_vehicle_personal = checkbox(is_personal)
    vehicle_personal_plate = vehicle_plate if is_personal else ""
    
    # Format Thai dates
    doc_date = to_thai_date_full(approval_row['created_at'])
    date_start_thai = to_thai_date(approval_row['date_start'])
    date_end_thai = to_thai_date(approval_row['date_end'])
    
    # Strip any parenthetical position suffix from the name string.
    # This is a backward-compat fallback: form.html already submits only the name,
    # but older records may still have "Name (Position)" stored in the DB.
    acting_rep = approval_row['acting_replacement'] or ""
    if " (" in acting_rep:
        acting_rep = acting_rep.split(" (")[0]
    acting_rep_display = acting_rep.strip()
    
    context = {
        # Main applicant details
        'staff_name': approval_row['staff_name'] or '',
        'staff_id': str(approval_row['staff_id'] or ''),
        'position_name': approval_row['position_name'] or '',
        'grade': str(approval_row['grade'] or ''),
        'section_name': approval_row['section_name'] or '',
        'division_name': approval_row['division_name'] or '',
        
        # Document metadata
        'document_number': approval_row['document_number'] or '',
        'document_date_thai': doc_date,
        
        # Dates and purpose
        'date_start_thai': date_start_thai,
        'date_end_thai': date_end_thai,
        'total_days': str(approval_row['total_days'] or 1),
        'purpose': approval_row['purpose'] or '',
        
        # Vehicle details
        'checkbox_vehicle_gov': checkbox_vehicle_gov,
        'vehicle_gov_plate': vehicle_gov_plate,
        'checkbox_vehicle_personal': checkbox_vehicle_personal,
        'vehicle_personal_plate': vehicle_personal_plate,
        
        # Acting replacement details
        'acting_replacement': acting_rep_display,
        'acting_replacement_position': approval_row['acting_replacement_position'] or '',
        
        # Backward compatibility fields
        'full_name': approval_row['staff_name'] or '',
        'position': approval_row['position_name'] or '',
        'department': f"{approval_row['section_name']} (กอง {approval_row['division_name']})" if approval_row['division_name'] else (approval_row['section_name'] or ''),
        'travel_date_start': date_start_thai,
        'travel_date_end': date_end_thai,
        'vehicle_plate': vehicle_plate,
        'vehicle_type': vehicle_type_name
    }
    
    # Add companion 1 to 4 variables
    for i in range(1, 5):
        if i <= len(companions_rows):
            c = companions_rows[i-1]
            context[f'companion_{i}_name'] = c['full_name'] or ''
            context[f'companion_{i}_id'] = str(c['staff_id'] or '')
            context[f'companion_{i}_position'] = c['position_name'] or ''
        else:
            context[f'companion_{i}_name'] = ""
            context[f'companion_{i}_id'] = ""
            context[f'companion_{i}_position'] = ""
            
    template_path = os.path.join(Config.TEMPLATE_DOCX_DIR, 'travel_approval_template.docx')
    output_filename = f"travel_approval_{approval_id}.docx"
    output_path = os.path.join(Config.OUTPUT_DOCX_DIR, output_filename)
    
    # Ensure template exists
    if not os.path.exists(template_path):
        create_mock_template(template_path, 'travel_approval')
        
    doc = DocxTemplate(template_path)
    doc.render(context)
    
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    doc.save(output_path)
    
    return output_path
