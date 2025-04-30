import os
import requests
import logging
import json
import time
import random
from typing import Optional, Dict, Any, List, Union, Callable

logger = logging.getLogger(__name__)

class OpenAIAPI:
    """
    A client for interacting with OpenAI's API for text generation to use in the question-answer system.
    """

    def __init__(self, api_key: Optional[str] = None, organization: Optional[str] = None):
        """
        Initialize the OpenAI client.

        Args:
            api_key: OpenAI API key (will use OPENAI_API_KEY env var if not provided)
            organization: OpenAI organization ID (optional)
        """
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.organization = organization or os.environ.get("OPENAI_ORGANIZATION")

        if not self.api_key:
            raise ValueError("OpenAI API key is required. Provide it as an argument or set OPENAI_API_KEY environment variable.")

        self.base_url = "https://api.openai.com/v1"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        if self.organization:
            self.headers["OpenAI-Organization"] = self.organization

    def generate_text(self,
                     prompt: str,
                     model: str = "gpt-3.5-turbo",
                     system_message: Optional[str] = None,
                     temperature: float = 0.7,
                     max_tokens: int = 1000,
                     top_p: float = 1.0,
                     frequency_penalty: float = 0.0,
                     presence_penalty: float = 0.0) -> str:
        """
        Generate text using OpenAI's chat completion API.

        Args:
            prompt: The user prompt/query
            model: The model to use (gpt-3.5-turbo, gpt-4, etc.)
            system_message: Optional system message to set context
            temperature: Controls randomness (0-1)
            max_tokens: Maximum tokens to generate
            top_p: Controls diversity via nucleus sampling
            frequency_penalty: Penalizes frequent tokens
            presence_penalty: Penalizes repeated tokens

        Returns:
            The generated text
        """
        url = f"{self.base_url}/chat/completions"

        messages = []
        if system_message:
            messages.append({"role": "system", "content": system_message})

        messages.append({"role": "user", "content": prompt})

        data = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "top_p": top_p,
            "frequency_penalty": frequency_penalty,
            "presence_penalty": presence_penalty
        }

        try:
            result = self._make_request_with_retries(url, data)
            return result["choices"][0]["message"]["content"]
        except requests.exceptions.RequestException as e:
            logger.error(f"Error generating text: {e}")
            if hasattr(e, 'response') and e.response:
                logger.error(f"Response: {e.response.text}")
            raise

    def _make_request_with_retries(self, url: str, data: Dict[str, Any], max_retries: int = 3) -> Dict[str, Any]:
        """
        Make a request to the OpenAI API with exponential backoff retries.
        
        Args:
            url: The API endpoint URL
            data: The request payload
            max_retries: Maximum number of retry attempts
            
        Returns:
            The JSON response from the API
            
        Raises:
            requests.exceptions.RequestException: If all retry attempts fail
        """
        retries = 0
        last_exception = None
        
        while retries <= max_retries:
            try:
                response = requests.post(url, headers=self.headers, json=data, timeout=30)
                
                # If we get a rate limit error, retry with exponential backoff
                if response.status_code == 429:
                    retry_after = int(response.headers.get('Retry-After', 1))
                    wait_time = retry_after if retry_after > 0 else (2 ** retries) + random.uniform(0, 1)
                    logger.warning(f"Rate limited. Retrying after {wait_time:.2f} seconds...")
                    time.sleep(wait_time)
                    retries += 1
                    continue
                    
                response.raise_for_status()
                return response.json()
                
            except requests.exceptions.RequestException as e:
                last_exception = e
                if hasattr(e, 'response') and e.response and e.response.status_code == 429:
                    retry_after = int(e.response.headers.get('Retry-After', 1))
                    wait_time = retry_after if retry_after > 0 else (2 ** retries) + random.uniform(0, 1)
                    logger.warning(f"Rate limited. Retrying after {wait_time:.2f} seconds...")
                    time.sleep(wait_time)
                else:
                    # For other errors, use exponential backoff
                    wait_time = (2 ** retries) + random.uniform(0, 1)
                    logger.warning(f"Request failed. Retrying after {wait_time:.2f} seconds...")
                    time.sleep(wait_time)
                    
                retries += 1
        
        # If we've exhausted retries, raise the last exception
        logger.error(f"Failed after {max_retries} retries")
        if last_exception:
            raise last_exception
        else:
            raise requests.exceptions.RequestException("Maximum retries exceeded")

    def generate_with_history(self,
                             conversation_history: List[Dict[str, str]],
                             model: str = "gpt-3.5-turbo",
                             system_message: Optional[str] = None,
                             temperature: float = 0.7,
                             max_tokens: int = 1000,
                             top_p: float = 1.0,
                             frequency_penalty: float = 0.0,
                             presence_penalty: float = 0.0) -> str:
        """
        Generate text using conversation history for context.
        
        Args:
            conversation_history: List of message dictionaries with 'role' and 'content' keys
                Example: [
                    {"role": "user", "content": "What's the capital of France?"},
                    {"role": "assistant", "content": "The capital of France is Paris."},
                    {"role": "user", "content": "What about Germany?"}
                ]
            model: The model to use (gpt-3.5-turbo, gpt-4, etc.)
            system_message: Optional system message to set context
            temperature: Controls randomness (0-1)
            max_tokens: Maximum tokens to generate
            top_p: Controls diversity via nucleus sampling
            frequency_penalty: Penalizes frequent tokens
            presence_penalty: Penalizes repeated tokens
            
        Returns:
            The generated text response
        """
        url = f"{self.base_url}/chat/completions"
        
        messages = []
        if system_message:
            messages.append({"role": "system", "content": system_message})
        
        # Add conversation history
        messages.extend(conversation_history)
        
        data = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "top_p": top_p,
            "frequency_penalty": frequency_penalty,
            "presence_penalty": presence_penalty
        }
        
        try:
            result = self._make_request_with_retries(url, data)
            return result["choices"][0]["message"]["content"]
        except requests.exceptions.RequestException as e:
            logger.error(f"Error generating text with history: {e}")
            if hasattr(e, 'response') and e.response:
                logger.error(f"Response: {e.response.text}")
            raise

    def call_with_function(self,
                          messages: List[Dict[str, str]],
                          functions: List[Dict[str, Any]],
                          function_call: Union[str, Dict[str, str]] = "auto",
                          model: str = "gpt-3.5-turbo",
                          temperature: float = 0.7) -> Dict[str, Any]:
        """
        Call the OpenAI API with function calling capability.
        
        Args:
            messages: List of message dictionaries with 'role' and 'content' keys
            functions: List of function definitions in OpenAI's format
                Example: [{
                    "name": "get_current_weather",
                    "description": "Get the current weather in a given location",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "location": {
                                "type": "string",
                                "description": "The city and state, e.g. San Francisco, CA"
                            },
                            "unit": {
                                "type": "string",
                                "enum": ["celsius", "fahrenheit"]
                            }
                        },
                        "required": ["location"]
                    }
                }]
            function_call: Control function calling behavior: "auto", "none", or {"name": "function_name"}
            model: The model to use (gpt-3.5-turbo, gpt-4, etc.)
            temperature: Controls randomness (0-1)
            
        Returns:
            The full API response including function call data if applicable
        """
        url = f"{self.base_url}/chat/completions"
        
        data = {
            "model": model,
            "messages": messages,
            "functions": functions,
            "function_call": function_call,
            "temperature": temperature
        }
        
        try:
            return self._make_request_with_retries(url, data)
        except requests.exceptions.RequestException as e:
            logger.error(f"Error calling with function: {e}")
            if hasattr(e, 'response') and e.response:
                logger.error(f"Response: {e.response.text}")
            raise

    def parse_function_call_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """
        Helper method to parse a function call response.
        
        Args:
            response: The full API response from a function call
            
        Returns:
            Dict containing:
                "called": True if a function was called, False otherwise
                "function_name": Name of the called function (if any)
                "function_args": Parsed arguments for the function (if any)
                "message_content": Content of the message (if no function was called)
        """
        if not response or "choices" not in response or not response["choices"]:
            return {
                "called": False,
                "function_name": None,
                "function_args": None,
                "message_content": None,
                "error": "Invalid response structure"
            }
            
        message = response["choices"][0]["message"]
        
        # Check if function was called
        if "function_call" in message:
            function_call = message["function_call"]
            function_name = function_call.get("name")
            
            # Parse arguments from JSON string
            try:
                function_args = json.loads(function_call.get("arguments", "{}"))
            except json.JSONDecodeError:
                function_args = {}
                logger.error(f"Failed to parse function arguments: {function_call.get('arguments')}")
            
            return {
                "called": True,
                "function_name": function_name,
                "function_args": function_args,
                "message_content": message.get("content"),
            }
        else:
            # No function was called
            return {
                "called": False,
                "function_name": None,
                "function_args": None,
                "message_content": message.get("content")
            }

    def query_for_answer(self, prompt: str, model: str = "gpt-3.5-turbo", temperature: float = 0.7, max_tokens: int = 1024) -> Union[str, Dict[str, str]]:
        """
        Send a query to OpenAI and return the response.
        
        This is a wrapper around generate_text specifically formatted to match the Ollama API
        interface used elsewhere in the application.
        
        Args:
            prompt: The text prompt to send to the LLM.
            model: The model name (default is "gpt-3.5-turbo").
            temperature: Controls randomness of responses (higher = more creative).
            max_tokens: Maximum number of tokens to generate in the response.
            
        Returns:
            The LLM-generated response as a string, or an error dictionary.
        """
        try:
            # Use system message to ensure consistent format
            system_prompt = "You are a helpful AI assistant designed to provide clear, direct responses to questions. Keep your answers concise and focused."
            
            return self.generate_text(
                prompt=prompt,
                model=model,
                system_message=system_prompt,
                temperature=temperature,
                max_tokens=max_tokens
            )
        except Exception as e:
            logger.error(f"Failed to connect to OpenAI: {str(e)}")
            return {"error": f"Failed to connect to OpenAI: {str(e)}"}

    def generate_new_question(self, 
                             original_question: str, 
                             user_response: str, 
                             model: str = "gpt-3.5-turbo") -> str:
        """
        Generates a follow-up question based on the original question and user response.
        
        Args:
            original_question: The original question asked
            user_response: The user's answer to the original question
            model: The model to use for generation
            
        Returns:
            A follow-up question as a string
        """
        prompt = (
            f"Given the original question: '{original_question}', "
            f"and the user's response: '{user_response}', "
            "generate a natural-sounding follow-up question that deepens the conversation. "
            "The question should feel personal and engaging, encouraging the user to share more about their stories, experiences, family, thoughts, values, or memories in a way that fosters connection. "
            "It should be open-ended but easy to answer, avoiding complex or unnatural phrasing. "
            "If the response hints at an interesting memory, relationship, or feeling, gently guide the conversation to explore it further. "
            "If the user shares something heartfelt, ask about their emotions or perspective at the time. "
            "If they reflect on a lesson or belief, encourage them to expand on how it shaped them. "
            "If a natural end of the conversation is reached, then ask a new question about either a similar topic or something new."
            "**ONLY RETURN THE ANSWER IN YOUR RESPONSE, DO NOT INCLUDE NOTES OR EXPLANATIONS. ONLY THE ANSWER SHOULD BE RETURNED**"
            "If the response contains sensitive, problematic, or inappropriate content, gracefully steer the discussion toward a positive and meaningful topic. "
            "Above all, ensure that the follow-up feels like something a caring family member or close friend would naturally ask in a warm, curious, and supportive way."
        )
        
        return self.query_for_answer(prompt, model)