# Question-Answering System with FastAPI, PostgreSQL, and Docker

## Overview

This project is a question-answering system built with **FastAPI**, **PostgreSQL with pgvector**, **pgAdmin**, and **Docker**. It allows users to store questions, retrieve similar questions using vector embeddings, generate follow-up questions with an LLM, and send questions/answers via SMS using the **TextBelt API**.

## Features

- **FastAPI**: Backend API with endpoints for storing questions, retrieving answers, querying LLM, and sending SMS.  
- **PostgreSQL with pgvector**: Vector search for similar questions.  
- **pgAdmin**: Database administration through a web interface.  
- **Docker**: Easy containerization and deployment.  
- **TextBelt API**: SMS integration for interactive Q&A.  
- **MQTT Integration**: Connect IoT devices to receive and answer questions.
- **OpenAI API** (Optional): Enhanced question generation with conversation history.

---

## 🚀 Quick Start Guide

### Prerequisites

- **Docker** and **Docker Compose** installed  
- **Python 3.10+** (if running locally without Docker)

### 1️⃣ Clone the Repository

```bash
git clone https://github.com/JoeLorenzoMontano/question-answering-system.git
cd question-answering-system
```

### 2️⃣ Configure Environment Variables

Create a `.env` file in the root directory and set your environment variables:

```env
# PostgreSQL
POSTGRES_USER=user
POSTGRES_PASSWORD=password
POSTGRES_DB=ollama_db

# PGAdmin
PGADMIN_DEFAULT_EMAIL=admin@example.com
PGADMIN_DEFAULT_PASSWORD=adminpassword

# Backend
DATABASE_URL=postgresql://user:password@postgres:5432/ollama_db
OPEN_WEBUI_API_URL=http://your-server-ip:3001
OPEN_WEBUI_API_KEY=your-open-webui-api-key
TEXTBELT_API_KEY=your-textbelt-api-key

# MQTT Broker
MQTT_BROKER_HOST=mqtt-broker
MQTT_BROKER_PORT=1883

# Optional: OpenAI Integration
USE_OPENAI=false
OPENAI_API_KEY=your-openai-api-key
```

### 3️⃣ Start the Services with Docker Compose

```bash
docker-compose up --build
```

- The **FastAPI backend** will be accessible at: `http://localhost:8001`
- **pgAdmin** will be accessible at: `http://localhost:5050`
  - Login: `admin@example.com`
  - Password: `adminpassword`
- **MQTT Broker** will be accessible at: `localhost:1883` (MQTT) and `localhost:9001` (WebSockets)

---

## 🛠️ Project Structure

```plaintext
.
├── backend/
│   ├── main.py                # FastAPI application
│   ├── database.py            # Database connection handler
│   ├── embeddings.py          # Vector embedding handler
│   ├── open_webui_api.py      # API handler for querying LLM
│   ├── openai_api.py          # OpenAI API integration (optional)
│   ├── mqtt_service.py        # MQTT service for IoT device integration
│   ├── family_endpoints.py    # Family management endpoints
│   ├── textbelt_api.py        # API handler for TextBelt
│   └── migrations/            # Database migrations
├── mqtt/
│   ├── config/                # MQTT broker configuration
│   ├── data/                  # MQTT broker data
│   └── log/                   # MQTT broker logs
├── examples/
│   ├── mqtt_client.py         # Example Python MQTT client
│   └── esp32_mqtt_client/     # Example ESP32 MQTT client
├── docker-compose.yml         # Docker Compose file
└── Dockerfile                 # Dockerfile for FastAPI backend
```

---

## 📡 API Endpoints

### 💾 Store a Question
- **Endpoint:** `POST /store/`
- **Request Body:**
  ```json
  {
    "question": "What is the capital of France?",
    "category": "geography"
  }
  ```
- **Response:**
  ```json
  {
    "question_id": "550e8400-e29b-41d4-a716-446655440000"
  }
  ```

---

### 📊 Find Similar Questions
- **Endpoint:** `GET /similar/`
- **Query Parameters:** `query`, `top_k`
- **Example:** `GET /similar/?query=capital of France&top_k=5`
- **Response:**
  ```json
  [
    {
      "question_id": "123",
      "question_text": "What is the capital city of France?",
      "similarity": 0.01
    }
  ]
  ```

