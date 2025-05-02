#!/usr/bin/env python3
"""
Example MQTT client for the Question Answer Scribe system.

This script demonstrates how to connect to the MQTT broker and
interact with the Question Answer Scribe system via MQTT.
"""

import json
import time
import argparse
import paho.mqtt.client as mqtt
import uuid
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("mqtt-client")

class ScribeMQTTClient:
    """MQTT client for the Question Answer Scribe system."""
    
    def __init__(self, broker_host, broker_port=1883, 
                 username=None, password=None, 
                 family_id=None, device_name="Example Device",
                 device_type="python"):
        """Initialize the MQTT client."""
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.username = username
        self.password = password
        self.family_id = family_id
        self.device_name = device_name
        self.device_type = device_type
        self.device_id = str(uuid.uuid4())
        self.connected = False
        self.message_callbacks = {}
        
        # Initialize the MQTT client
        self.client = mqtt.Client(client_id=f"scribe-client-{self.device_id}")
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
        
        # Set authentication if provided
        if username and password:
            self.client.username_pw_set(username, password)
            
    def connect(self):
        """Connect to the MQTT broker."""
        try:
            logger.info(f"Connecting to MQTT broker at {self.broker_host}:{self.broker_port}")
            self.client.connect(self.broker_host, self.broker_port, 60)
            self.client.loop_start()
            return True
        except Exception as e:
            logger.error(f"Failed to connect to MQTT broker: {e}")
            return False
            
    def disconnect(self):
        """Disconnect from the MQTT broker."""
        try:
            self._publish_status("disconnected")
            self.client.disconnect()
            self.client.loop_stop()
            logger.info("Disconnected from MQTT broker")
            return True
        except Exception as e:
            logger.error(f"Error disconnecting from MQTT broker: {e}")
            return False
            
    def _on_connect(self, client, userdata, flags, rc):
        """Callback for when the client connects to the broker."""
        if rc == 0:
            logger.info("Connected to MQTT broker successfully")
            self.connected = True
            
            # Subscribe to topics
            self._subscribe_to_topics()
            
            # Publish status
            self._publish_status("connected")
        else:
            logger.error(f"Failed to connect to MQTT broker with code {rc}")
            self.connected = False
            
    def _on_disconnect(self, client, userdata, rc):
        """Callback for when the client disconnects from the broker."""
        logger.warning(f"Disconnected from MQTT broker with code {rc}")
        self.connected = False
            
    def _on_message(self, client, userdata, msg):
        """Callback for when a message is received from the broker."""
        try:
            topic = msg.topic
            payload = msg.payload.decode('utf-8')
            logger.debug(f"Received message on topic {topic}: {payload}")
            
            # Parse the payload
            try:
                data = json.loads(payload)
            except json.JSONDecodeError:
                data = {"content": payload}
                
            # Handle topic-specific callbacks
            if topic in self.message_callbacks:
                for callback in self.message_callbacks[topic]:
                    try:
                        callback(topic, data)
                    except Exception as e:
                        logger.error(f"Error in message handler for topic {topic}: {e}")
                        
            # Handle wildcard subscriptions
            for pattern, callbacks in self.message_callbacks.items():
                if '+' in pattern or '#' in pattern:
                    # Convert MQTT wildcards to regex patterns
                    regex_pattern = pattern.replace('+', '[^/]+').replace('#', '.+')
                    if re.match(regex_pattern, topic):
                        for callback in callbacks:
                            try:
                                callback(topic, data)
                            except Exception as e:
                                logger.error(f"Error in wildcard handler for topic {topic}: {e}")
                
        except Exception as e:
            logger.error(f"Error processing MQTT message: {e}")
            
    def _subscribe_to_topics(self):
        """Subscribe to relevant topics."""
        if not self.family_id:
            logger.warning("No family ID provided, not subscribing to family topics")
            return
            
        # Subscribe to family topics
        family_topics = [
            f"scribe/families/{self.family_id}/questions",
            f"scribe/families/{self.family_id}/notifications",
            f"scribe/families/{self.family_id}/devices/{self.device_id}/#"
        ]
        
        for topic in family_topics:
            logger.info(f"Subscribing to topic: {topic}")
            self.client.subscribe(topic)
            
    def _publish_status(self, status):
        """Publish device status."""
        if not self.family_id:
            logger.warning("No family ID provided, not publishing status")
            return
            
        topic = f"scribe/clients/{self.device_id}/status"
        payload = {
            "status": status,
            "device_name": self.device_name,
            "device_type": self.device_type,
            "device_id": self.device_id,
            "family_id": self.family_id,
            "timestamp": time.time()
        }
        
        self.client.publish(topic, json.dumps(payload), qos=1, retain=True)
        logger.info(f"Published {status} status")
        
    def add_message_handler(self, topic, callback):
        """
        Add a message handler for a specific topic.
        
        Args:
            topic: MQTT topic to subscribe to
            callback: Function to call when a message is received on this topic
                     Should accept (topic, data) arguments
        """
        if topic not in self.message_callbacks:
            self.message_callbacks[topic] = []
            if self.connected:
                logger.info(f"Subscribing to topic: {topic}")
                self.client.subscribe(topic)
                
        self.message_callbacks[topic].append(callback)
        
    def publish_answer(self, question_id, answer_text):
        """
        Publish an answer to a question.
        
        Args:
            question_id: ID of the question being answered
            answer_text: Text of the answer
        """
        if not self.family_id:
            logger.warning("No family ID provided, not publishing answer")
            return False
            
        topic = f"scribe/families/{self.family_id}/answers"
        payload = {
            "question_id": question_id,
            "answer": answer_text,
            "device_id": self.device_id,
            "device_name": self.device_name,
            "timestamp": time.time()
        }
        
        result = self.client.publish(topic, json.dumps(payload), qos=1)
        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            logger.info(f"Published answer for question {question_id}")
            return True
        else:
            logger.error(f"Failed to publish answer: {result}")
            return False
            
    def request_question(self):
        """Request a new question from the system."""
        if not self.family_id:
            logger.warning("No family ID provided, not requesting question")
            return False
            
        topic = f"scribe/families/{self.family_id}/request"
        payload = {
            "type": "question_request",
            "device_id": self.device_id,
            "device_name": self.device_name,
            "timestamp": time.time()
        }
        
        result = self.client.publish(topic, json.dumps(payload), qos=1)
        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            logger.info("Requested new question")
            return True
        else:
            logger.error(f"Failed to request question: {result}")
            return False

