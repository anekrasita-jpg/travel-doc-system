def to_thai_date(iso_date_str):
    """
    Converts an ISO Gregorian date string (YYYY-MM-DD) to a Thai Buddhist Calendar date string (dd/mm/yyyy).
    Example: '2026-07-30' -> '30/07/2569'
    """
    if not iso_date_str:
        return ""
    
    # In case we get a string with time parts
    if " " in iso_date_str:
        iso_date_str = iso_date_str.split(" ")[0]
    elif "T" in iso_date_str:
        iso_date_str = iso_date_str.split("T")[0]

    try:
        parts = iso_date_str.split('-')
        if len(parts) != 3:
            return iso_date_str  # Return original if it doesn't match YYYY-MM-DD
        
        year, month, day = parts
        thai_year = int(year) + 543
        return f"{day}/{month}/{thai_year}"
    except (ValueError, TypeError):
        return iso_date_str

def to_gregorian_iso(thai_date_str):
    """
    Converts a Thai Buddhist Calendar date string (dd/mm/yyyy) back to ISO Gregorian (YYYY-MM-DD).
    Useful if parses are needed from user inputs in Thai format.
    """
    if not thai_date_str:
        return ""
    try:
        parts = thai_date_str.split('/')
        if len(parts) != 3:
            return thai_date_str
        
        day, month, thai_year = parts
        gregorian_year = int(thai_year) - 543
        return f"{gregorian_year}-{month}-{day}"
    except (ValueError, TypeError):
        return thai_date_str

def to_thai_date_full(date_val) -> str:
    """
    Converts a date object, datetime object or ISO date string (YYYY-MM-DD)
    to a full Thai Buddhist calendar date string.
    Example: date(2026, 8, 8) or '2026-08-08' -> '8 สิงหาคม 2569'
    """
    import datetime
    if not date_val:
        return ""
        
    dt = None
    if isinstance(date_val, str):
        if " " in date_val:
            date_val = date_val.split(" ")[0]
        elif "T" in date_val:
            date_val = date_val.split("T")[0]
        try:
            dt = datetime.datetime.strptime(date_val, "%Y-%m-%d")
        except ValueError:
            return date_val
    elif isinstance(date_val, (datetime.date, datetime.datetime)):
        dt = date_val
    else:
        return ""
        
    thai_months = [
        "", "มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน",
        "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม"
    ]
    day = dt.day
    month = thai_months[dt.month]
    year_be = dt.year + 543
    return f"{day} {month} {year_be}"
