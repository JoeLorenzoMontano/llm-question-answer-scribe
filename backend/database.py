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

def add_new_user(request: RegistrationRequest, verification_code: str, family_id: str = None) -> bool:
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
        
        # Create a new family for this user if no family_id provided
        if not family_id:
            family_name = f"{request.username}'s Family"
            cursor.execute(
                "INSERT INTO families (family_name) VALUES (%s) RETURNING id",
                (family_name,)
            )
            family_id = cursor.fetchone()["id"]

        cursor.execute(
            "INSERT INTO users (id, username, password_hash, phone_number, verification_code, is_verified, family_id) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (user_id, request.username, hashed_password, request.phone, verification_code, False, family_id)
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
        
def is_admin_user(user_id: str) -> bool:
    """
    Check if a user has admin privileges.
    Currently, this checks if the user has the is_admin flag set to TRUE.
    
    Args:
        user_id: The user ID to check
        
    Returns:
        True if the user is an admin, False otherwise
    """
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        # Check if is_admin column exists first
        cursor.execute("""
            SELECT EXISTS (
                SELECT 1 
                FROM information_schema.columns 
                WHERE table_name = 'users' AND column_name = 'is_admin'
            ) as column_exists
        """)
        
        column_exists = cursor.fetchone()["column_exists"]
        
        if not column_exists:
            # If the column doesn't exist yet, no admins
            return False
        
        # Check if the user is an admin
        cursor.execute("SELECT is_admin FROM users WHERE id = %s", (user_id,))
        user = cursor.fetchone()
        
        return user is not None and user.get("is_admin", False)
    
    except Exception as e:
        print(f"Error checking admin status: {e}")
        return False
        
    finally:
        cursor.close()
        conn.close()
        
def get_user_chat_history(phone_number: str):
    """
    Retrieve chat history (questions and answers) for a specific user by phone number.
    
    This version filters by the user's family_id to only show relevant questions/answers.
    
    Args:
        phone_number: User's phone number to retrieve history for
        
    Returns:
        A list of chat messages in chronological order
    """
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        # First, check if the user exists and is verified
        cursor.execute("SELECT id, family_id, is_verified FROM users WHERE phone_number = %s", (phone_number,))
        user = cursor.fetchone()
        
        if not user:
            return {"error": "User not found"}
            
        if not user.get("is_verified"):
            return {"error": "User not verified"}
        
        family_id = user.get("family_id")
        
        # Get questions and answers for this family
        query = """
        WITH qa_messages AS (
            -- Get questions belonging to this family
            SELECT 
                question_id,
                question_text AS content,
                'assistant' AS role,
                created_at AS timestamp,
                NULL AS answer_id
            FROM questions
            WHERE family_id = %s
            
            UNION ALL
            
            -- Get answers to questions in this family
            SELECT 
                a.question_id,
                a.answer_text AS content,
                'user' AS role,
                a.created_at AS timestamp,
                a.answer_id
            FROM answers a
            JOIN questions q ON a.question_id = q.question_id
            WHERE q.family_id = %s
        )
        SELECT * FROM qa_messages
        ORDER BY timestamp ASC
        """
        
        cursor.execute(query, (family_id, family_id))
        history = cursor.fetchall()
        
        # Convert database rows to JSON-friendly format
        chat_history = []
        for item in history:
            chat_history.append({
                "question_id": str(item["question_id"]) if item["question_id"] else None,
                "answer_id": str(item["answer_id"]) if item["answer_id"] else None,
                "content": item["content"],
                "role": item["role"],
                "timestamp": item["timestamp"].isoformat() if item["timestamp"] else None
            })
            
        return chat_history
        
    except Exception as e:
        print(f"Error retrieving chat history: {e}")
        return {"error": f"Failed to retrieve chat history: {str(e)}"}
        
    finally:
        cursor.close()
        conn.close()
        
def generate_auth_code(phone_number: str) -> str:
    """
    Generate and store a new verification code for viewing chat history.
    
    Args:
        phone_number: The phone number to generate a code for
        
    Returns:
        The generated verification code, or an error message
    """
    print(f"Generating auth code for phone: {phone_number}")
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        # Check if user exists
        cursor.execute("SELECT id FROM users WHERE phone_number = %s", (phone_number,))
        user = cursor.fetchone()
        
        if not user:
            print(f"User not found for phone: {phone_number}")
            return {"error": "User not found. You need to register first before viewing chat history."}
        
        # Generate a random 6-digit code
        import random
        verification_code = str(random.randint(100000, 999999))
        print(f"Generated code: {verification_code} for user ID: {user['id']}")
        
        # Update user's verification code
        cursor.execute(
            "UPDATE users SET verification_code = %s WHERE id = %s", 
            (verification_code, user['id'])
        )
        conn.commit()
        print(f"Successfully updated verification code in database")
        
        return verification_code
        
    except Exception as e:
        print(f"Error generating auth code: {e}")
        try:
            conn.rollback()
        except:
            pass
        return {"error": f"Failed to generate auth code: {str(e)}"}
        
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
