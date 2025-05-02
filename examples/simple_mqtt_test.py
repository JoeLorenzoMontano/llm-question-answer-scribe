#!/usr/bin/env python3
"""
Simple MQTT Test Client for Question Answer Scribe System

This script connects to the MQTT broker and subscribes to test topics to verify
that the broker is working properly. It also allows sending test messages.

Usage:
    python simple_mqtt_test.py --host localhost --port 1883
"""

import argparse
import time
import json
import paho.mqtt.client as mqtt
import uuid
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("simple-mqtt-test")

class SimpleMQTTTest:
    def __init__(self, host, port=1883):
        self.host = host
        self.port = port
        self.connected = False
        self.client_id = f"simple-test-{uuid.uuid4().hex[:8]}"
        
        # Initialize MQTT client
        self.client = mqtt.Client(client_id=self.client_id)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect
        
    def connect(self):
        """Connect to the MQTT broker"""
        try:
            logger.info(f"Connecting to MQTT broker at {self.host}:{self.port}")
            self.client.connect(self.host, self.port, 60)
            self.client.loop_start()
            return True
        except Exception as e:
            logger.error(f"Failed to connect to MQTT broker: {e}")
            return False
            
    def disconnect(self):
        """Disconnect from the MQTT broker"""
        try:
            self.client.disconnect()
            self.client.loop_stop()
            logger.info("Disconnected from MQTT broker")
            return True
        except Exception as e:
            logger.error(f"Error disconnecting from MQTT broker: {e}")
            return False
            
    def _on_connect(self, client, userdata, flags, rc):
        """Callback for when the client connects to the broker"""
        if rc == 0:
            self.connected = True
            logger.info("Connected to MQTT broker successfully")
            
            # Subscribe to test topics
            self.client.subscribe("test/#")
            logger.info("Subscribed to 'test/#' topics")
            
        else:
            logger.error(f"Failed to connect to MQTT broker with code {rc}")
            self.connected = False
            
    def _on_disconnect(self, client, userdata, rc):
        """Callback for when the client disconnects from the broker"""
        logger.warning(f"Disconnected from MQTT broker with code {rc}")
        self.connected = False
            
    def _on_message(self, client, userdata, msg):
        """Callback for when a message is received from the broker"""
        topic = msg.topic
        payload = msg.payload.decode('utf-8')
        logger.info(f"Received message on topic {topic}:")
        logger.info(f"Payload: {payload}")
        
        # Try to parse as JSON if possible
        try:
            payload_json = json.loads(payload)
            logger.info(f"JSON: {json.dumps(payload_json, indent=2)}")
        except:
            pass
            
    def publish_test_message(self, message="Test message"):
        """Publish a test message to the test topic"""
        if not self.connected:
            logger.warning("Not connected to MQTT broker - can't publish")
            return False
            
        topic = f"test/{self.client_id}"
        payload = {
            "message": message,
            "client_id": self.client_id,
            "timestamp": time.time()
        }
        
        try:
            result = self.client.publish(topic, json.dumps(payload))
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                logger.info(f"Published test message to {topic}")
                return True
            else:
                logger.error(f"Failed to publish test message: {result}")
                return False
        except Exception as e:
            logger.error(f"Error publishing test message: {e}")
            return False

def main():
    """Main function"""
    parser = argparse.ArgumentParser(description="Simple MQTT Test Client")
    parser.add_argument("--host", default="localhost", help="MQTT broker host")
    parser.add_argument("--port", type=int, default=1883, help="MQTT broker port")
    args = parser.parse_args()
    
    # Create client and connect
    client = SimpleMQTTTest(args.host, args.port)
    if not client.connect():
        logger.error("Failed to connect - exiting")
        return 1
        
    try:
        # Print instructions
        print("\nSimple MQTT Test Client")
        print("======================")
        print("Commands:")
        print("  p <message>  - Publish a test message")
        print("  q            - Quit")
        print("\nListening for messages on 'test/#' topics...\n")
        
        # Main loop
        while True:
            cmd = input("> ")
            cmd = cmd.strip()
            
            if cmd.lower() == 'q':
                break
            elif cmd.lower().startswith('p '):
                message = cmd[2:].strip()
                client.publish_test_message(message)
            else:
                print("Unknown command. Type 'p <message>' to publish or 'q' to quit.")
                
    except KeyboardInterrupt:
        print("\nInterrupted by user")
    finally:
        client.disconnect()
        
    return 0

if __name__ == "__main__":
    exit(main())