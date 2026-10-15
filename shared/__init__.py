from shared.db import get_db, init_db
from shared.date_utils import to_thai_date, to_gregorian_iso, to_thai_date_full
from shared.docx_engine import generate_docx, checkbox, generate_medical_expense_docx, convert_docx_to_pdf, generate_travel_approval_docx
from shared.md_logger import log_to_markdown
from shared.staff_lookup import get_active_staff, get_staff_details
