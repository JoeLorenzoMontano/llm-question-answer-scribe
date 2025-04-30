"""
Database migration utility for the LLM Question Answer Scribe application.

This utility manages the application of migrations in a sequential, ordered manner.
It keeps track of applied migrations in a migrations table and only applies new ones.
"""

import os
import logging
import argparse
import glob
import psycopg2
from psycopg2.extras import RealDictCursor
import re

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("migration")

def get_connection_string():
    """Get database connection string from environment variables"""
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise ValueError("DATABASE_URL environment variable not set")
    return db_url

def get_db_connection():
    """Establish a database connection"""
    return psycopg2.connect(get_connection_string())

def ensure_migrations_table():
    """Ensure the migrations tracking table exists"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Create migrations table if it doesn't exist
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS migrations (
                id SERIAL PRIMARY KEY,
                migration_name VARCHAR(255) UNIQUE NOT NULL,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        logger.info("Migrations table checked/created successfully")
    except Exception as e:
        logger.error(f"Error ensuring migrations table: {e}")
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()

def get_applied_migrations():
    """Get a list of already applied migrations"""
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        cursor.execute("SELECT migration_name FROM migrations ORDER BY id")
        applied = [row["migration_name"] for row in cursor.fetchall()]
        return applied
    except Exception as e:
        logger.error(f"Error getting applied migrations: {e}")
        raise
    finally:
        cursor.close()
        conn.close()

def get_available_migrations():
    """Get all available migration scripts in order"""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    migration_files = glob.glob(os.path.join(current_dir, "*.sql"))
    
    # Extract the migration number prefix and sort numerically
    def get_migration_number(path):
        filename = os.path.basename(path)
        match = re.match(r'^(\d+)_', filename)
        if match:
            return int(match.group(1))
        return 0  # Default for files without number prefix
    
    migration_files.sort(key=get_migration_number)
    return migration_files

def apply_migration(migration_path):
    """Apply a single migration file"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    migration_name = os.path.basename(migration_path)
    logger.info(f"Applying migration: {migration_name}")
    
    try:
        # Read migration file
        with open(migration_path, 'r') as f:
            migration_sql = f.read()
            
        # Execute migration
        cursor.execute(migration_sql)
        
        # Record the migration
        cursor.execute(
            "INSERT INTO migrations (migration_name) VALUES (%s)",
            (migration_name,)
        )
            
        conn.commit()
        logger.info(f"Successfully applied migration: {migration_name}")
        return True
    except Exception as e:
        logger.error(f"Error applying migration {migration_name}: {e}")
        conn.rollback()
        return False
    finally:
        cursor.close()
        conn.close()

def run_migrations():
    """Run all pending migrations"""
    # Ensure migrations table exists
    ensure_migrations_table()
    
    # Get already applied migrations
    applied = get_applied_migrations()
    logger.info(f"Already applied migrations: {len(applied)}")
    
    # Get available migrations
    available = get_available_migrations()
    logger.info(f"Available migrations: {len(available)}")
    
    # Apply pending migrations
    success_count = 0
    error_count = 0
    
    for migration_path in available:
        migration_name = os.path.basename(migration_path)
        
        if migration_name in applied:
            logger.info(f"Skipping already applied migration: {migration_name}")
            continue
            
        if apply_migration(migration_path):
            success_count += 1
        else:
            error_count += 1
            # Stop on first error
            break
    
    logger.info(f"Migration complete. Applied: {success_count}, Errors: {error_count}")
    return error_count == 0

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Database migration utility")
    parser.add_argument("--check", action="store_true", help="Check for pending migrations without applying them")
    args = parser.parse_args()
    
    if args.check:
        # Check mode - just print pending migrations
        ensure_migrations_table()
        applied = get_applied_migrations()
        available = get_available_migrations()
        
        pending = []
        for migration_path in available:
            migration_name = os.path.basename(migration_path)
            if migration_name not in applied:
                pending.append(migration_name)
        
        if pending:
            logger.info(f"Pending migrations: {len(pending)}")
            for migration in pending:
                logger.info(f"- {migration}")
            exit(1)  # Exit with error code if pending migrations exist
        else:
            logger.info("No pending migrations.")
            exit(0)
    else:
        # Run migrations
        success = run_migrations()
        exit(0 if success else 1)