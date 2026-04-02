import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from feishu_client import FeishuClient

load_dotenv()

app_id = os.environ.get("FEISHU_APP_ID", "")
app_secret = os.environ.get("FEISHU_APP_SECRET", "")

if not app_id or not app_secret:
    raise ValueError("Please set FEISHU_APP_ID and FEISHU_APP_SECRET environment variables")

feishu = FeishuClient(app_id, app_secret)

port = int(os.environ.get("PORT", 8000))

mcp = FastMCP(
    "Feishu Calendar",
    instructions="帮助用户在飞书中创建和管理日程。当用户说要建立日程/会议/安排时，使用 create_calendar_event 工具。",
    host="0.0.0.0",
    port=port,
)


@mcp.tool()
async def create_calendar_event(
    summary: str,
    start_time: str,
    end_time: str,
    description: str = "",
) -> str:
    """在飞书日历中创建一个日程事件。

    Args:
        summary: 日程标题，例如 "产品评审会议"
        start_time: 开始时间，ISO 8601 格式，例如 "2026-04-01T10:00:00+08:00"
        end_time: 结束时间，ISO 8601 格式，例如 "2026-04-01T11:00:00+08:00"
        description: 日程描述（可选）
    """
    try:
        start_dt = datetime.fromisoformat(start_time)
        end_dt = datetime.fromisoformat(end_time)

        start_ts = int(start_dt.timestamp())
        end_ts = int(end_dt.timestamp())

        event = await feishu.create_event(
            summary=summary,
            start_time=start_ts,
            end_time=end_ts,
            description=description,
        )
        event_id = event.get("event_id", "unknown")
        return f"日程创建成功！\n标题: {summary}\n开始: {start_time}\n结束: {end_time}\n事件ID: {event_id}"
    except Exception as e:
        return f"创建日程失败: {str(e)}"


@mcp.tool()
async def list_calendars() -> str:
    """列出飞书中可用的日历列表。"""
    try:
        calendars = await feishu.list_calendars()
        if not calendars:
            return "没有找到可用的日历。"
        lines = ["可用日历列表:"]
        for cal in calendars:
            name = cal.get("summary", "未命名")
            cal_id = cal.get("calendar_id", "")
            role = cal.get("role", "unknown")
            lines.append(f"  - {name} (权限: {role}, ID: {cal_id})")
        return "\n".join(lines)
    except Exception as e:
        return f"获取日历列表失败: {str(e)}"


# Remove outputSchema from tools (claude.ai doesn't support it yet)
for tool in mcp._tool_manager._tools.values():
    if hasattr(tool, 'output_schema'):
        tool.output_schema = None


if __name__ == "__main__":
    import asyncio
    import uvicorn
    from starlette.requests import Request
    from starlette.responses import JSONResponse, StreamingResponse
    from starlette.routing import Route

    async def health(request: Request):
        return JSONResponse({"status": "ok"})

    async def mcp_get_handler(request: Request):
        """Handle GET /mcp requests from claude.ai for SSE streaming.

        claude.ai sends GET /mcp without Accept: text/event-stream header,
        which causes the MCP SDK to return 406. This handler intercepts GET
        requests and returns a proper keep-alive SSE stream.
        """
        async def event_stream():
            # Send an initial comment to keep the connection alive
            yield ": ok\n\n"
            # Keep the stream open for a while
            try:
                while True:
                    await asyncio.sleep(30)
                    yield ": ping\n\n"
            except asyncio.CancelledError:
                return

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "Connection": "keep-alive",
            },
        )

    starlette_app = mcp.streamable_http_app()
    # Insert GET /mcp handler BEFORE the default MCP route to intercept GET requests
    starlette_app.routes.insert(0, Route("/mcp", mcp_get_handler, methods=["GET"]))
    starlette_app.routes.append(Route("/health", health, methods=["GET"]))

    uvicorn.run(starlette_app, host="0.0.0.0", port=port)
