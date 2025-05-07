# Question Answer Scribe MCP Server

This package provides an MCP (Model Context Protocol) server for the Question Answer Scribe service.

## Installation

```bash
# Install globally
npm install -g @question-answer-scribe/mcp-server

# Or use without installation via npx
npx @question-answer-scribe/mcp-server
```

## Usage with Claude Desktop

Configure Claude Desktop to use this MCP server:

```json
{
  "mcpServers": {
    "scribe": {
      "command": "npx",
      "args": [
        "-y",
        "@question-answer-scribe/mcp-server",
        "username"  // Optional username parameter
      ]
    }
  }
}
```

## Available Tools

The server provides the following tools:

- `get_chat_history_for_user`: Retrieves chat history for a specific user
- `echo`: Simple echo function for testing

## Development

To build and test locally:

```bash
# Clone the repository
git clone https://github.com/your-org/question-answer-scribe.git

# Navigate to the node wrapper
cd question-answer-scribe/node-wrapper

# Install dependencies
npm install

# Link package locally for testing
npm link

# Test the command
scribe-mcp
```