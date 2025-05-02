/*
 * ESP32 MQTT Client for Question Answer Scribe
 * 
 * This example demonstrates how to connect an ESP32 device to the 
 * Question Answer Scribe system using MQTT.
 * 
 * Dependencies:
 * - PubSubClient: https://github.com/knolleary/pubsubclient
 * - ArduinoJson: https://arduinojson.org/
 */

#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>

// WiFi credentials
const char* ssid = "YOUR_WIFI_SSID";      // Replace with your WiFi SSID
const char* password = "YOUR_WIFI_PASSWORD"; // Replace with your WiFi password

// MQTT broker settings
const char* mqtt_broker = "mqtt-broker";  // Replace with your MQTT broker address
const int mqtt_port = 1883;
const char* mqtt_username = "mqtt_username"; // Replace with your MQTT username
const char* mqtt_password = "mqtt_password"; // Replace with your MQTT password

// Scribe settings
const char* family_id = "YOUR_FAMILY_ID";  // Replace with your family ID
const char* device_name = "ESP32 Client";
const char* device_type = "esp32";
String device_id = "esp32-"; // Will be appended with MAC address

// MQTT topics
String status_topic;
String questions_topic;
String answers_topic;
String notifications_topic;
String device_topic;
String request_topic;

// MQTT client
WiFiClient espClient;
PubSubClient client(espClient);

// Buffer for JSON serialization
char mqttBuffer[512];

// Variables to store the current question
String current_question_id = "";
String current_question_text = "";

// Forward declarations
void connect_mqtt();
void publish_status(const char* status);
void publish_answer(const String& question_id, const String& answer_text);
void request_question();

void setup() {
  // Initialize serial communication
  Serial.begin(115200);
  Serial.println("ESP32 MQTT client for Question Answer Scribe");
  
  // Generate device ID using MAC address
  uint64_t mac = ESP.getEfuseMac();
  char mac_str[13];
  sprintf(mac_str, "%04X%08X", (uint16_t)(mac >> 32), (uint32_t)mac);
  device_id += mac_str;
  
  Serial.print("Device ID: ");
  Serial.println(device_id);
  
  // Set up WiFi
  WiFi.begin(ssid, password);
  Serial.print("Connecting to WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nWiFi connected");
  Serial.print("IP address: ");
  Serial.println(WiFi.localIP());
  
  // Set up MQTT topics
  status_topic = "scribe/clients/" + device_id + "/status";
  questions_topic = "scribe/families/" + String(family_id) + "/questions";
  answers_topic = "scribe/families/" + String(family_id) + "/answers";
  notifications_topic = "scribe/families/" + String(family_id) + "/notifications";
  device_topic = "scribe/families/" + String(family_id) + "/devices/" + device_id + "/#";
  request_topic = "scribe/families/" + String(family_id) + "/request";
  
  // Set up MQTT client
  client.setServer(mqtt_broker, mqtt_port);
  client.setCallback(mqtt_callback);
  client.setBufferSize(512); // Increase the buffer size for larger messages
  
  // Connect to MQTT broker
  connect_mqtt();
}

void loop() {
  // Maintain MQTT connection
  if (!client.connected()) {
    connect_mqtt();
  }
  client.loop();
  
  // Check for user input from serial console
  if (Serial.available() > 0) {
    String input = Serial.readStringUntil('\n');
    input.trim();
    
    if (input.startsWith("request")) {
      // Request a new question
      request_question();
    }
    else if (input.startsWith("answer:") && current_question_id.length() > 0) {
      // Send an answer to the current question
      String answer = input.substring(7);
      answer.trim();
      publish_answer(current_question_id, answer);
      current_question_id = "";
      current_question_text = "";
    }
    else if (input == "status") {
      // Publish status
      publish_status("connected");
    }
    else {
      Serial.println("Commands:");
      Serial.println("  request - Request a new question");
      Serial.println("  answer:<text> - Answer the current question");
      Serial.println("  status - Publish status");
    }
  }
  
  // Add any other logic you need here
  
  delay(100);
}

void connect_mqtt() {
  // Connect to MQTT broker
  Serial.print("Connecting to MQTT broker...");
  
  // Create a client ID based on device ID
  String clientId = "esp32-scribe-" + device_id;
  
  // Connect with authentication
  if (client.connect(clientId.c_str(), mqtt_username, mqtt_password)) {
    Serial.println("connected");
    
    // Subscribe to topics
    client.subscribe(questions_topic.c_str());
    client.subscribe(notifications_topic.c_str());
    client.subscribe(device_topic.c_str());
    
    // Publish connected status
    publish_status("connected");
  } else {
    Serial.print("failed, rc=");
    Serial.print(client.state());
    Serial.println(" trying again in 5 seconds");
    // Wait 5 seconds before retrying
    delay(5000);
  }
}

void mqtt_callback(char* topic, byte* payload, unsigned int length) {
  // Handle received messages
  Serial.print("Message received on topic: ");
  Serial.println(topic);
  
  // Create a temporary buffer for the payload
  char buffer[length + 1];
  memcpy(buffer, payload, length);
  buffer[length] = '\0';
  
  // Parse the JSON payload
  DynamicJsonDocument doc(512);
  DeserializationError error = deserializeJson(doc, buffer);
  
  if (error) {
    Serial.print("JSON parsing failed: ");
    Serial.println(error.c_str());
    return;
  }
  
  String topic_str = String(topic);
  
  // Handle questions
  if (topic_str == questions_topic) {
    current_question_id = doc["question_id"].as<String>();
    current_question_text = doc["content"].as<String>();
    
    Serial.println("New question received:");
    Serial.println(current_question_text);
    Serial.println("Type 'answer:<your answer>' to respond");
  }
  // Handle notifications
  else if (topic_str == notifications_topic) {
    String content = doc["content"].as<String>();
    Serial.println("Notification received:");
    Serial.println(content);
  }
  // Handle device-specific messages
  else if (topic_str.startsWith(device_topic.substring(0, device_topic.length() - 2))) {
    String content = doc["content"].as<String>();
    String type = doc["type"].as<String>();
    
    Serial.print("Device message received (");
    Serial.print(type);
    Serial.println("):");
    Serial.println(content);
  }
}

void publish_status(const char* status) {
  // Publish device status
  DynamicJsonDocument doc(256);
  doc["status"] = status;
  doc["device_name"] = device_name;
  doc["device_type"] = device_type;
  doc["device_id"] = device_id;
  doc["family_id"] = family_id;
  doc["timestamp"] = millis() / 1000;
  
  size_t n = serializeJson(doc, mqttBuffer);
  client.publish(status_topic.c_str(), mqttBuffer, true); // retained message
  
  Serial.print("Published status: ");
  Serial.println(status);
}

void publish_answer(const String& question_id, const String& answer_text) {
  // Publish an answer to a question
  DynamicJsonDocument doc(512);
  doc["question_id"] = question_id;
  doc["answer"] = answer_text;
  doc["device_id"] = device_id;
  doc["device_name"] = device_name;
  doc["timestamp"] = millis() / 1000;
  
  size_t n = serializeJson(doc, mqttBuffer);
  client.publish(answers_topic.c_str(), mqttBuffer);
  
  Serial.println("Answer published");
}

void request_question() {
  // Request a new question
  DynamicJsonDocument doc(256);
  doc["type"] = "question_request";
  doc["device_id"] = device_id;
  doc["device_name"] = device_name;
  doc["timestamp"] = millis() / 1000;
  
  size_t n = serializeJson(doc, mqttBuffer);
  client.publish(request_topic.c_str(), mqttBuffer);
  
  Serial.println("Question requested");
}