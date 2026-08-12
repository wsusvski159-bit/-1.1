from __future__ import annotations

import contextlib
import html
import os
import secrets
import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from mcp.server.transport_security import TransportSecuritySettings

from video_analyzer import analyze_video, get_report, list_reports
from mcp_bridge import mcp as video_mcp

load_dotenv()
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("DATA_DIR", str(BASE_DIR / "data"))).resolve()
UPLOADS_DIR = DATA_DIR / "uploads"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "80"))
APP_USERNAME = os.getenv("APP_USERNAME", "gongkan").strip() or "gongkan"
APP_PASSWORD = os.getenv("APP_PASSWORD", "").strip()
MCP_PATH_TOKEN = os.getenv("MCP_PATH_TOKEN", "").strip()
ICON_PATH = BASE_DIR / "app-icon-512.png"


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    async with video_mcp.session_manager.run():
        yield


app = FastAPI(title="共看", lifespan=lifespan)
# GONGKAN_UI_V1_5_DESIGN_MATCH

# MCP endpoint: https://<host>/bridge-<MCP_PATH_TOKEN>/mcp
if MCP_PATH_TOKEN:
    render_host = os.getenv("RENDER_EXTERNAL_HOSTNAME", "").strip()
    allowed_hosts = [render_host, f"{render_host}:443"] if render_host else []
    video_mcp.settings.transport_security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=allowed_hosts,
        allowed_origins=[
            "https://chatgpt.com",
            "https://www.chatgpt.com",
            "https://chat.openai.com",
        ],
    )
    app.mount(f"/bridge-{MCP_PATH_TOKEN}", video_mcp.streamable_http_app())

security = HTTPBasic(auto_error=False)


def require_auth(credentials: HTTPBasicCredentials | None = Depends(security)) -> None:
    if not APP_PASSWORD:
        return
    ok_user = credentials is not None and secrets.compare_digest(credentials.username, APP_USERNAME)
    ok_pass = credentials is not None and secrets.compare_digest(credentials.password, APP_PASSWORD)
    if not (ok_user and ok_pass):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="需要密码",
            headers={"WWW-Authenticate": 'Basic realm="GongKan"'},
        )


