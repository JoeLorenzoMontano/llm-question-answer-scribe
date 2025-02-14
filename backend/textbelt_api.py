import requests
import logging

class TextBeltAPI:
    """A class to interact with the TextBelt API for sending, tracking, and receiving SMS messages."""

    BASE_URL = "https://textbelt.com"

    def __init__(self, api_key: str):
        """
        Initializes the TextBelt API client.

        :param api_key: Your TextBelt API key.
        """
        self.api_key = api_key
        self.logger = logging.getLogger(__name__)

    def __init__(self, api_key: str):
        """
        Initializes the TextBelt API client.

        :param api_key: Your TextBelt API key.
        """
        self.api_key = api_key
        self.logger = logging.getLogger(__name__)

    def send_sms(self, phone_number: str, message: str, webhook_url: str = None, webhook_data: str = None) -> dict:
        """
        Sends an SMS using the TextBelt API with an optional webhook for SMS replies and webhookData.

        :param phone_number: The recipient's phone number in international format (e.g., +1234567890).
        :param message: The message text.
        :param webhook_url: The URL to receive SMS replies (optional).
        :param webhook_data: Custom data that will be sent back with the webhook (optional).
        :return: API response as a dictionary.
        """
        url = f"{self.BASE_URL}/text"
        payload = {
            "phone": phone_number,
            "message": message,
            "key": self.api_key
        }

        if webhook_url:
            payload["replyWebhookUrl"] = webhook_url  # Add webhook URL if provided

        if webhook_data:
            payload["webhookData"] = webhook_data  # Add custom webhook data if provided

        try:
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            data = response.json()

            if not data.get("success"):
                self.logger.warning(f"SMS failed: {data}")
            return data

        except requests.exceptions.RequestException as e:
            self.logger.error(f"Error sending SMS: {e}")
            return {"success": False, "error": str(e)}

    @staticmethod
    def process_webhook_data(data: dict) -> dict:
        """
        Processes incoming SMS replies from TextBelt's webhook.

        :param data: A dictionary representing the JSON payload from the webhook.
        :return: A response dictionary confirming the webhook was received or an error message.
        """
        try:
            if not data:
                return {"success": False, "error": "Invalid request, no data received"}

            phone_number = data.get("fromNumber")
            message = data.get("text")

            if not phone_number or not message:
                return {"success": False, "error": "Missing required fields"}

            logging.info(f"Received SMS reply from {phone_number}: {message}")

            # Here, you can process the reply (e.g., store in a database, trigger automation, etc.)

            return {"success": True, "message": "Webhook processed successfully"}

        except Exception as e:
            logging.error(f"Error processing webhook: {e}")
            return {"success": False, "error": str(e)}

    def check_status(self, message_id: str) -> dict:
        """
        Checks the delivery status of a sent SMS.

        :param message_id: The ID returned when sending an SMS.
        :return: API response as a dictionary.
        """
        url = f"{self.BASE_URL}/status/{message_id}"

        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            return response.json()

        except requests.exceptions.RequestException as e:
            self.logger.error(f"Error checking SMS status: {e}")
            return {"success": False, "error": str(e)}
