"""Local OAuth. Tokens stay on this machine."""

import os
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

CONFIG_DIR = Path(
    os.environ.get("EMAIL_ORGANISER_HOME", Path.home() / ".email-organiser")
)
CREDENTIALS_FILE = CONFIG_DIR / "credentials.json"
TOKEN_FILE = CONFIG_DIR / "token.json"


def get_service():
    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDENTIALS_FILE.exists():
                raise SystemExit(
                    f"Missing {CREDENTIALS_FILE}.\n"
                    "Create an OAuth client (Desktop app) in Google Cloud Console, "
                    "enable the Gmail API, download the JSON, and save it there."
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CREDENTIALS_FILE), SCOPES
            )
            creds = flow.run_local_server(port=0)

        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        TOKEN_FILE.write_text(creds.to_json())
        TOKEN_FILE.chmod(0o600)

    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def get_owner_address(service) -> str:
    return service.users().getProfile(userId="me").execute()["emailAddress"]
