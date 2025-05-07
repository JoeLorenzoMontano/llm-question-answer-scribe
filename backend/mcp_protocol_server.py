#!/usr/bin/env python3
"""
MCP Protocol server for the question-answer-scribe service

Implements the Model Context Protocol (MCP) interface for Claude Desktop
"""

import json
import sys
import logging
import asyncio
from datetime import datetime
from typing import Dict, Any, Optional, List, Union
from database import get_db_connection
from psycopg2.extras import RealDictCursor
from passlib.context import CryptContext

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stderr)]
)

logger = logging.getLogger("mcp-server")

# Authentication
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class MCPServer:
    """Implementation of MCP protocol server"""
    
    def __init__(self):
        self.tools = [
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
                }
            }
        ]
        
    async def handle_stdin_stdout(self):
        """Main loop to handle MCP protocol over stdin/stdout"""
        logger.info("MCP server starting")
        
        while True:
            try:
                # Read content-length header
                header = await self._read_line()
                if not header:
                    continue
                    
                if not header.startswith("Content-Length: "):
                    logger.error(f"Invalid header: {header}")
                    continue
                    
                content_length = int(header.split("Content-Length: ")[1])
                
                # Read empty line
                await self._read_line()
                
                # Read message body
                body = await self._read_exact(content_length)
                
                # Parse and process message
                message = json.loads(body)
                logger.info(f"Received message: {message}")
                
                # Process based on method
                response = await self._handle_message(message)
                
                # Write response
                await self._write_response(response)
                
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                # Send error response if we know the message ID
                if 'message' in locals() and isinstance(message, dict) and 'id' in message:
                    error_response = {
                        "jsonrpc": "2.0",
                        "id": message.get("id"),
                        "error": {
                            "code": -32603,
                            "message": f"Internal error: {str(e)}"
                        }
                    }
                    await self._write_response(error_response)
    
    async def _read_line(self):
        """Read a line from stdin"""
        return (await asyncio.get_event_loop().run_in_executor(None, sys.stdin.readline)).rstrip()
    
    async def _read_exact(self, n):
        """Read exactly n bytes from stdin"""
        return await asyncio.get_event_loop().run_in_executor(None, lambda: sys.stdin.read(n))
    
    async def _write_response(self, response):
        """Write a JSON-RPC response to stdout"""
        response_json = json.dumps(response)
        print(f"Content-Length: {len(response_json)}", flush=True)
        print("", flush=True)
        print(response_json, flush=True)
        logger.info(f"Sent response: {response}")
    
    async def _handle_message(self, message):
        """Process an MCP message and return a response"""
        method = message.get("method")
        msg_id = message.get("id")
        
        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "serverInfo": {
                        "name": "question-answer-scribe",
                        "version": "1.0.0"
                    },
                    "capabilities": {}
                }
            }
            
        elif method == "getTools":
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "tools": self.tools
                }
            }
            
        elif method == "executeToolCall":
            params = message.get("params", {})
            tool_call = params.get("toolCall", {})
            tool_name = tool_call.get("name")
            tool_params = tool_call.get("parameters", {})
            
            if tool_name == "scribe_chat_history":
                result = await self._execute_chat_history(tool_params)
                if "error" in result:
                    return {
                        "jsonrpc": "2.0",
                        "id": msg_id,
                        "error": result["error"]
                    }
                else:
                    return {
                        "jsonrpc": "2.0",
                        "id": msg_id,
                        "result": {
                            "result": result
                        }
                    }
            else:
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {
                        "code": -32601,
                        "message": f"Tool not found: {tool_name}"
                    }
                }
                
        elif method == "shutdown":
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": None
            }
            
        else:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {
                    "code": -32601,
                    "message": f"Method not supported: {method}"
                }
            }
    
    async def _execute_chat_history(self, params):
        """Execute the scribe_chat_history tool"""
        username = params.get("username")
        if not username:
            return {
                "error": {
                    "code": -32602,
                    "message": "Missing required parameter: username"
                }
            }
            
        try:
            # For this example, we're assuming authentication is handled elsewhere
            # or using a default user account for demo purposes
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
            if not user:
                return {
                    "error": {
                        "code": 404,
                        "message": f"User not found: {username}"
                    }
                }
                
            # Query for chat history
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
            
            cursor.execute(query, (user["family_id"], user["family_id"]))
            history = cursor.fetchall()
            
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
            logger.error(f"Error executing chat history: {e}")
            return {
                "error": {
                    "code": -32603,
                    "message": f"Internal error: {str(e)}"
                }
            }
            
        finally:
            if 'cursor' in locals():
                cursor.close()
            if 'conn' in locals():
                conn.close()

async def main():
    """Main entry point"""
    server = MCPServer()
    await server.handle_stdin_stdout()

if __name__ == "__main__":
    asyncio.run(main())