from bahttext import bahttext

def amount_to_thai_text(amount: float) -> str:
    """
    Converts a numeric float amount to a Thai Baht text description.
    Example: 1500 -> "หนึ่งพันห้าร้อยบาทถ้วน"
    """
    if amount is None:
        return ""
    try:
        return bahttext(float(amount))
    except (ValueError, TypeError):
        return ""
