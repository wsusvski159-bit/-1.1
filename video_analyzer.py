from __future__ import annotations

import base64
import json
import math
import os
import shutil
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("DATA_DIR", str(BASE_DIR / "data"))).resolve()
REPORTS_DIR = DATA_DIR / "reports"
TMP_DIR = DATA_DIR / "tmp"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)
TMP_DIR.mkdir(parents=True, exist_ok=True)


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    except subprocess.CalledProcessError as e:
        stderr = (e.stderr or "").strip()
        tail = stderr[-1800:] if stderr else "没有收到 FFmpeg 的详细错误输出。"
        raise RuntimeError(f"FFmpeg 处理失败：{tail}") from e


def ensure_ffmpeg() -> None:
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        raise RuntimeError("没有检测到 FFmpeg/ffprobe。Render 版请确认仍在使用仓库里的 Dockerfile。")


def probe_duration(video_path: Path) -> float:
    out = _run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(video_path),
    ]).stdout.strip()
    try:
        return max(0.0, float(out))
    except Exception:
        return 0.0


def _transcode_for_inline(video_path: Path, work_dir: Path, duration: float, target_mb: float) -> Path:
    """准备适合 Gemini-compatible API inline_data 的 MP4。

    小体积 MP4 直接发送，避免 Render 免费实例为了"再压一次"而白白消耗 CPU/RAM。
    只有文件偏大时才低资源转码。
    """
    target_bytes = max(4, int(target_mb * 1024 * 1024))

    # 手机拍出来的短 MP4 如果本来就够小，直接交给 Gemini。
    # 这也是最稳的路径：不改画面、不改声音、不额外吃 Render 资源。
    if video_path.suffix.lower() in {".mp4", ".m4v"} and video_path.stat().st_size <= target_bytes:
        return video_path

    out = work_dir / "gemini-input.mp4"
    if duration > 0.3:
        total_kbps = int((target_bytes * 8 / duration) / 1000 * 0.82)
        total_kbps = max(420, min(total_kbps, 1800))
    else:
        total_kbps = 1000
    audio_kbps = 64
    video_kbps = max(320, total_kbps - audio_kbps)

    def encode(v_kbps: int) -> None:
        _run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(video_path),
            "-map", "0:v:0", "-map", "0:a?",
            "-vf", "scale='min(720,iw)':-2:force_original_aspect_ratio=decrease",
            "-c:v", "libx264", "-preset", "ultrafast", "-threads", "1", "-pix_fmt", "yuv420p",
            "-b:v", f"{v_kbps}k", "-maxrate", f"{int(v_kbps * 1.15)}k", "-bufsize", f"{int(v_kbps * 1.5)}k",
            "-c:a", "aac", "-b:a", f"{audio_kbps}k", "-ac", "1", "-ar", "32000",
            "-movflags", "+faststart",
            str(out),
        ])

    encode(video_kbps)
    if not out.exists() or out.stat().st_size == 0:
        raise RuntimeError("视频转码失败。请换一个常见视频格式（如 MP4/H.264）再试。")

    # 如果估算仍偏大，再压一次；继续保持单线程，优先兼容 Render Free。
    if out.stat().st_size > target_bytes * 1.12:
        encode(max(260, int(video_kbps * 0.62)))

    return out

def _api_settings() -> tuple[str, str, str, str]:
    # 公共版不内置任何人的 Key。优先使用通用变量名，同时兼容早期 NEWAPI_* 变量。
    api_key = (os.getenv("GEMINI_API_KEY", "") or os.getenv("NEWAPI_API_KEY", "")).strip()
    if not api_key:
        raise RuntimeError("还没有配置 GEMINI_API_KEY（或兼容变量 NEWAPI_API_KEY）。")

    base_url = (
        os.getenv("GEMINI_BASE_URL", "")
        or os.getenv("NEWAPI_BASE_URL", "")
        or "https://generativelanguage.googleapis.com"
    ).strip().rstrip("/")
    primary = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()
    fallback = os.getenv("GEMINI_FALLBACK_MODEL", "").strip()
    return api_key, base_url, primary, fallback


