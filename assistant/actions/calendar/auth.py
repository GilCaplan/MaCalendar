"""MSAL authentication for Microsoft Graph API."""

import os
from typing import List

import msal

from assistant.config import MicrosoftConfig
from assistant.exceptions import AuthError, AuthExpiredError

SCOPES: List[str] = ["Calendars.ReadWrite", "User.Read"]


class MSALAuth:
    """
    Manages Microsoft OAuth tokens using MSAL's device-code flow.

    Token cache is persisted to disk so the user only needs to authenticate once.
    Silent refresh handles expiry automatically.
    """

    def __init__(self, config: MicrosoftConfig) -> None:
        self.config = config
        self.cache_path = os.path.expanduser(config.token_cache_path)
        self._cache = msal.SerializableTokenCache()

        if os.path.exists(self.cache_path):
            with open(self.cache_path) as f:
                self._cache.deserialize(f.read())

        self._app = msal.PublicClientApplication(
            config.client_id,
            authority=f"https://login.microsoftonline.com/{config.tenant_id}",
            token_cache=self._cache,
        )

    def get_token(self) -> str:
        """
        Return a valid access token. Tries silent refresh first.
        Raises AuthExpiredError if silent refresh fails (user must re-authenticate).
        """
        accounts = self._app.get_accounts()
        if accounts:
            result = self._app.acquire_token_silent(SCOPES, account=accounts[0])
            if result and "access_token" in result:
                self._save_cache()
                return result["access_token"]

        raise AuthExpiredError(
            "Microsoft token expired or missing. "
            "Run `python scripts/setup_auth.py` or use the Re-authenticate menu item."
        )

    def start_device_flow(self) -> dict:
        """
        Begin the device-code flow. Returns the flow dict, which includes
        'message' (human-readable instructions), 'user_code', and
        'verification_uri' — display these to the user before calling
        complete_device_flow(), which blocks until they finish in a browser.
        """
        flow = self._app.initiate_device_flow(scopes=SCOPES)
        if "user_code" not in flow:
            raise AuthError(
                f"Failed to start device-code flow: {flow.get('error_description', 'unknown error')}"
            )
        return flow

    def complete_device_flow(self, flow: dict) -> str:
        """Blocks until the user finishes authenticating at the flow's URL.

        Returns the access token on success.
        """
        result = self._app.acquire_token_by_device_flow(flow)
        if "access_token" not in result:
            raise AuthError(
                f"Authentication failed: {result.get('error_description', 'unknown error')}"
            )

        self._save_cache()
        return result["access_token"]

    def device_code_flow(self) -> str:
        """
        Full interactive device-code flow. Prints a URL + code for the user to enter
        at https://microsoft.com/devicelogin. Blocks until authentication completes.

        Returns the access token on success.
        """
        flow = self.start_device_flow()
        # This message contains the URL and one-time code.
        print(flow["message"])
        return self.complete_device_flow(flow)

    def force_reauth(self) -> str:
        """Wipe the token cache and run a fresh device-code flow."""
        if os.path.exists(self.cache_path):
            os.remove(self.cache_path)
        self._cache = msal.SerializableTokenCache()
        self._app.token_cache = self._cache
        return self.device_code_flow()

    def _save_cache(self) -> None:
        if self._cache.has_state_changed:
            os.makedirs(os.path.dirname(self.cache_path), exist_ok=True)
            with open(self.cache_path, "w") as f:
                f.write(self._cache.serialize())
