"""Config flow for Google."""
import asyncio
from copy import deepcopy
from functools import partial
import logging

from aiohttp import web_response
import async_timeout
from google_auth_oauthlib.flow import Flow

from homeassistant import config_entries
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import callback

from .const import CLIENT_ID, CLIENT_SECRET, DOMAIN, GOOGLE_CLIENT_SECRETS, SCOPE

AUTH_CALLBACK_PATH = "/auth/google/callback"
AUTH_CALLBACK_NAME = "auth:google:callback"

_LOGGER = logging.getLogger(__name__)


@callback
def register_flow_implementation(hass, client_id, client_secret):
    """Register a flow implementation.

    client_id: Client id.
    client_secret: Client secret.
    """
    hass.data[DOMAIN][CLIENT_ID] = client_id
    hass.data[DOMAIN][CLIENT_SECRET] = client_secret


class GoogleFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL

    def __init__(self):
        """Instantiate config flow."""
        self._credentials = None
        self._google_flow = None

    async def async_step_import(self, user_input=None):
        """Handle external yaml configuration."""
        if self.hass.config_entries.async_entries(DOMAIN):
            return self.async_abort(reason="already_setup")
        return await self.async_step_auth()

    async def async_step_user(self, user_input=None):
        """Handle a flow start."""
        if self.hass.config_entries.async_entries(DOMAIN):
            return self.async_abort(reason="already_setup")

        if DOMAIN not in self.hass.data:
            return self.async_abort(reason="missing_configuration")

        return await self.async_step_auth()

    async def async_step_auth(self, user_input=None):
        """Create an entry for auth."""
        # Flow has been triggered from Google website
        if user_input:
            return await self.async_step_code(user_input)

        try:
            with async_timeout.timeout(10):
                url, state = await self._get_authorization_url()
        except asyncio.TimeoutError:
            return self.async_abort(reason="authorize_url_timeout")

        return self.async_external_step(step_id="auth", url=url)

    async def _get_authorization_url(self):
        """Get Google authorization url."""
        client_id = self.hass.data[DOMAIN][CLIENT_ID]
        client_secret = self.hass.data[DOMAIN][CLIENT_SECRET]
        # FIXME: Google does not allow ip address in the redirect
        # redirect_uri = f"{self.hass.config.api.base_url}{AUTH_CALLBACK_PATH}"
        # http://localhost:8123/auth/google/callback
        localhost = "http://localhost:8123"
        redirect_uri = f"{localhost}{AUTH_CALLBACK_PATH}"
        client_config = deepcopy(GOOGLE_CLIENT_SECRETS)
        client_config["web"]["client_id"] = client_id
        client_config["web"]["client_secret"] = client_secret
        client_config["web"]["redirect_uris"] = [redirect_uri]
        self._google_flow = google_flow = Flow.from_client_config(
            client_config, [SCOPE]
        )
        google_flow.redirect_uri = redirect_uri

        self.hass.http.register_view(GoogleAuthCallbackView())

        # Thanks to the state, we can forward the flow id to Google that will
        # add it in the callback.
        get_url = partial(
            google_flow.authorization_url,
            access_type="offline",
            include_granted_scopes="true",
            state=self.flow_id,
        )
        return await self.hass.async_add_executor_job(get_url)

    async def async_step_code(self, code):
        """Received code for authentication."""
        fetch_token = partial(self._google_flow.fetch_token, code=code)
        try:
            await self.hass.async_add_executor_job(fetch_token)
        except OSError:
            return self.async_abort(reason="code_exchange_fail")
        _LOGGER.info("Successfully authenticated with Google")
        return self.async_external_step_done(next_step_id="creation")

    async def async_step_creation(self, user_input=None):
        """Create Google api and entries."""
        creds = self._google_flow.credentials
        data = {
            "token": creds.token,
            "refresh_token": creds.refresh_token,
            "token_uri": creds.token_uri,
            "client_id": creds.client_id,
            "client_secret": creds.client_secret,
            "scopes": creds.scopes,
            "expiry": creds.expiry.isoformat(),
        }

        return self.async_create_entry(title="Google", data=data)


class GoogleAuthCallbackView(HomeAssistantView):
    """Google Authorization Callback View."""

    requires_auth = False
    url = AUTH_CALLBACK_PATH
    name = AUTH_CALLBACK_NAME

    @staticmethod
    async def get(request):
        """Receive authorization code."""
        if "code" not in request.query or "state" not in request.query:
            return web_response.Response(
                text="Missing code or state parameter in " + request.url
            )

        hass = request.app["hass"]
        hass.async_create_task(
            hass.config_entries.flow.async_configure(
                flow_id=request.query["state"], user_input=request.query["code"]
            )
        )

        return web_response.Response(
            headers={"content-type": "text/html"},
            text="<script>window.close()</script>",
        )
