import requests
import os

OPEN_WEBUI_API_URL = os.getenv("OPEN_WEBUI_API_URL")
OPEN_WEBUI_API_KEY = os.getenv("OPEN_WEBUI_API_KEY")

def query_ollama(prompt: str, model: str = "deepseek-r1:8b", history: list = None, temperature: float = 0.7, max_tokens: int = 512):
    """
    Send a query to Ollama and return the response.
    
    :param prompt: The text prompt to send to the LLM.
    :param model: The model name (default is "deepseek-r1:7b").
    :param history: Optional list of past messages for context (e.g., [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]).
    :param temperature: Controls randomness of responses (higher = more creative).
    :param max_tokens: Maximum number of tokens to generate in the response.
    :return: The LLM-generated response as a dictionary.
    """
    if history is None:
        history = []
    
    payload = {
        "model": model,
        "prompt": prompt,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "messages": history + [{"role": "user", "content": prompt}]
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {OPEN_WEBUI_API_KEY}"
    }

    try:
        response = requests.post(f"{OPEN_WEBUI_API_URL}/api/chat/completions", json=payload, headers=headers)
        response.raise_for_status()  # Raise error for HTTP failures
        response_text = response.json().get("choices", [{}])[0].get("message", {}).get("content", "No response received")
        return response_text
    
    except requests.exceptions.RequestException as e:
        return {"error": f"Failed to connect to Ollama: {str(e)}"}

    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}"}


def send_assistant_message(message: str, model: str = "deepseek-r1:7b", ):
    """
    Simulates an AI response by sending an assistant message to Open-WebUI.

    :param message: The message content to send as an AI-generated response.
    :return: The API response from Open-WebUI.
    """
    payload = {
      "chat": {
        "model": f"{model}", 
        "messages": [
          { "role": "assistant", "content": f"{send_assistant_message}" } 
        ]
      }
    } 


    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {OPEN_WEBUI_API_KEY}"
    }

    try:
        response = requests.post(f"{OPEN_WEBUI_API_URL}/api/v1/chat/new", json=payload, headers=headers)
        response.raise_for_status()
        return response.json()
    
    except requests.exceptions.RequestException as e:
        print(payload)
        return {"error": f"Failed to send message to Open-WebUI: {str(e)}"}

    except Exception as e:
        print(payload)
        return {"error": f"Unexpected error: {str(e)}"}