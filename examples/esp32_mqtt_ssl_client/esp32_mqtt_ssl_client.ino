/*
 * ESP32 MQTT Client with SSL for Question Answer Scribe
 * 
 * This example demonstrates how to connect an ESP32 device to the 
 * Question Answer Scribe system using MQTT over SSL.
 * 
 * Dependencies:
 * - PubSubClient: https://github.com/knolleary/pubsubclient
 * - ArduinoJson: https://arduinojson.org/
 * - WiFiClientSecure from ESP32 core
 */

#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>

// WiFi credentials
const char* ssid = "YOUR_WIFI_SSID";
const char* password = "YOUR_WIFI_PASSWORD";

// MQTT broker settings
const char* mqtt_server = "question-answer.jolomo.io";
const int mqtt_port = 8883; // MQTT over SSL port
const char* mqtt_username = ""; // If authentication is enabled
const char* mqtt_password = ""; // If authentication is enabled

// Scribe settings
const char* family_id = "YOUR_FAMILY_ID";
const char* device_name = "ESP32 Secure Client";
const char* device_type = "esp32";
String device_id = "esp32-"; // Will be appended with MAC address

// SSL Certificate - Replace with your domain's certificate
// Use the root CA certificate or your own self-signed certificate
const char* root_ca = \
"-----BEGIN CERTIFICATE-----\n" \
"MIIDSjCCAjKgAwIBAgIQRK+wgNajJ7qJMDmGLvhAazANBgkqhkiG9w0BAQUFADA/\n" \
"MSQwIgYDVQQKExtEaWdpdGFsIFNpZ25hdHVyZSBUcnVzdCBDby4xFzAVBgNVBAMT\n" \
"...\n" \ 
"-----END CERTIFICATE-----\n";

// WiFi and MQTT clients
WiFiClientSecure espClient;
PubSubClient client(espClient);

// Buffer for JSON serialization
char mqttBuffer[512];

// Variables to store the current question
String current_question_id = "";
String current_question_text = "";

// Function prototypes
void setup_wifi();
void callback(char* topic, byte* payload, unsigned int length);
void reconnect();
void publish_status(const char* status);
void publish_answer(const String& question_id, const String& answer_text);
void request_question();

void setup() {
  // Initialize serial
  Serial.begin(115200);
  Serial.println("ESP32 MQTT SSL Client for Question Answer Scribe");
  
  // Generate device ID using MAC address
  uint64_t mac = ESP.getEfuseMac();
  char mac_str[13];
  sprintf(mac_str, "%04X%08X", (uint16_t)(mac >> 32), (uint32_t)mac);
  device_id += mac_str;
  
  Serial.print("Device ID: ");
  Serial.println(device_id);
  
  // Setup wifi
  setup_wifi();
  
  // Configure SSL certificate
  espClient.setCACert(root_ca);
  
  // Configure MQTT server
  client.setServer(mqtt_server, mqtt_port);
  client.setCallback(callback);
}

void loop() {
  // Maintain MQTT connection
  if (!client.connected()) {
    reconnect();
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
  
  delay(100);
}

void setup_wifi() {
  delay(10);
  Serial.println();
  Serial.print("Connecting to ");
  Serial.println(ssid);

  WiFi.begin(ssid, password);

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println("");
  Serial.println("WiFi connected");
  Serial.println("IP address: ");
  Serial.println(WiFi.localIP());
}

void callback(char* topic, byte* payload, unsigned int length) {
  Serial.print("Message arrived [");
  Serial.print(topic);
  Serial.print("] ");
  
  // Create a null-terminated string
  char message[length + 1];
  memcpy(message, payload, length);
  message[length] = '\0';
  Serial.println(message);
  
  // Parse JSON payload
  DynamicJsonDocument doc(512);
  DeserializationError error = deserializeJson(doc, message);
  
  if (error) {
    Serial.print("deserializeJson() failed: ");
    Serial.println(error.c_str());
    return;
  }
  
  // Check if this is a question message
  String topic_str = String(topic);
  if (topic_str.startsWith("scribe/families/" + String(family_id) + "/questions")) {
    // Store question ID and text
    if (doc.containsKey("question_id") && doc.containsKey("content")) {
      current_question_id = doc["question_id"].as<String>();
      current_question_text = doc["content"].as<String>();
      
      Serial.println("\n===== NEW QUESTION =====");
      Serial.println(current_question_text);
      Serial.println("To answer, type: answer:your response");
      Serial.println("=======================");
    }
  }
}

void reconnect() {
  // Loop until we're reconnected
  int attempts = 0;
  while (!client.connected() && attempts < 5) {
    attempts++;
    Serial.print("Attempting MQTT connection...");
    
    // Create a random client ID
    String clientId = device_id;
    
    // Attempt to connect
    bool connected = false;
    if (mqtt_username && *mqtt_username != '\0') {
      connected = client.connect(clientId.c_str(), mqtt_username, mqtt_password);
    } else {
      connected = client.connect(clientId.c_str());
    }
    
    if (connected) {
      Serial.println("connected");
      
      // Once connected, publish an announcement...
      publish_status("connected");
      
      // Subscribe to topics
      String question_topic = "scribe/families/" + String(family_id) + "/questions";
      client.subscribe(question_topic.c_str());
      Serial.println("Subscribed to: " + question_topic);
      
      String device_topic = "scribe/families/" + String(family_id) + "/devices/" + device_id + "/#";
      client.subscribe(device_topic.c_str());
      Serial.println("Subscribed to: " + device_topic);
    } else {
      Serial.print("failed, rc=");
      Serial.print(client.state());
      Serial.println(" try again in 5 seconds");
      delay(5000);
    }
  }
  
  if (attempts >= 5 && !client.connected()) {
    Serial.println("Failed to connect to MQTT after multiple attempts.");
    Serial.println("Restarting ESP32...");
    ESP.restart();
  }
}

void publish_status(const char* status) {
  if (!client.connected()) {
    return;
  }
  
  DynamicJsonDocument doc(256);
  doc["status"] = status;
  doc["device_name"] = device_name;
  doc["device_type"] = device_type;
  doc["device_id"] = device_id;
  doc["family_id"] = family_id;
  doc["timestamp"] = millis() / 1000;
  
  String topic = "scribe/clients/" + device_id + "/status";
  
  serializeJson(doc, mqttBuffer);
  client.publish(topic.c_str(), mqttBuffer, true); // retained message
  
  Serial.print("Published status: ");
  Serial.println(status);
}

void publish_answer(const String& question_id, const String& answer_text) {
  if (!client.connected() || question_id.length() == 0) {
    return;
  }
  
  DynamicJsonDocument doc(512);
  doc["question_id"] = question_id;
  doc["answer"] = answer_text;
  doc["device_id"] = device_id;
  doc["device_name"] = device_name;
  doc["timestamp"] = millis() / 1000;
  
  String topic = "scribe/families/" + String(family_id) + "/answers";
  
  serializeJson(doc, mqttBuffer);
  client.publish(topic.c_str(), mqttBuffer);
  
  Serial.println("Answer published to question: " + question_id);
}

void request_question() {
  if (!client.connected()) {
    return;
  }
  
  DynamicJsonDocument doc(256);
  doc["type"] = "question_request";
  doc["device_id"] = device_id;
  doc["device_name"] = device_name;
  doc["timestamp"] = millis() / 1000;
  
  String topic = "scribe/families/" + String(family_id) + "/request";
  
  serializeJson(doc, mqttBuffer);
  client.publish(topic.c_str(), mqttBuffer);
  
  Serial.println("Question requested");
}