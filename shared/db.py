import sqlite3
import os
from contextlib import contextmanager
from config import Config

@contextmanager
def get_db():
    """
    Context manager for SQLite database connection.
    Yields a connection that yields dict-like sqlite3.Row rows,
    automatically commits changes, or rolls back on failure,
    and closes the connection when done.
    """
    conn = sqlite3.connect(Config.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    # Enable foreign keys
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db():
    """
    Initializes the database by creating all the required tables if they don't exist.
    """
    # Make sure parent directory of the database file exists
    db_dir = os.path.dirname(Config.DATABASE_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

    with get_db() as conn:
        # Create schema_version table if it doesn't exist
        conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY
        );
        """)
        cursor = conn.execute("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1;")
        row = cursor.fetchone()
        current_version = row['version'] if row else 0

        # Check if it is a completely fresh database (no tables exist except schema_version)
        if current_version == 0:
            cursor_check = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name != 'schema_version';")
            if not cursor_check.fetchall():
                print("[DB] Fresh database detected. Setting schema version to 12.")
                conn.execute("INSERT INTO schema_version (version) VALUES (12);")
                current_version = 12

        # Migration: Drop old flat schema (no master tables) if needed
        if current_version < 1:
            cursor2 = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='divisions';")
            has_master_tables = cursor2.fetchone() is not None
            if not has_master_tables:
                print("[DB] Migrating to schema v1: dropping old flat schema...")
                for t in ['travel_expenses', 'travel_approvals', 'medical_expenses',
                          'staff', 'vehicles', 'vehicle_types', 'positions',
                          'sections', 'divisions', 'medical_facilities', 'expense_rates']:
                    conn.execute(f"DROP TABLE IF EXISTS {t};")

        # Migration v2: Add ON DELETE SET NULL to transaction table FK columns
        if current_version < 2:
            print("[DB] Migrating to schema v2: adding ON DELETE SET NULL to transaction tables...")
            _migrate_transaction_tables_v2(conn)

        # Migration v3: Remove AUTOINCREMENT from staff.id to allow manual employee ID input
        if current_version < 3:
            print("[DB] Migrating to schema v3: removing AUTOINCREMENT from staff.id...")
            _migrate_staff_v3(conn)
            conn.execute("DELETE FROM schema_version;")
            conn.execute("INSERT INTO schema_version (version) VALUES (3);")
            current_version = 3

        # Migration v4: Rebuild travel_expenses with new schema (legs-based design)
        # and create travel_expense_legs child table.
        if current_version < 4:
            print("[DB] Migrating to schema v4: rebuilding travel_expenses for legs-based design...")
            _migrate_travel_expenses_v4(conn)
            conn.execute("DELETE FROM schema_version;")
            conn.execute("INSERT INTO schema_version (version) VALUES (4);")
            current_version = 4

        # Migration v5: Decouple travel approval references in travel_expenses
        if current_version < 5:
            print("[DB] Migrating to schema v5: changing approval_id to approval_document_number in travel_expenses...")
            _migrate_travel_expenses_v5(conn)
            conn.execute("DELETE FROM schema_version;")
            conn.execute("INSERT INTO schema_version (version) VALUES (5);")
            current_version = 5

        # Migration v6: Add has_accommodation to travel_expense_legs
        if current_version < 6:
            print("[DB] Migrating to schema v6: adding has_accommodation column to travel_expense_legs...")
            cursor = conn.execute("PRAGMA table_info(travel_expense_legs);")
            columns = [c['name'] for c in cursor.fetchall()]
            if 'has_accommodation' not in columns:
                conn.execute("ALTER TABLE travel_expense_legs ADD COLUMN has_accommodation BOOLEAN DEFAULT 0;")
            conn.execute("DELETE FROM schema_version;")
            conn.execute("INSERT INTO schema_version (version) VALUES (6);")
            current_version = 6

        # Migration v7: Rebuild travel_approvals and create travel_approval_companions
        if current_version < 7:
            print("[DB] Migrating to schema v7: rebuilding travel_approvals and creating travel_approval_companions...")
            _migrate_travel_approvals_v7(conn)
            conn.execute("DELETE FROM schema_version;")
            conn.execute("INSERT INTO schema_version (version) VALUES (7);")
            current_version = 7

        # Migration v8: Create medical_dependents and rebuild medical_expenses
        if current_version < 8:
            print("[DB] Migrating to schema v8: creating medical_dependents and rebuilding medical_expenses...")
            _migrate_medical_expenses_v8(conn)
            conn.execute("DELETE FROM schema_version;")
            conn.execute("INSERT INTO schema_version (version) VALUES (8);")
            current_version = 8

        # Migration v9: Add is_deleted column for Soft Delete support
        if current_version < 9:
            print("[DB] Migrating to schema v9: adding is_deleted columns to transaction tables...")
            _migrate_soft_delete_v9(conn)
            conn.execute("DELETE FROM schema_version;")
            conn.execute("INSERT INTO schema_version (version) VALUES (9);")
            current_version = 9

        # Migration v10: Add pdf_path column to medical_expenses
        if current_version < 10:
            print("[DB] Migrating to schema v10: adding pdf_path column to medical_expenses...")
            _migrate_pdf_path_v10(conn)
            conn.execute("DELETE FROM schema_version;")
            conn.execute("INSERT INTO schema_version (version) VALUES (10);")
            current_version = 10

        # Migration v11: Add acting_replacement_position column to travel_approvals
        if current_version < 11:
            print("[DB] Migrating to schema v11: adding acting_replacement_position column to travel_approvals...")
            _migrate_acting_replacement_position_v11(conn)
            conn.execute("DELETE FROM schema_version;")
            conn.execute("INSERT INTO schema_version (version) VALUES (11);")
            current_version = 11

        # Migration v12: Add pdf_path column to travel_approvals
        if current_version < 12:
            print("[DB] Migrating to schema v12: adding pdf_path column to travel_approvals...")
            _migrate_pdf_path_travel_approvals_v12(conn)
            conn.execute("DELETE FROM schema_version;")
            conn.execute("INSERT INTO schema_version (version) VALUES (12);")
            current_version = 12

        # Migration v13: Add updated_at column to travel_approvals, travel_expenses, and medical_expenses
        if current_version < 13:
            print("[DB] Migrating to schema v13: adding updated_at columns to transaction tables...")
            _migrate_updated_at_v13(conn)
            conn.execute("DELETE FROM schema_version;")
            conn.execute("INSERT INTO schema_version (version) VALUES (13);")
            current_version = 13

        # ==========================================
        # 1. MASTER DATA TABLES
        # ==========================================

        # Divisions (กอง)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS divisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            division_name TEXT NOT NULL UNIQUE
        );
        """)

        # Sections (งาน)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS sections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            section_name TEXT NOT NULL UNIQUE,
            division_id INTEGER REFERENCES divisions(id) ON DELETE SET NULL
        );
        """)

        # Positions (ตำแหน่งงาน)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            position_name TEXT NOT NULL UNIQUE
        );
        """)

        # Vehicle Types (ประเภทรถ)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS vehicle_types (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type_name TEXT NOT NULL UNIQUE,
            rate_per_km REAL
        );
        """)

        # Medical Facilities (สถานพยาบาล)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS medical_facilities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            facility_name TEXT NOT NULL UNIQUE,
            facility_type TEXT
        );
        """)

        # Expense Rates (อัตราเบี้ยเลี้ยง/ที่พัก)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS expense_rates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            position_id INTEGER REFERENCES positions(id) ON DELETE CASCADE,
            per_diem_rate REAL NOT NULL,
            accommodation_rate REAL NOT NULL,
            effective_date TEXT
        );
        """)

        # ==========================================
        # 2. PEOPLE & ASSETS TABLES
        # ==========================================

        # Staff (พนักงาน) - id is plain PRIMARY KEY (no AUTOINCREMENT) for manual employee code entry
        conn.execute("""
        CREATE TABLE IF NOT EXISTS staff (
            id INTEGER PRIMARY KEY,
            full_name TEXT NOT NULL,
            position_id INTEGER REFERENCES positions(id) ON DELETE SET NULL,
            grade TEXT,
            section_id INTEGER REFERENCES sections(id) ON DELETE SET NULL,
            phone TEXT,
            is_active BOOLEAN DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # Vehicles (ทะเบียนรถ)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS vehicles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plate_number TEXT NOT NULL UNIQUE,
            vehicle_type_id INTEGER REFERENCES vehicle_types(id) ON DELETE SET NULL,
            staff_id INTEGER REFERENCES staff(id) ON DELETE SET NULL,
            contract_year TEXT
        );
        """)

        # ==========================================
        # 3. TRANSACTION TABLES
        # ==========================================

        # Travel Approvals (ขออนุมัติเดินทาง)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS travel_approvals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_number TEXT,
            staff_id INTEGER REFERENCES staff(id) ON DELETE SET NULL,
            date_start TEXT,
            date_end TEXT,
            total_days INTEGER,
            purpose TEXT,
            vehicle_id INTEGER REFERENCES vehicles(id) ON DELETE SET NULL,
            acting_replacement TEXT,
            acting_replacement_position TEXT,
            status TEXT DEFAULT 'pending',
            approved_by TEXT,
            approved_date TEXT,
            docx_path TEXT,
            pdf_path TEXT,
            is_deleted BOOLEAN DEFAULT 0,
            updated_at TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # Travel Approval Companions (ผู้เดินทางร่วม)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS travel_approval_companions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            travel_approval_id INTEGER REFERENCES travel_approvals(id) ON DELETE CASCADE,
            staff_id INTEGER REFERENCES staff(id) ON DELETE SET NULL
        );
        """)

        # Travel Expenses (เบิกจ่ายค่าเดินทาง) — header record (1 row = 1 ใบเบิก)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS travel_expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            approval_document_number TEXT,
            staff_id INTEGER REFERENCES staff(id) ON DELETE SET NULL,
            vehicle_id INTEGER REFERENCES vehicles(id) ON DELETE SET NULL,
            depart_date TEXT,
            depart_time TEXT,
            return_date TEXT,
            return_time TEXT,
            fuel_cost REAL DEFAULT 0,
            toll_cost REAL DEFAULT 0,
            total_amount REAL,
            docx_path TEXT,
            is_deleted BOOLEAN DEFAULT 0,
            updated_at TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # Travel Expense Legs (รายละเอียดเส้นทาง — หลายแถวต่อ 1 ใบเบิก)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS travel_expense_legs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            travel_expense_id INTEGER REFERENCES travel_expenses(id) ON DELETE CASCADE,
            leg_order INTEGER DEFAULT 1,
            from_location TEXT,
            depart_date TEXT,
            depart_time TEXT,
            to_location TEXT,
            arrive_date TEXT,
            arrive_time TEXT,
            work_report TEXT,
            distance_km REAL,
            per_diem_multiplier REAL DEFAULT 1,
            has_accommodation BOOLEAN DEFAULT 0
        );
        """)

        # Medical Dependents (ผู้พึ่งพิง/บุตร)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS medical_dependents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            staff_id INTEGER REFERENCES staff(id) ON DELETE CASCADE,
            full_name TEXT NOT NULL,
            relationship TEXT DEFAULT 'บุตร',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # Medical Expenses (เบิกจ่ายค่ารักษาพยาบาล)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS medical_expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            staff_id INTEGER REFERENCES staff(id) ON DELETE SET NULL,
            beneficiary_type TEXT NOT NULL,
            dependent_id INTEGER REFERENCES medical_dependents(id) ON DELETE SET NULL,
            facility_id INTEGER REFERENCES medical_facilities(id) ON DELETE SET NULL,
            treatment_date_start TEXT,
            treatment_date_end TEXT,
            amount_requested REAL,
            receipt_count INTEGER,
            is_full_amount BOOLEAN DEFAULT 1,
            amount_approved REAL,
            docx_path TEXT,
            pdf_path TEXT,
            is_deleted BOOLEAN DEFAULT 0,
            updated_at TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # Seed data if tables are empty
        seed_data(conn)

def _migrate_transaction_tables_v2(conn):
    """
    Recreates travel_approvals, travel_expenses, and medical_expenses with
    explicit ON DELETE SET NULL on all FK references.
    
    SQLite doesn't support ALTER TABLE ADD/CHANGE CONSTRAINT, so we use the
    standard rename → create → copy → drop pattern.
    Data is preserved.
    """
    # Temporarily disable FK checks during restructuring
    conn.execute("PRAGMA foreign_keys = OFF;")

    # --- travel_approvals ---
    conn.execute("ALTER TABLE travel_approvals RENAME TO _travel_approvals_old;")
    conn.execute("""
    CREATE TABLE travel_approvals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        staff_id INTEGER REFERENCES staff(id) ON DELETE SET NULL,
        document_number TEXT,
        travel_date_start TEXT,
        travel_date_end TEXT,
        destination TEXT,
        reason TEXT,
        status TEXT DEFAULT 'pending',
        approved_by TEXT,
        approved_date TEXT,
        docx_path TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """)
    conn.execute("""
    INSERT INTO travel_approvals 
    SELECT id, staff_id, document_number, travel_date_start, travel_date_end,
           destination, reason, status, approved_by, approved_date, docx_path, created_at
    FROM _travel_approvals_old;
    """)
    conn.execute("DROP TABLE _travel_approvals_old;")

    # --- travel_expenses ---
    conn.execute("ALTER TABLE travel_expenses RENAME TO _travel_expenses_old;")
    conn.execute("""
    CREATE TABLE travel_expenses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        approval_id INTEGER REFERENCES travel_approvals(id) ON DELETE SET NULL,
        staff_id INTEGER REFERENCES staff(id) ON DELETE SET NULL,
        per_diem_full_days INTEGER DEFAULT 0,
        per_diem_partial_days INTEGER DEFAULT 0,
        accommodation_nights INTEGER DEFAULT 0,
        vehicle_id INTEGER REFERENCES vehicles(id) ON DELETE SET NULL,
        distance_km REAL DEFAULT 0,
        fuel_cost REAL DEFAULT 0,
        toll_cost REAL DEFAULT 0,
        other_expenses REAL DEFAULT 0,
        total_amount REAL,
        expense_date TEXT,
        docx_path TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """)
    conn.execute("""
    INSERT INTO travel_expenses
    SELECT id, approval_id, staff_id, per_diem_full_days, per_diem_partial_days,
           accommodation_nights, vehicle_id, distance_km, fuel_cost, toll_cost,
           other_expenses, total_amount, expense_date, docx_path, created_at
    FROM _travel_expenses_old;
    """)
    conn.execute("DROP TABLE _travel_expenses_old;")

    # --- medical_expenses ---
    conn.execute("ALTER TABLE medical_expenses RENAME TO _medical_expenses_old;")
    conn.execute("""
    CREATE TABLE medical_expenses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        staff_id INTEGER REFERENCES staff(id) ON DELETE SET NULL,
        facility_id INTEGER REFERENCES medical_facilities(id) ON DELETE SET NULL,
        amount REAL,
        treatment_date TEXT,
        docx_path TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """)
    conn.execute("""
    INSERT INTO medical_expenses
    SELECT id, staff_id, facility_id, amount, treatment_date, docx_path, created_at
    FROM _medical_expenses_old;
    """)
    conn.execute("DROP TABLE _medical_expenses_old;")

    # Re-enable FK checks
    conn.execute("PRAGMA foreign_keys = ON;")
    print("[DB] Schema v2 migration complete: transaction tables now have ON DELETE SET NULL.")

def _migrate_staff_v3(conn):
    """
    Recreates the staff table with id as INTEGER PRIMARY KEY (no AUTOINCREMENT),
    so that manual employee codes can be provided via the admin form.
    Existing data (including seeded IDs) is fully preserved.
    """
    conn.execute("PRAGMA foreign_keys = OFF;")

    # Check if staff table exists before attempting migration
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='staff';")
    if cursor.fetchone() is None:
        conn.execute("PRAGMA foreign_keys = ON;")
        return  # Nothing to migrate - table will be created fresh by CREATE TABLE IF NOT EXISTS

    conn.execute("ALTER TABLE staff RENAME TO _staff_old;")
    conn.execute("""
    CREATE TABLE staff (
        id INTEGER PRIMARY KEY,
        full_name TEXT NOT NULL,
        position_id INTEGER REFERENCES positions(id) ON DELETE SET NULL,
        grade TEXT,
        section_id INTEGER REFERENCES sections(id) ON DELETE SET NULL,
        phone TEXT,
        is_active BOOLEAN DEFAULT 1,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """)
    conn.execute("""
    INSERT INTO staff
    SELECT id, full_name, position_id, grade, section_id, phone, is_active, created_at
    FROM _staff_old;
    """)
    conn.execute("DROP TABLE _staff_old;")

    conn.execute("PRAGMA foreign_keys = ON;")
    print("[DB] Schema v3 migration complete: staff.id no longer AUTOINCREMENT.")

def _migrate_travel_expenses_v4(conn):
    """
    Rebuilds travel_expenses to match the new legs-based schema.
    Old records (if any) are dropped since the column layout is incompatible.
    Also creates travel_expense_legs child table.
    """
    conn.execute("PRAGMA foreign_keys = OFF;")

    conn.execute("DROP TABLE IF EXISTS travel_expense_legs;")
    conn.execute("DROP TABLE IF EXISTS travel_expenses;")

    conn.execute("""
    CREATE TABLE travel_expenses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        approval_id INTEGER REFERENCES travel_approvals(id) ON DELETE SET NULL,
        staff_id INTEGER REFERENCES staff(id) ON DELETE SET NULL,
        vehicle_id INTEGER REFERENCES vehicles(id) ON DELETE SET NULL,
        depart_date TEXT,
        depart_time TEXT,
        return_date TEXT,
        return_time TEXT,
        fuel_cost REAL DEFAULT 0,
        toll_cost REAL DEFAULT 0,
        total_amount REAL,
        docx_path TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """)

    conn.execute("""
    CREATE TABLE travel_expense_legs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        travel_expense_id INTEGER REFERENCES travel_expenses(id) ON DELETE CASCADE,
        leg_order INTEGER DEFAULT 1,
        from_location TEXT,
        depart_date TEXT,
        depart_time TEXT,
        to_location TEXT,
        arrive_date TEXT,
        arrive_time TEXT,
        work_report TEXT,
        distance_km REAL,
        per_diem_multiplier REAL DEFAULT 1
    );
    """)

    conn.execute("PRAGMA foreign_keys = ON;")
    print("[DB] Schema v4 migration complete: travel_expenses rebuilt with legs-based design.")

def _migrate_travel_expenses_v5(conn):
    """
    Recreates travel_expenses table with approval_document_number TEXT instead of
    approval_id INTEGER REFERENCES travel_approvals(id).
    Preserves data by mapping old approval_id to travel_approvals.document_number.
    """
    conn.execute("PRAGMA foreign_keys = OFF;")

    # Check if travel_expenses exists and has approval_id column
    cursor = conn.execute("PRAGMA table_info(travel_expenses);")
    columns = [c['name'] for c in cursor.fetchall()]

    if 'approval_id' in columns:
        conn.execute("ALTER TABLE travel_expenses RENAME TO _travel_expenses_old;")

        conn.execute("""
        CREATE TABLE travel_expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            approval_document_number TEXT,
            staff_id INTEGER REFERENCES staff(id) ON DELETE SET NULL,
            vehicle_id INTEGER REFERENCES vehicles(id) ON DELETE SET NULL,
            depart_date TEXT,
            depart_time TEXT,
            return_date TEXT,
            return_time TEXT,
            fuel_cost REAL DEFAULT 0,
            toll_cost REAL DEFAULT 0,
            total_amount REAL,
            docx_path TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # Check if travel_approvals exists to resolve document_number
        cursor_app = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='travel_approvals';")
        has_approvals = cursor_app.fetchone() is not None

        if has_approvals:
            conn.execute("""
            INSERT INTO travel_expenses (
                id, approval_document_number, staff_id, vehicle_id, depart_date, depart_time,
                return_date, return_time, fuel_cost, toll_cost, total_amount, docx_path, created_at
            )
            SELECT e.id, a.document_number, e.staff_id, e.vehicle_id, e.depart_date, e.depart_time,
                   e.return_date, e.return_time, e.fuel_cost, e.toll_cost, e.total_amount, e.docx_path, e.created_at
            FROM _travel_expenses_old e
            LEFT JOIN travel_approvals a ON e.approval_id = a.id;
            """)
        else:
            conn.execute("""
            INSERT INTO travel_expenses (
                id, approval_document_number, staff_id, vehicle_id, depart_date, depart_time,
                return_date, return_time, fuel_cost, toll_cost, total_amount, docx_path, created_at
            )
            SELECT e.id, NULL, e.staff_id, e.vehicle_id, e.depart_date, e.depart_time,
                   e.return_date, e.return_time, e.fuel_cost, e.toll_cost, e.total_amount, e.docx_path, e.created_at
            FROM _travel_expenses_old e;
            """)

        conn.execute("DROP TABLE _travel_expenses_old;")

    conn.execute("PRAGMA foreign_keys = ON;")
    print("[DB] Schema v5 migration complete: travel_expenses updated to approval_document_number.")

