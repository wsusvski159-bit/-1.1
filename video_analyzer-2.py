from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
import ipaddress

import httpx

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("DATA_DIR", str(BASE_DIR / "data"))).resolve()
REPORTS_DIR = DATA_DIR / "reports"
TMP_DIR = DATA_DIR / "tmp"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)
TMP_DIR.mkdir(parents=True, exist_ok=True)


def _run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if check and p.returncode != 0:
        stderr = (p.stderr or "").strip()
        tail = stderr[-1800:] if stderr else "没有收到 FFmpeg 的详细错误输出。"
        raise RuntimeError(f"FFmpeg 处理失败：{tail}")
    return p


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
    target_bytes = max(4, int(target_mb * 1024 * 1024))
    if video_path.suffix.lower() in {".mp4", ".m4v"} and video_path.stat().st_size <= target_bytes:
        return video_path

    out = work_dir / "model-input.mp4"
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
            "-vf", "scale='min(720,iw)':-2:force_original_aspect_ratio=decrease,pad=ceil(iw/2)*2:ceil(ih/2)*2",
            "-c:v", "libx264", "-preset", "ultrafast", "-threads", "1", "-pix_fmt", "yuv420p",
            "-b:v", f"{v_kbps}k", "-maxrate", f"{int(v_kbps * 1.15)}k", "-bufsize", f"{int(v_kbps * 1.5)}k",
            "-c:a", "aac", "-b:a", f"{audio_kbps}k", "-ac", "1", "-ar", "32000",
            "-movflags", "+faststart", str(out),
        ])

    encode(video_kbps)
    if not out.exists() or out.stat().st_size == 0:
        raise RuntimeError("视频转码失败。请换一个常见视频格式（如 MP4/H.264）再试。")
    if out.stat().st_size > target_bytes * 1.12:
        encode(max(260, int(video_kbps * 0.62)))
    return out


def _validate_remote_base_url(base_url: str) -> str:
    base = (base_url or "").strip().rstrip("/")
    if not base:
        raise RuntimeError("还没有配置 API Base URL。")
    if len(base) > 500:
        raise RuntimeError("API Base URL 太长。")
    parsed = urlparse(base)
    if parsed.scheme != "https" or not parsed.hostname:
        raise RuntimeError("API Base URL 必须是 https:// 开头的公网地址。")
    host = parsed.hostname.lower()
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        raise RuntimeError("为了安全，不能把 API Base URL 指向本机或局域网地址。")
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            raise RuntimeError("为了安全，不能把 API Base URL 指向私有网络地址。")
    except ValueError:
        pass
    return base


def _settings(overrides: dict[str, str] | None = None) -> dict[str, str]:
    overrides = overrides or {}

    def pick(key: str, *env_names: str, default: str = "") -> str:
        v = str(overrides.get(key) or "").strip()
        if v:
            return v
        for name in env_names:
            v = os.getenv(name, "").strip()
            if v:
                return v
        return default

    mode = pick("mode", "API_MODE", default="gemini").lower()
    if mode not in {"gemini", "openai"}:
        raise RuntimeError("API 类型只能选择 Gemini-compatible 或 OpenAI-compatible。")

    api_key = pick("api_key", "API_KEY", "GEMINI_API_KEY", "NEWAPI_API_KEY")
    if not api_key:
        raise RuntimeError("还没有连接自己的 API。请在共看的“API 设置”里填写 API Key。")
    if len(api_key) > 1200:
        raise RuntimeError("API Key 长度异常。")

    base_url = _validate_remote_base_url(pick("base_url", "API_BASE_URL", "GEMINI_BASE_URL", "NEWAPI_BASE_URL"))
    model = pick("model", "API_MODEL", "GEMINI_MODEL")
    if not model:
        raise RuntimeError("还没有填写模型名称。")
    if len(model) > 240:
        raise RuntimeError("模型名称太长。")

    fallback = pick("fallback", "API_FALLBACK_MODEL", "GEMINI_FALLBACK_MODEL")
    audio_model = pick("audio_model", "API_AUDIO_MODEL", default="whisper-1")
    auth_style = pick("auth_style", "GEMINI_AUTH_STYLE", default="query_key").lower()
    if auth_style not in {"query_key", "bearer"}:
        auth_style = "query_key"
    return {
        "mode": mode,
        "api_key": api_key,
        "base_url": base_url,
        "model": model,
        "fallback": fallback,
        "audio_model": audio_model,
        "auth_style": auth_style,
    }


def _prompt_direct(duration: float) -> str:
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


