import os
import requests
import json

TOKEN_FILE = "dropbox_token.json"  # Fil där vi sparar access-token lokalt

DROPBOX_REFRESH_TOKEN = os.getenv("DROPBOX_REFRESH_TOKEN")
DROPBOX_CLIENT_ID = os.getenv("DROPBOX_CLIENT_ID")
DROPBOX_CLIENT_SECRET = os.getenv("DROPBOX_CLIENT_SECRET")

if not all([DROPBOX_REFRESH_TOKEN, DROPBOX_CLIENT_ID, DROPBOX_CLIENT_SECRET]):
    raise ValueError("Saknar en eller flera Dropbox-miljövariabler.")

def load_access_token():
    """Läs access-token från fil om den finns."""
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "r") as f:
            token_data = json.load(f)
            return token_data.get("access_token")
    return None

def save_access_token(token):
    """Spara access-token till fil."""
    with open(TOKEN_FILE, "w") as f:
        json.dump({"access_token": token}, f)

def get_new_access_token():
    """Hämtar en ny access-token med hjälp av refresh token."""
    url = "https://api.dropbox.com/oauth2/token"
    data = {
        "grant_type": "refresh_token",
        "refresh_token": DROPBOX_REFRESH_TOKEN,
        "client_id": DROPBOX_CLIENT_ID,
        "client_secret": DROPBOX_CLIENT_SECRET
    }
    response = requests.post(url, data=data)
    response_json = response.json()

    if "access_token" not in response_json:
        raise ValueError(f"Misslyckades att uppdatera access token: {response_json}")

    save_access_token(response_json["access_token"])  # Spara den nya tokenen
    return response_json["access_token"]

def get_access_token():
    """Returnerar en giltig access token, hämtar en ny om den är ogiltig."""
    token = load_access_token()
    if not token:
        token = get_new_access_token()
    return token