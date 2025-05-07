from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.security import HTTPBasicCredentials, HTTPBasic
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from database import get_db_connection
from psycopg2.extras import RealDictCursor
from passlib.context import CryptContext
import logging
import json
from datetime import datetime

router = APIRouter()
security = HTTPBasic()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
logger = logging.getLogger(__name__)

# MCP compatible schema models
class MCPMetadata(BaseModel):
    """Metadata for MCP responses"""
    source: str = "question-answer-scribe"
    version: str = "1.0.0"
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())

class MCPChatMessage(BaseModel):
    """Individual chat message in MCP format"""
    id: str
    content: str
    role: str
    timestamp: str
    username: str
    metadata: Optional[Dict[str, Any]] = {}

class MCPChatHistory(BaseModel):
    """Complete chat history response in MCP format"""
    metadata: MCPMetadata = Field(default_factory=MCPMetadata)
    messages: List[MCPChatMessage]
    user_info: Dict[str, Any]

def verify_credentials(credentials: HTTPBasicCredentials):
    """Verify username and password credentials against database"""
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        # Get user record by username
        cursor.execute("SELECT id, username, password_hash FROM users WHERE username = %s", (credentials.username,))
        user = cursor.fetchone()
        
        if not user:
            raise HTTPException(status_code=401, detail="Invalid username or password")
        
        # Verify password
        if not pwd_context.verify(credentials.password, user["password_hash"]):
            raise HTTPException(status_code=401, detail="Invalid username or password")
        
        return user
        
    except Exception as e:
        logger.error(f"Error verifying credentials: {e}")
        raise HTTPException(status_code=500, detail="Authentication error")
    
    finally:
        cursor.close()
        conn.close()

@router.get("/chat-history/{target_username}", response_model=MCPChatHistory)
async def get_user_chat_history(target_username: str, credentials: HTTPBasicCredentials = Depends(security)):
    """
    MCP-compatible API endpoint to retrieve chat history for a target user
    Requires valid username/password authentication
    Returns data in MCP-compatible format
    """
    # Verify requester credentials
    auth_user = verify_credentials(credentials)
    
    # Connect to database
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        # First, get the target user info and family info
        cursor.execute("""
            SELECT u.id, u.family_id, f.family_name, u.is_verified, u.is_admin
            FROM users u 
            JOIN families f ON u.family_id = f.id
            WHERE u.username = %s
        """, (target_username,))
        
        target_user = cursor.fetchone()
        
        if not target_user:
            raise HTTPException(status_code=404, detail="Target user not found")
            
        # Security check: Verify requester is either:
        # 1. The target user themselves
        # 2. An admin user in the same family
        if auth_user["id"] != target_user["id"]:
            # Get requester's family and admin status
            cursor.execute("""
                SELECT family_id, is_admin 
                FROM users 
                WHERE id = %s
            """, (auth_user["id"],))
            
            requester = cursor.fetchone()
            
            # Check if requester is in same family AND is an admin
            if not (requester["family_id"] == target_user["family_id"] and requester.get("is_admin", False)):
                raise HTTPException(status_code=403, detail="Insufficient permissions to access this user's chat history")
        
        # Query for chat history - updated to match the actual database schema
        query = """
        WITH qa_messages AS (
            -- Get questions belonging to this user's family
            SELECT 
                q.question_id,
                q.question_text AS content,
                'assistant' AS role,
                q.created_at AS timestamp,
                NULL AS answer_id,
                'system' AS username
            FROM questions q
            WHERE q.family_id = %s
            
            UNION ALL
            
            -- Get answers from this user's family
            SELECT 
                a.question_id,
                a.answer_text AS content,
                'user' AS role,
                a.created_at AS timestamp,
                a.answer_id,
                COALESCE(u.username, 'unknown') AS username
            FROM answers a
            JOIN questions q ON a.question_id = q.question_id
            LEFT JOIN users u ON a.user_id = u.id
            WHERE q.family_id = %s
        )
        SELECT * FROM qa_messages
        ORDER BY timestamp ASC
        """
        
        cursor.execute(query, (target_user["family_id"], target_user["family_id"]))
        history = cursor.fetchall()
        
        # Convert database rows to MCP-compatible format
        chat_messages = []
        for item in history:
            # Determine message ID (use answer_id if available, otherwise question_id)
            message_id = str(item["answer_id"]) if item["answer_id"] else str(item["question_id"])
            
            # Format timestamp
            timestamp = item["timestamp"].isoformat() if item["timestamp"] else datetime.now().isoformat()
            
            # Create MCP message object
            message = MCPChatMessage(
                id=message_id,
                content=item["content"],
                role=item["role"],
                timestamp=timestamp,
                username=item["username"],
                metadata={
                    "question_id": str(item["question_id"]) if item["question_id"] else None,
                    "answer_id": str(item["answer_id"]) if item["answer_id"] else None,
                }
            )
            chat_messages.append(message)
            
        # Create user info dictionary
        user_info = {
            "username": target_username,
            "family_name": target_user["family_name"],
            "family_id": str(target_user["family_id"]),
        }
        
        # Create and return MCP-compatible response
        return MCPChatHistory(
            metadata=MCPMetadata(),
            messages=chat_messages,
            user_info=user_info
        )
        
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
        
    except Exception as e:
        logger.error(f"Error retrieving chat history: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve chat history: {str(e)}")
        
    finally:
        cursor.close()
        conn.close()

# MCP Tool declaration endpoint
@router.get("/mcp-manifest")
async def get_mcp_manifest():
    """
    Provide MCP tool manifest for discovery
    """
    return {
        "tools": [
            {
                "name": "scribe_chat_history",
                "description": "Retrieve family scribe chat history for a user",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "username": {
                            "type": "string",
                            "description": "The username to fetch chat history for"
                        }
                    },
                    "required": ["username"]
                },
                "endpoint": "/mcp/chat-history/{username}"
            }
        ],
        "auth": {
            "type": "basic",
            "description": "HTTP Basic Authentication with username and password"
        },
        "version": "1.0.0",
        "provider": "question-answer-scribe"
    }