def _base_css() -> str:
    return """
:root{
  --bg:#f8f4e9;
  --paper:#fffef9;
  --ink:#1f3b2f;
  --text:#415249;
  --muted:#7b847d;
  --sage:#78996f;
  --sage-2:#66865f;
  --sage-soft:#edf4e9;
  --sage-line:#d6e2cf;
  --sand:#e9dfc8;
  --shadow:0 18px 48px rgba(51,73,53,.10);
  --radius:28px;
}
*{box-sizing:border-box}
html,body{margin:0;width:100%;max-width:100%;overflow-x:hidden;background:var(--bg);color-scheme:light}
body{
  min-height:100vh;
  color:var(--text);
  font-family:system-ui,-apple-system,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;
  background:
    radial-gradient(circle at 88% 8%,rgba(191,205,170,.30),transparent 20rem),
    radial-gradient(circle at 4% 85%,rgba(236,225,198,.62),transparent 25rem),
    linear-gradient(180deg,#faf7ef 0%,#f7f2e6 100%);
}
a{color:inherit;text-decoration:none}
button,input{font:inherit}
.shell{width:min(100%,760px);margin:0 auto;padding:26px 18px calc(46px + env(safe-area-inset-bottom));position:relative;overflow:hidden}
.decor{position:absolute;right:6px;top:42px;width:150px;height:155px;opacity:.42;pointer-events:none;z-index:0}
.hero{position:relative;display:grid;grid-template-columns:112px minmax(0,1fr);gap:24px;align-items:center;padding:24px 8px 30px;min-width:0;z-index:1}
.hero>div{min-width:0}.logo{width:108px;height:108px;border-radius:30px;background:#fffaf0;object-fit:cover;box-shadow:0 14px 30px rgba(78,96,69,.15);border:1px solid rgba(220,210,188,.8)}
.hero h1{margin:0 0 12px;color:var(--ink);font-size:clamp(46px,12vw,66px);line-height:.98;letter-spacing:.05em;font-weight:850}
.hero p{margin:0;max-width:430px;color:#506057;font-size:18px;line-height:1.75;padding-right:82px}
.card{width:100%;min-width:0;margin:16px 0;padding:22px;background:rgba(255,254,249,.96);border:1px solid rgba(215,225,204,.96);border-radius:var(--radius);box-shadow:var(--shadow);overflow:hidden}
.status{padding:22px;background:linear-gradient(145deg,rgba(247,250,241,.98),rgba(240,246,233,.98));border-color:#d6e1c8}
.status-top{display:grid;grid-template-columns:1fr 1fr auto;gap:13px 16px;align-items:center;min-width:0}
.status-item{min-width:0;display:flex;align-items:center;gap:10px;font-size:16px;color:#31493a}.status-icon{width:34px;height:34px;flex:0 0 34px;border-radius:50%;display:grid;place-items:center;background:#7a9b6f;color:#fff;font-size:19px;font-weight:900}.status-icon.warn{background:#b5aa7b}.lock-icon{width:36px;height:36px;color:#6f8d66;display:grid;place-items:center}
.model{margin-top:17px;padding-top:16px;border-top:1px solid #dce5d5;color:#3d5044;font-size:15px;line-height:1.65;overflow-wrap:anywhere;word-break:break-word}
.msg{width:100%;min-width:0;margin:15px 0;padding:15px 17px;border-radius:18px;border:1px solid #d4e5cf;background:#eef6ea;color:#35503d;line-height:1.7;overflow-wrap:anywhere;word-break:break-word}
.upload{padding:30px 26px}.file-row{display:flex;align-items:center;gap:14px;min-width:0}.file-label{flex:0 0 auto;display:inline-flex;align-items:center;gap:9px;padding:12px 16px;border:1.7px dashed #92aa85;border-radius:16px;background:#fbfcf7;color:#66815e;font-weight:750;cursor:pointer}.file-label input{position:absolute;opacity:0;width:1px;height:1px;pointer-events:none}.filename{min-width:0;flex:1;color:#67716a;font-size:15px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.divider{height:1px;margin:24px 0 20px;background:linear-gradient(90deg,transparent,#e0d6bd 12%,#e0d6bd 88%,transparent)}
.primary{width:100%;min-height:68px;border:0;border-radius:22px;background:linear-gradient(135deg,#7c9c71,#65895f);color:#fff;font-size:22px;font-weight:850;letter-spacing:.08em;box-shadow:0 12px 28px rgba(92,124,87,.23);cursor:pointer}.primary:active{transform:translateY(1px)}.privacy{display:flex;justify-content:center;align-items:center;gap:7px;margin:15px 0 0;color:#858d86;font-size:13px;text-align:center}
.section-title{display:flex;justify-content:space-between;align-items:center;gap:12px;min-width:0;margin-bottom:16px}.title-left{display:flex;align-items:center;min-width:0;gap:10px}.badge-icon{width:38px;height:38px;flex:0 0 38px;border-radius:50%;display:grid;place-items:center;background:#e5efdf;color:#66845f;font-size:18px}.section-title h2{margin:0;color:#213c30;font-size:25px;line-height:1.2}.section-link{color:#6d8a64;font-size:14px;white-space:nowrap}
.recent-list{display:grid;grid-template-columns:minmax(0,1fr);gap:11px;width:100%;min-width:0}.recent-item{width:100%;min-width:0;display:flex;align-items:center;justify-content:space-between;gap:12px;padding:15px 16px;border-radius:17px;background:#f8faf5;border:1px solid #e1e8dc;overflow:hidden}.recent-name{flex:1 1 auto;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#2f4938}.recent-meta{flex:0 0 auto;color:#8c938d;font-size:12px;white-space:nowrap}
.empty{text-align:center;padding:28px 10px 18px;color:#7b837e}.empty-illus{width:110px;height:90px;margin:0 auto 10px}.empty strong{display:block;margin-bottom:5px;color:#3c5144;font-size:19px}.empty span{font-size:14px}
.footnote{display:flex;align-items:flex-start;gap:12px;margin-top:18px;padding:17px 18px;border:1px solid #d7e1cf;border-radius:23px;background:rgba(244,247,237,.90);color:#69736b;font-size:14px;line-height:1.75}.info{width:30px;height:30px;flex:0 0 30px;border-radius:50%;display:grid;place-items:center;background:#73916b;color:#fff;font-weight:900}
.report-head{display:flex;align-items:center;margin:2px 0 14px}.back{display:inline-flex;align-items:center;gap:6px;padding:9px 13px;border-radius:14px;background:#edf3e8;color:#4e6950}.report-title{margin:0 0 7px;color:#213c30;font-size:26px;overflow-wrap:anywhere;word-break:break-word}.report-meta{margin:0;color:#7c857e;font-size:13px;line-height:1.7;overflow-wrap:anywhere;word-break:break-word}.report-section h3{margin:0 0 11px;color:#294334;font-size:19px}.report-section pre{margin:0;max-width:100%;padding:16px;border-radius:18px;background:#f7f8f4;border:1px solid #e2e7de;color:#34473a;white-space:pre-wrap;word-break:break-word;overflow-wrap:anywhere;overflow-x:auto;font-family:inherit;line-height:1.78}
@media(max-width:560px){.shell{padding:18px 15px 38px}.decor{width:118px;height:128px;right:2px;top:42px;opacity:.34}.hero{grid-template-columns:90px minmax(0,1fr);gap:16px;padding:20px 4px 28px}.logo{width:88px;height:88px;border-radius:24px}.hero h1{font-size:46px}.hero p{font-size:16px;line-height:1.7;padding-right:52px}.card{padding:18px;border-radius:25px}.status{padding:18px}.status-top{grid-template-columns:minmax(0,1fr) minmax(0,1fr) auto;gap:10px}.status-item{font-size:14px;gap:7px}.status-icon{width:30px;height:30px;flex-basis:30px}.lock-icon{width:30px;height:30px}.upload{padding:22px 18px}.file-row{gap:10px}.file-label{padding:11px 13px;font-size:14px}.filename{font-size:13px}.primary{font-size:20px;min-height:58px}.section-title h2{font-size:22px}}
@media(max-width:390px){.status-top{grid-template-columns:1fr 1fr}.lock-icon{display:none}.hero p{padding-right:0}.file-row{align-items:flex-start;flex-direction:column}.filename{width:100%}}
"""

