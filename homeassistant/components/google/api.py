"""API for Google Calendars bound to Home Assistant OAuth."""
from typing import Any

from aiogoogle import Aiogoogle
from aiogoogle.auth import Oauth2Manager
from aiogoogle.auth.creds import ClientCreds, UserCreds

from homeassistant.helpers import config_entry_oauth2_flow

from .const import LOGGER


class AsyncConfigEntryAuth(Oauth2Manager):  # type: ignore
    """Provide Google Calendars authentication tied to an OAuth2 based config entry."""

    def __init__(
        self,
        oauth_session: config_entry_oauth2_flow.OAuth2Session,
    ) -> None:
        """Initialize Google Calendars auth."""
        super().__init__()
        self._oauth_session = oauth_session

    def get_user_creds(self) -> UserCreds:
        """Build UserCreds from token data."""
        return self._build_user_creds_from_res({**self._oauth_session.token})

    async def refresh(
        self, user_creds: UserCreds, client_creds: ClientCreds = None
    ) -> UserCreds:
        """Return a valid UserCreds instance."""
        if not self._oauth_session.valid_token:
            await self._oauth_session.async_ensure_token_valid()

        return self.get_user_creds()


class CalendarService:
    """Represent a calendar service."""

    def __init__(self, client: Aiogoogle) -> None:
        """Set up instance."""
        self.client = client
        # Close the any client.active_session attribute when exiting app.

    async def list_calendars(self) -> dict:
        """List calendars."""
        calendar_v3 = await self.client.discover("calendar", "v3")
        result: dict = await self.client.as_user(calendar_v3.calendarList.list())
        LOGGER.debug("List calendars result: %s", result)
        return result

    async def list_events(self, calendar_id: str = "primary", **kwargs: Any) -> dict:
        """List events of a calendar."""
        calendar_v3 = await self.client.discover("calendar", "v3")
        result: dict = await self.client.as_user(
            calendar_v3.events.list(calendarId=calendar_id, **kwargs)
        )
        LOGGER.debug("List events result: %s", result)
        return result

    async def insert_events(
        self, *, calendar_id: str = "primary", event_data: dict
    ) -> dict:
        """Insert calendar events."""
        calendar_v3 = await self.client.discover("calendar", "v3")
        result: dict = await self.client.as_user(
            calendar_v3.events.insert(calendarId=calendar_id, **event_data)
        )
        LOGGER.debug("Inserted events result: %s", result)
        return result
