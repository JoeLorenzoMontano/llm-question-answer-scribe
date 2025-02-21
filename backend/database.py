import psycopg2
from psycopg2.extras import RealDictCursor
from passlib.context import CryptContext
from request_models import RegistrationRequest
import uuid
import os
import re

DATABASE_URL = os.getenv("DATABASE_URL")

def is_valid_username(username: str) -> bool:
    return bool(re.match(r"^[a-zA-Z0-9._]{3,30}$", username))

def is_valid_password(password: str) -> bool:
    return bool(re.match(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*])[A-Za-z\d!@#$%^&*]{8,}$", password))
    
def get_db_connection():
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    return conn

def hash_password(password: str) -> str:
    # Setup password hashing
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    return pwd_context.hash(password)

def add_new_user(request: RegistrationRequest, verification_code: str) -> bool:
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    try:
        # Validate username & password
        if not is_valid_username(request.username):
            raise ValueError("Invalid username format.")
        if not is_valid_password(request.password):
            raise ValueError("Password does not meet security standards.")

        # Check if phone number already exists
        cursor.execute("SELECT id FROM users WHERE phone_number = %s", (request.phone,))
        existing_user = cursor.fetchone()

        if existing_user:
            return False 

        # Generate a new UUID for the user
        user_id = str(uuid.uuid4())
        hashed_password = hash_password(request.password)

        cursor.execute(
            "INSERT INTO users (id, username, password_hash, phone_number, verification_code, is_verified) VALUES (%s, %s, %s, %s, %s, %s)",
            (user_id, request.username, hashed_password, request.phone, verification_code, False)
        )

        conn.commit()
        return True

    except Exception as e:
        print(f"Error adding new user: {e}")
        conn.rollback()
        return False

    finally:
        cursor.close()
        conn.close()

def verify_user(phone_number: str, input_code: str) -> bool:
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    try:
        cursor.execute("SELECT id FROM users WHERE phone_number = %s AND verification_code = %s", (phone_number, input_code))
        user = cursor.fetchone()

        if user:
            cursor.execute("UPDATE users SET is_verified = TRUE WHERE id = %s", (user["id"],))
            conn.commit()
            return True

        return False

    except Exception as e:
        print(f"Error verifying user: {e}")
        return False

    finally:
        cursor.close()
        conn.close()

# CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

# CREATE TABLE users (
#     id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
#     username VARCHAR(50) UNIQUE NOT NULL,
#     password_hash TEXT NOT NULL,
#     phone_number VARCHAR(20) UNIQUE NOT NULL,
#     verification_code VARCHAR(10),
#     is_verified BOOLEAN DEFAULT FALSE,
#     created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
# );

# CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

# CREATE TABLE questions (
#     id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
#     family_id UUID NOT NULL REFERENCES families(id) ON DELETE CASCADE,
#     user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
#     question_text TEXT NOT NULL,
#     embedding VECTOR(1536),  -- Stores the question embedding for similarity searches
#     metadata JSONB,  -- Stores any extra information (e.g., tags, topic, AI-generated details)
#     created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
# );

# CREATE TABLE answers (
#     id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
#     question_id UUID NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
#     user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
#     answer_text TEXT NOT NULL,
#     embedding VECTOR(1536),  -- Stores the answer embedding for similarity searches
#     metadata JSONB,  -- Stores any extra information (e.g., AI confidence, feedback)
#     created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
# );

# CREATE TABLE families (
#     id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
#     family_name VARCHAR(100) UNIQUE NOT NULL,
#     created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
# );
