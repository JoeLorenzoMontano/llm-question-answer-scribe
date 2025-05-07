#!/usr/bin/env python3
"""
Example MCP client for the question-answer-scribe service
Demonstrates how to interact with the MCP-compatible API
"""

import requests
import json
from typing import Dict, Any, Optional
import argparse
import sys
import getpass
from base64 import b64encode

class MCPClient:
    """Model Context Protocol client for question-answer-scribe"""
    
    def __init__(self, base_url: str, username: str, password: str):
        """
        Initialize the MCP client
        
        Args:
            base_url: Base URL of the MCP server, e.g., 'https://question-answer.jolomo.io'
            username: Username for authentication
            password: Password for authentication
        """
        self.base_url = base_url.rstrip('/')
        self.username = username
        self.password = password
        self.auth_header = self._create_auth_header(username, password)
        
    def _create_auth_header(self, username: str, password: str) -> Dict[str, str]:
        """Create HTTP Basic Auth header"""
        credentials = f"{username}:{password}"
        print(f"DEBUG: Raw credentials string: {credentials}")
        encoded = b64encode(credentials.encode()).decode()
        print(f"DEBUG: Base64 encoded credentials: {encoded}")
        return {"Authorization": f"Basic {encoded}"}
    
    def get_manifest(self) -> Dict[str, Any]:
        """Get the MCP tool manifest"""
        url = f"{self.base_url}/mcp/mcp-manifest"
        response = requests.get(url, headers=self.auth_header)
        response.raise_for_status()
        return response.json()
    
    def get_chat_history(self, target_username: str) -> Dict[str, Any]:
        """
        Get chat history for a specific user
        
        Args:
            target_username: Username to fetch chat history for
            
        Returns:
            Dict containing chat history in MCP format
        """
        url = f"{self.base_url}/mcp/chat-history/{target_username}"
        print(f"DEBUG: Making request to URL: {url}")
        print(f"DEBUG: Using auth header: {self.auth_header}")
        
        response = requests.get(url, headers=self.auth_header)
        
        if response.status_code != 200:
            print(f"DEBUG: Server returned status code: {response.status_code}")
            print(f"DEBUG: Response content: {response.text}")
            
        response.raise_for_status()
        return response.json()
    
    def format_chat_history(self, history: Dict[str, Any]) -> str:
        """Format chat history for display"""
        output = f"Chat History for {history['user_info']['username']} in {history['user_info']['family_name']}\n"
        output += "=" * 80 + "\n\n"
        
        for msg in history['messages']:
            role = "AI" if msg['role'] == 'assistant' else msg['username']
            timestamp = msg['timestamp'].split('T')[0]  # Just get the date part
            output += f"[{timestamp}] {role}: {msg['content']}\n\n"
            
        return output

def main():
    parser = argparse.ArgumentParser(description='MCP Client for Question-Answer Scribe')
    parser.add_argument('--url', type=str, default='http://localhost:8001', 
                        help='Base URL of the MCP server')
    parser.add_argument('--username', type=str, required=True,
                        help='Your username for authentication')
    parser.add_argument('--password', type=str,
                        help='Your password for authentication (omit to enter securely)')
    parser.add_argument('--target', type=str, required=True,
                        help='Target username to fetch chat history for')
    parser.add_argument('--output', type=str, help='Output file (defaults to stdout)')
    parser.add_argument('--debug', action='store_true', help='Print additional debug information')
    args = parser.parse_args()
    
    # If password not provided on command line, prompt for it securely
    password = args.password
    if not password:
        password = getpass.getpass(f"Enter password for {args.username}: ")
    
    try:
        client = MCPClient(args.url, args.username, password)
        
        # First check the manifest to see what's available
        manifest = client.get_manifest()
        print(f"Connected to MCP Provider: {manifest['provider']} v{manifest['version']}")
        
        # Get chat history
        history = client.get_chat_history(args.target)
        formatted = client.format_chat_history(history)
        
        # Output formatting
        if args.output:
            with open(args.output, 'w') as f:
                f.write(formatted)
            print(f"Chat history saved to {args.output}")
        else:
            print("\n" + formatted)
            
    except requests.exceptions.HTTPError as e:
        print(f"HTTP Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
