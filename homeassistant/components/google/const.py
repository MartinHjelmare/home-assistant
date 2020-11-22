"""Constants for the Google Calendars integration."""

DOMAIN = "google"

CALENDAR_CONFIG = "google_calendar_config"
CALENDAR_SERVICE = "google_calendar_service"
DISCOVER_CALENDAR = "google_discover_calendar"
LISTENERS = "google_listeners"
GOOGLE_CALENDAR_API = "calendar_api"

OAUTH2_AUTHORIZE = "https://accounts.google.com/o/oauth2/v2/auth"
OAUTH2_TOKEN = "https://oauth2.googleapis.com/token"

SCOPES = {
    GOOGLE_CALENDAR_API: [
        "https://www.googleapis.com/auth/calendar",
    ],
}
