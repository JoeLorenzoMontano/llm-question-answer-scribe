#!/usr/bin/env python3
"""
MCP server for question-answer-scribe using FastMCP library
"""
from typing import Dict, List, Any, Optional
import os
import sys
import logging
from datetime import datetime
import asyncio
import httpx

# Add parent directory to path for imports
parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, parent_dir)

# Import from MCP server package
from mcp.server.fastmcp import FastMCP

# Initialize FastMCP server
mcp = FastMCP("scribe")

# Import database modules
sys.path.append(parent_dir)  # Ensure parent directory is in path
from database import get_db_connection
from psycopg2.extras import RealDictCursor
from passlib.context import CryptContext

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stderr)
    ]
)

logger = logging.getLogger("scribe-mcp")

# Authentication
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Helper functions for database access
async def get_user_and_family(username: str) -> Dict[str, Any]:
    """Get user and family information"""
    # Convert to async for best practices
    def _db_query():
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        try:
            # Get user info
            cursor.execute("""
                SELECT u.id, u.family_id, f.family_name
                FROM users u 
                JOIN families f ON u.family_id = f.id
                WHERE u.username = %s
            """, (username,))
            
            user = cursor.fetchone()
            return user
            
        finally:
            cursor.close()
            conn.close()
    
    # Run database query in executor
    user = await asyncio.get_event_loop().run_in_executor(None, _db_query)
    
    if not user:
        logger.error(f"User not found: {username}")
        return {"error": f"User not found: {username}"}
        
    return user

async def get_chat_history(family_id: int) -> List[Dict[str, Any]]:
    """Get chat history for a family"""
    # Convert to async for best practices
    def _db_query():
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        try:
            # Query for chat history
            query = """
            WITH qa_messages AS (
                -- Get questions belonging to this family
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
                
                -- Get answers from this family
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
            
            cursor.execute(query, (family_id, family_id))
            history = cursor.fetchall()
            return history
            
        finally:
            cursor.close()
            conn.close()
    
    # Run database query in executor
    history = await asyncio.get_event_loop().run_in_executor(None, _db_query)
    
    # Format messages
    messages = []
    for item in history:
        message_id = str(item["answer_id"]) if item["answer_id"] else str(item["question_id"])
        timestamp = item["timestamp"].isoformat() if item["timestamp"] else datetime.now().isoformat()
        
        messages.append({
            "id": message_id,
            "content": item["content"],
            "role": item["role"],
            "timestamp": timestamp,
            "username": item["username"],
            "metadata": {
                "question_id": str(item["question_id"]) if item["question_id"] else None,
                "answer_id": str(item["answer_id"]) if item["answer_id"] else None,
            }
        })
        
    return messages

# Define MCP tools
@mcp.tool()
async def get_chat_history_for_user(username: str) -> Dict[str, Any]:
    """Get the chat history for a specific user.
    
    Args:
        username: The username to fetch chat history for
    """
    logger.info(f"Fetching chat history for user: {username}")
    
    # Get user and family information
    user = await get_user_and_family(username)
    if "error" in user:
        return {"error": user["error"]}
    
    # Get chat history
    messages = await get_chat_history(user["family_id"])
    
    # Create the result object
    return {
        "metadata": {
            "source": "question-answer-scribe",
            "version": "1.0.0",
            "timestamp": datetime.now().isoformat()
        },
        "messages": messages,
        "user_info": {
            "username": username,
            "family_name": user["family_name"],
            "family_id": str(user["family_id"]),
        }
    }

@mcp.tool()
async def list_family_members(username: str) -> Dict[str, Any]:
    """Get the list of family members for a user's family.
    
    Args:
        username: The username to fetch family members for
    """
    logger.info(f"Listing family members for user: {username}")
    
    # Get user and family information
    user = await get_user_and_family(username)
    if "error" in user:
        return {"error": user["error"]}
    
    # Convert to async for best practices
    def _db_query():
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        try:
            # Get family members
            cursor.execute("""
                SELECT u.username, u.is_admin, u.is_verified
                FROM users u
                WHERE u.family_id = %s
                ORDER BY u.username
            """, (user["family_id"],))
            
            members = cursor.fetchall()
            return members
            
        finally:
            cursor.close()
            conn.close()
    
    # Run database query in executor
    members = await asyncio.get_event_loop().run_in_executor(None, _db_query)
    
    # Create the result object
    return {
        "family_name": user["family_name"],
        "family_id": str(user["family_id"]),
        "members": [
            {
                "username": member["username"],
                "is_admin": member["is_admin"],
                "is_verified": member["is_verified"]
            }
            for member in members
        ]
    }

if __name__ == "__main__":
    # Initialize and run the server
    mcp.run(transport='stdio')