# MQTT Integration Plan for Family Q&A System

This document outlines the plan for adding MQTT support to the family question-answer system, allowing families to integrate with home automation, custom applications, and IoT devices.

## 1. System Architecture

```
┌────────────────┐      ┌─────────────────┐      ┌────────────────┐
│  Family Client │◄────►│  MQTT Broker    │◄────►│  Backend API   │
│  (IoT devices, │      │ (Mosquitto)     │      │ (FastAPI)      │
│   Smart Home)  │      │                 │      │                │
└────────────────┘      └─────────────────┘      └────────────────┘
                                                         │
                                                         ▼
                                                  ┌────────────────┐
                                                  │   Database     │
                                                  │  (PostgreSQL)  │
                                                  └────────────────┘
```

## 2. Database Changes

### Add MQTT Configuration to Families Table

```sql
-- Migration: Add MQTT fields to families table
ALTER TABLE families ADD COLUMN mqtt_enabled BOOLEAN DEFAULT FALSE;
ALTER TABLE families ADD COLUMN mqtt_username VARCHAR(100) UNIQUE;
ALTER TABLE families ADD COLUMN mqtt_password VARCHAR(100);
ALTER TABLE families ADD COLUMN mqtt_topic_prefix VARCHAR(100) UNIQUE;
```

## 3. MQTT Broker Setup

1. **Deploy Mosquitto MQTT Broker**:
   - Set up as a service in Docker Compose
   - Configure authentication and ACLs
   - Set up TLS for secure connections

2. **MQTT Topic Structure**:
   ```
   family/{family_id}/questions        # New questions published here
   family/{family_id}/answers          # New answers published here
   family/{family_id}/ask              # Clients publish here to ask a new question
   family/{family_id}/respond          # Clients publish here to respond to a question
   ```

## 4. Backend Components

### 1. MQTT Service Class

```python
class MQTTService:
    def __init__(self, broker_host, broker_port, client_id):
        self.client = mqtt.Client(client_id)
        self.broker_host = broker_host
        self.broker_port = broker_port
        
    async def connect(self, username=None, password=None):
        # Connect to MQTT broker
        
    async def publish_question(self, family_id, question_data):
        # Publish a new question
        
    async def publish_answer(self, family_id, answer_data):
        # Publish a new answer
        
    async def subscribe_to_family(self, family_id):
        # Subscribe to family topics
        
    async def on_message(self, client, userdata, message):
        # Handle incoming messages
```

### 2. Family MQTT Management Endpoints

```python
@router.post("/families/{family_id}/mqtt/enable")
async def enable_mqtt(family_id: str, request: MQTTEnableRequest):
    # Enable MQTT for a family
    
@router.post("/families/{family_id}/mqtt/disable")
async def disable_mqtt(family_id: str):
    # Disable MQTT for a family
    
@router.get("/families/{family_id}/mqtt/status")
async def get_mqtt_status(family_id: str):
    # Get MQTT status and credentials
```

### 3. MQTT Event Handlers

```python
async def handle_mqtt_question(family_id, message):
    # Process a question submitted via MQTT
    
async def handle_mqtt_answer(family_id, question_id, message):
    # Process an answer submitted via MQTT
```

## 5. Integration with Existing System

1. **Update Question Creation**:
   ```python
   def store_and_return_question(question_text, category, family_id):
       # Store the question in the database
       # ...
       
       # If family has MQTT enabled, publish the question
       if family_mqtt_enabled(family_id):
           mqtt_service.publish_question(family_id, question_data)
       
       return question_data
   ```

2. **Update Answer Storage**:
   ```python
   def save_answer_to_db(question_id, answer_text):
       # Store the answer in the database
       # ...
       
       # Get the family ID for this question
       family_id = get_family_id_for_question(question_id)
       
       # If family has MQTT enabled, publish the answer
       if family_mqtt_enabled(family_id):
           mqtt_service.publish_answer(family_id, answer_data)
       
       return answer_data
   ```

## 6. UI Components

1. **MQTT Configuration Panel**:
   - Toggle to enable/disable MQTT
   - Display MQTT credentials
   - Reset MQTT credentials
   - Test MQTT connection

2. **Documentation Tab**:
   - MQTT broker connection details
   - Topic structure and examples
   - Example code snippets for common clients (Python, JavaScript, Arduino, ESPHome)

## 7. Security Considerations

1. **Authentication**:
   - Generate unique username/password per family
   - Store passwords securely (hashed)

2. **Authorization**:
   - Configure ACLs to restrict each family to their own topics
   - Prevent families from subscribing to other families' topics

3. **Rate Limiting**:
   - Implement rate limiting to prevent abuse
   - Configure maximum message size

4. **Encryption**:
   - Enable TLS for secure connections
   - Provide instructions for secure client setup

## 8. Implementation Phases

### Phase 1: Infrastructure
1. Set up MQTT broker in Docker Compose
2. Add MQTT configuration to families table
3. Implement basic MQTT service

### Phase 2: Core Features
1. Implement family MQTT configuration endpoints
2. Update question/answer storage to publish to MQTT
3. Implement basic MQTT client handler

### Phase 3: UI & Documentation
1. Create MQTT configuration panel in family settings
2. Add documentation for MQTT integration
3. Create example clients

### Phase 4: Security & Testing
1. Implement security best practices
2. Add monitoring and logging
3. Test with various MQTT clients

## 9. Testing Strategy

1. **Unit Tests**:
   - Test MQTT service functions
   - Test family MQTT configuration

2. **Integration Tests**:
   - Test end-to-end flow from question creation to MQTT publication
   - Test receiving messages from MQTT and processing them

3. **Security Tests**:
   - Verify ACLs prevent cross-family access
   - Test authentication requirements

