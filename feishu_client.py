import time
import httpx


class FeishuClient:
    BASE_URL = "https://open.feishu.cn/open-apis"

    def __init__(self, app_id: str, app_secret: str):
        self.app_id = app_id
        self.app_secret = app_secret
        self._token: str | None = None
        self._token_expires_at: float = 0

    async def _get_token(self) -> str:
        if self._token and time.time() < self._token_expires_at:
            return self._token

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.BASE_URL}/auth/v3/tenant_access_token/internal",
                json={"app_id": self.app_id, "app_secret": self.app_secret},
            )
            resp.raise_for_status()
            data = resp.json()

        if data.get("code") != 0:
            raise Exception(f"Failed to get token: {data.get('msg')}")

        self._token = data["tenant_access_token"]
        self._token_expires_at = time.time() + data.get("expire", 7200) - 300
        return self._token

    async def _request(self, method: str, path: str, **kwargs) -> dict:
        token = await self._get_token()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"}

        async with httpx.AsyncClient() as client:
            resp = await client.request(method, f"{self.BASE_URL}{path}", headers=headers, **kwargs)
            resp.raise_for_status()
            return resp.json()

    async def list_calendars(self) -> list[dict]:
        data = await self._request("GET", "/calendar/v4/calendars")
        if data.get("code") != 0:
            raise Exception(f"Failed to list calendars: {data.get('msg')}")
        return data.get("data", {}).get("calendar_list", [])

    async def get_primary_calendar_id(self) -> str:
        calendars = await self.list_calendars()
        for cal in calendars:
            if cal.get("role") in ("owner", "writer"):
                return cal["calendar_id"]
        raise Exception("No writable calendar found")

    async def create_event(
        self,
        summary: str,
        start_time: int,
        end_time: int,
        description: str = "",
        calendar_id: str | None = None,
    ) -> dict:
        if not calendar_id:
            calendar_id = await self.get_primary_calendar_id()

        body = {
            "summary": summary,
            "start_time": {"timestamp": str(start_time)},
            "end_time": {"timestamp": str(end_time)},
        }
        if description:
            body["description"] = description

        data = await self._request(
            "POST",
            f"/calendar/v4/calendars/{calendar_id}/events",
            json=body,
        )
        if data.get("code") != 0:
            raise Exception(f"Failed to create event: {data.get('msg')}")
        return data.get("data", {}).get("event", {})
