"""
Firebase Cloud Messaging over the HTTP v1 API.
Signs a short-lived Google OAuth token with the service account, then sends each device
its own message. The private key and device tokens are never written to logs.
"""

import asyncio
import json
import time
from dataclasses import dataclass, field

import httpx
import jwt
from loguru import logger

from app.core.config import settings
from app.core.exceptions import ServiceUnavailableError

ANDROID_CHANNEL_ID = "creditvance_reminders"
_TOKEN_URL = "https://oauth2.googleapis.com/token"
_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
_STALE_ERROR_CODES = {"UNREGISTERED", "NOT_FOUND", "SENDER_ID_MISMATCH"}


@dataclass
class PushSendResult:
    success_count: int = 0
    failure_count: int = 0
    invalid_tokens: list[str] = field(default_factory=list)
    error: str | None = None


class FirebasePushService:
    def __init__(self) -> None:
        self._ready = False
        self._project_id: str | None = None
        self._client_email: str | None = None
        self._private_key: str | None = None
        self._access_token: str | None = None
        self._access_token_expiry: float = 0
        self._token_lock = asyncio.Lock()

    def status(self) -> dict[str, object]:
        path = settings.resolved_firebase_credentials_path
        return {
            "enabled": settings.FIREBASE_ENABLED,
            "configured": path.is_file(),
            "initialized": self._ready,
            "project_id": self._project_id,
            "android_channel_id": ANDROID_CHANNEL_ID,
        }

    def initialize(self) -> bool:
        """Read the service account once. A missing file disables sending and leaves the API up."""
        if not settings.FIREBASE_ENABLED:
            logger.info("Firebase push is disabled via FIREBASE_ENABLED=false.")
            return False
        if self._ready:
            return True

        path = settings.resolved_firebase_credentials_path
        if not path.is_file():
            logger.warning(f"Firebase credentials file not found at {path}. Push sending is disabled.")
            return False

        try:
            with path.open(encoding="utf-8") as handle:
                info = json.load(handle)
            project_id = info.get("project_id")
            client_email = info.get("client_email")
            private_key = info.get("private_key")
            if info.get("type") != "service_account" or not project_id or not client_email or not private_key:
                logger.error("Firebase credentials file is not a usable service account.")
                return False
            self._project_id = str(project_id)
            self._client_email = str(client_email)
            self._private_key = str(private_key)
            self._ready = True
            logger.info(f"Firebase push initialized for project {self._project_id}.")
            return True
        except Exception as exc:
            logger.exception(f"Firebase initialization failed: {type(exc).__name__}")
            self._ready = False
            return False

    async def send_to_tokens(
        self,
        tokens: list[str],
        title: str,
        body: str,
        data: dict[str, str],
    ) -> PushSendResult:
        cleaned = [token.strip() for token in tokens if token and token.strip()]
        if not cleaned:
            return PushSendResult()
        if not self._ready and not self.initialize():
            raise ServiceUnavailableError("Push notifications are not configured on the server.")

        payload = {key: str(value) for key, value in data.items() if value is not None}
        result = PushSendResult()
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                access_token = await self._access_token_value(client)
                pairs = await asyncio.gather(
                    *[
                        self._send_one(client, access_token, token, title, body, payload)
                        for token in cleaned
                    ]
                )
        except ServiceUnavailableError:
            raise
        except Exception as exc:
            logger.exception(f"Firebase send failed: {type(exc).__name__}")
            return PushSendResult(failure_count=len(cleaned), error="Push delivery failed.")

        for token, outcome in pairs:
            if outcome == "sent":
                result.success_count += 1
            else:
                result.failure_count += 1
                if outcome == "stale":
                    result.invalid_tokens.append(token)
                    logger.info("Dropping an unregistered Firebase device token.")
        if result.failure_count and result.success_count == 0 and not result.invalid_tokens:
            result.error = "Push delivery failed."
        return result

    async def _access_token_value(self, client: httpx.AsyncClient) -> str:
        async with self._token_lock:
            if self._access_token and time.time() < self._access_token_expiry - 60:
                return self._access_token
            now = int(time.time())
            assertion = jwt.encode(
                {
                    "iss": self._client_email,
                    "scope": _SCOPE,
                    "aud": _TOKEN_URL,
                    "iat": now,
                    "exp": now + 3600,
                },
                self._private_key,
                algorithm="RS256",
            )
            response = await client.post(
                _TOKEN_URL,
                data={
                    "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                    "assertion": assertion,
                },
            )
            if response.status_code != 200:
                logger.error(f"Firebase OAuth token request failed with status {response.status_code}.")
                raise ServiceUnavailableError("Push notifications could not authenticate with Firebase.")
            body = response.json()
            self._access_token = str(body["access_token"])
            self._access_token_expiry = time.time() + int(body.get("expires_in", 3600))
            return self._access_token

    async def _send_one(
        self,
        client: httpx.AsyncClient,
        access_token: str,
        token: str,
        title: str,
        body: str,
        data: dict[str, str],
    ) -> tuple[str, str]:
        url = f"https://fcm.googleapis.com/v1/projects/{self._project_id}/messages:send"
        message = {
            "message": {
                "token": token,
                "notification": {"title": title, "body": body},
                "data": data,
                "android": {
                    "priority": "HIGH",
                    "collapse_key": (data.get("type") or "general")[:64],
                    "notification": {
                        "channel_id": ANDROID_CHANNEL_ID,
                        "sound": "default",
                    },
                },
                "apns": {
                    "headers": {"apns-priority": "10"},
                    "payload": {"aps": {"sound": "default"}},
                },
            }
        }
        response = await client.post(
            url,
            headers={"Authorization": f"Bearer {access_token}"},
            json=message,
        )
        if response.status_code == 200:
            return token, "sent"
        if response.status_code == 401:
            # Access token may have been revoked. One refresh, then a single retry.
            self._access_token = None
            refreshed = await self._access_token_value(client)
            retry = await client.post(
                url,
                headers={"Authorization": f"Bearer {refreshed}"},
                json=message,
            )
            if retry.status_code == 200:
                return token, "sent"
            response = retry
        if _is_stale_response(response):
            return token, "stale"
        logger.warning(f"Firebase rejected a message with status {response.status_code}.")
        return token, "failed"


def _is_stale_response(response: httpx.Response) -> bool:
    try:
        body = response.json()
    except Exception:
        return False
    error = body.get("error") or {}
    status = str(error.get("status") or "")
    if status in _STALE_ERROR_CODES and status != "INVALID_ARGUMENT":
        return True
    for detail in error.get("details") or []:
        code = str(detail.get("errorCode") or "")
        if code in {"UNREGISTERED", "SENDER_ID_MISMATCH"}:
            return True
    message = str(error.get("message") or "").lower()
    return "registration token" in message and "not a valid" in message


firebase_push_service = FirebasePushService()
