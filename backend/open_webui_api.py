import requests
import os

# Use the existing environment variable for backward compatibility
OLLAMA_API_URL = os.getenv("OPEN_WEBUI_API_URL", "http://localhost:11434")

def query_ollama(prompt: str, model: str = "deepseek-r1:8b", history: list = None, temperature: float = 0.7, max_tokens: int = 1024):
    """
    Send a query to Ollama and return the response.
    
    :param prompt: The text prompt to send to the LLM.
    :param model: The model name (default is "deepseek-r1:8b").
    :param history: Optional list of past messages for context.
    :param temperature: Controls randomness of responses (higher = more creative).
    :param max_tokens: Maximum number of tokens to generate in the response.
    :return: The LLM-generated response as a string.
    """
    if history is None:
        history = []
    
    # Format payload for Ollama's API
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens
        }
    }

    try:
        response = requests.post(f"{OLLAMA_API_URL}/api/chat", json=payload)
        response.raise_for_status()  # Raise error for HTTP failures
        return response.json().get("message", {}).get("content", "No response received")
    
    except requests.exceptions.RequestException as e:
        return {"error": f"Failed to connect to Ollama: {str(e)}"}

    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}"}


def send_assistant_message(message: str, model: str = "deepseek-r1:8b"):
    """
    This function is not used with direct Ollama integration.
    Kept for compatibility, but will return a mock response.

    :param message: The message content to send as an AI-generated response.
    :param model: The model name (default is "deepseek-r1:8b").
    :return: A mock response indicating this function is not used with Ollama.
    """
    return {
        "success": True, 
        "message": "This function is not used with direct Ollama integration",
        "content": message
    }