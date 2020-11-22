"""API for Google Calendars bound to Home Assistant OAuth."""
from datetime import datetime
from functools import wraps
import logging
from typing import Any

from aiogoogle import Aiogoogle, AiogoogleError, AuthError, HTTPError
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
        token_data = {**self._oauth_session.token}
        scopes = token_data.pop("scope").split(" ")
        # Use offset-naive datetime explicitly to match library.
        expires_at = datetime.utcfromtimestamp(token_data.pop("expires_at"))
        return UserCreds(**token_data, expires_at=expires_at.isoformat(), scopes=scopes)

    async def refresh(
        self, user_creds: UserCreds, client_creds: ClientCreds = None
    ) -> UserCreds:
        """Return a valid UserCreds instance."""
        if not self._oauth_session.valid_token:
            await self._oauth_session.async_ensure_token_valid()

        return self.get_user_creds()


def log_catch_api(api_name):
    """Return decorator that logs and catches Google api failures."""

    def decorator(func):
        """Return a function wrapper."""

        @wraps(func)
        async def wrapper(*args, **kwargs):
            """Wrap a Google api call."""
            try:
                result = await func(*args, **kwargs)
            except AuthError as exc:
                LOGGER.error(
                    "Failed to authenticate during call to %s. "
                    "Please remove and re-add integration: %s",
                    api_name,
                    exc,
                )
                raise
            except HTTPError as exc:
                level = logging.ERROR
                if exc.res.status_code == 404:
                    level = logging.DEBUG

                LOGGER.log(level, "Failed calling %s: %s", api_name, exc)
                raise

            except AiogoogleError as exc:
                LOGGER.error("Failed calling %s: %s", api_name, exc)
                raise
            else:
                LOGGER.debug("Called %s: %s", api_name, result)
                return result

        return wrapper

    return decorator


class CalendarService:
    """Represent a calendar service."""

    def __init__(self, client: Aiogoogle) -> None:
        """Set up instance."""
        self.client = client
        # Close the any client.active_session attribute when exiting app.

    @log_catch_api("list_calendars")
    async def list_calendars(self) -> dict:
        """List calendars."""
        calendar_v3 = await self.client.discover("calendar", "v3")
        result: dict = await self.client.as_user(calendar_v3.calendarList.list())
        return result

    @log_catch_api("list_events")
    async def list_events(self, calendar_id: str = "primary", **kwargs: Any) -> dict:
        """List events of a calendar."""
        calendar_v3 = await self.client.discover("calendar", "v3")
        result: dict = await self.client.as_user(
            calendar_v3.events.list(calendarId=calendar_id, **kwargs)
        )
        return result

    @log_catch_api("insert_events")
    async def insert_events(
        self, *, calendar_id: str = "primary", event_data: dict
    ) -> dict:
        """Insert calendar events."""
        calendar_v3 = await self.client.discover("calendar", "v3")
        result: dict = await self.client.as_user(
            calendar_v3.events.insert(calendarId=calendar_id, **event_data)
        )
        return result