def main():
    """Run the example MQTT client."""
    parser = argparse.ArgumentParser(description="Example MQTT client for Question Answer Scribe")
    parser.add_argument("--host", default="localhost", help="MQTT broker host")
    parser.add_argument("--port", type=int, default=1883, help="MQTT broker port")
    parser.add_argument("--username", help="MQTT username")
    parser.add_argument("--password", help="MQTT password")
    parser.add_argument("--family-id", required=True, help="Family ID")
    parser.add_argument("--device-name", default="Example Python Client", help="Device name")
    args = parser.parse_args()
    
    # Create the client
    client = ScribeMQTTClient(
        broker_host=args.host,
        broker_port=args.port,
        username=args.username,
        password=args.password,
        family_id=args.family_id,
        device_name=args.device_name
    )
    
    # Add message handlers
    def on_question(topic, data):
        """Handle incoming questions."""
        question_id = data.get("question_id")
        question_text = data.get("content")
        logger.info(f"Received question: {question_text}")
        
        # In a real client, you might prompt the user for an answer
        # For this example, we'll just send a fixed response
        time.sleep(1)  # Simulate thinking
        client.publish_answer(question_id, "This is an automated response from the example client.")
        
    def on_notification(topic, data):
        """Handle notifications."""
        logger.info(f"Received notification: {data.get('content')}")
    
    # Register handlers
    client.add_message_handler(f"scribe/families/{args.family_id}/questions", on_question)
    client.add_message_handler(f"scribe/families/{args.family_id}/notifications", on_notification)
    
    # Connect to the broker
    if not client.connect():
        logger.error("Failed to connect, exiting")
        return
    
    try:
        # Request a question to start
        client.request_question()
        
        # Keep the client running
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("Interrupted by user, shutting down")
    finally:
        client.disconnect()

if __name__ == "__main__":
    main()