## 10. Example Client Code

### Python MQTT Client

```python
import paho.mqtt.client as mqtt
import json
import time

# Configuration
BROKER_HOST = "mqtt.example.com"
BROKER_PORT = 8883  # TLS port
FAMILY_ID = "your-family-id"
USERNAME = "your-mqtt-username"
PASSWORD = "your-mqtt-password"

# Topic structure
topics = {
    "questions": f"family/{FAMILY_ID}/questions",
    "answers": f"family/{FAMILY_ID}/answers",
    "ask": f"family/{FAMILY_ID}/ask",
    "respond": f"family/{FAMILY_ID}/respond"
}

# Callback when connecting
def on_connect(client, userdata, flags, rc):
    print(f"Connected with result code {rc}")
    # Subscribe to topics
    client.subscribe(topics["questions"])
    client.subscribe(topics["answers"])

# Callback when a message is received
def on_message(client, userdata, msg):
    print(f"Received message on {msg.topic}: {msg.payload.decode()}")
    try:
        # Parse the JSON message
        data = json.loads(msg.payload.decode())
        
        # Handle different message types
        if msg.topic == topics["questions"]:
            print(f"New question: {data['question_text']}")
        elif msg.topic == topics["answers"]:
            print(f"New answer: {data['answer_text']}")
    except Exception as e:
        print(f"Error processing message: {e}")

# Set up the client
client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message

# Set username and password
client.username_pw_set(USERNAME, PASSWORD)

# Connect to the broker
client.connect(BROKER_HOST, BROKER_PORT, 60)

# Start the network loop
client.loop_start()

# Example: Ask a question
def ask_question(question_text):
    payload = json.dumps({
        "question_text": question_text,
        "category": "general"
    })
    client.publish(topics["ask"], payload)

# Example: Respond to a question
def respond_to_question(question_id, answer_text):
    payload = json.dumps({
        "question_id": question_id,
        "answer_text": answer_text
    })
    client.publish(topics["respond"], payload)

# Example usage
ask_question("What is your favorite memory from childhood?")

# Keep the program running to receive messages
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    client.loop_stop()
    client.disconnect()
```

### Arduino/ESP8266/ESP32 MQTT Client Example

```cpp
#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>

// WiFi credentials
const char* ssid = "YourWiFiSSID";
const char* password = "YourWiFiPassword";

// MQTT configuration
const char* mqtt_server = "mqtt.example.com";
const int mqtt_port = 8883;
const char* mqtt_username = "your-mqtt-username";
const char* mqtt_password = "your-mqtt-password";
const char* family_id = "your-family-id";

// MQTT topics
String questions_topic = String("family/") + family_id + "/questions";
String answers_topic = String("family/") + family_id + "/answers";
String ask_topic = String("family/") + family_id + "/ask";
String respond_topic = String("family/") + family_id + "/respond";

// Initialize WiFi and MQTT clients
WiFiClient espClient;
PubSubClient client(espClient);

void setup_wifi() {
  delay(10);
  Serial.println("Connecting to WiFi...");
  
  WiFi.begin(ssid, password);
  
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  
  Serial.println("WiFi connected");
  Serial.println("IP address: ");
  Serial.println(WiFi.localIP());
}

void callback(char* topic, byte* payload, unsigned int length) {
  Serial.print("Message arrived [");
  Serial.print(topic);
  Serial.print("] ");
  
  // Convert payload to string
  String message;
  for (int i = 0; i < length; i++) {
    message += (char)payload[i];
  }
  Serial.println(message);
  
  // Parse JSON
  DynamicJsonDocument doc(1024);
  deserializeJson(doc, message);
  
  // Handle different message types
  if (String(topic) == questions_topic) {
    String questionText = doc["question_text"].as<String>();
    String questionId = doc["question_id"].as<String>();
    Serial.print("New question: ");
    Serial.println(questionText);
    
    // Here you could display the question on an LCD/OLED screen
    // or trigger an LED to indicate a new question
  }
}

void reconnect() {
  while (!client.connected()) {
    Serial.print("Attempting MQTT connection...");
    String clientId = "ESP32Client-";
    clientId += String(random(0xffff), HEX);
    
    if (client.connect(clientId.c_str(), mqtt_username, mqtt_password)) {
      Serial.println("connected");
      
      // Subscribe to topics
      client.subscribe(questions_topic.c_str());
      client.subscribe(answers_topic.c_str());
    } else {
      Serial.print("failed, rc=");
      Serial.print(client.state());
      Serial.println(" try again in 5 seconds");
      delay(5000);
    }
  }
}

void setup() {
  Serial.begin(115200);
  setup_wifi();
  client.setServer(mqtt_server, mqtt_port);
  client.setCallback(callback);
}

void loop() {
  if (!client.connected()) {
    reconnect();
  }
  client.loop();
  
  // Example: Sending an answer when a button is pressed
  if (digitalRead(BUTTON_PIN) == HIGH) {
    String questionId = "last-received-question-id"; // You would store this from the received question
    String answerText = "This is my answer from ESP32";
    
    DynamicJsonDocument doc(1024);
    doc["question_id"] = questionId;
    doc["answer_text"] = answerText;
    
    String payload;
    serializeJson(doc, payload);
    
    client.publish(respond_topic.c_str(), payload.c_str());
    Serial.println("Answer sent!");
    
    delay(1000);  // Debounce
  }
}
```

## 11. Resources

- [Mosquitto MQTT Broker](https://mosquitto.org/)
- [Paho MQTT Python Client](https://pypi.org/project/paho-mqtt/)
- [MQTT.js (JavaScript Client)](https://github.com/mqttjs/MQTT.js)
- [PubSubClient (Arduino)](https://pubsubclient.knolleary.net/)