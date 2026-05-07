from datetime import date
import os
from dotenv import load_dotenv

load_dotenv()

DATA_INICIO = date(2026, 3, 1)
CLIENT_NAME = "NÚCLEA"
API_BASE_URL = "https://runrun.it/api/v1.0"

_emails_env = os.getenv("ALLOWED_DATE_OVERRIDE_EMAILS", "")
ALLOWED_DATE_OVERRIDE_EMAILS = [email.strip().lower() for email in _emails_env.split(",")] if _emails_env else []

