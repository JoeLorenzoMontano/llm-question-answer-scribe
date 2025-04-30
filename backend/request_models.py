from pydantic import BaseModel
from typing import List, Optional

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

class RegistrationRequest(BaseModel):
    username: str
    password: str
    phone: str
    
class ChatHistoryRequest(BaseModel):
    phone: str
    
class VerifyCodeRequest(BaseModel):
    phone: str
    code: str