def _migrate_travel_approvals_v7(conn):
    """
    Rebuilds travel_approvals with updated columns (date_start, date_end, purpose, total_days, etc.)
    and creates travel_approval_companions.
    """
    conn.execute("PRAGMA foreign_keys = OFF;")

    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='travel_approvals';")
    if cursor.fetchone() is not None:
        conn.execute("ALTER TABLE travel_approvals RENAME TO _travel_approvals_old;")

        conn.execute("""
        CREATE TABLE travel_approvals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_number TEXT,
            staff_id INTEGER REFERENCES staff(id) ON DELETE SET NULL,
            date_start TEXT,
            date_end TEXT,
            total_days INTEGER,
            purpose TEXT,
            vehicle_id INTEGER REFERENCES vehicles(id) ON DELETE SET NULL,
            acting_replacement TEXT,
            acting_replacement_position TEXT,
            status TEXT DEFAULT 'pending',
            approved_by TEXT,
            approved_date TEXT,
            docx_path TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # Get existing columns
        cursor_cols = conn.execute("PRAGMA table_info(_travel_approvals_old);")
        old_cols = [c['name'] for c in cursor_cols.fetchall()]

        select_date_start = "travel_date_start" if "travel_date_start" in old_cols else "NULL"
        select_date_end = "travel_date_end" if "travel_date_end" in old_cols else "NULL"
        select_purpose = "reason" if "reason" in old_cols else ("purpose" if "purpose" in old_cols else "NULL")

        conn.execute(f"""
        INSERT INTO travel_approvals (
            id, document_number, staff_id, date_start, date_end, total_days,
            purpose, vehicle_id, acting_replacement, status, approved_by, approved_date, docx_path, created_at
        )
        SELECT id, document_number, staff_id, {select_date_start}, {select_date_end}, 1,
               {select_purpose}, NULL, NULL, status, approved_by, approved_date, docx_path, created_at
        FROM _travel_approvals_old;
        """)

        conn.execute("DROP TABLE _travel_approvals_old;")
    else:
        conn.execute("""
        CREATE TABLE travel_approvals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_number TEXT,
            staff_id INTEGER REFERENCES staff(id) ON DELETE SET NULL,
            date_start TEXT,
            date_end TEXT,
            total_days INTEGER,
            purpose TEXT,
            vehicle_id INTEGER REFERENCES vehicles(id) ON DELETE SET NULL,
            acting_replacement TEXT,
            acting_replacement_position TEXT,
            status TEXT DEFAULT 'pending',
            approved_by TEXT,
            approved_date TEXT,
            docx_path TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """)

    conn.execute("DROP TABLE IF EXISTS travel_approval_companions;")
    conn.execute("""
    CREATE TABLE travel_approval_companions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        travel_approval_id INTEGER REFERENCES travel_approvals(id) ON DELETE CASCADE,
        staff_id INTEGER REFERENCES staff(id) ON DELETE SET NULL
    );
    """)

    conn.execute("PRAGMA foreign_keys = ON;")
    print("[DB] Schema v7 migration complete: travel_approvals rebuilt, companions table created.")

def _migrate_medical_expenses_v8(conn):
    """
    Creates the medical_dependents table and rebuilds medical_expenses
    to support beneficiary_type, dependent_id, treatment_date_start, treatment_date_end,
    amount_requested, receipt_count, is_full_amount, amount_approved.
    Copies existing medical_expenses data if any, mapping old columns appropriately.
    """
    conn.execute("PRAGMA foreign_keys = OFF;")
    
    # Create medical_dependents
    conn.execute("""
    CREATE TABLE IF NOT EXISTS medical_dependents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        staff_id INTEGER REFERENCES staff(id) ON DELETE CASCADE,
        full_name TEXT NOT NULL,
        relationship TEXT DEFAULT 'บุตร',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """)
    
    # Rebuild medical_expenses
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='medical_expenses';")
    if cursor.fetchone() is not None:
        conn.execute("ALTER TABLE medical_expenses RENAME TO _medical_expenses_old;")
        
        conn.execute("""
        CREATE TABLE medical_expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            staff_id INTEGER REFERENCES staff(id) ON DELETE SET NULL,
            beneficiary_type TEXT NOT NULL,
            dependent_id INTEGER REFERENCES medical_dependents(id) ON DELETE SET NULL,
            facility_id INTEGER REFERENCES medical_facilities(id) ON DELETE SET NULL,
            treatment_date_start TEXT,
            treatment_date_end TEXT,
            amount_requested REAL,
            receipt_count INTEGER,
            is_full_amount BOOLEAN DEFAULT 1,
            amount_approved REAL,
            docx_path TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """)
        
        # Check if old table has data
        cursor_cols = conn.execute("PRAGMA table_info(_medical_expenses_old);")
        old_cols = [c['name'] for c in cursor_cols.fetchall()]
        
        select_amount = "amount" if "amount" in old_cols else "amount_requested"
        select_date = "treatment_date" if "treatment_date" in old_cols else "treatment_date_start"
        
        conn.execute(f"""
        INSERT INTO medical_expenses (
            id, staff_id, beneficiary_type, dependent_id, facility_id, 
            treatment_date_start, treatment_date_end, amount_requested, receipt_count, 
            is_full_amount, amount_approved, docx_path, created_at
        )
        SELECT id, staff_id, 'self', NULL, facility_id, 
               {select_date}, {select_date}, {select_amount}, 1, 
               1, {select_amount}, docx_path, created_at
        FROM _medical_expenses_old;
        """)
        
        conn.execute("DROP TABLE _medical_expenses_old;")
    else:
        conn.execute("""
        CREATE TABLE medical_expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            staff_id INTEGER REFERENCES staff(id) ON DELETE SET NULL,
            beneficiary_type TEXT NOT NULL,
            dependent_id INTEGER REFERENCES medical_dependents(id) ON DELETE SET NULL,
            facility_id INTEGER REFERENCES medical_facilities(id) ON DELETE SET NULL,
            treatment_date_start TEXT,
            treatment_date_end TEXT,
            amount_requested REAL,
            receipt_count INTEGER,
            is_full_amount BOOLEAN DEFAULT 1,
            amount_approved REAL,
            docx_path TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """)
        
    conn.execute("PRAGMA foreign_keys = ON;")
    print("[DB] Schema v8 migration complete: medical_dependents created and medical_expenses rebuilt.")

def seed_data(conn):
    """
    Seeds initial reference data if tables are empty.
    """
    # 1. Seed Divisions
    cursor = conn.execute("SELECT COUNT(*) FROM divisions")
    if cursor.fetchone()[0] == 0:
        divisions = [("เทคโนโลยีสารสนเทศ",), ("บริการเทคโนโลยีควบคุมผลิต",)]
        conn.executemany("INSERT INTO divisions (division_name) VALUES (?)", divisions)

    # 2. Seed Sections
    cursor = conn.execute("SELECT COUNT(*) FROM sections")
    if cursor.fetchone()[0] == 0:
        sections = [
            ("งานเทคโนโลยีควบคุมผลิต", 2),
            ("งานระบบเครือข่าย", 1),
            ("งานพัฒนาระบบ", 1)
        ]
        conn.executemany("INSERT INTO sections (section_name, division_id) VALUES (?, ?)", sections)

    # 3. Seed Positions
    cursor = conn.execute("SELECT COUNT(*) FROM positions")
    if cursor.fetchone()[0] == 0:
        positions = [
            ("ผู้จัดการ",),
            ("หัวหน้างาน",),
            ("วิศวกรคอมพิวเตอร์ชำนาญการ",),
            ("นักวิเคราะห์นโยบายและแผน",),
            ("เจ้าพนักงานธุรการปฏิบัติงาน",)
        ]
        conn.executemany("INSERT INTO positions (position_name) VALUES (?)", positions)

    # 4. Seed Vehicle Types
    cursor = conn.execute("SELECT COUNT(*) FROM vehicle_types")
    if cursor.fetchone()[0] == 0:
        types = [
            ("รถยนต์ส่วนตัว", 4.0),
            ("รถเช่า กปภ.", None)
        ]
        conn.executemany("INSERT INTO vehicle_types (type_name, rate_per_km) VALUES (?, ?)", types)

    # 5. Seed Medical Facilities
    cursor = conn.execute("SELECT COUNT(*) FROM medical_facilities")
    if cursor.fetchone()[0] == 0:
        facilities = [
            ("โรงพยาบาลศิริราช", "รัฐบาล"),
            ("โรงพยาบาลระยอง", "รัฐบาล"),
            ("โรงพยาบาลกรุงเทพ", "เอกชน")
        ]
        conn.executemany("INSERT INTO medical_facilities (facility_name, facility_type) VALUES (?, ?)", facilities)

    # 6. Seed Expense Rates
    cursor = conn.execute("SELECT COUNT(*) FROM expense_rates")
    if cursor.fetchone()[0] == 0:
        rates = [
            (1, 300.0, 1600.0, "2026-01-01"), # ผู้จัดการ
            (2, 270.0, 1400.0, "2026-01-01"), # หัวหน้างาน
            (3, 240.0, 1200.0, "2026-01-01"), # วิศวกรชำนาญการ
            (4, 240.0, 1200.0, "2026-01-01"), # นักวิเคราะห์ฯ
            (5, 240.0, 1200.0, "2026-01-01")  # เจ้าพนักงานฯ
        ]
        conn.executemany("INSERT INTO expense_rates (position_id, per_diem_rate, accommodation_rate, effective_date) VALUES (?, ?, ?, ?)", rates)

    # 7. Seed Staff
    cursor = conn.execute("SELECT COUNT(*) FROM staff")
    if cursor.fetchone()[0] == 0:
        staff = [
            ("นายสมชาย ยอดกล้า", 3, "ซี 7", 1, "081-234-5678"),
            ("นางสาวสมศรี ดีใจ", 4, "ซี 5", 1, "089-876-5432"),
            ("นายรักชาติ ยิ่งชีพ", 5, "ซี 4", 1, "085-555-5555")
        ]
        conn.executemany("INSERT INTO staff (full_name, position_id, grade, section_id, phone) VALUES (?, ?, ?, ?, ?)", staff)

    # 8. Seed Vehicles
    cursor = conn.execute("SELECT COUNT(*) FROM vehicles")
    if cursor.fetchone()[0] == 0:
        vehicles = [
            ("กข 1234 ระยอง", 1, 1, None),  # รถส่วนตัวของสมชาย
            ("รย 5678 กรุงเทพ", 2, None, "2568") # รถเช่า กปภ. สัญญาปี 2568
        ]
        conn.executemany("INSERT INTO vehicles (plate_number, vehicle_type_id, staff_id, contract_year) VALUES (?, ?, ?, ?)", vehicles)

    print("Master database seeded successfully.")

def _migrate_soft_delete_v9(conn):
    for table in ['travel_approvals', 'travel_expenses', 'medical_expenses']:
        cursor = conn.execute(f"PRAGMA table_info({table});")
        columns = [c['name'] for c in cursor.fetchall()]
        if 'is_deleted' not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN is_deleted BOOLEAN DEFAULT 0;")
            print(f"[DB] Added column 'is_deleted' to '{table}' table.")

def _migrate_pdf_path_v10(conn):
    cursor = conn.execute("PRAGMA table_info(medical_expenses);")
    columns = [c['name'] for c in cursor.fetchall()]
    if 'pdf_path' not in columns:
        conn.execute("ALTER TABLE medical_expenses ADD COLUMN pdf_path TEXT;")
        print("[DB] Added column 'pdf_path' to 'medical_expenses' table.")

def _migrate_acting_replacement_position_v11(conn):
    cursor = conn.execute("PRAGMA table_info(travel_approvals);")
    columns = [c['name'] for c in cursor.fetchall()]
    if 'acting_replacement_position' not in columns:
        conn.execute("ALTER TABLE travel_approvals ADD COLUMN acting_replacement_position TEXT;")
        print("[DB] Added column 'acting_replacement_position' to 'travel_approvals' table.")

def _migrate_pdf_path_travel_approvals_v12(conn):
    cursor = conn.execute("PRAGMA table_info(travel_approvals);")
    columns = [c['name'] for c in cursor.fetchall()]
    if 'pdf_path' not in columns:
        conn.execute("ALTER TABLE travel_approvals ADD COLUMN pdf_path TEXT;")
        print("[DB] Added column 'pdf_path' to 'travel_approvals' table.")

def _migrate_updated_at_v13(conn):
    for table in ['travel_approvals', 'travel_expenses', 'medical_expenses']:
        cursor = conn.execute(f"PRAGMA table_info({table});")
        columns = [c['name'] for c in cursor.fetchall()]
        if 'updated_at' not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN updated_at TEXT;")
            print(f"[DB] Added column 'updated_at' to '{table}' table.")