def _prompt_frames(duration: float, transcript: str, frame_count: int, audio_warning: str = "") -> str:
    transcript_block = transcript.strip() or "（没有可用的语音转写。）"
    warning_block = audio_warning.strip() or "无"
    return f"""
你将看到从一段约 {duration:.1f} 秒视频中按时间均匀抽取的 {frame_count} 张画面截图，并得到该视频音轨的自动语音转写。

注意：你没有收到完整连续视频，也没有直接听到原始音轨。因此不能声称看见截图之间未出现的动作，也不能凭转写判断音乐、笑声、语气或环境音。只能根据截图与转写做保守分析。

语音转写：
{transcript_block}

音频处理提示：
{warning_block}

请只返回一个 JSON 对象，不要 Markdown 代码块，字段必须为：
{{
  "summary": "一句话概括",
  "timeline": [{{"time": "约 0:05", "event": "可由截图或转写支持的关键事件"}}],
  "visual": "截图中明确可见的画面、人物/物体、场景、可确认文字",
  "audio": "只根据语音转写描述可确认的台词；无法确认的声音特征明确说明",
  "transcript": "保留或整理语音转写",
  "av_relationship": "仅在截图和转写足以支持时描述音画对应，否则说明无法确定",
  "discussion_points": ["最值得一起聊的点"],
  "uncertainty": ["由于使用抽帧/转写而无法确定的地方"]
}}
""".strip()


def _extract_gemini_text(data: dict[str, Any]) -> str:
    for candidate in data.get("candidates") or []:
        parts = ((candidate or {}).get("content") or {}).get("parts") or []
        texts = [p.get("text", "") for p in parts if isinstance(p, dict) and p.get("text")]
        if texts:
            return "\n".join(texts).strip()
    if data.get("error"):
        err = data["error"]
        if isinstance(err, dict):
            raise RuntimeError(str(err.get("message") or err.get("status") or "Gemini API 返回错误"))
    raise RuntimeError("Gemini-compatible API 没有返回可读内容。")


def _extract_openai_text(data: dict[str, Any]) -> str:
    choices = data.get("choices") or []
    if choices:
        content = ((choices[0] or {}).get("message") or {}).get("content")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            texts = []
            for part in content:
                if isinstance(part, dict):
                    text = part.get("text") or part.get("content")
                    if text:
                        texts.append(str(text))
            if texts:
                return "\n".join(texts).strip()
    err = data.get("error")
    if isinstance(err, dict):
        raise RuntimeError(str(err.get("message") or err.get("type") or "OpenAI-compatible API 返回错误"))
    raise RuntimeError("OpenAI-compatible API 没有返回可读内容。")


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
    start, end = raw.find("{"), raw.rfind("}")
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


def _http_error(resp: httpx.Response, api_key: str, label: str) -> RuntimeError:
    message = ""
    try:
        body = resp.json()
        err = body.get("error") if isinstance(body, dict) else None
        if isinstance(err, dict):
            message = str(err.get("message") or err.get("status") or err.get("type") or "")
        elif isinstance(body, dict):
            message = str(body.get("message") or "")
    except Exception:
        message = resp.text[:500]
    if api_key:
        message = message.replace(api_key, "***")
    return RuntimeError(f"{label} 请求失败（HTTP {resp.status_code}）：{message or '上游没有给出详细原因'}")


def _call_gemini(video_mp4: Path, duration: float, model: str, api_key: str, base_url: str, auth_style: str) -> dict[str, Any]:
    encoded = base64.b64encode(video_mp4.read_bytes()).decode("ascii")
    url = f"{base_url}/v1beta/models/{model}:generateContent"
    payload = {
        "contents": [{
            "role": "user",
            "parts": [
                {"text": _prompt_direct(duration)},
                {"inline_data": {"mime_type": "video/mp4", "data": encoded}},
            ],
        }],
        "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"},
    }
    params = {"key": api_key} if auth_style != "bearer" else None
    headers = {"Authorization": f"Bearer {api_key}"} if auth_style == "bearer" else None
    try:
        with httpx.Client(timeout=httpx.Timeout(240.0, connect=30.0)) as client:
            resp = client.post(url, params=params, headers=headers, json=payload)
    except httpx.RequestError as e:
        raise RuntimeError(f"连接 Gemini-compatible API 失败：{e.__class__.__name__}") from e
    if resp.status_code >= 400:
        raise _http_error(resp, api_key, model)
    try:
        data = resp.json()
    except Exception as e:
        raise RuntimeError("Gemini-compatible API 返回的不是 JSON。") from e
    return _parse_json_text(_extract_gemini_text(data))


