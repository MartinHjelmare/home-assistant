"""Support for Google Calendar."""
from datetime import datetime, timedelta
import logging

from googleapiclient import discovery as google_discovery
from google.oauth2.credentials import Credentials
import voluptuous as vol
from voluptuous.error import Error as VoluptuousError
import yaml

from homeassistant import config_entries
from homeassistant.helpers.dispatcher import dispatcher_send
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity import generate_entity_id

from . import config_flow
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

CONF_CLIENT_ID = "client_id"
CONF_CLIENT_SECRET = "client_secret"
CONF_TRACK_NEW = "track_new_calendar"

CONF_CAL_ID = "cal_id"
CONF_DEVICE_ID = "device_id"
CONF_NAME = "name"
CONF_ENTITIES = "entities"
CONF_TRACK = "track"
CONF_SEARCH = "search"
CONF_OFFSET = "offset"
CONF_IGNORE_AVAILABILITY = "ignore_availability"
CONF_MAX_RESULTS = "max_results"

DEFAULT_CONF_TRACK_NEW = True
DEFAULT_CONF_OFFSET = "!!"

EVENT_CALENDAR_ID = "calendar_id"
EVENT_DESCRIPTION = "description"
EVENT_END_CONF = "end"
EVENT_END_DATE = "end_date"
EVENT_END_DATETIME = "end_date_time"
EVENT_IN = "in"
EVENT_IN_DAYS = "days"
EVENT_IN_WEEKS = "weeks"
EVENT_START_CONF = "start"
EVENT_START_DATE = "start_date"
EVENT_START_DATETIME = "start_date_time"
EVENT_SUMMARY = "summary"
EVENT_TYPES_CONF = "event_types"

SERVICE_SCAN_CALENDARS = "scan_for_calendars"
SERVICE_FOUND_CALENDARS = "found_calendar"
SERVICE_ADD_EVENT = "add_event"

DATA_INDEX = "google_calendars"
DATA_CALENDAR_SERVICE = "google_calendar_service"
DATA_CONFIG = "google_config"
DATA_DISPATCHERS = "google_dispatchers"

YAML_DEVICES = f"{DOMAIN}_calendars.yaml"
DISCOVER_CALENDAR = "google_discover_calendar"

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required(CONF_CLIENT_ID): cv.string,
                vol.Required(CONF_CLIENT_SECRET): cv.string,
                vol.Optional(
                    CONF_TRACK_NEW, default=DEFAULT_CONF_TRACK_NEW
                ): cv.boolean,
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)

_SINGLE_CALSEARCH_CONFIG = vol.Schema(
    {
        vol.Required(CONF_NAME): cv.string,
        vol.Required(CONF_DEVICE_ID): cv.string,
        vol.Optional(CONF_IGNORE_AVAILABILITY, default=True): cv.boolean,
        vol.Optional(CONF_OFFSET): cv.string,
        vol.Optional(CONF_SEARCH): cv.string,
        vol.Optional(CONF_TRACK): cv.boolean,
        vol.Optional(CONF_MAX_RESULTS): cv.positive_int,
    }
)

DEVICE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_CAL_ID): cv.string,
        vol.Required(CONF_ENTITIES, None): vol.All(
            cv.ensure_list, [_SINGLE_CALSEARCH_CONFIG]
        ),
    },
    extra=vol.ALLOW_EXTRA,
)

_EVENT_IN_TYPES = vol.Schema(
    {
        vol.Exclusive(EVENT_IN_DAYS, EVENT_TYPES_CONF): cv.positive_int,
        vol.Exclusive(EVENT_IN_WEEKS, EVENT_TYPES_CONF): cv.positive_int,
    }
)

