import os
from dotenv import load_dotenv

# Load .env file
load_dotenv()

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-fallback')
    
    # SQLite Database File Location (convert to absolute path to avoid confusion with CWD)
    db_path = os.getenv('DATABASE_PATH', 'data/system.db')
    if not os.path.isabs(db_path):
        # Resolve path relative to the application's root directory
        base_dir = os.path.abspath(os.path.dirname(__file__))
        DATABASE_PATH = os.path.join(base_dir, db_path)
    else:
        DATABASE_PATH = db_path

    # Ensure the parent directory of the database file exists

    # Admin config
    ADMIN_USERNAME = os.getenv('ADMIN_USERNAME', 'admin')
    ADMIN_PASSWORD_HASH = os.getenv('ADMIN_PASSWORD_HASH', '')

    # Templates & outputs directories
    TEMPLATE_DOCX_DIR = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'document_templates')
    OUTPUT_DOCX_DIR = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'generated_documents')
    KNOWLEDGE_BASE_DIR = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'knowledge-base')

