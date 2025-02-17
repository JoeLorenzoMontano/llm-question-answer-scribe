import logging
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from database import get_db_connection
from embeddings import generate_embedding
from open_webui_api import query_ollama, send_assistant_message
from textbelt_api import TextBeltAPI
import uuid
from uuid import UUID
from pydantic import BaseModel
import numpy as np
from typing import List
import re
import psycopg2.extras  # Needed for dictionary cursorimport os
import os

TEXTBELT_API_KEY = os.getenv("TEXTBELT_API_KEY")

# Setup Logging
logging.basicConfig(
    level=logging.INFO,  # Set to DEBUG for more details
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("app.log"),  # Log to a file
        logging.StreamHandler()  # Log to console
    ]
)

logger = logging.getLogger(__name__)

app = FastAPI()

textbelt = TextBeltAPI(TEXTBELT_API_KEY)

class QuestionRequest(BaseModel):
    question: str
    category: str = None

class AnswerRequest(BaseModel):
    question_id: str
    answer: str

class AskRequest(BaseModel):
    prompt: str
    model: str = "deepseek-r1:7b"

class QuestionBatch(BaseModel):
    questions: List[QuestionRequest]

class AnswerText(BaseModel):
    answer: str 

class SMSRequest(BaseModel):
    phone: str
    message: str = None

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

@app.post("/store/")
def store_question(request: QuestionRequest):
    question = store_and_return_question(request.question, request.category)
    return {"question_id": question.question_id}

@app.get("/similar/")
def get_similar_questions(query: str, top_k: int = 5):
    logger.info(f"Finding similar questions for: {query}")

    query_embedding = generate_embedding(query)
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        search_query = """
        SELECT question_id, question_text, embedding <-> %s::vector AS similarity
        FROM questions
        ORDER BY similarity ASC
        LIMIT %s;
        """

        cursor.execute(search_query, (np.array(query_embedding, dtype=np.float32).tolist(), top_k))
        results = cursor.fetchall()
        
        cursor.close()
        conn.close()

        logger.info(f"Found {len(results)} similar questions.")
        return results
    except Exception as e:
        logger.error(f"Error retrieving similar questions: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/ask/")
def ask_llm(request: AskRequest):
    logger.info(f"Asking LLM: {request.prompt}")

    try:
        response = query_ollama(request.prompt, request.model)
        logger.info("LLM Response received successfully.")
        return {"response": response}
    except Exception as e:
        logger.error(f"Error querying LLM: {e}")
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

@app.post("/answer/")
def store_answer(request: AnswerRequest):
    return save_answer_to_db(request.question_id, request.answer)

@app.get("/answers/{question_id}")
def get_answers_for_question(question_id: UUID):
    logger.info(f"Retrieving answers for question ID: {question_id}")

    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        search_query = """
        SELECT answer_id, answer_text, created_at 
        FROM answers 
        WHERE question_id = %s 
        ORDER BY created_at DESC
        """

        cursor.execute(search_query, (str(question_id),))
        results = cursor.fetchall()

        cursor.close()
        conn.close()

        if not results:
            logger.warning(f"No answers found for question ID: {question_id}")
            raise HTTPException(status_code=404, detail="No answers found for this question.")

        return results

    except Exception as e:
        logger.error(f"Error retrieving answers: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/find-question/")
def find_question(request: AnswerText):
    """
    Finds the most relevant question for a given answer using vector similarity.
    
    :param request: The answer text input.
    :return: The most similar question from the database.
    """
    try:
        # Generate embedding for the answer
        answer_embedding = generate_embedding(request.answer)

        if isinstance(answer_embedding, np.ndarray):
            answer_embedding = answer_embedding.tolist()  # Ensure correct format

        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)  # Use DictCursor

        # Find the closest matching question
        search_query = """
        SELECT question_id, question_text, category, embedding <-> %s::vector AS similarity
        FROM questions
        ORDER BY similarity ASC
        LIMIT 1;
        """
        cursor.execute(search_query, (answer_embedding,))  # Ensure correct format
        result = cursor.fetchone()

        cursor.close()
        conn.close()

        # Handle no matches found
        if not result:
            logger.warning(f"No matching question found for input: {request.answer}")
            raise HTTPException(status_code=404, detail="No matching question found.")

        # Convert similarity score to float (ensures JSON serializability)
        result["similarity"] = float(result["similarity"])

        return result

    except Exception as e:
        logging.error(f"Error sending SMS: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/store-questions/")