def _openai_endpoint(base_url: str, path: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith("/v1") and path.startswith("/v1/"):
        return base + path[3:]
    if not base.endswith("/v1") and path.startswith("/v1/"):
        return base + path
    return base + "/" + path.lstrip("/")


def _extract_openai_frames(video_path: Path, work_dir: Path, duration: float, max_frames: int = 8) -> list[Path]:
    frame_dir = work_dir / "frames"
    frame_dir.mkdir(parents=True, exist_ok=True)
    count = max(2, min(max_frames, 10))
    if duration <= 0.5:
        times = [0.0]
    else:
        start = min(0.15, duration * 0.05)
        end = max(start, duration - min(0.15, duration * 0.05))
        if count == 1:
            times = [(start + end) / 2]
        else:
            times = [start + (end - start) * i / (count - 1) for i in range(count)]

    frames: list[Path] = []
    for i, t in enumerate(times, 1):
        out = frame_dir / f"frame-{i:02d}.jpg"
        p = _run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-ss", f"{t:.3f}", "-i", str(video_path), "-frames:v", "1",
            "-vf", "scale='min(960,iw)':-2:force_original_aspect_ratio=decrease",
            "-q:v", "4", str(out),
        ], check=False)
        if p.returncode == 0 and out.exists() and out.stat().st_size > 0:
            frames.append(out)
    if not frames:
        raise RuntimeError("没有成功抽取视频画面，OpenAI-compatible 模式无法继续。")
    return frames


def _extract_audio_wav(video_path: Path, work_dir: Path) -> Path | None:
    out = work_dir / "audio.wav"
    p = _run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(video_path),
        "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(out),
    ], check=False)
    if p.returncode != 0 or not out.exists() or out.stat().st_size < 1000:
        return None
    return out


def _openai_transcribe(audio_path: Path | None, api_key: str, base_url: str, audio_model: str) -> tuple[str, str]:
    if audio_path is None:
        return "", "视频没有检测到可用音轨，或音轨提取失败。"
    if not audio_model:
        return "", "未配置 API_AUDIO_MODEL，因此跳过语音转写。"

    url = _openai_endpoint(base_url, "/v1/audio/transcriptions")
    try:
        with audio_path.open("rb") as f, httpx.Client(timeout=httpx.Timeout(180.0, connect=30.0)) as client:
            resp = client.post(
                url,
                headers={"Authorization": f"Bearer {api_key}"},
                data={"model": audio_model, "response_format": "json"},
                files={"file": ("audio.wav", f, "audio/wav")},
            )
    except httpx.RequestError as e:
        return "", f"语音转写连接失败：{e.__class__.__name__}。"
    if resp.status_code >= 400:
        err = _http_error(resp, api_key, audio_model)
        return "", f"语音转写不可用：{err}"
    try:
        data = resp.json()
        text = str(data.get("text") or "").strip()
        return text, ""
    except Exception:
        return "", "语音转写接口返回格式无法读取。"


def _call_openai_frames(video_path: Path, duration: float, model: str, api_key: str, base_url: str, audio_model: str, work_dir: Path) -> dict[str, Any]:
    frames = _extract_openai_frames(video_path, work_dir, duration, int(os.getenv("OPENAI_FRAME_COUNT", "8")))
    audio_path = _extract_audio_wav(video_path, work_dir)
    transcript, audio_warning = _openai_transcribe(audio_path, api_key, base_url, audio_model)

    content: list[dict[str, Any]] = [{
        "type": "text",
        "text": _prompt_frames(duration, transcript, len(frames), audio_warning),
    }]
    for frame in frames:
        data_url = "data:image/jpeg;base64," + base64.b64encode(frame.read_bytes()).decode("ascii")
        content.append({"type": "image_url", "image_url": {"url": data_url, "detail": "low"}})

    url = _openai_endpoint(base_url, "/v1/chat/completions")
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": content}],
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }
    try:
        with httpx.Client(timeout=httpx.Timeout(240.0, connect=30.0)) as client:
            resp = client.post(url, headers={"Authorization": f"Bearer {api_key}"}, json=payload)
    except httpx.RequestError as e:
        raise RuntimeError(f"连接 OpenAI-compatible API 失败：{e.__class__.__name__}") from e

    # 部分兼容网关不支持 response_format，自动再试一次。
    if resp.status_code >= 400 and resp.status_code in {400, 404, 422}:
        payload.pop("response_format", None)
        with httpx.Client(timeout=httpx.Timeout(240.0, connect=30.0)) as client:
            resp = client.post(url, headers={"Authorization": f"Bearer {api_key}"}, json=payload)
    if resp.status_code >= 400:
        raise _http_error(resp, api_key, model)
    try:
        data = resp.json()
    except Exception as e:
        raise RuntimeError("OpenAI-compatible API 返回的不是 JSON。") from e

    obs = _parse_json_text(_extract_openai_text(data))
    if not obs.get("transcript") and transcript:
        obs["transcript"] = transcript
    if audio_warning:
        uncertainty = obs.get("uncertainty")
        if not isinstance(uncertainty, list):
            uncertainty = [] if not uncertainty else [str(uncertainty)]
        uncertainty.append(audio_warning)
        obs["uncertainty"] = uncertainty
    return obs


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