def _icon_html() -> str:
    if ICON_PATH.exists():
        return '<img class="logo" src="/app-icon.png" alt="共看图标">'
    return '<div class="logo" style="display:grid;place-items:center;font-size:38px">▶</div>'


def page(message: str = "") -> str:
    reports = list_reports(8)
    if reports:
        items = "".join(
            '<a class="recent-item" href="/report/{id}"><span class="recent-name">{name}</span>'
            '<span class="recent-meta">{duration:.1f}s ›</span></a>'.format(
                id=html.escape(str(r["video_id"])),
                name=html.escape(r.get("original_name") or r["video_id"]),
                duration=float(r.get("duration_seconds") or 0),
            )
            for r in reports
        )
        recent_html = f'<div class="recent-list">{items}</div>'
    else:
        recent_html = """
        <div class="empty">
          <svg class="empty-illus" viewBox="0 0 140 110" aria-hidden="true">
            <defs><linearGradient id="boxg" x1="0" x2="1"><stop offset="0" stop-color="#dbe7d2"/><stop offset="1" stop-color="#b9cba9"/></linearGradient></defs>
            <path d="M30 48 70 26l40 22-40 22Z" fill="#e8efe1"/>
            <path d="M30 48v32l40 22V70Z" fill="url(#boxg)"/><path d="M110 48v32l-40 22V70Z" fill="#c6d5ba"/>
            <path d="M30 48 14 64l40 20 16-14Z" fill="#edf3e8"/><path d="m110 48 16 16-40 20-16-14Z" fill="#d7e3cf"/>
            <path d="M70 28c-4-12 8-17 13-8 5-9 17-4 13 8-3 8-13 13-13 13S73 36 70 28Z" fill="#a8bf98"/>
          </svg>
          <strong>还没有分析记录</strong><span>上传视频，开启你的第一次共看吧</span>
        </div>
        """

    msg = f'<div class="msg">{html.escape(message)}</div>' if message else ""
    api_ok = bool((os.getenv("API_KEY", "") or os.getenv("GEMINI_API_KEY", "") or os.getenv("NEWAPI_API_KEY", "")).strip())
    api_mode = os.getenv("API_MODE", "gemini").strip().lower()
    model = (os.getenv("API_MODEL", "") or os.getenv("GEMINI_MODEL", "") or "未配置").strip()

    model_dot = "✓" if api_ok else "!"
    password_dot = "✓" if APP_PASSWORD else "!"
    password_cls = "" if APP_PASSWORD else " warn"

    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#f8f4e9"><title>共看</title><style>{_base_css()}</style></head>
