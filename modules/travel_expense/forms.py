"""
travel_expense/forms.py

Lightweight form helper — validation is now handled directly in routes.py
since the legs-based dynamic form doesn't map cleanly to a simple form class.
This module is kept for structural consistency with other blueprint modules.
"""

class TravelExpenseForm:
    """Legacy form class — no longer used. Validation moved to routes._handle_post()."""
    pass
