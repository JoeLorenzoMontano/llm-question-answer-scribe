#!/usr/bin/env python3
"""
MCP Server for Question Answer Scribe
This script is embedded in the npm package
"""
import os
import sys
import logging
import json
import subprocess
import tempfile
import venv
import site
from pathlib import Path

# Setup basic logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stderr)]
)

logger = logging.getLogger("scribe-mcp")

def setup_virtualenv():
    """Set up a virtual environment and install dependencies"""
    venv_dir = os.path.join(tempfile.gettempdir(), "scribe-mcp-env")
    
    # Create virtualenv if it doesn't exist
    if not os.path.exists(os.path.join(venv_dir, "bin", "python")):
        logger.info(f"Creating virtual environment at {venv_dir}")
        venv.create(venv_dir, with_pip=True)
    
    # Activate the virtualenv
    if sys.platform == 'win32':
        activate_script = os.path.join(venv_dir, "Scripts", "activate")
    else:
        activate_script = os.path.join(venv_dir, "bin", "activate")
    
    # Add venv site-packages to path
    if sys.platform == 'win32':
        site_packages = os.path.join(venv_dir, "Lib", "site-packages")
    else:
        site_packages = os.path.join(venv_dir, "lib", f"python{sys.version_info.major}.{sys.version_info.minor}", "site-packages")
    
    sys.path.insert(0, site_packages)
    
    # Install required packages if needed
    try:
        import mcp.server.fastmcp
        logger.info("MCP server package already installed")
    except ImportError:
        logger.info("Installing required packages...")
        pip_path = os.path.join(venv_dir, "bin", "pip") if sys.platform != 'win32' else os.path.join(venv_dir, "Scripts", "pip")
        subprocess.check_call([pip_path, "install", "mcp-server", "psycopg2-binary", "passlib"])
        
        # Refresh sys.path after installing packages
        site.addsitedir(site_packages)
        
    return venv_dir

# Set up the virtualenv
venv_dir = setup_virtualenv()

# Now we can import mcp packages
from mcp.server.fastmcp import FastMCP

# Initialize FastMCP server
mcp = FastMCP("scribe")

# Parse command-line args
username_arg = sys.argv[1] if len(sys.argv) > 1 else None

@mcp.tool()
async def echo(text: str) -> str:
    """Echo back the provided text.

    Args:
        text: The text to echo
    """
    return text

@mcp.tool()
async def get_chat_history_for_user(username: str = None) -> dict:
    """Get the chat history for a specific user.
    
    Args:
        username: The username to fetch chat history for
    """
    # Use the username from command line if not provided
    if not username and username_arg:
        username = username_arg
    
    if not username:
        return {"error": "No username provided. Please specify a username."}
    
    # Placeholder - would normally make a database call here
    # In a real implementation, this would query a database
    return {
        "metadata": {
            "source": "question-answer-scribe",
            "version": "1.0.0"
        },
        "messages": [
            {
                "id": "1",
                "content": "What is your favorite memory from childhood?",
                "role": "assistant",
                "timestamp": "2025-05-01T12:00:00Z",
                "username": "system"
            },
            {
                "id": "2",
                "content": f"Hello, {username}! This is a simulated chat history response.",
                "role": "user",
                "timestamp": "2025-05-01T12:05:00Z",
                "username": username
            }
        ],
        "user_info": {
            "username": username,
            "family_name": "Example Family",
            "family_id": "123"
        }
    }

if __name__ == "__main__":
    logger.info(f"Starting MCP server with username context: {username_arg}")
    try:
        # Run with stdio transport
        mcp.run(transport='stdio')
    except Exception as e:
        logger.error(f"Error running MCP server: {e}", exc_info=True)
        sys.exit(1)