ADD_EVENT_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Required(EVENT_CALENDAR_ID): cv.string,
        vol.Required(EVENT_SUMMARY): cv.string,
        vol.Optional(EVENT_DESCRIPTION, default=""): cv.string,
        vol.Exclusive(EVENT_START_DATE, EVENT_START_CONF): cv.date,
        vol.Exclusive(EVENT_END_DATE, EVENT_END_CONF): cv.date,
        vol.Exclusive(EVENT_START_DATETIME, EVENT_START_CONF): cv.datetime,
        vol.Exclusive(EVENT_END_DATETIME, EVENT_END_CONF): cv.datetime,
        vol.Exclusive(EVENT_IN, EVENT_START_CONF, EVENT_END_CONF): _EVENT_IN_TYPES,
    }
)


async def async_setup(hass, config):
    """Set up the Google component."""
    conf = config.get(DOMAIN, {})
    if not conf:
        # component is set up by tts platform, or by user step in config flow
        return True

    hass.data[DOMAIN] = {}
    hass.data[DOMAIN][DATA_CONFIG] = conf

    config_flow.register_flow_implementation(
        hass, config[DOMAIN][CONF_CLIENT_ID], config[DOMAIN][CONF_CLIENT_SECRET]
    )

    hass.async_create_task(
        hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_IMPORT}
        )
    )

    return True


async def async_setup_entry(hass, entry):
    """Set up Google from a config entry."""
    hass.data[DOMAIN][DATA_INDEX] = {}
    hass.data[DOMAIN][DATA_DISPATCHERS] = []
    conf = hass.data[DOMAIN][DATA_CONFIG]
    await hass.async_add_executor_job(do_setup, hass, entry, conf)

    hass.async_create_task(
        hass.config_entries.async_forward_entry_setup(entry, "calendar")
    )

    return True


async def async_unload_entry(hass, entry):
    """Unload Google config entry."""
    dispatchers = hass.data[DOMAIN].pop(DATA_DISPATCHERS, [])
    for unsub_dispatcher in dispatchers:
        unsub_dispatcher()

    await hass.config_entries.async_forward_entry_unload(entry, "calendar")

    del hass.data[DOMAIN][DATA_INDEX]

    return True


# FIXME: Replace checking scope


def check_correct_scopes(token_file):
    """Check for the correct scopes in file."""
    with open(token_file, "r") as file_handle:
        tokenfile = file_handle.read()
    if "readonly" in tokenfile:
        return False
    return True


def setup_services(hass, track_new_found_calendars, calendar_service):
    """Set up the service listeners."""

    def _found_calendar(call):
        """Check if we know about a calendar and generate PLATFORM_DISCOVER."""
        calendar = get_calendar_info(hass, call.data)
        if hass.data[DOMAIN][DATA_INDEX].get(calendar[CONF_CAL_ID]) is None:
            return

        hass.data[DOMAIN][DATA_INDEX][calendar[CONF_CAL_ID]] = calendar

        update_config(hass.config.path(YAML_DEVICES), calendar)

        dispatcher_send(hass, DISCOVER_CALENDAR, calendar)

    hass.services.register(DOMAIN, SERVICE_FOUND_CALENDARS, _found_calendar)

    def _scan_for_calendars(call):
        """Scan for new calendars."""
        service = calendar_service.get()
        cal_list = service.calendarList()
        calendars = cal_list.list().execute()["items"]
        for calendar in calendars:
            calendar["track"] = track_new_found_calendars
            hass.services.call(DOMAIN, SERVICE_FOUND_CALENDARS, calendar)

    hass.services.register(DOMAIN, SERVICE_SCAN_CALENDARS, _scan_for_calendars)

    def _add_event(call):
        """Add a new event to calendar."""
        service = calendar_service.get()
        start = {}
        end = {}

        if EVENT_IN in call.data:
            if EVENT_IN_DAYS in call.data[EVENT_IN]:
                now = datetime.now()

                start_in = now + timedelta(days=call.data[EVENT_IN][EVENT_IN_DAYS])
                end_in = start_in + timedelta(days=1)

                start = {"date": start_in.strftime("%Y-%m-%d")}
                end = {"date": end_in.strftime("%Y-%m-%d")}

            elif EVENT_IN_WEEKS in call.data[EVENT_IN]:
                now = datetime.now()

                start_in = now + timedelta(weeks=call.data[EVENT_IN][EVENT_IN_WEEKS])
                end_in = start_in + timedelta(days=1)

                start = {"date": start_in.strftime("%Y-%m-%d")}
                end = {"date": end_in.strftime("%Y-%m-%d")}

        elif EVENT_START_DATE in call.data:
            start = {"date": str(call.data[EVENT_START_DATE])}
            end = {"date": str(call.data[EVENT_END_DATE])}

        elif EVENT_START_DATETIME in call.data:
            start_dt = str(
                call.data[EVENT_START_DATETIME].strftime("%Y-%m-%dT%H:%M:%S")
            )
            end_dt = str(call.data[EVENT_END_DATETIME].strftime("%Y-%m-%dT%H:%M:%S"))
            start = {"dateTime": start_dt, "timeZone": str(hass.config.time_zone)}
            end = {"dateTime": end_dt, "timeZone": str(hass.config.time_zone)}

        event = {
            "summary": call.data[EVENT_SUMMARY],
            "description": call.data[EVENT_DESCRIPTION],
            "start": start,
            "end": end,
        }
        service_data = {"calendarId": call.data[EVENT_CALENDAR_ID], "body": event}
        service.events().insert(**service_data).execute()

    hass.services.register(
        DOMAIN, SERVICE_ADD_EVENT, _add_event, schema=ADD_EVENT_SERVICE_SCHEMA
    )