def _prompt(duration: float) -> str:
    return f"""
你正在观看并聆听一段约 {duration:.1f} 秒的短视频。请同时使用视频画面和视频原始音轨来理解它。

目标：生成一份给另一个 AI 随后和用户自然聊这条视频时使用的“音画观察报告”。

请严格遵守：
- 只把视频里明确看见或听见的内容当事实；不确定就明确说不确定，不要脑补。
- 尽量按时间顺序描述关键事件，并给出近似时间点。
- 不只转写说话内容，也注意语气、笑声、停顿、音乐、音效、环境声、节奏和音画反差。
- 屏幕上的字幕或文字只有在能看清时才写，不要猜小字。
- 不要猜现实人物身份。
- 如果音频里没有清晰语音，也要描述能听到的音乐/音效/环境声。

请只返回一个 JSON 对象，不要 Markdown 代码块，字段必须为：
{{
  "summary": "一句话概括",
  "timeline": [{{"time": "约 0:05", "event": "关键事件"}}],
  "visual": "主要画面、人物/物体、动作、场景、可确认文字",
  "audio": "台词、语气、音乐、音效、环境声",
  "transcript": "尽可能完整的可听清语音转写；没有清晰语音就写空字符串",
  "av_relationship": "声音和画面的配合、反差、节奏、情绪或笑点",
  "discussion_points": ["最值得一起聊的点"],
  "uncertainty": ["看不清/听不清/无法确定的地方"]
}}
""".strip()


def _extract_response_text(data: dict[str, Any]) -> str:
    candidates = data.get("candidates") or []
    for candidate in candidates:
        content = (candidate or {}).get("content") or {}
        parts = content.get("parts") or []
        texts = [p.get("text", "") for p in parts if isinstance(p, dict) and p.get("text")]
        if texts:
            return "\n".join(texts).strip()
    # 让报错信息可读，但不要把鉴权信息带出来。
    if data.get("error"):
        err = data["error"]
        if isinstance(err, dict):
            raise RuntimeError(str(err.get("message") or err.get("status") or "Gemini API 返回错误"))
    raise RuntimeError("Gemini 没有返回可读内容。")


def _parse_json_text(text: str) -> dict[str, Any]:
    raw = text.strip()
    if raw.startswith("```"):
        raw = raw.strip("`").strip()
        if raw.lower().startswith("json"):
            raw = raw[4:].strip()
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass

    # 容错：有些中转会在 JSON 前后加一句话。
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        try:
            parsed = json.loads(raw[start:end + 1])
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass

    return {
        "summary": "模型返回了非 JSON 格式的观察。",
        "timeline": [],
        "visual": raw,
        "audio": "",
        "transcript": "",
        "av_relationship": "",
        "discussion_points": [],
        "uncertainty": ["返回格式没有按预期结构化，但原始观察已保留。"],
    }


def _call_gemini(video_mp4: Path, duration: float, model: str, api_key: str, base_url: str) -> dict[str, Any]:
    encoded = base64.b64encode(video_mp4.read_bytes()).decode("ascii")
    url = f"{base_url}/v1beta/models/{model}:generateContent"
    payload = {
        "contents": [{
            "role": "user",
            "parts": [
                {"text": _prompt(duration)},
                {"inline_data": {"mime_type": "video/mp4", "data": encoded}},
            ],
        }],
        "generationConfig": {
            "temperature": 0.2,
            "responseMimeType": "application/json",
        },
    }

    try:
        with httpx.Client(timeout=httpx.Timeout(240.0, connect=30.0)) as client:
            resp = client.post(url, params={"key": api_key}, json=payload)
    except httpx.RequestError as e:
        raise RuntimeError(f"连接视频 API 失败：{e.__class__.__name__}") from e

    if resp.status_code >= 400:
        message = ""
        try:
            body = resp.json()
            err = body.get("error") if isinstance(body, dict) else None
            if isinstance(err, dict):
                message = str(err.get("message") or err.get("status") or "")
            elif isinstance(body, dict):
                message = str(body.get("message") or "")
        except Exception:
            message = resp.text[:500]
        message = message.replace(api_key, "***") if api_key else message
        raise RuntimeError(f"{model} 请求失败（HTTP {resp.status_code}）：{message or '上游没有给出详细原因'}")

    try:
        data = resp.json()
    except Exception as e:
        raise RuntimeError("视频 API 返回的不是 JSON。") from e

    text = _extract_response_text(data)
    return _parse_json_text(text)


def _timeline_text(items: Any) -> str:
    if not isinstance(items, list) or not items:
        return "（模型没有单独列出时间线。）"
    lines = []
    for item in items:
        if isinstance(item, dict):
            t = str(item.get("time") or "").strip()
            ev = str(item.get("event") or "").strip()
            if ev:
                lines.append(f"- {t + ' ' if t else ''}{ev}")
        elif item:
            lines.append(f"- {item}")
    return "\n".join(lines) or "（模型没有单独列出时间线。）"


