import logging
from fastapi import FastAPI, HTTPException, Request
from textbelt_api import TextBeltAPI
from database import get_db_connection
import os
import uuid
from uuid import UUID
from open_webui_api import query_ollama, send_assistant_message
from embeddings import generate_embedding
import psycopg2.extras  # Needed for dictionary cursorimport os
from request_models import QuestionRequest, AnswerRequest, AskRequest, QuestionBatch, AnswerText, SMSRequest
from helpers import send_random_question_via_sms, save_answer_to_db, get_question_by_id, generate_new_question

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