<body><main class="shell">
<svg class="decor" viewBox="0 0 150 160" aria-hidden="true"><path d="M83 150c11-38 23-69 52-102-4 40-18 73-52 102Z" fill="#9eb28e"/><path d="M72 128c-18-26-37-38-58-42 10 25 28 40 58 42Z" fill="#c9d5bb"/><path d="M92 99c-8-28-4-52 8-75 9 30 6 55-8 75Z" fill="#b5c7a6"/><path d="M46 48c-5-15 10-22 17-10 7-12 22-5 17 10-5 12-17 19-17 19S51 60 46 48Z" fill="#cbd6b8"/></svg>
<section class="hero">{_icon_html()}<div><h1>共看</h1><p>上传视频，让 AI 帮你看画面、听声音，生成清晰总结。</p></div></section>
<section class="card status"><div class="status-top">
  <div class="status-item"><span class="status-icon">{model_dot}</span><span>{"Gemini 看+听" if api_mode == "gemini" else "AI 看+听"}</span></div>
  <div class="status-item"><span class="status-icon{password_cls}">{password_dot}</span><span>网页密码</span></div>
  <div class="lock-icon" aria-hidden="true"><svg width="27" height="27" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9"><rect x="5" y="10" width="14" height="10" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/></svg></div>
</div><div class="model">主模型：{html.escape(model)}</div></section>{msg}
<section class="card upload"><form action="/upload" method="post" enctype="multipart/form-data">
  <div class="file-row"><label class="file-label"><span style="font-size:20px">▱</span><span>选择文件</span><input id="videoInput" type="file" name="video" accept="video/*" required></label><span id="fileName" class="filename">未选择任何文件</span></div>
  <div class="divider"></div><button class="primary" type="submit">✦ 开始共看</button>
  <p class="privacy"><span>♢</span><span>文件仅用于本次分析，完成后会删除临时原视频</span></p>