def do_setup(hass, entry, config):
    """Run the setup after we have everything configured."""
    # Load calendars the user has configured
    hass.data[DOMAIN][DATA_INDEX] = load_config(hass.config.path(YAML_DEVICES))

    calendar_service = GoogleCalendarService(entry)
    hass.data[DOMAIN][DATA_CALENDAR_SERVICE] = calendar_service
    track_new_found_calendars = config[CONF_TRACK_NEW]
    setup_services(hass, track_new_found_calendars, calendar_service)


class GoogleCalendarService:
    """Calendar service interface to Google."""

    def __init__(self, entry):
        """Init the Google Calendar service."""
        self.entry = entry

    def get(self):
        """Get the calendar service from the stored token."""
        try:
            credentials = Credentials.from_authorized_user_info(self.entry.data)
        except ValueError:
            _LOGGER.error("Failed to generate credentials")
            raise
        # FIXME: Extract magic strings
        service = google_discovery.build(
            "calendar", "v3", credentials=credentials, cache_discovery=False
        )
        return service


def get_calendar_info(hass, calendar):
    """Convert data from Google into DEVICE_SCHEMA."""
    calendar_info = DEVICE_SCHEMA(
        {
            CONF_CAL_ID: calendar["id"],
            CONF_ENTITIES: [
                {
                    CONF_TRACK: calendar["track"],
                    CONF_NAME: calendar["summary"],
                    CONF_DEVICE_ID: generate_entity_id(
                        "{}", calendar["summary"], hass=hass
                    ),
                }
            ],
        }
    )
    return calendar_info


def load_config(path):
    """Load the google_calendar_devices.yaml."""
    calendars = {}
    try:
        with open(path) as file:
            data = yaml.safe_load(file)
            for calendar in data:
                try:
                    calendars.update({calendar[CONF_CAL_ID]: DEVICE_SCHEMA(calendar)})
                except VoluptuousError as exception:
                    # keep going
                    _LOGGER.warning("Calendar Invalid Data: %s", exception)
    except FileNotFoundError:
        # When YAML file could not be loaded/did not contain a dict
        return {}

    return calendars


def update_config(path, calendar):
    """Write the google_calendar_devices.yaml."""
    with open(path, "a") as out:
        out.write("\n")
        yaml.dump([calendar], out, default_flow_style=False)
