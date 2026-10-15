from shared.db import get_db

def get_active_staff():
    """
    Retrieves all active staff members from the database.
    Joins with positions and sections to fetch user labels for dropdown lists,
    along with their current per-diem and accommodation rates.
    """
    with get_db() as conn:
        cursor = conn.execute("""
            SELECT s.id, s.full_name, p.position_name as position, sec.section_name as department,
                   COALESCE(r.per_diem_rate, 240.0) as per_diem_rate,
                   COALESCE(r.accommodation_rate, 1200.0) as accommodation_rate
            FROM staff s
            LEFT JOIN positions p ON s.position_id = p.id
            LEFT JOIN sections sec ON s.section_id = sec.id
            LEFT JOIN (
                SELECT position_id, per_diem_rate, accommodation_rate
                FROM expense_rates
                WHERE id IN (
                    SELECT MAX(id) FROM expense_rates GROUP BY position_id
                )
            ) r ON s.position_id = r.position_id
            WHERE s.is_active = 1
            ORDER BY s.full_name
        """)
        return [dict(row) for row in cursor.fetchall()]

def get_staff_details(staff_id):
    """
    Retrieves details of a specific staff member by their ID, joining master data tables.
    """
    with get_db() as conn:
        cursor = conn.execute("""
            SELECT s.id, s.full_name, s.position_id, s.section_id, s.grade, s.phone, s.is_active,
                   p.position_name as position, sec.section_name as department, div.division_name
            FROM staff s
            LEFT JOIN positions p ON s.position_id = p.id
            LEFT JOIN sections sec ON s.section_id = sec.id
            LEFT JOIN divisions div ON sec.division_id = div.id
            WHERE s.id = ?
        """, (staff_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
