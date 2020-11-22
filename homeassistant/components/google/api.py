"""API for Google Calendars bound to Home Assistant OAuth."""
from aiogoogle.auth import Oauth2Manager
from aiogoogle.auth.creds import ClientCreds, UserCreds

from homeassistant.helpers import config_entry_oauth2_flow


class AsyncConfigEntryAuth(Oauth2Manager):
    """Provide Google Calendars authentication tied to an OAuth2 based config entry."""

    def __init__(
        self,
        oauth_session: config_entry_oauth2_flow.OAuth2Session,
    ) -> None:
        """Initialize Google Calendars auth."""
        super().__init__()
        self._oauth_session = oauth_session

    async def refresh(
        self, user_creds: UserCreds, client_creds: ClientCreds = None
    ) -> UserCreds:
        """Return a valid UserCreds instance."""
        if not self._oauth_session.valid_token:
            await self._oauth_session.async_ensure_token_valid()

        return self._build_user_creds_from_res(self._oauth_session.token)