---

### 💬 Ask the LLM
- **Endpoint:** `POST /ask/`
- **Request Body:**
  ```json
  {
    "prompt": "What is the capital of Italy?",
    "model": "deepseek-r1:7b"
  }
  ```
- **Response:**
  ```json
  {
    "response": "The capital of Italy is Rome."
  }
  ```

---

### 📝 Submit an Answer
- **Endpoint:** `POST /answer/`
- **Request Body:**
  ```json
  {
    "question_id": "550e8400-e29b-41d4-a716-446655440000",
    "answer": "The capital of France is Paris."
  }
  ```
- **Response:**
  ```json
  {
    "answer_id": "660e950f-cb32-4c2a-a07d-d36dcdc2617b",
    "message": "Answer stored successfully."
  }
  ```

---

### 📱 Send SMS with TextBelt
- **Endpoint:** `POST /send_sms/`
- **Request Body:**
  ```json
  {
    "phone": "+1234567890",
    "message": "What is the capital of Spain?"
  }
  ```
- **Response:**
  ```json
  {
    "success": true,
    "message": "SMS sent successfully."
  }
  ```

---

## 📂 Database Schema Overview

- **Table `questions`**  
  - `question_id`: UUID (Primary Key)  
  - `question_text`: TEXT  
  - `category`: TEXT  
  - `embedding`: VECTOR  
  - `answer_seed`: UUID

- **Table `answers`**  
  - `answer_id`: UUID (Primary Key)  
  - `question_id`: UUID (Foreign Key)  
  - `answer_text`: TEXT  
  - `embedding`: VECTOR  
  - `created_at`: TIMESTAMP  

---

## 🧪 Running Tests (Optional)

If running locally with Python:

```bash
pip install -r requirements.txt
pytest tests/
```

---

## 🛑 Stopping the Services

```bash
docker-compose down
```

---

## 📝 Notes

- **OpenWebUI URL:** Replace `OPEN_WEBUI_API_URL` with your server's actual URL.  
- **API Keys:** Keep your `OPEN_WEBUI_API_KEY`, `TEXTBELT_API_KEY`, and `OPENAI_API_KEY` secure.
- **Docker Volumes:** Data persists between restarts via Docker volumes.
- **OpenAI Integration:** Set `USE_OPENAI=true` in your `.env` file to enable OpenAI for enhanced question generation with conversation history.
- **MQTT Integration:** See the `examples/` directory for sample MQTT clients that connect to the system.

---

## 🌐 MQTT Integration

The system includes an MQTT broker for IoT device integration, allowing devices to receive and answer questions.

### MQTT Topics

- `scribe/clients/{device_id}/status` - Device status messages
- `scribe/families/{family_id}/questions` - Questions for the family
- `scribe/families/{family_id}/answers` - Answers to questions
- `scribe/families/{family_id}/notifications` - Notifications for the family
- `scribe/families/{family_id}/devices/{device_id}/#` - Device-specific messages

### MQTT API Endpoints

- `GET /api/families/{family_id}/mqtt` - Get MQTT configuration for a family
- `PUT /api/families/{family_id}/mqtt` - Update MQTT configuration
- `POST /api/families/{family_id}/mqtt/devices` - Add a new allowed MQTT device
- `DELETE /api/families/{family_id}/mqtt/devices/{device_id}` - Remove an allowed MQTT device
- `GET /api/families/{family_id}/mqtt/connected-devices` - Get list of connected devices
- `POST /api/families/{family_id}/mqtt/send-message` - Send a message to devices

---

## ❤️ Contributing

Contributions are welcome! Please open an issue or submit a pull request for improvements.

---

## 📄 License

Contact me for information: JoeLorenzoMontano@gmail.com

---

## 🙌 Acknowledgements

- [FastAPI](https://fastapi.tiangolo.com)  
- [PostgreSQL](https://www.postgresql.org)  
- [pgvector](https://github.com/pgvector/pgvector)  
- [TextBelt](https://textbelt.com)  
- [Eclipse Mosquitto](https://mosquitto.org)
- [OpenAI](https://openai.com)

---

**✨ Built with ❤️ and FastAPI!** 🚀💡