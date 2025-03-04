import logging
import uvicorn
from fastapi import FastAPI, HTTPException, Request
import os
from database import add_new_user, verify_user
from fastapi.responses import HTMLResponse
from textbelt_api import TextBeltAPI
from request_models import QuestionRequest, AnswerRequest, AskRequest, QuestionBatch, AnswerText, SMSRequest, RegistrationRequest
from helpers import store_and_return_question, save_answer_to_db, get_random_question, send_random_question_via_sms, strip_think_tags, generate_new_question, get_question_by_id, generate_verification_code, generate_verification_code


TEXTBELT_API_KEY = os.getenv("TEXTBELT_API_KEY")
ENVIRONMENT = os.getenv("ENVIRONMENT", "production")

# Store phone numbers & codes in memory (replace with DB in production)
verification_codes = {}

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

@app.get("/", response_class=HTMLResponse)
async def index():
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Alpha Test Registration</title>
        <style>
            body {
                font-family: Arial, sans-serif;
                text-align: center;
                padding: 20px;
            }
            .container {
                max-width: 500px;
                margin: auto;
                padding: 20px;
                border: 1px solid #ddd;
                border-radius: 10px;
                background-color: #f9f9f9;
            }
            input, button {
                margin-top: 10px;
                padding: 10px;
                width: 80%;
                font-size: 16px;
            }
            button {
                background-color: #28a745;
                color: white;
                border: none;
                cursor: pointer;
            }
            button:hover {
                background-color: #218838;
            }
            .message {
                margin-top: 10px;
                font-weight: bold;
            }
            #verification-box {
                display: none;
            }
        </style>
        <script>
            function validateForm(event) {
                event.preventDefault();

                let username = document.getElementById("username").value;
                let password = document.getElementById("password").value;
                let confirmPassword = document.getElementById("confirm_password").value;
                let phoneNumber = document.getElementById("phone_number").value;
                let messageDiv = document.getElementById("password-error");

                // Username validation (No spaces, only letters/numbers/_/.)
                let usernameRegex = /^[a-zA-Z0-9._]{3,30}$/;
                if (!usernameRegex.test(username)) {
                    messageDiv.innerText = "Invalid username. Only letters, numbers, '_', and '.' allowed (3-30 chars).";
                    messageDiv.style.display = "block";
                    return;
                }

                // Password validation (No spaces, at least 8 chars, 1 uppercase, 1 lowercase, 1 number, 1 special char)
                let passwordRegex = /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*])[A-Za-z\d!@#$%^&*]{8,}$/;
                if (!passwordRegex.test(password)) {
                    messageDiv.innerText = "Password must be at least 8 characters, include 1 uppercase, 1 lowercase, 1 number, and 1 special character.";
                    messageDiv.style.display = "block";
                    return;
                }

                // Confirm password match
                if (password !== confirmPassword) {
                    messageDiv.innerText = "Passwords do not match.";
                    messageDiv.style.display = "block";
                    return;
                }

                messageDiv.style.display = "none";

                // Submit form if all validations pass
                registerUser();
            }

            async function registerUser() {
                event.preventDefault();
                
                let username = document.getElementById('username').value;
                let password = document.getElementById('password').value;
                let phoneNumber = document.getElementById('phone_number').value;
                let messageDiv = document.getElementById('password-error');

                try {
                    let response = await fetch("/register/", {
                        method: "POST",
                        headers: {
                            "Content-Type": "application/json"
                        },
                        body: JSON.stringify({
                            username: username,
                            password: password,
                            phone: phoneNumber
                        })
                    });

                    let result = await response.json();

                    messageDiv.innerText = result.message || "Verification code sent!";

                    document.getElementById("verification-box").style.display = "block";
                    document.getElementById("username").disabled = true;
                    document.getElementById("password").disabled = true;
                    document.getElementById("confirm_password").disabled = true;
                    document.getElementById("phone_number").disabled = true;
                    document.getElementById("register-btn").disabled = true;
                    document.getElementById("hidden-phone").value = phoneNumber;
                } catch (error) {
                    messageDiv.innerText = "Error sending verification code.";
                }
            }

            async function verifyCode(event) {
                event.preventDefault();
                let phoneNumber = document.getElementById("hidden-phone").value;
                let code = document.getElementById("verification_code").value;
                let messageDiv = document.getElementById("verify-message");

                if (!code) {
                    messageDiv.innerText = "Please enter the verification code.";
                    return;
                }

                messageDiv.innerText = "Verifying code...";

                try {
                    let response = await fetch("/verify/", {
                        method: "POST",
                        headers: {
                            "Content-Type": "application/json"
                        },
                        body: JSON.stringify({
                            fromNumber: phoneNumber,
                            code: code,
                        })
                    });

                    if (!response.ok) {
                        // Handle HTTP errors properly
                        let errorData = await response.json();
                        throw new Error(errorData.detail || "Verification failed.");
                    }

                    document.getElementById("verify_button").disabled = true;
                    let result = await response.json();
                    messageDiv.innerText = result.message || "Verification successful!";

                } catch (error) {
                    messageDiv.innerText = error.message;
                }
            }

            function formatPhoneNumber(input) {
                let value = input.value.replace(/\D/g, ""); // Remove all non-numeric characters

                if (value.length > 10) {
                    value = value.substring(0, 10); // Limit input to 10 digits
                }

                // Format as (555) 555-5555
                if (value.length > 6) {
                    input.value = `(${value.substring(0, 3)}) ${value.substring(3, 6)}-${value.substring(6)}`;
                } else if (value.length > 3) {
                    input.value = `(${value.substring(0, 3)}) ${value.substring(3)}`;
                } else if (value.length > 0) {
                    input.value = `(${value}`;
                }
            }

        </script>
    </head>
    <body>
        <div class="container">
            <h2>Welcome to the Alpha Test</h2>
            <p>We're testing a new AI-driven family scribe system. Enter your phone number below to register and receive a verification code.</p>
            
            <form onsubmit="validateForm(event)">
                <input type="text" id="username" placeholder="Username" required>
                <input type="password" id="password" placeholder="Password" required>
                <input type="password" id="confirm_password" placeholder="Confirm Password" required>
                <input type="tel" id="phone_number" placeholder="(555) 555-5555" required maxlength="14" oninput="formatPhoneNumber(this)">
                <br/>
                <p id="password-error" style="color: red; display: none;">Passwords do not match.</p>
                <table style='width: 100%;'>
                    <tr>
                        <td style='width: 50%;'>
                            <button type="submit" id="register-btn">Register</button>
                        </td>
                        <td style='width: 50%;'>
                            <button type="submit" id="resend-btn" disabled>Resend Code</button>
                        </td>
                    </tr>
                </table>
            </form>

            <p class="message" id="message"></p>

            <div id="verification-box">
                <p>Enter the verification code sent to your phone:</p>
                <form onsubmit="verifyCode(event)">
                    <input type="hidden" id="hidden-phone">
                    <input type="text" id="verification_code" placeholder="Enter code" required>
                    <button id="verify_button" type="submit">Verify</button>
                </form>
                <p class="message" id="verify-message"></p>
            </div>
        </div>
    </body>
    </html>
    """

@app.post("/register/")
def register_user(request: RegistrationRequest):
    try:
        verification_code = generate_verification_code()
        if not add_new_user(request, verification_code):
            raise HTTPException(status_code=400, detail="Phone number already registered")

        response = textbelt.send_sms(
            phone_number=request.phone,
            message=f"Your verification code is {verification_code}"
        )
        return {"message": "Verification code sent"}

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))  # Handle invalid username/password errors

    except Exception as e:
        raise HTTPException(status_code=500, detail="An unexpected error occurred")

@app.post("/verify/")
async def verify_code(request: Request):
    try:
        data = await request.json()
        phone_number = data.get("fromNumber")
        received_code = data.get("code").strip()
        if verify_user(phone_number, received_code):
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
