#!/usr/bin/env python3
"""
Production-ready MCP server for question-answer-scribe
Implements the Model Context Protocol for chat history access
"""
import os
import sys
import logging
import asyncio
from datetime import datetime
import json
import argparse
from typing import Dict, List, Any, Optional, Union, Tuple
import traceback

# Add parent directory to path for imports
parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, parent_dir)

# Import MCP server libraries
try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    logging.error("Failed to import MCP libraries. Please install with: pip install mcp-server")
    sys.exit(1)

# Import database modules
try:
    sys.path.append(parent_dir)  # Ensure parent directory is in path
    from database import get_db_connection
    from psycopg2.extras import RealDictCursor
    from passlib.context import CryptContext
except ImportError as e:
    logging.error(f"Failed to import database modules: {e}")
    logging.error("Please install with: pip install psycopg2-binary passlib")
    sys.exit(1)

# Setup basic logging for startup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stderr)]
)

logger = logging.getLogger("scribe-mcp")

# Initialize FastMCP server
mcp = FastMCP("scribe")

# Authentication
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class DatabaseHelper:
    """Helper class for database operations"""
    
    @staticmethod
    async def get_user_and_family(username: str) -> Dict[str, Any]:
        """Get user and family information"""
        # Convert to async for best practices
        def _db_query():
            conn = None
            cursor = None
            try:
                conn = get_db_connection()
                cursor = conn.cursor(cursor_factory=RealDictCursor)
                
                # Get user info
                cursor.execute("""
                    SELECT u.id, u.family_id, f.family_name
                    FROM users u 
                    JOIN families f ON u.family_id = f.id
                    WHERE u.username = %s
                """, (username,))
                
                user = cursor.fetchone()
                return user
            except Exception as e:
                logger.error(f"Database error in get_user_and_family: {e}")
                return {"error": f"Database error: {str(e)}"}
            finally:
                if cursor:
                    cursor.close()
                if conn:
                    conn.close()
        
        # Run database query in executor
        user = await asyncio.get_event_loop().run_in_executor(None, _db_query)
        
        if not user:
            logger.error(f"User not found: {username}")
            return {"error": f"User not found: {username}"}
            
        return user

    @staticmethod
    async def get_chat_history(family_id: int) -> List[Dict[str, Any]]:
        """Get chat history for a family"""
        # Convert to async for best practices
        def _db_query():
            conn = None
            cursor = None
            try:
                conn = get_db_connection()
                cursor = conn.cursor(cursor_factory=RealDictCursor)
                
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
            except Exception as e:
                logger.error(f"Database error in get_chat_history: {e}")
                return []
            finally:
                if cursor:
                    cursor.close()
                if conn:
                    conn.close()
        
        # Run database query in executor
        history = await asyncio.get_event_loop().run_in_executor(None, _db_query)
        
        # Format messages
        messages = []
        for item in history:
            try:
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
            except Exception as e:
                logger.error(f"Error formatting message: {e}")
                # Continue with other messages
        
        return messages

    @staticmethod
    async def list_family_members(family_id: int) -> List[Dict[str, Any]]:
        """List all members of a family"""
        def _db_query():
            conn = None
            cursor = None
            try:
                conn = get_db_connection()
                cursor = conn.cursor(cursor_factory=RealDictCursor)
                
                # Get family members
                cursor.execute("""
                    SELECT u.username, u.is_admin, u.is_verified
                    FROM users u
                    WHERE u.family_id = %s
                    ORDER BY u.username
                """, (family_id,))
                
                members = cursor.fetchall()
                return members
            except Exception as e:
                logger.error(f"Database error in list_family_members: {e}")
                return []
            finally:
                if cursor:
                    cursor.close()
                if conn:
                    conn.close()
        
        # Run database query in executor
        members = await asyncio.get_event_loop().run_in_executor(None, _db_query)
        return members

# Define MCP tools
@mcp.tool()
async def get_chat_history_for_user(username: str) -> Dict[str, Any]:
    """Get the chat history for a specific user.
    
    Args:
        username: The username to fetch chat history for
    """
    try:
        logger.info(f"Fetching chat history for user: {username}")
        
        # Get user and family information
        user = await DatabaseHelper.get_user_and_family(username)
        if "error" in user:
            return {"error": user["error"]}
        
        # Get chat history
        messages = await DatabaseHelper.get_chat_history(user["family_id"])
        
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
    except Exception as e:
        logger.error(f"Error in get_chat_history_for_user: {e}", exc_info=True)
        return {
            "error": f"Failed to retrieve chat history: {str(e)}"
        }

@mcp.tool()
async def list_family_members(username: str) -> Dict[str, Any]:
    """Get the list of family members for a user's family.
    
    Args:
        username: The username to fetch family members for
    """
    try:
        logger.info(f"Listing family members for user: {username}")
        
        # Get user and family information
        user = await DatabaseHelper.get_user_and_family(username)
        if "error" in user:
            return {"error": user["error"]}
        
        # Get family members
        members = await DatabaseHelper.list_family_members(user["family_id"])
        
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
    except Exception as e:
        logger.error(f"Error in list_family_members: {e}", exc_info=True)
        return {
            "error": f"Failed to list family members: {str(e)}"
        }

def main():
    """Main entry point with error handling"""
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stderr)],
        force=True
    )
    
    # Log startup information
    logger.info(f"Starting MCP server v1.0.0 for question-answer-scribe")
    logger.info(f"Python version: {sys.version}")
    
    try:
        logger.info("Running in stdio mode for Claude Desktop")
        # Run with standard stdio transport as shown in the examples
        mcp.run(transport='stdio')
    except KeyboardInterrupt:
        logger.info("Shutting down MCP server due to keyboard interrupt")
    except Exception as e:
        logger.error(f"Error running MCP server: {str(e)}")
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()