thai_months_abbr = ["", "ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.",
                     "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]

def to_thai_date_excel_short(date_obj) -> str:
    """
    Converts a date/datetime object to a short Thai Buddhist date string.
    Example: 2026-08-04 -> '4 ส.ค. 69'
    """
    if not date_obj:
        return ""
    day = date_obj.day
    month = thai_months_abbr[date_obj.month]
    year_be_short = (date_obj.year + 543) % 100  # เอาแค่ 2 หลักท้าย
    return f"{day} {month} {year_be_short}"