def store_questions(request: QuestionBatch):
    """
    Ensures that the provided questions exist in the database.
    If a question does not exist, it is inserted along with its category.
    
    :param request: List of questions with categories (CSV format)
    :return: Summary of inserted and existing questions.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # Fetch existing questions for quick lookup
    cursor.execute("SELECT question_text FROM questions")
    existing_questions = {row["question_text"] for row in cursor.fetchall()}  # Ensures correct indexing

    questions_to_insert = []

    for question_data in request.questions:
        question_text = question_data.question.strip()
        category = question_data.category.strip()

        if question_text not in existing_questions:
            question_id = str(uuid.uuid4())  # Generate unique ID
            embedding = generate_embedding(question_text)  # Compute embedding
            questions_to_insert.append((question_id, question_text, category, embedding))

    # Bulk insert new questions if needed
    if questions_to_insert:
        insert_query = """
        INSERT INTO questions (question_id, question_text, category, embedding) 
        VALUES (%s, %s, %s, %s)
        """
        cursor.executemany(insert_query, questions_to_insert)
        conn.commit()

    cursor.close()
    conn.close()

    return {
        "existing_questions": len(existing_questions),
        "inserted_questions": len(questions_to_insert),
        "total_questions": len(existing_questions) + len(questions_to_insert)
    }

@app.post("/send_sms")
def send_sms(request: SMSRequest):
    """
    Endpoint to send an SMS using TextBelt API.
    """
    try:
        response = textbelt.send_sms(request.phone, request.message, "https://question-answer.jolomo.io/handleSmsReply")
        return response
    except Exception as e:
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

@app.post("/send_sms_random_question")
def send_sms_random_question(request: SMSRequest):
    """
    Fetches a random question from the database and sends it via SMS.
    """
    return send_random_question_via_sms(request.phone)

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
        "generate a thoughtful follow-up question that; encourages deeper reflection, learns more about their family, learns more about past experiances or opinions, or exploration of related ideas. "
        "Ensure the question remains open-ended, engaging, and contextually relevant to the conversation. "
        "The goal of this Q & A system is to get to know a loved one more and to learn and preserve their prospective."
        "If the response contains sensitive, problematic, or inappropriate content, do not engage or reinforce it; instead, shift the discussion towards a constructive and neutral topic."
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

@app.post("/handleSmsReply")
async def handle_sms_reply(request: Request):
    """
    Handles incoming SMS replies sent by TextBelt's webhook.
    """
    try:
        data = await request.json()  # Extract JSON payload
        logging.info(f"Received webhook data: {data}")

        # Process webhook data
        # response = textbelt.process_webhook_data(data)
       # data = textbelt.process_webhook_data(data)

        if not data:
            return {"success": False, "error": "Invalid request, no data received"}

        phone_number = data.get("fromNumber")
        message = data.get("text")
        webhookData = data.get("data")

        # if not phone_number or not message:
        #     return {"success": False, "error": "Missing required fields"}

        logging.info(f"Received SMS reply from {phone_number}: {message} : {webhookData}")

        # If user requests a new question, send a new random question
        if message.lower().strip() == "new question":
            return send_random_question_via_sms(phone_number)
        else:
            answer = save_answer_to_db(webhookData, message)
            logging.info(f"Answer: {answer}")
            previous_question = get_question_by_id(webhookData)
            question = generate_new_question(previous_question.get("question_text"), message, answer['answer_id'])
            return textbelt.send_sms(
                phone_number=phone_number,
                message=question.get("question_text"),
                webhook_url="https://question-answer.jolomo.io/handleSmsReply",
                webhook_data=question.get("question_id")
            )

    except Exception as e:
        logging.error(f"Error processing SMS webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    logger.info("Starting FastAPI server on http://0.0.0.0:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