def analyze_video(video_path: Path, original_name: str, api_config: dict[str, str] | None = None) -> dict[str, Any]:
    ensure_ffmpeg()
    cfg = _settings(api_config)

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
    fallback_error = None
    used_model = cfg["model"]
    try:
        if cfg["mode"] == "gemini":
            prepared = _transcode_for_inline(video_path, work_dir, duration, inline_target_mb)
            prepared_mb = prepared.stat().st_size / (1024 * 1024)
            if prepared_mb > inline_target_mb * 1.25:
                raise RuntimeError(f"自动压缩后仍有 {prepared_mb:.1f}MB，暂时不适合 inline 视频请求。请把视频再剪短一点。")
            try:
                obs = _call_gemini(prepared, duration, cfg["model"], cfg["api_key"], cfg["base_url"], cfg["auth_style"])
            except Exception as first_error:
                if cfg["fallback"] and cfg["fallback"] != cfg["model"]:
                    fallback_error = str(first_error)
                    used_model = cfg["fallback"]
                    obs = _call_gemini(prepared, duration, used_model, cfg["api_key"], cfg["base_url"], cfg["auth_style"])
                else:
                    raise
            pipeline = "Gemini-compatible：小 MP4 直接发送，较大视频低资源压缩 → 模型直接读取视频画面与原始音轨 → 保存音画报告"
        else:
            try:
                obs = _call_openai_frames(video_path, duration, cfg["model"], cfg["api_key"], cfg["base_url"], cfg["audio_model"], work_dir)
            except Exception as first_error:
                if cfg["fallback"] and cfg["fallback"] != cfg["model"]:
                    fallback_error = str(first_error)
                    used_model = cfg["fallback"]
                    obs = _call_openai_frames(video_path, duration, used_model, cfg["api_key"], cfg["base_url"], cfg["audio_model"], work_dir)
                else:
                    raise
            pipeline = "OpenAI-compatible：FFmpeg 均匀抽取关键帧 + 可用时调用音频转写接口 → 视觉模型结合截图与转写生成报告。不是原生连续视频理解。"
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)

    video_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    transcript = str(obs.get("transcript") or "").strip()
    audio_obs = str(obs.get("audio") or "").strip()
    report = {
        "video_id": video_id,
        "original_name": original_name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "duration_seconds": round(duration, 3),
        "size_mb": round(size_mb, 3),
        "analysis": _compose_analysis(obs),
        "transcript": transcript or "（没有得到清晰语音转写；请看声音观察与不确定项。）",
        "audio_observation": audio_obs or "（模型没有单独返回声音观察。）",
        "frame_times_seconds": [],
        "models": {
            "provider_mode": cfg["mode"],
            "video_audio_understanding": used_model,
            "primary": cfg["model"],
            "fallback": cfg["fallback"],
            "audio_transcription": cfg["audio_model"] if cfg["mode"] == "openai" else "",
        },
        "pipeline": pipeline,
        "gateway": cfg["base_url"],
        "primary_model_error_before_fallback": fallback_error,
        "raw_structured_observation": obs,
    }
    (REPORTS_DIR / f"{video_id}.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def list_reports(limit: int = 10) -> list[dict[str, Any]]:
    files = sorted(REPORTS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]
    out = []
    for p in files:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            obs = data.get("raw_structured_observation") or {}
            summary = obs.get("summary") if isinstance(obs, dict) else ""
            out.append({
                "video_id": data.get("video_id"),
                "original_name": data.get("original_name"),
                "created_at": data.get("created_at"),
                "duration_seconds": data.get("duration_seconds"),
                "summary": summary or "",
            })
        except Exception:
            pass
    return out


def get_report(video_id: str) -> dict[str, Any] | None:
    if not _safe_video_id(video_id):
        return None
    path = REPORTS_DIR / f"{video_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _safe_video_id(video_id: str) -> bool:
    if not video_id or len(video_id) > 120:
        return False
    return all(ch.isalnum() or ch in {"-", "_"} for ch in video_id)


def delete_report(video_id: str) -> bool:
    if not _safe_video_id(video_id):
        return False
    path = REPORTS_DIR / f"{video_id}.json"
    if not path.exists():
        return False
    path.unlink(missing_ok=True)
    return True


def clear_reports() -> int:
    count = 0
    for path in REPORTS_DIR.glob("*.json"):
        try:
            path.unlink(missing_ok=True)
            count += 1
        except Exception:
            pass
    return count
