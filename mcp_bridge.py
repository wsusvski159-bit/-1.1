from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from video_analyzer import get_report, list_reports

mcp = FastMCP(
    "共看",
    instructions=(
        "只读视频分析报告。用户说‘看刚才那个视频’、‘读最新视频’、"
        "‘刚才视频里发生了什么’时，优先调用 get_latest_video_report。"
    ),
    stateless_http=True,
    json_response=True,
)

READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)


@mcp.tool(annotations=READ_ONLY)
def list_recent_videos(limit: int = 8) -> list[dict[str, Any]]:
    """列出最近分析过的视频。只读，不会修改或删除任何内容。"""
    limit = max(1, min(int(limit), 20))
    return list_reports(limit)


@mcp.tool(annotations=READ_ONLY)
def get_latest_video_report() -> dict[str, Any]:
    """读取最近一条视频的完整音画分析报告。用户说‘刚才那个视频’时使用。"""
    recent = list_reports(1)
    if not recent:
        return {"ok": False, "message": "还没有视频分析报告。"}
    report = get_report(str(recent[0]["video_id"]))
    if not report:
        return {"ok": False, "message": "最新报告暂时读取不到。"}
    return {"ok": True, "report": report}


@mcp.tool(annotations=READ_ONLY)
def get_video_report(video_id: str) -> dict[str, Any]:
    """按报告 ID 读取指定视频的完整音画分析报告。只读。"""
    report = get_report(video_id.strip())
    if not report:
        return {"ok": False, "message": f"没有找到报告 {video_id}"}
    return {"ok": True, "report": report}
