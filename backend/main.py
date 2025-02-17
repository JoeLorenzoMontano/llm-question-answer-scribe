import logging
import uvicorn
from fastapi import FastAPI, HTTPException, Request
import os
from textbelt_api import TextBeltAPI
from request_models import QuestionRequest, AnswerRequest, AskRequest, QuestionBatch, AnswerText, SMSRequest
from helpers import store_and_return_question, save_answer_to_db, get_random_question, send_random_question_via_sms, strip_think_tags, generate_new_question, get_question_by_id, generate_verification_code, generate_verification_code


TEXTBELT_API_KEY = os.getenv("TEXTBELT_API_KEY")
ENVIRONMENT = os.getenv("ENVIRONMENT", "production")

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

@app.post("/register/")
def register_user(request: SMSRequest):
    phone_number = request.phone
    verification_code = generate_verification_code()

    try:
        response = textbelt.send_sms(
            phone_number=phone_number,
            message=f"Your verification code is {verification_code}",
            webhook_url="https://question-answer.jolomo.io/verify",
            webhook_data=verification_code
        )
        return {"message": "Verification code sent"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/verify/")
async def verify_code(request: Request):
    try:
        data = await request.json()
        received_code = data.get("text").strip()
        expected_code = data.get("data")

        if received_code == expected_code:
            phone_number = data.get("fromNumber")
            return send_random_question_via_sms(phone_number)
        else:
            raise HTTPException(status_code=400, detail="Invalid verification code")

    except Exception as e:
        logging.error(f"Error verifying code: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/answer/")
def store_answer(request: AnswerRequest):
    return save_answer_to_db(request.question_id, request.answer)

@app.post("/send_sms_random_question")
def send_sms_random_question(request: SMSRequest):
    """
    Fetches a random question from the database and sends it via SMS.
    """
    return send_random_question_via_sms(request.phone)

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

# Conditionally include dev endpoints
if ENVIRONMENT in ["development", "testing"]:
    from dev_endpoints import app as dev_app
    app.mount("/dev", dev_app)

if __name__ == "__main__":
    logger.info("Starting FastAPI server on http://0.0.0.0:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
