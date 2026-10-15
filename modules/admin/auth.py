from functools import wraps
from flask import session, redirect, url_for, flash

def admin_required(f):
    """
    Decorator that checks if the admin is logged in.
    If not, redirects to the admin login page.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_logged_in'):
            flash('กรุณาเข้าสู่ระบบผู้ดูแลระบบก่อนเข้าใช้หน้านี้', 'danger')
            return redirect(url_for('admin.login'))
        return f(*args, **kwargs)
    return decorated_function
