import logging
import uuid
from typing import List, Dict, Any, Optional
from uuid import UUID
from database import get_db_connection
from embeddings import generate_embedding
from open_webui_api import query_ollama
from fastapi import HTTPException
import psycopg2.extras
import numpy as np
from textbelt_api import TextBeltAPI
import os
import re
import random

# Conditionally import OpenAI API if enabled
USE_OPENAI = os.environ.get("USE_OPENAI", "false").lower() == "true"
if USE_OPENAI:
    try:
        from openai_api import OpenAIAPI
        openai_client = OpenAIAPI()
        logging.info("OpenAI API integration enabled")
    except (ImportError, ValueError) as e:
        logging.warning(f"Failed to initialize OpenAI: {e}")
        USE_OPENAI = False

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("app.log"),
        logging.StreamHandler()
    ]
)

textbelt = TextBeltAPI(os.getenv("TEXTBELT_API_KEY"))

def generate_verification_code():
    return str(random.randint(100000, 999999))

def store_and_return_question(question_text: str, category: str = "general", answer_seed: str = None):
    """
    Stores a newly generated question in the database and returns the inserted question.
    
    :param question_text: The text of the question to store.
    :param category: The category of the question (default: "general").
    :param answer_seed: The previous answer UUID that spawned this question response
    :return: A dictionary containing the stored question details.
    """
    question_id = uuid.uuid4()  # Generate unique question ID
    embedding = generate_embedding(question_text)  # Generate embedding for the question

    logging.info(f"Storing question: {question_text} (Category: {category})")

    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute(
            "INSERT INTO questions (question_id, question_text, embedding, category, answer_seed) VALUES (%s, %s, %s, %s, %s)",
            (str(question_id), question_text, embedding, category, answer_seed)
        )
        conn.commit()

        # Retrieve and return the newly inserted question
        cursor.execute(
            "SELECT question_id, question_text, category FROM questions WHERE question_id = %s",
            (str(question_id),)
        )
        stored_question = cursor.fetchone()

        cursor.close()
        conn.close()

        if stored_question:
            return {
                "question_id": stored_question.get("question_id"),
                "question_text": stored_question.get("question_text"),
                "category": stored_question.get("category")
            }
        else:
            logging.error(f"Failed to retrieve the stored question with ID: {str(question_id)}")
            raise HTTPException(status_code=500, detail="Failed to retrieve stored question")

    except Exception as e:
        logging.error(f"Failed to store and retrieve question: {e}")
        raise HTTPException(status_code=500, detail=str(e))

def save_answer_to_db(question_id: str, answer_text: str):
    """
    Saves an answer to the database for a given question ID.

    :param question_id: The ID of the question being answered.
    :param answer_text: The answer text to store.
    :return: A dictionary with the answer ID and a success message.
    """
    logger = logging.getLogger(__name__)

    # Generate a unique answer ID and embedding
    answer_id = str(uuid.uuid4())
    answer_embedding = generate_embedding(answer_text)

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Ensure the question exists before inserting the answer
        cursor.execute("SELECT 1 FROM questions WHERE question_id = %s", (question_id,))
        if cursor.fetchone() is None:
            logger.warning(f"Question ID {question_id} not found.")
            raise HTTPException(status_code=404, detail="Question not found.")

        # Insert the answer into the database
        cursor.execute(
            "INSERT INTO answers (answer_id, question_id, answer_text, embedding) VALUES (%s, %s, %s, %s)",
            (answer_id, question_id, answer_text, answer_embedding)
        )

        conn.commit()
        cursor.close()
        conn.close()

        logger.info(f"Successfully stored answer ID: {answer_id}")

        return {"answer_id": answer_id, "message": "Answer stored successfully."}

    except Exception as e:
        logger.error(f"Error storing answer: {e}")
        raise HTTPException(status_code=500, detail=str(e))

