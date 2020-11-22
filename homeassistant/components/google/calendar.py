"""Support for Google Calendar Search binary sensors."""
import copy
from datetime import timedelta

from homeassistant.components.calendar import (
    ENTITY_ID_FORMAT,
    CalendarEventDevice,
    calculate_offset,
    is_offset_reached,
)
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import async_generate_entity_id
from homeassistant.util import Throttle, dt

from . import (
    CONF_CAL_ID,
    CONF_DEVICE_ID,
    CONF_ENTITIES,
    CONF_IGNORE_AVAILABILITY,
    CONF_MAX_RESULTS,
    CONF_NAME,
    CONF_OFFSET,
    CONF_SEARCH,
    CONF_TRACK,
    DEFAULT_CONF_OFFSET,
    SERVICE_SCAN_CALENDARS,
)
from .const import (
    CALENDAR_SERVICE,
    DISCOVER_CALENDAR,
    DISPATCHERS,
    DOMAIN as GOOGLE_DOMAIN,
)

DEFAULT_GOOGLE_SEARCH_PARAMS = {
    "orderBy": "startTime",
    "maxResults": 5,
    "singleEvents": True,
}

MIN_TIME_BETWEEN_UPDATES = timedelta(minutes=15)


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the google calendar platform."""

    async def async_discover(discovery_info):
        await _async_setup_entities(hass, entry, async_add_entities, discovery_info)

    unsub = async_dispatcher_connect(hass, DISCOVER_CALENDAR, async_discover)
    hass.data[GOOGLE_DOMAIN][DISPATCHERS].append(unsub)

    # Look for any new calendars
    await hass.services.async_call(GOOGLE_DOMAIN, SERVICE_SCAN_CALENDARS, blocking=True)


async def _async_setup_entities(hass, entry, async_add_entities, discovery_info):
    """Set up the Google calendars."""
    if discovery_info is None:
        return

    if not any(data[CONF_TRACK] for data in discovery_info[CONF_ENTITIES]):
        return

    calendar_service = hass.data[GOOGLE_DOMAIN][entry.entry_id][CALENDAR_SERVICE]
    entities = []
    for data in discovery_info[CONF_ENTITIES]:
        if not data[CONF_TRACK]:
            continue
        entity_id = async_generate_entity_id(
            ENTITY_ID_FORMAT, data[CONF_DEVICE_ID], hass=hass
        )
        entity = GoogleCalendarEventDevice(
            calendar_service, discovery_info[CONF_CAL_ID], data, entity_id
        )
        entities.append(entity)

    async_add_entities(entities, True)


class GoogleCalendarEventDevice(CalendarEventDevice):
    """A calendar event device."""

    def __init__(self, calendar_service, calendar_id, data, entity_id):
        """Create the Calendar event device."""
        self.data = GoogleCalendarData(
            calendar_service,
            calendar_id,
            data.get(CONF_SEARCH),
            data.get(CONF_IGNORE_AVAILABILITY),
            data.get(CONF_MAX_RESULTS),
        )
        self._event = None
        self._name = data[CONF_NAME]
        self._offset = data.get(CONF_OFFSET, DEFAULT_CONF_OFFSET)
        self._offset_reached = False
        self.entity_id = entity_id

    @property
    def device_state_attributes(self):
        """Return the device state attributes."""
        return {"offset_reached": self._offset_reached}

    @property
    def event(self):
        """Return the next upcoming event."""
        return self._event

    @property
    def name(self):
        """Return the name of the entity."""
        return self._name

    async def async_get_events(self, hass, start_date, end_date):
        """Get all events in a specific time frame."""
        return await self.data.async_get_events(hass, start_date, end_date)

    async def async_update(self):
        """Update event data."""
        await self.data.async_update()
        event = copy.deepcopy(self.data.event)
        if event is None:
            self._event = event
            return
        event = calculate_offset(event, self._offset)
        self._offset_reached = is_offset_reached(event)
        self._event = event


class GoogleCalendarData:
    """Class to utilize calendar service object to get next event."""

    def __init__(
        self, calendar_service, calendar_id, search, ignore_availability, max_results
    ):
        """Set up how we are going to search the google calendar."""
        self.calendar_service = calendar_service
        self.calendar_id = calendar_id
        self.search = search
        self.ignore_availability = ignore_availability
        self.max_results = max_results
        self.event = None

    def _prepare_query(self):
        params = dict(DEFAULT_GOOGLE_SEARCH_PARAMS)
        if self.max_results:
            params["maxResults"] = self.max_results
        if self.search:
            params["q"] = self.search

        return params

    async def async_get_events(self, hass, start_date, end_date):
        """Get all events in a specific time frame."""
        params = self._prepare_query
        params["timeMin"] = start_date.isoformat("T")
        params["timeMax"] = end_date.isoformat("T")

        result = await self.calendar_service.list_events(self.calendar_id, **params)

        items = result.get("items", [])
        event_list = []
        for item in items:
            if not self.ignore_availability and "transparency" in item:
                if item["transparency"] == "opaque":
                    event_list.append(item)
            else:
                event_list.append(item)
        return event_list

    @Throttle(MIN_TIME_BETWEEN_UPDATES)
    async def async_update(self):
        """Get the latest data."""
        params = self._prepare_query()
        params["timeMin"] = dt.now().isoformat("T")

        result = await self.calendar_service.list_events(self.calendar_id, **params)

        items = result.get("items", [])

        new_event = None
        for item in items:
            if not self.ignore_availability and "transparency" in item:
                if item["transparency"] == "opaque":
                    new_event = item
                    break
            else:
                new_event = item
                break

        self.event = new_event
