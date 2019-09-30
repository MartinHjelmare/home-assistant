"""Define constants for the Google component."""

DOMAIN = "google"
CLIENT_ID = "client_id"
CLIENT_SECRET = "client_secret"
INSTALLED = "installed"
REDIRECT_URIS = "redirect_uris"
GOOGLE_CLIENT_SECRETS = {
    INSTALLED: {
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        CLIENT_ID: "REPLACE_ME",
        CLIENT_SECRET: "REPLACE_ME",
        REDIRECT_URIS: ["REPLACE_ME"],
        "token_uri": "https://oauth2.googleapis.com/token",
    }
}
SCOPE = "https://www.googleapis.com/auth/calendar"