def get_random_question():
    """
    Fetches a random question from the database.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)  # Fetch as dictionary

        cursor.execute("SELECT question_id, question_text FROM questions ORDER BY RANDOM() LIMIT 1")
        question = cursor.fetchone()

        cursor.close()
        conn.close()

        if not question:
            raise HTTPException(status_code=404, detail="No questions found in the database.")

        return question

    except Exception as e:
        logging.error(f"Error sending SMS: {e}")
        raise HTTPException(status_code=500, detail=str(e))

def send_random_question_via_sms(phone_number: str):
    """
    Fetches a random question from the database and sends it via SMS.

    :param phone_number: The recipient's phone number.
    :return: Response from the TextBelt API.
    """
    try:
        # Fetch a random question
        question = get_random_question()
        question_id = question["question_id"]
        question_text = question["question_text"]

        logging.info(f"Sending random question (ID: {question_id}) via SMS to {phone_number}")

        # Send the question text as an SMS
        response = textbelt.send_sms(
            phone_number=phone_number,
            message=question_text,
            webhook_url="https://question-answer.jolomo.io/handleSmsReply",
            webhook_data=question_id
        )

        return response

    except Exception as e:
        logging.error(f"Error sending SMS: {e}")
        raise HTTPException(status_code=500, detail=str(e))

def strip_think_tags(text: str) -> str:
    """
    Removes everything before and including '</think>'. 
    If '<think>' is present, it removes '<think>...</think>' entirely.
    """
    # Remove everything before and including </think>
    text = re.sub(r".*?</think>", "", text, flags=re.DOTALL).strip()
    return text

def generate_new_question(original_question: str, user_response: str, answer_seed: str):
    """
    Generates a new question using an LLM (Ollama or OpenAI) based on the user's previous response.
    If USE_OPENAI=true environment variable is set, it will use OpenAI's API with conversation history.
    Otherwise, it falls back to Ollama.
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

    # Get previous Q&A pairs for this conversation thread if using OpenAI
    conversation_history = None
    if USE_OPENAI:
        try:
            conversation_history = get_conversation_history(answer_seed)
            new_question_text = generate_with_openai(original_question, user_response, conversation_history)
        except Exception as e:
            logging.error(f"OpenAI error: {e}")
            # Fall back to Ollama if OpenAI fails
            new_question_text = query_ollama(prompt)
    else:
        # Use Ollama (default behavior)
        new_question_text = query_ollama(prompt)

    if isinstance(new_question_text, dict) and "error" in new_question_text:
        # If LLM request fails, fall back to a random question with a friendly message
        logging.error(f"LLM error: {new_question_text['error']}")
        random_q = get_random_question()
        if isinstance(random_q, dict) and "question_text" in random_q:
            new_question_text = random_q["question_text"]
        else:
            # Ultimate fallback if everything fails
            new_question_text = "I'd like to hear more about your experiences. Could you share another story with me?"

    return store_and_return_question(strip_think_tags(new_question_text), "", answer_seed)

def generate_with_openai(original_question: str, user_response: str, conversation_history: Optional[List[Dict[str, str]]] = None) -> str:
    """
    Generate a new question using OpenAI's API with conversation history for context.
    
    Args:
        original_question: The original question that was asked
        user_response: The user's response to the original question
        conversation_history: Optional list of previous messages in the conversation
    
    Returns:
        A follow-up question as a string
    """
    if not conversation_history:
        # If no history provided, just use the prompt directly
        return openai_client.generate_new_question(original_question, user_response)
    
    # Add system message to guide the model
    messages = [
        {"role": "system", "content": "You are a friendly, curious assistant helping to ask meaningful follow-up questions that deepen conversations. Your questions should feel personal and engaging, encouraging users to share more about their experiences, thoughts, and memories. Always respond with ONLY the follow-up question."}
    ]
    
    # Add conversation history
    messages.extend(conversation_history)
    
    # Add the most recent question and response
    messages.append({"role": "assistant", "content": original_question})
    messages.append({"role": "user", "content": user_response})
    
    # Generate a follow-up question using the full conversation context
    try:
        response = openai_client.generate_with_history(
            conversation_history=messages,
            model="gpt-3.5-turbo",
            temperature=0.7
        )
        return response
    except Exception as e:
        logging.error(f"Error generating with OpenAI history: {e}")
        # Fall back to basic prompt if error occurs
        return openai_client.generate_new_question(original_question, user_response)

def get_conversation_history(answer_seed: str) -> List[Dict[str, str]]:
    """
    Fetch the conversation history for a given answer thread.
    
    This function traces back through the question-answer chain to build
    a complete history of the conversation for context.
    
    Args:
        answer_seed: The ID of the answer that spawned the current question
        
    Returns:
        A list of message dictionaries with 'role' and 'content' keys
    """
    history = []
    current_answer_id = answer_seed
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Traverse up to 10 Q&A pairs (to limit context size)
        for _ in range(10):
            if not current_answer_id:
                break
                
            # Get the answer and its question
            cursor.execute("""
                SELECT a.answer_text, q.question_text, q.answer_seed
                FROM answers a
                JOIN questions q ON a.question_id = q.question_id
                WHERE a.answer_id = %s
            """, (current_answer_id,))
            
            result = cursor.fetchone()
            if not result:
                break
                
            # Add the Q&A pair to the history in reverse order (oldest first)
            history.insert(0, {"role": "assistant", "content": result["question_text"]})
            history.insert(1, {"role": "user", "content": result["answer_text"]})
            
            # Move to the previous Q&A pair
            current_answer_id = result["answer_seed"]
        
        cursor.close()
        conn.close()
        
        return history
    except Exception as e:
        logging.error(f"Error retrieving conversation history: {e}")
        return []

def get_question_by_id(question_id: UUID):
    """
    Retrieves a question from the database using the provided question_id.
    
    :param question_id: The unique identifier of the question.
    :return: A dictionary containing the question details.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cursor.execute(
            "SELECT question_id, question_text, category FROM questions WHERE question_id = %s",
            (str(question_id),)  
        )

        question = cursor.fetchone()

        cursor.close()
        conn.close()

        if question:
            return question
        else:
            logging.warning(f"Question not found with ID: {question_id}")
            raise HTTPException(status_code=404, detail="Question not found")

    except Exception as e:
        logging.error(f"Error retrieving question with ID {question_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
