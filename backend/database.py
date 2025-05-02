import psycopg2
from psycopg2.extras import RealDictCursor, Json
from passlib.context import CryptContext
from request_models import RegistrationRequest, MQTTConfigRequest
import uuid
import os
import re
import secrets
import string
import json
import logging
import datetime
import time

DATABASE_URL = os.getenv("DATABASE_URL")
logger = logging.getLogger(__name__)

def is_valid_username(username: str) -> bool:
    return bool(re.match(r"^[a-zA-Z0-9._]{3,30}$", username))

def is_valid_password(password: str) -> bool:
    return bool(re.match(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*])[A-Za-z\d!@#$%^&*]{8,}$", password))
    
def get_db_connection(max_retries=3, retry_delay=2):
    """
    Get a database connection with retry logic.
    
    Args:
        max_retries: Maximum number of retry attempts
        retry_delay: Initial delay between retries in seconds (will be doubled each retry)
        
    Returns:
        A database connection
        
    Raises:
        Exception: If connection failed after max_retries
    """
    last_exception = None
    
    for attempt in range(max_retries):
        try:
            conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
            return conn
        except Exception as e:
            last_exception = e
            if attempt < max_retries - 1:
                # Only log and retry if we have attempts left
                logger.warning(f"Database connection attempt {attempt+1}/{max_retries} failed: {e}")
                logger.info(f"Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
                retry_delay *= 2  # Exponential backoff
    
    # If we get here, all retries failed
    logger.error(f"Failed to connect to database after {max_retries} attempts")
    raise last_exception

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

# MQTT-related database functions

def generate_mqtt_credentials(length=12):
    """
    Generate a random username and password for MQTT authentication.
    
    Args:
        length: Length of the generated strings
        
    Returns:
        Tuple of (username, password)
    """
    alphabet = string.ascii_letters + string.digits
    username = ''.join(secrets.choice(alphabet) for _ in range(length))
    password = ''.join(secrets.choice(alphabet) for _ in range(length))
    return (username, password)

def get_family_mqtt_config(family_id: str):
    """
    Get MQTT configuration for a family.
    
    Args:
        family_id: The family ID to get configuration for
        
    Returns:
        Dictionary with MQTT configuration, or None if not found
    """
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        # Check if the family exists
        cursor.execute("""
            SELECT 
                id, 
                family_name, 
                mqtt_enabled, 
                mqtt_client_id, 
                mqtt_username, 
                mqtt_password, 
                mqtt_topic_prefix, 
                mqtt_allowed_devices,
                mqtt_last_connection
            FROM families 
            WHERE id = %s
        """, (family_id,))
        
        family = cursor.fetchone()
        
        if not family:
            return None
            
        # Convert mqtt_allowed_devices from JSONB to Python dict
        if family.get("mqtt_allowed_devices"):
            family["mqtt_allowed_devices"] = json.loads(family["mqtt_allowed_devices"])
        else:
            family["mqtt_allowed_devices"] = []
            
        # Format last connection timestamp if available
        if family.get("mqtt_last_connection"):
            family["mqtt_last_connection"] = family["mqtt_last_connection"].isoformat()
            
        return {
            "family_id": str(family["id"]),
            "family_name": family["family_name"],
            "mqtt_enabled": family.get("mqtt_enabled", False),
            "mqtt_client_id": family.get("mqtt_client_id"),
            "mqtt_username": family.get("mqtt_username"),
            "mqtt_password": family.get("mqtt_password"),
            "mqtt_topic_prefix": family.get("mqtt_topic_prefix"),
            "mqtt_allowed_devices": family.get("mqtt_allowed_devices", []),
            "mqtt_last_connection": family.get("mqtt_last_connection")
        }
        
    except Exception as e:
        logger.error(f"Error getting family MQTT config: {e}")
        return None
        
    finally:
        cursor.close()
        conn.close()

def update_family_mqtt_config(family_id: str, config: MQTTConfigRequest):
    """
    Update MQTT configuration for a family.
    
    Args:
        family_id: The family ID to update
        config: MQTT configuration request
        
    Returns:
        Dictionary with updated configuration, or error message
    """
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        # Verify the family exists
        cursor.execute("SELECT id FROM families WHERE id = %s", (family_id,))
        family = cursor.fetchone()
        
        if not family:
            return {"error": "Family not found"}
            
        # Generate credentials if enabled and not provided
        mqtt_username = config.mqtt_username
        mqtt_password = config.mqtt_password
        
        if config.enabled and not (mqtt_username and mqtt_password):
            mqtt_username, mqtt_password = generate_mqtt_credentials()
        
        # Generate client ID if needed
        mqtt_client_id = f"family-{family_id}"
        
        # Generate topic prefix if not provided
        mqtt_topic_prefix = config.topic_prefix or f"scribe/families/{family_id}"
        
        # Convert allowed devices to JSON
        allowed_devices_json = Json([]) if not config.allowed_devices else Json([d.dict() for d in config.allowed_devices])
        
        # Update the family record
        cursor.execute("""
            UPDATE families 
            SET 
                mqtt_enabled = %s,
                mqtt_client_id = %s,
                mqtt_username = %s,
                mqtt_password = %s,
                mqtt_topic_prefix = %s,
                mqtt_allowed_devices = %s
            WHERE id = %s
            RETURNING id
        """, (
            config.enabled,
            mqtt_client_id,
            mqtt_username,
            mqtt_password,
            mqtt_topic_prefix,
            allowed_devices_json,
            family_id
        ))
        
        updated = cursor.fetchone()
        conn.commit()
        
        if not updated:
            return {"error": "Failed to update MQTT configuration"}
            
        # Return the updated configuration
        return {
            "family_id": family_id,
            "mqtt_enabled": config.enabled,
            "mqtt_client_id": mqtt_client_id,
            "mqtt_username": mqtt_username,
            "mqtt_password": mqtt_password,
            "mqtt_topic_prefix": mqtt_topic_prefix,
            "allowed_devices": config.allowed_devices or []
        }
        
    except Exception as e:
        logger.error(f"Error updating family MQTT config: {e}")
        conn.rollback()
        return {"error": f"Failed to update MQTT configuration: {str(e)}"}
        
    finally:
        cursor.close()
        conn.close()

def add_mqtt_device_to_family(family_id: str, device_name: str, device_type: str = "generic"):
    """
    Add a new allowed MQTT device to a family.
    
    Args:
        family_id: The family ID to update
        device_name: Name of the device
        device_type: Type of device (e.g., 'arduino', 'esp32', 'mobile')
        
    Returns:
        Dictionary with device info, or error message
    """
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        # Get current allowed devices
        cursor.execute("SELECT mqtt_allowed_devices FROM families WHERE id = %s", (family_id,))
        family = cursor.fetchone()
        
        if not family:
            return {"error": "Family not found"}
            
        # Parse current devices list
        current_devices = []
        if family.get("mqtt_allowed_devices"):
            current_devices = json.loads(family["mqtt_allowed_devices"])
        
        # Generate a device ID
        device_id = str(uuid.uuid4())
        
        # Add new device
        new_device = {
            "device_id": device_id,
            "device_name": device_name,
            "device_type": device_type,
            "created_at": datetime.datetime.now().isoformat()
        }
        
        current_devices.append(new_device)
        
        # Update the database
        cursor.execute(
            "UPDATE families SET mqtt_allowed_devices = %s WHERE id = %s",
            (Json(current_devices), family_id)
        )
        
        conn.commit()
        
        return new_device
        
    except Exception as e:
        logger.error(f"Error adding MQTT device: {e}")
        conn.rollback()
        return {"error": f"Failed to add MQTT device: {str(e)}"}
        
    finally:
        cursor.close()
        conn.close()

def remove_mqtt_device_from_family(family_id: str, device_id: str):
    """
    Remove an allowed MQTT device from a family.
    
    Args:
        family_id: The family ID to update
        device_id: ID of the device to remove
        
    Returns:
        Success message or error
    """
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        # Get current allowed devices
        cursor.execute("SELECT mqtt_allowed_devices FROM families WHERE id = %s", (family_id,))
        family = cursor.fetchone()
        
        if not family:
            return {"error": "Family not found"}
            
        # Parse current devices list
        current_devices = []
        if family.get("mqtt_allowed_devices"):
            current_devices = json.loads(family["mqtt_allowed_devices"])
        
        # Filter out the device to remove
        updated_devices = [d for d in current_devices if d.get("device_id") != device_id]
        
        # If no devices were removed, the device wasn't found
        if len(current_devices) == len(updated_devices):
            return {"error": "Device not found"}
        
        # Update the database
        cursor.execute(
            "UPDATE families SET mqtt_allowed_devices = %s WHERE id = %s",
            (Json(updated_devices), family_id)
        )
        
        conn.commit()
        
        return {"message": "Device removed successfully"}
        
    except Exception as e:
        logger.error(f"Error removing MQTT device: {e}")
        conn.rollback()
        return {"error": f"Failed to remove MQTT device: {str(e)}"}
        
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
