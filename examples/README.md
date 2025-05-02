# Question Answer Scribe MQTT Examples

This directory contains example clients for connecting to the Question Answer Scribe system using MQTT.

## Python MQTT Client

The Python client (`mqtt_client.py`) demonstrates how to connect to the MQTT broker and interact with the Question Answer Scribe system using Python.

### Requirements

- Python 3.6+
- paho-mqtt library

### Usage

```bash
python mqtt_client.py --host <mqtt-broker-host> --port <mqtt-broker-port> --username <mqtt-username> --password <mqtt-password> --family-id <family-id>
```

Replace the placeholders with your actual MQTT broker details and family ID.

## ESP32 MQTT Client

The ESP32 client (`esp32_mqtt_client/esp32_mqtt_client.ino`) demonstrates how to connect an ESP32 microcontroller to the Question Answer Scribe system using MQTT.

### Requirements

- Arduino IDE
- ESP32 board support in Arduino IDE
- PubSubClient library
- ArduinoJson library

### Configuration

Edit the following variables in the code to match your environment:

```cpp
const char* ssid = "YOUR_WIFI_SSID";      // Replace with your WiFi SSID
const char* password = "YOUR_WIFI_PASSWORD"; // Replace with your WiFi password
const char* mqtt_broker = "mqtt-broker";  // Replace with your MQTT broker address
const int mqtt_port = 1883;
const char* mqtt_username = "mqtt_username"; // Replace with your MQTT username
const char* mqtt_password = "mqtt_password"; // Replace with your MQTT password
const char* family_id = "YOUR_FAMILY_ID";  // Replace with your family ID
```

### Usage

1. Connect your ESP32 board to your computer
2. Open the `.ino` file in Arduino IDE
3. Update the configuration settings
4. Upload the sketch to your ESP32 board
5. Open the Serial Monitor to interact with the device

## MQTT Topics

The MQTT topics used in these examples follow this structure:

- `scribe/clients/{device_id}/status` - Device status messages
- `scribe/families/{family_id}/questions` - Questions for the family
- `scribe/families/{family_id}/answers` - Answers to questions
- `scribe/families/{family_id}/notifications` - Notifications for the family
- `scribe/families/{family_id}/devices/{device_id}/#` - Device-specific messages
- `scribe/families/{family_id}/request` - Request messages

## Message Format

All messages are formatted as JSON objects. Here are the main message formats:

### Question

```json
{
  "question_id": "uuid-string",
  "content": "The question text",
  "timestamp": 1619712345.678
}
```

### Answer

```json
{
  "question_id": "uuid-string",
  "answer": "The answer text",
  "device_id": "device-uuid-string",
  "device_name": "Example Device",
  "timestamp": 1619712345.678
}
```

### Status

```json
{
  "status": "connected", // or "disconnected"
  "device_name": "Example Device",
  "device_type": "python", // or "esp32", "mobile", etc.
  "device_id": "device-uuid-string",
  "family_id": "family-uuid-string",
  "timestamp": 1619712345.678
}
```

### Question Request

```json
{
  "type": "question_request",
  "device_id": "device-uuid-string",
  "device_name": "Example Device",
  "timestamp": 1619712345.678
}
```