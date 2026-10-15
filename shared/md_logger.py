import os
import datetime
from config import Config

def clean_val(value):
    """
    Cleans value to prevent breaking the Markdown table formatting.
    Replaces newlines with space, and pipes with a hyphen.
    """
    if value is None:
        return ""
    val_str = str(value)
    return val_str.replace("|", "-").replace("\n", " ").replace("\r", "")

def get_log_file_path(module_type, date_str=None):
    """
    Resolves the Markdown log file path for a specific module and month.
    e.g., 'travel_approval' and '2026-07-30' -> 'knowledge-base/travel-approvals/logs/2026-07.md'
    """
    folder_mapping = {
        'travel_approval': 'travel-approvals',
        'travel_expense': 'travel-expenses',
        'medical_expense': 'medical-expenses'
    }
    
    folder = folder_mapping.get(module_type)
    if not folder:
        raise ValueError(f"Unknown module type: {module_type}")

    # Use current date if none provided
    if not date_str:
        now = datetime.datetime.now()
    else:
        try:
            # Try to parse YYYY-MM-DD
            now = datetime.datetime.strptime(date_str.split(' ')[0], '%Y-%m-%d')
        except ValueError:
            now = datetime.datetime.now()

    year_month = now.strftime('%Y-%m')
    log_dir = os.path.join(Config.KNOWLEDGE_BASE_DIR, folder, 'logs')
    os.makedirs(log_dir, exist_ok=True)
    return os.path.join(log_dir, f"{year_month}.md")

def log_to_markdown(module_type, record_data):
    """
    Appends a row to the Markdown table log file.
    Creates the file with appropriate headers if it doesn't exist yet.
    """
    date_for_log = record_data.get('created_at') or datetime.datetime.now().strftime('%Y-%m-%d')
    file_path = get_log_file_path(module_type, date_for_log)
    
    file_exists = os.path.exists(file_path)
    
    headers = {
        'travel_approval': [
            "ID", "Staff Name", "Doc Number", "Date Start", "Date End", "Total Days",
            "Purpose", "Vehicle", "Replacement", "Companions", "Status", "Created At"
        ],
        'travel_expense': [
            "ID", "Staff Name", "Approval Document Number", "Amount (Baht)", 
            "Expense Date (Thai)", "Created At"
        ],
        'medical_expense': [
            "ID", "Staff Name", "Beneficiary Type", "Dependent Name", "Hospital Name", 
            "Treatment Date (Thai)", "Amount Requested", "Receipts", "Full Amount?", "Amount Approved", "Created At"
        ]
    }
    
    current_headers = headers.get(module_type)
    
    with open(file_path, 'a', encoding='utf-8') as f:
        if not file_exists:
            # Write header
            title_mapping = {
                'travel_approval': "บันทึกการขออนุมัติเดินทาง",
                'travel_expense': "บันทึกการเบิกจ่ายค่าเดินทาง",
                'medical_expense': "บันทึกการเบิกจ่ายค่ารักษาพยาบาล"
            }
            f.write(f"# {title_mapping[module_type]}\n\n")
            f.write("| " + " | ".join(current_headers) + " |\n")
            f.write("| " + " | ".join(["---"] * len(current_headers)) + " |\n")
            
        # Build row
        row_values = []
        if module_type == 'travel_approval':
            row_values = [
                record_data.get('id'),
                record_data.get('staff_name'),
                record_data.get('document_number'),
                record_data.get('date_start'),
                record_data.get('date_end'),
                record_data.get('total_days'),
                record_data.get('purpose'),
                record_data.get('vehicle'),
                record_data.get('acting_replacement'),
                record_data.get('companions'),
                record_data.get('status', 'pending'),
                record_data.get('created_at')
            ]
        elif module_type == 'travel_expense':
            row_values = [
                record_data.get('id'),
                record_data.get('staff_name'),
                record_data.get('approval_id'),
                record_data.get('amount'),
                record_data.get('expense_date_thai'),
                record_data.get('created_at')
            ]
        elif module_type == 'medical_expense':
            row_values = [
                record_data.get('id'),
                record_data.get('staff_name'),
                record_data.get('beneficiary_type'),
                record_data.get('dependent_name'),
                record_data.get('hospital_name'),
                record_data.get('treatment_date_thai'),
                record_data.get('amount_requested'),
                record_data.get('receipt_count'),
                record_data.get('is_full_amount'),
                record_data.get('amount_approved'),
                record_data.get('created_at')
            ]
            
        cleaned_values = [clean_val(v) for v in row_values]
        f.write("| " + " | ".join(cleaned_values) + " |\n")
