import os
import httpx
from dotenv import load_dotenv

load_dotenv()

EVOLUTION_API_URL = os.environ.get("EVOLUTION_API_URL")
EVOLUTION_API_KEY = os.environ.get("EVOLUTION_API_KEY")
INSTANCE_ID = os.environ.get("EVOLUTION_INSTANCE_ID")

class EvolutionService:
    def __init__(self):
        self.base_url = EVOLUTION_API_URL
        self.api_key = EVOLUTION_API_KEY
        self.instance = INSTANCE_ID
        self.headers = {
            "apikey": self.api_key,
            "Content-Type": "application/json"
        }

    async def send_text_message(self, remote_jid: str, text: str):
        """Send a message back to WhatsApp via Evolution API."""
        if not self.base_url or not self.api_key:
            print(f"MOCK MSG to {remote_jid}: {text}")
            return {"status": "mock"}

        url = f"{self.base_url}/message/sendText/{self.instance}"
        payload = {
            "number": remote_jid,
            "text": text,
            "delay": 1500, # delay for typing effect
            "linkPreview": False
        }

        async with httpx.AsyncClient() as client:
            try:
                import logging
                logger = logging.getLogger("CardioAgent")
                response = await client.post(url, json=payload, headers=self.headers)
                logger.info(f"Evolution API Response: {response.status_code} - {response.text}")
                response.raise_for_status()
                return response.json()
            except Exception as e:
                import logging
                logger = logging.getLogger("CardioAgent")
                logger.error(f"Error sending message to {remote_jid}: {e}")
                return None

evo_service = EvolutionService()