def _list_text(items: Any) -> str:
    if isinstance(items, list):
        vals = [str(x).strip() for x in items if str(x).strip()]
        return "\n".join(f"- {x}" for x in vals) if vals else "（无）"
    if items:
        return str(items)
    return "（无）"


def _compose_analysis(obs: dict[str, Any]) -> str:
    return "\n\n".join([
        "1. 一句话概括\n" + str(obs.get("summary") or "（未提供）"),
        "2. 关键时间线\n" + _timeline_text(obs.get("timeline")),
        "3. 我看到了什么\n" + str(obs.get("visual") or "（未提供）"),
        "4. 我听到了什么\n" + str(obs.get("audio") or "（未提供）"),
        "5. 音画关系\n" + str(obs.get("av_relationship") or "（未提供）"),
        "6. 最值得一起聊的地方\n" + _list_text(obs.get("discussion_points")),
        "7. 我不确定的地方\n" + _list_text(obs.get("uncertainty")),
    ])


def analyze_video(video_path: Path, original_name: str) -> dict[str, Any]:
    ensure_ffmpeg()
    api_key, base_url, primary_model, fallback_model = _api_settings()

    max_duration = float(os.getenv("MAX_DURATION_SECONDS", "60"))
    max_upload_mb = float(os.getenv("MAX_UPLOAD_MB", "80"))
    inline_target_mb = float(os.getenv("GEMINI_INLINE_TARGET_MB", "14"))

    size_mb = video_path.stat().st_size / (1024 * 1024)
    if size_mb > max_upload_mb:
        raise RuntimeError(f"视频约 {size_mb:.1f}MB，超过当前 {max_upload_mb:.0f}MB 上传上限。先剪短或压小一点再试。")

    duration = probe_duration(video_path)
    if duration > max_duration:
        raise RuntimeError(f"视频约 {duration:.1f} 秒，超过当前 {max_duration:.0f} 秒上限。先剪到一分钟以内再上传。")

    work_dir = TMP_DIR / f"job-{uuid.uuid4().hex}"
    work_dir.mkdir(parents=True, exist_ok=True)
    try:
        prepared = _transcode_for_inline(video_path, work_dir, duration, inline_target_mb)
        prepared_mb = prepared.stat().st_size / (1024 * 1024)
        # Google generateContent 的 inline 视频适合小请求；留出 base64/JSON 的空间。
        if prepared_mb > inline_target_mb * 1.25:
            raise RuntimeError(f"自动压缩后仍有 {prepared_mb:.1f}MB，暂时不适合 inline 视频请求。请把视频再剪短一点。")

        used_model = primary_model
        fallback_error = None
        try:
            obs = _call_gemini(prepared, duration, primary_model, api_key, base_url)
        except Exception as first_error:
            if fallback_model and fallback_model != primary_model:
                fallback_error = str(first_error)
                used_model = fallback_model
                obs = _call_gemini(prepared, duration, fallback_model, api_key, base_url)
            else:
                raise
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)

    video_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    transcript = str(obs.get("transcript") or "").strip()
    audio_obs = str(obs.get("audio") or "").strip()
    final_analysis = _compose_analysis(obs)

    report = {
        "video_id": video_id,
        "original_name": original_name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "duration_seconds": round(duration, 3),
        "size_mb": round(size_mb, 3),
        "analysis": final_analysis,
        "transcript": transcript or "（没有得到清晰语音转写；请看声音观察。）",
        "audio_observation": audio_obs or "（模型没有单独返回声音观察。）",
        "frame_times_seconds": [],
        "models": {
            "video_audio_understanding": used_model,
            "primary": primary_model,
            "fallback": fallback_model,
        },
        "pipeline": "小 MP4 直接发送；较大视频才用低资源 FFmpeg 压缩 → Gemini-compatible API inline_data 同时看画面+听音轨 → 保存音画报告",
        "gateway": base_url,
        "primary_model_error_before_fallback": fallback_error,
        "raw_structured_observation": obs,
    }
    (REPORTS_DIR / f"{video_id}.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return report


def list_reports(limit: int = 10) -> list[dict[str, Any]]:
    files = sorted(REPORTS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]
    out = []
    for p in files:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            out.append({k: data.get(k) for k in ["video_id", "original_name", "created_at", "duration_seconds"]})
        except Exception:
            pass
    return out


def get_report(video_id: str) -> dict[str, Any] | None:
    path = REPORTS_DIR / f"{video_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
