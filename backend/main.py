import logging
import uvicorn
from fastapi import FastAPI, HTTPException, Request, Form, Depends
import os
from database import add_new_user, verify_user, get_user_chat_history, generate_auth_code
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from textbelt_api import TextBeltAPI
from request_models import QuestionRequest, AnswerRequest, AskRequest, QuestionBatch, AnswerText, SMSRequest, RegistrationRequest, ChatHistoryRequest, VerifyCodeRequest
from helpers import store_and_return_question, save_answer_to_db, get_random_question, send_random_question_via_sms, strip_think_tags, generate_new_question, get_question_by_id, generate_verification_code


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

# Configure Jinja2 templates - using absolute path to prevent errors
import os
current_dir = os.path.dirname(os.path.abspath(__file__))
templates_dir = os.path.join(current_dir, "templates")
templates = Jinja2Templates(directory=templates_dir)
logging.info(f"Using templates directory: {templates_dir}")

# Mount static files if needed
try:
    static_dir = os.path.join(current_dir, "static")
    if not os.path.exists(static_dir):
        os.makedirs(static_dir)
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
    logging.info(f"Mounted static directory: {static_dir}")
except Exception as e:
    logging.warning(f"Could not mount static directory: {e}")

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
            .navbar {
                background-color: #333;
                overflow: hidden;
                border-radius: 5px;
                margin-bottom: 20px;
            }
            .navbar a {
                float: left;
                display: block;
                color: white;
                text-align: center;
                padding: 14px 16px;
                text-decoration: none;
            }
            .navbar a:hover {
                background-color: #ddd;
                color: black;
            }
            .navbar a.active {
                background-color: #28a745;
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

# Chat history endpoints
@app.get("/chat-history", response_class=HTMLResponse)
async def chat_history(request: Request):
    """
    Display the chat history page - initial view with phone number entry form
    """
    return templates.TemplateResponse(
        "chat_history.html", 
        {"request": request, "phone_verified": False, "verification_sent": False}
    )

@app.get("/mqtt-dashboard", response_class=HTMLResponse)
async def mqtt_dashboard():
    """
    Display the MQTT dashboard
    """
    # Get the current directory path
    current_dir = os.path.dirname(os.path.abspath(__file__))
    # Construct the path to the MQTT dashboard HTML file
    mqtt_dashboard_path = os.path.join(current_dir, "static", "mqtt-client.html")
    return FileResponse(mqtt_dashboard_path)

@app.post("/request-chat-code")
async def request_chat_code(request: Request, phone: str = Form(...)):
    """
    Handle request for a verification code to view chat history
    """
    try:
        # Add debug logging
        logging.info(f"Received request for chat code with phone: {phone}")
        
        # Clean phone number format - only keep digits
        clean_phone = ''.join(char for char in phone if char.isdigit())
        logging.info(f"Cleaned phone number: {clean_phone}")
        
        # Generate verification code
        verification_code = generate_auth_code(clean_phone)
        logging.info(f"Generated verification code response: {verification_code}")
        
        if isinstance(verification_code, dict) and "error" in verification_code:
            # Handle error case
            logging.error(f"Error generating auth code: {verification_code['error']}")
            return templates.TemplateResponse(
                "chat_history.html", 
                {
                    "request": request, 
                    "phone_verified": False, 
                    "verification_sent": False,
                    "error": verification_code["error"]
                }
            )
        
        # Log before sending SMS
        logging.info(f"Sending verification code via SMS to {clean_phone}")
        
        # Send the verification code via SMS
        response = textbelt.send_sms(
            phone_number=clean_phone,
            message=f"Your chat history verification code is: {verification_code}"
        )
        
        logging.info(f"SMS send response: {response}")
        
        if not response.get("success", False):
            logging.error(f"Failed to send SMS: {response}")
            return templates.TemplateResponse(
                "chat_history.html", 
                {
                    "request": request, 
                    "phone_verified": False, 
                    "verification_sent": False,
                    "error": "Failed to send verification code. Please try again."
                }
            )
        
        # Show verification code entry form
        logging.info(f"Successfully sent verification code, showing code entry form")
        return templates.TemplateResponse(
            "chat_history.html", 
            {
                "request": request, 
                "phone_verified": False, 
                "verification_sent": True,
                "phone_number": clean_phone
            }
        )
        
    except Exception as e:
        logging.error(f"Error requesting chat code: {e}")
        return templates.TemplateResponse(
            "chat_history.html", 
            {
                "request": request, 
                "phone_verified": False, 
                "verification_sent": False,
                "error": "An unexpected error occurred. Please try again."
            }
        )

@app.post("/verify-chat-code")
async def verify_chat_code(request: Request, phone: str = Form(...), code: str = Form(...)):
    """
    Verify the code and show chat history if valid
    """
    try:
        # Clean phone number - only keep digits
        clean_phone = ''.join(char for char in phone if char.isdigit())
        
        # Verify the code
        is_valid = verify_user(clean_phone, code)
        
        if not is_valid:
            return templates.TemplateResponse(
                "chat_history.html", 
                {
                    "request": request, 
                    "phone_verified": False, 
                    "verification_sent": True,
                    "phone_number": clean_phone,
                    "error": "Invalid verification code. Please try again."
                }
            )
        
        # Get chat history for this user
        chat_history = get_user_chat_history(clean_phone)
        
        if isinstance(chat_history, dict) and "error" in chat_history:
            return templates.TemplateResponse(
                "chat_history.html", 
                {
                    "request": request, 
                    "phone_verified": False, 
                    "verification_sent": False,
                    "error": chat_history["error"]
                }
            )
        
        # Format dates for display
        import datetime
        
        for message in chat_history:
            if message["timestamp"]:
                # Parse ISO format timestamp
                try:
                    dt = datetime.datetime.fromisoformat(message["timestamp"])
                    # Format it in a more user-friendly way
                    message["timestamp"] = dt.strftime("%b %d, %Y at %I:%M %p")
                except (ValueError, TypeError):
                    message["timestamp"] = "Unknown time"
        
        # Show chat history
        return templates.TemplateResponse(
            "chat_history.html", 
            {
                "request": request, 
                "phone_verified": True, 
                "phone_number": clean_phone,
                "chat_history": chat_history
            }
        )
        
    except Exception as e:
        logging.error(f"Error verifying chat code: {e}")
        return templates.TemplateResponse(
            "chat_history.html", 
            {
                "request": request, 
                "phone_verified": False, 
                "verification_sent": False,
                "error": "An unexpected error occurred. Please try again."
            }
        )

# Include family management endpoints
from family_endpoints import router as family_router
app.include_router(family_router, prefix="/api")

# Conditionally include dev endpoints
if ENVIRONMENT in ["development", "testing"]:
    from dev_endpoints import app as dev_app
    app.mount("/dev", dev_app)

@app.on_event("startup")
async def startup_event():
    """Run database migrations and initialize MQTT service on app startup"""
    # Initialize MQTT service - do this first since it has retry logic
    logger.info("Initializing MQTT service...")
    try:
        from mqtt_service import get_mqtt_service
        mqtt_service = get_mqtt_service()
        logger.info("MQTT service initialization started (will retry connections in background)")
    except Exception as e:
        logger.error(f"Failed to initialize MQTT service: {e}")
    
    # Run database migrations with retry logic
    logger.info("Running database migrations...")
    max_attempts = 5
    attempt = 0
    while attempt < max_attempts:
        try:
            from migrations.migrate import run_migrations
            success = run_migrations()
            if success:
                logger.info("Database migrations completed successfully.")
                break
            else:
                logger.error("Database migrations failed. Will retry...")
        except Exception as e:
            attempt += 1
            if attempt >= max_attempts:
                logger.error(f"Failed to run database migrations after {max_attempts} attempts: {e}")
                break
            
            # Wait with exponential backoff
            wait_time = 2 ** attempt
            logger.info(f"Database connection failed. Retrying in {wait_time} seconds... (Attempt {attempt}/{max_attempts})")
            import time
            time.sleep(wait_time)

if __name__ == "__main__":
    logger.info("Starting FastAPI server on http://0.0.0.0:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
