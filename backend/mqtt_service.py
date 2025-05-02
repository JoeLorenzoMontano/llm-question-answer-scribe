"""
MQTT Service for the Question Answer Scribe application.

This module provides a service for handling MQTT connections and message publishing/subscription.
"""

import os
import json
import logging
import time
import uuid
import socket
from typing import Dict, List, Optional, Callable, Any
import paho.mqtt.client as mqtt
from database import get_db_connection
import threading

# Configure logging
logger = logging.getLogger(__name__)

# Get broker settings from environment
MQTT_BROKER_HOST = os.getenv("MQTT_BROKER_HOST", "localhost")  # Default to localhost for easier testing
MQTT_BROKER_PORT = int(os.getenv("MQTT_BROKER_PORT", 1883))
MQTT_KEEP_ALIVE = 60  # seconds

# Resolve host to IP address if possible to avoid DNS issues
try:
    # Try to resolve the host to an IP address
    resolved_ip = socket.gethostbyname(MQTT_BROKER_HOST)
    if resolved_ip != MQTT_BROKER_HOST:
        logger.info(f"Resolved MQTT broker host {MQTT_BROKER_HOST} to IP {resolved_ip}")
        MQTT_BROKER_HOST = resolved_ip
except socket.gaierror:
    logger.warning(f"Could not resolve MQTT broker host {MQTT_BROKER_HOST}. Using as is.")
except Exception as e:
    logger.warning(f"Error resolving MQTT broker host: {e}. Using as is.")

