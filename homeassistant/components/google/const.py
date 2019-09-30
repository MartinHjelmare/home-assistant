"""Define constants for the Google component."""

DOMAIN = "google"
CLIENT_ID = "client_id"
CLIENT_SECRET = "client_secret"
GOOGLE_CLIENT_SECRETS = {
    "web": {
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "client_id": "REPLACE_ME",
        "client_secret": "REPLACE_ME",
        "redirect_uris": ["REPLACE_ME"],
        "token_uri": "https://oauth2.googleapis.com/token",
    }
}
SCOPE = "https://www.googleapis.com/auth/calendar"
