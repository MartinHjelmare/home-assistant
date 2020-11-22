"""The Google Calendars integration."""
import asyncio
from datetime import datetime, timedelta
import logging

from aiogoogle import Aiogoogle
import voluptuous as vol
from voluptuous.error import Error as VoluptuousError
import yaml

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_CLIENT_ID, CONF_CLIENT_SECRET
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_entry_oauth2_flow, config_validation as cv
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.entity import async_generate_entity_id

from . import api, config_flow
from .const import (
    AUTH_MANAGER,
    CALENDAR_CONFIG,
    CALENDAR_SERVICE,
    DISCOVER_CALENDAR,
    DISPATCHERS,
    DOMAIN,
    OAUTH2_AUTHORIZE,
    OAUTH2_TOKEN,
)

_LOGGER = logging.getLogger(__name__)

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

YAML_DEVICES = f"{DOMAIN}_calendars.yaml"


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

PLATFORMS = ["calendar"]


async def async_setup(hass: HomeAssistant, config: dict):
    """Set up the Google Calendars component."""
    hass.data[DOMAIN] = {}

    if DOMAIN not in config:
        return True

    # Store legacy config for backwards compatibility for now.
    hass.data[DOMAIN][CONF_TRACK_NEW] = config[DOMAIN][CONF_TRACK_NEW]

    config_flow.OAuth2FlowHandler.async_register_implementation(
        hass,
        config_entry_oauth2_flow.LocalOAuth2Implementation(
            hass,
            DOMAIN,
            config[DOMAIN][CONF_CLIENT_ID],
            config[DOMAIN][CONF_CLIENT_SECRET],
            OAUTH2_AUTHORIZE,
            OAUTH2_TOKEN,
        ),
    )

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Google Calendars from a config entry."""
    implementation = (
        await config_entry_oauth2_flow.async_get_config_entry_implementation(
            hass, entry
        )
    )

    session = config_entry_oauth2_flow.OAuth2Session(hass, entry, implementation)

    google_entry_data = hass.data[DOMAIN].setdefault(entry.entry_id, {})
    auth_manager = google_entry_data[AUTH_MANAGER] = api.AsyncConfigEntryAuth(session)

    await async_do_setup(hass, entry, auth_manager)

    for component in PLATFORMS:
        hass.async_create_task(
            hass.config_entries.async_forward_entry_setup(entry, component)
        )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = all(
        await asyncio.gather(
            *[
                hass.config_entries.async_forward_entry_unload(entry, component)
                for component in PLATFORMS
            ]
        )
    )
    if unload_ok:
        dispatchers = hass.data[DOMAIN].pop(DISPATCHERS, [])
        for unsub_dispatcher in dispatchers:
            unsub_dispatcher()

        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def async_do_setup(
    hass: HomeAssistant, entry: ConfigEntry, auth_manager: api.AsyncConfigEntryAuth
) -> None:
    """Run the setup after we have everything configured."""
    # Load calendars the user has configured
    hass.data[DOMAIN][entry.entry_id][
        CALENDAR_CONFIG
    ] = await hass.async_add_executor_job(load_config, hass.config.path(YAML_DEVICES))
    track_new_found_calendars = hass.data[DOMAIN][CONF_TRACK_NEW]

    user_creds = await auth_manager.refresh()
    client = Aiogoogle(user_creds=user_creds)
    client.oauth2 = auth_manager
    calendar_service = CalendarService(client)

    hass.data[DOMAIN][entry.entry_id][CALENDAR_SERVICE] = CalendarService

    await async_setup_services(hass, entry, track_new_found_calendars, calendar_service)

    # Look for any new calendars
    await hass.services.async_call(DOMAIN, SERVICE_SCAN_CALENDARS, None)


class CalendarService:
    """Represent a calendar service."""

    def __init__(self, client: Aiogoogle) -> None:
        """Set up instance."""
        self.client = client

    async def list_calendars(self) -> dict:
        """List calendars."""
        async with self.client as client_session:
            calendar_v3 = await client_session.discover("calendar", "v3")
            return await client_session.as_user(calendar_v3.calendarList.list())

    async def list_events(self, calendar_id: str = "primary", **kwargs) -> dict:
        """List events of a calendar."""
        async with self.client as client_session:
            calendar_v3 = await client_session.discover("calendar", "v3")
            return await client_session.as_user(
                calendar_v3.events.list(calendarId=calendar_id, **kwargs)
            )

    async def insert_events(
        self, *, calendar_id: str = "primary", event_data: dict
    ) -> dict:
        """Insert calendar events."""
        async with self.client as client_session:
            calendar_v3 = await client_session.discover("calendar", "v3")
            return await client_session.as_user(
                calendar_v3.events.insert(calendarId=calendar_id, **event_data)
            )


async def async_setup_services(
    hass, entry, track_new_found_calendars, calendar_service
):
    """Set up the service listeners."""

    async def _found_calendar(call):
        """Check if we know about a calendar and generate PLATFORM_DISCOVER."""
        calendar = async_get_calendar_info(hass, call.data)
        if (
            hass.data[DOMAIN][entry.entry_id][CALENDAR_CONFIG].get(
                calendar[CONF_CAL_ID]
            )
            is not None
        ):
            return

        hass.data[DOMAIN][entry.entry_id][CALENDAR_CONFIG][
            calendar[CONF_CAL_ID]
        ] = calendar

        await hass.async_add_executor_job(
            update_config, hass.config.path(YAML_DEVICES), calendar
        )

        async_dispatcher_send(hass, DISCOVER_CALENDAR, calendar)

    hass.services.async_register(DOMAIN, SERVICE_FOUND_CALENDARS, _found_calendar)

    async def _scan_for_calendars(call):
        """Scan for new calendars."""
        calendars = await calendar_service.list_events()["items"]
        for calendar in calendars:
            calendar["track"] = track_new_found_calendars
            await hass.services.async_call(DOMAIN, SERVICE_FOUND_CALENDARS, calendar)

    hass.services.async_register(DOMAIN, SERVICE_SCAN_CALENDARS, _scan_for_calendars)

    async def _add_event(call):
        """Add a new event to calendar."""
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

        event = await calendar_service.insert_events(
            calendar_id=call.data[EVENT_CALENDAR_ID], event_data=event
        )

    hass.services.async_register(
        DOMAIN, SERVICE_ADD_EVENT, _add_event, schema=ADD_EVENT_SERVICE_SCHEMA
    )
    return True


def async_get_calendar_info(hass, calendar):
    """Convert data from Google into DEVICE_SCHEMA."""
    calendar_info = DEVICE_SCHEMA(
        {
            CONF_CAL_ID: calendar["id"],
            CONF_ENTITIES: [
                {
                    CONF_TRACK: calendar["track"],
                    CONF_NAME: calendar["summary"],
                    CONF_DEVICE_ID: async_generate_entity_id(
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
