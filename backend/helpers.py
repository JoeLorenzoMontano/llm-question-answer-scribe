import logging
import uuid
from typing import List
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
    Generates a new question using an LLM (Ollama) based on the user's previous response.
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
        "If a natural end of the conversation is reached, then ask a new quesiton about either a similar topic or something new."
        "**ONLY RETURN THE ANSWER IN YOUR RESPONSE, DO NOT INCLUDE NOTES OR EXPLANATIONS. ONLY THE ANSWER SHOULD BE RETURNED**"
        "If the response contains sensitive, problematic, or inappropriate content, gracefully steer the discussion toward a positive and meaningful topic. "
        "Above all, ensure that the follow-up feels like something a caring family member or close friend would naturally ask in a warm, curious, and supportive way."
    )

    # Query Ollama for a new question
    new_question_text = query_ollama(prompt)

    if isinstance(new_question_text, dict) and "error" in new_question_text:
        # If Ollama request fails, fall back to a random question
        logging.error(f"Ollama error: {new_question_text['error']}")
        new_question_text = get_random_question()

    return store_and_return_question(strip_think_tags(new_question_text), "", answer_seed)

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
