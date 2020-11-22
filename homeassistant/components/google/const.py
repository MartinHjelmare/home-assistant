"""Constants for the Google Calendars integration."""

DOMAIN = "google"

GOOGLE_CALENDAR_API = "calendar_api"

OAUTH2_AUTHORIZE = "https://accounts.google.com/o/oauth2/v2/auth"
OAUTH2_TOKEN = "https://oauth2.googleapis.com/token"

SCOPES = {
    GOOGLE_CALENDAR_API: [
        "https://www.googleapis.com/auth/calendar",
    ],
}
