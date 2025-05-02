from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

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
    family_id: Optional[str] = None
    
class ChatHistoryRequest(BaseModel):
    phone: str
    
class VerifyCodeRequest(BaseModel):
    phone: str
    code: str
    
class FamilyCreationRequest(BaseModel):
    family_name: str
    user_id: Optional[str] = None
    
class FamilyMemberAddRequest(BaseModel):
    phone_number: str

class MQTTDeviceInfo(BaseModel):
    device_name: str
    device_type: str = Field(default="generic", description="Type of device (e.g., 'arduino', 'esp32', 'mobile')")
    device_id: Optional[str] = None
    
class MQTTConfigRequest(BaseModel):
    enabled: bool = Field(default=True, description="Whether MQTT is enabled for this family")
    mqtt_username: Optional[str] = None
    mqtt_password: Optional[str] = None
    topic_prefix: Optional[str] = None
    allowed_devices: Optional[List[MQTTDeviceInfo]] = None
    
class MQTTMessageRequest(BaseModel):
    family_id: str
    device_id: Optional[str] = None
    message_type: str = Field(default="notification", description="Type of message (e.g., 'notification', 'question')")
    content: str
    metadata: Optional[Dict[str, Any]] = None