class MQTTService:
    """
    MQTT Service for handling MQTT connections and message publishing/subscription.
    
    This service manages the MQTT connection for the application, including:
    - Client connections and authentication
    - Message publishing
    - Message subscription and handling
    - Connection monitoring
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        """Singleton pattern to ensure only one MQTT service instance exists."""
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(MQTTService, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance
    
    def __init__(self):
        """Initialize the MQTT service if not already initialized."""
        if self._initialized:
            return
            
        self._initialized = True
        self.client = mqtt.Client(client_id=f"scribe-service-{uuid.uuid4()}")
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
        self.connected = False
        self.topic_handlers = {}
        self.family_clients = {}  # Track connected family clients
        
        # Connect in a separate thread to avoid blocking
        threading.Thread(target=self._connect, daemon=True).start()
    
    def _connect(self):
        """Connect to the MQTT broker."""
        try:
            logger.info(f"Connecting to MQTT broker at {MQTT_BROKER_HOST}:{MQTT_BROKER_PORT}")
            self.client.connect(MQTT_BROKER_HOST, MQTT_BROKER_PORT, MQTT_KEEP_ALIVE)
            self.client.loop_start()
        except Exception as e:
            logger.error(f"Failed to connect to MQTT broker: {e}")
            # Schedule reconnection attempts
            threading.Timer(10.0, self._retry_connect).start()
            
    def _retry_connect(self, max_attempts=10):
        """Retry connecting to the MQTT broker."""
        if hasattr(self, '_connect_attempts'):
            self._connect_attempts += 1
        else:
            self._connect_attempts = 1
            
        if self._connect_attempts <= max_attempts:
            logger.info(f"Retrying connection to MQTT broker (attempt {self._connect_attempts}/{max_attempts})")
            try:
                self.client.connect(MQTT_BROKER_HOST, MQTT_BROKER_PORT, MQTT_KEEP_ALIVE)
                self.client.loop_start()
                logger.info("Successfully connected to MQTT broker")
                self._connect_attempts = 0  # Reset counter on success
            except Exception as e:
                logger.error(f"Failed to connect to MQTT broker (retry): {e}")
                # Schedule next retry with exponential backoff
                delay = min(30, 5 * self._connect_attempts)
                threading.Timer(delay, self._retry_connect, [max_attempts]).start()
        else:
            logger.warning(f"Maximum connection attempts ({max_attempts}) reached. Giving up on MQTT connection.")
    
    def _on_connect(self, client, userdata, flags, rc):
        """Callback for when the client connects to the broker."""
        if rc == 0:
            logger.info("Connected to MQTT broker successfully")
            self.connected = True
            
            # Subscribe to system topics
            self.client.subscribe("scribe/system/#")
            
            # Subscribe to client connection topics
            self.client.subscribe("scribe/clients/+/status")
            
        else:
            logger.error(f"Failed to connect to MQTT broker with code {rc}")
            self.connected = False
    
    def _on_disconnect(self, client, userdata, rc):
        """Callback for when the client disconnects from the broker."""
        logger.warning(f"Disconnected from MQTT broker with code {rc}")
        self.connected = False
        
        # Try to reconnect if unexpected disconnection
        if rc != 0:
            threading.Thread(target=self._reconnect, daemon=True).start()
    
    def _reconnect(self, max_retries=10, retry_delay=5):
        """Attempt to reconnect to the MQTT broker."""
        retries = 0
        while not self.connected and retries < max_retries:
            try:
                logger.info(f"Attempting to reconnect to MQTT broker (attempt {retries+1}/{max_retries})")
                self.client.reconnect()
                logger.info("Reconnected to MQTT broker successfully")
                return
            except Exception as e:
                logger.error(f"Failed to reconnect to MQTT broker: {e}")
                retries += 1
                time.sleep(retry_delay)
    
    def _on_message(self, client, userdata, msg):
        """Callback for when a message is received from the broker."""
        try:
            topic = msg.topic
            payload = msg.payload.decode('utf-8')
            logger.debug(f"Received message on topic {topic}: {payload}")
            
            # Handle client status messages
            if topic.startswith("scribe/clients/") and topic.endswith("/status"):
                self._handle_client_status(topic, payload)
                return
            
            # Handle topic-specific handlers
            if topic in self.topic_handlers:
                for handler in self.topic_handlers[topic]:
                    try:
                        handler(topic, payload)
                    except Exception as e:
                        logger.error(f"Error in message handler for topic {topic}: {e}")
        
        except Exception as e:
            logger.error(f"Error processing MQTT message: {e}")
    
    def _handle_client_status(self, topic, payload):
        """Handle client status messages."""
        try:
            # Extract client ID from topic
            parts = topic.split('/')
            if len(parts) >= 3:
                client_id = parts[2]
                status_data = json.loads(payload)
                
                # Update client status
                if status_data.get("status") == "connected":
                    self._record_client_connection(client_id, status_data)
                elif status_data.get("status") == "disconnected":
                    self._record_client_disconnection(client_id)
        
        except Exception as e:
            logger.error(f"Error handling client status message: {e}")
    
    def _record_client_connection(self, client_id, status_data):
        """Record a client connection in the database."""
        try:
            family_id = status_data.get("family_id")
            if not family_id:
                logger.warning(f"Client {client_id} connected without family_id")
                return
                
            # Update family_clients cache
            device_info = {
                "client_id": client_id,
                "device_name": status_data.get("device_name", "Unknown Device"),
                "device_type": status_data.get("device_type", "unknown"),
                "connected_at": time.time(),
                "ip_address": status_data.get("ip_address")
            }
            
            if family_id not in self.family_clients:
                self.family_clients[family_id] = {}
            self.family_clients[family_id][client_id] = device_info
            
            # Update database
            conn = get_db_connection()
            cursor = conn.cursor()
            try:
                cursor.execute(
                    "UPDATE families SET mqtt_last_connection = CURRENT_TIMESTAMP WHERE id = %s",
                    (family_id,)
                )
                conn.commit()
            finally:
                cursor.close()
                conn.close()
                
            logger.info(f"Client {client_id} for family {family_id} connected")
            
        except Exception as e:
            logger.error(f"Error recording client connection: {e}")
    
    def _record_client_disconnection(self, client_id):
        """Record a client disconnection."""
        try:
            # Remove from family_clients cache
            for family_id, clients in list(self.family_clients.items()):
                if client_id in clients:
                    del self.family_clients[family_id][client_id]
                    logger.info(f"Client {client_id} for family {family_id} disconnected")
                    
                    # Clean up empty family entries
                    if not self.family_clients[family_id]:
                        del self.family_clients[family_id]
                    break
        
        except Exception as e:
            logger.error(f"Error recording client disconnection: {e}")
    
    def subscribe(self, topic: str, handler: Callable[[str, str], None]):
        """
        Subscribe to an MQTT topic and register a handler for messages.
        
        Args:
            topic: The topic to subscribe to
            handler: Function to call when a message is received
        """
        if not self.connected:
            logger.warning(f"MQTT not connected, queuing subscription to {topic}")
        
        # Register the handler
        if topic not in self.topic_handlers:
            self.topic_handlers[topic] = []
            # Subscribe to the topic if we're connected
            if self.connected:
                self.client.subscribe(topic)
        
        self.topic_handlers[topic].append(handler)
    
    def publish(self, topic: str, payload: Any, qos: int = 0, retain: bool = False, max_retries=3, retry_delay=1.0):
        """
        Publish a message to an MQTT topic.
        
        Args:
            topic: The topic to publish to
            payload: The message payload (will be converted to JSON if not a string)
            qos: Quality of Service level (0, 1, or 2)
            retain: Whether the broker should retain the message
            max_retries: Maximum number of retries if not connected
            retry_delay: Delay between retries in seconds
        
        Returns:
            True if the message was published, False otherwise
        """
        # If not connected, try to connect and retry
        if not self.connected:
            logger.warning(f"MQTT not connected, will try to connect before publishing to {topic}")
            
            # Don't block for too long - try max_retries times
            for retry in range(max_retries):
                if self.connected:
                    break
                    
                logger.info(f"Waiting for MQTT connection (attempt {retry+1}/{max_retries})...")
                time.sleep(retry_delay)
                
            if not self.connected:
                logger.error(f"MQTT still not connected after {max_retries} retries, cannot publish to {topic}")
                return False
        
        try:
            # Convert payload to JSON string if it's not already a string
            if not isinstance(payload, str):
                payload = json.dumps(payload)
                
            # Publish the message
            result = self.client.publish(topic, payload, qos, retain)
            if result.rc != mqtt.MQTT_ERR_SUCCESS:
                logger.error(f"Failed to publish to {topic}: {result}")
                return False
            
            logger.debug(f"Successfully published message to {topic}")
            return True
        
        except Exception as e:
            logger.error(f"Error publishing to {topic}: {e}")
            return False
    
    def get_connected_clients(self, family_id: str = None) -> Dict:
        """
        Get information about connected clients.
        
        Args:
            family_id: Optional family ID to filter by
            
        Returns:
            Dictionary of connected clients
        """
        if family_id:
            return self.family_clients.get(family_id, {})
        return self.family_clients
    
    def send_question_to_family(self, family_id: str, question_data: Dict) -> bool:
        """
        Send a question to all connected devices in a family.
        
        Args:
            family_id: The family ID to send to
            question_data: Dictionary with question information
            
        Returns:
            True if the message was published, False otherwise
        """
        # Create a topic specific to this family
        topic = f"scribe/families/{family_id}/questions"
        
        # Add timestamp to the question data
        question_data["timestamp"] = time.time()
        
        # Publish the question
        return self.publish(topic, question_data)
    
    def send_message_to_device(self, family_id: str, client_id: str, message_type: str, message_data: Dict) -> bool:
        """
        Send a message to a specific device.
        
        Args:
            family_id: The family ID the device belongs to
            client_id: The client ID to send to
            message_type: Type of message (e.g., "question", "notification")
            message_data: Dictionary with message information
            
        Returns:
            True if the message was published, False otherwise
        """
        # Create a topic specific to this device
        topic = f"scribe/families/{family_id}/devices/{client_id}/{message_type}"
        
        # Add timestamp to the message data
        message_data["timestamp"] = time.time()
        
        # Publish the message
        return self.publish(topic, message_data)

# Create a global instance of the MQTT service
mqtt_service = MQTTService()

def get_mqtt_service() -> MQTTService:
    """Get the global MQTT service instance."""
    return mqtt_service