</form></section>
<section class="card"><div class="section-title"><div class="title-left"><span class="badge-icon">◷</span><h2>最近的视频</h2></div><span class="section-link">查看全部　›</span></div>{recent_html}</section>
<div class="footnote" style="position:relative;overflow:hidden"><span class="info">i</span><div style="position:relative;z-index:1;padding-right:72px">建议 60 秒以内，单个视频不超过 {MAX_UPLOAD_MB}MB。服务器会在需要时自动转换成适合模型读取的格式；原视频分析完成后删除。</div><svg viewBox="0 0 110 90" aria-hidden="true" style="position:absolute;right:-4px;bottom:-10px;width:105px;opacity:.34"><path d="M58 84c8-28 18-51 40-73-3 29-13 54-40 73Z" fill="#91a982"/><path d="M47 72c-16-20-29-28-44-29 9 19 22 28 44 29Z" fill="#bacaaa"/><path d="M66 49c-3-18 1-32 10-44 5 19 2 34-10 44Z" fill="#a6b999"/><path d="M33 21c-4-10 7-15 12-7 5-8 15-3 12 7-4 8-12 13-12 13S36 29 33 21Z" fill="#9cb18b"/></svg></div>
</main><script>const input=document.getElementById('videoInput');const name=document.getElementById('fileName');if(input)input.addEventListener('change',()=>{{name.textContent=input.files&&input.files[0]?input.files[0].name:'未选择任何文件';}});</script></body></html>"""


@app.get("/app-icon.png", include_in_schema=False)
def app_icon():
    if not ICON_PATH.exists():
        raise HTTPException(404, "icon not found")
    return FileResponse(ICON_PATH, media_type="image/png")


@app.get("/health")
def health():
    return {"ok": True, "name": "共看", "ui": "v1.5-design-match"}


@app.get("/", response_class=HTMLResponse, dependencies=[Depends(require_auth)])
def home():
    return page()


@app.post("/upload", response_class=HTMLResponse, dependencies=[Depends(require_auth)])
def upload(video: UploadFile = File(...)):
    suffix = Path(video.filename or "video.mp4").suffix.lower() or ".mp4"
    temp_path = UPLOADS_DIR / f"upload-{uuid.uuid4().hex}{suffix}"
    try:
        size = 0
        max_bytes = MAX_UPLOAD_MB * 1024 * 1024
        with temp_path.open("wb") as f:
            while True:
                chunk = video.file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > max_bytes:
                    raise HTTPException(413, f"视频超过 {MAX_UPLOAD_MB}MB 上限")
                f.write(chunk)

        report = analyze_video(temp_path, video.filename or "video")
        used = (report.get("models") or {}).get("video_audio_understanding") or "AI"
        note = ""
        first_error = report.get("primary_model_error_before_fallback")
        if first_error:
            note = f"（主模型失败后已自动改用备用模型 {used}。）"
        return HTMLResponse(page(f"分析完成：{report['original_name']}。报告 ID：{report['video_id']} {note}"))
    except HTTPException:
        raise
    except Exception as e:
        return HTMLResponse(page(f"分析失败：{e}"), status_code=500)
    finally:
        try:
            temp_path.unlink(missing_ok=True)
        except Exception:
            pass


@app.get("/report/{video_id}", response_class=HTMLResponse, dependencies=[Depends(require_auth)])
def report_page(video_id: str):
    r = get_report(video_id)
    if not r:
        raise HTTPException(404, "report not found")
    analysis = html.escape(r.get("analysis") or "")
    transcript = html.escape(r.get("transcript") or "")
    audio = html.escape(r.get("audio_observation") or "")
    model = html.escape(str((r.get("models") or {}).get("video_audio_understanding") or ""))
    name = html.escape(r.get("original_name") or video_id)
    vid = html.escape(video_id)
    return HTMLResponse(f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><meta name="theme-color" content="#f7f3e9"><title>{name} · 共看</title><style>{_base_css()}</style></head><body><main class="shell">
<div class="report-head"><a class="back" href="/">← 返回共看</a></div>
<section class="card"><h1 class="report-title">{name}</h1><p class="report-meta">报告 ID：{vid}<br>模型：{model}</p></section>
<section class="card report-section"><h3>音画分析</h3><pre>{analysis}</pre></section>
<section class="card report-section"><h3>语音转写</h3><pre>{transcript}</pre></section>
<section class="card report-section"><h3>声音观察</h3><pre>{audio}</pre></section>
</main></body></html>""")


@app.get("/api/recent", dependencies=[Depends(require_auth)])
def api_recent():
    return JSONResponse(list_reports(20))


@app.get("/api/report/{video_id}", dependencies=[Depends(require_auth)])
def api_report(video_id: str):
    r = get_report(video_id)
    if not r:
        raise HTTPException(404, "report not found")
    return JSONResponse(r)
