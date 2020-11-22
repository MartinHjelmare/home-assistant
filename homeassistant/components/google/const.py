"""Constants for the Google Calendars integration."""

DOMAIN = "google"

AUTH_MANAGER = "auth_manager"
CALENDAR_CONFIG = "calendar_config"
CALENDAR_SERVICE = "calendar_service"
DISCOVER_CALENDAR = "google_discover_calendar"
DISPATCHERS = "google_dispatchers"
GOOGLE_CALENDAR_API = "calendar_api"

OAUTH2_AUTHORIZE = "https://accounts.google.com/o/oauth2/v2/auth"
OAUTH2_TOKEN = "https://oauth2.googleapis.com/token"

SCOPES = {
    GOOGLE_CALENDAR_API: [
        "https://www.googleapis.com/auth/calendar",
    ],
}
