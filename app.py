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
  --cream:#f7f3e9;--cream-2:#fffdf7;--paper:#fffefb;--ink:#20372d;--muted:#6f776f;
  --sage:#76906c;--sage-deep:#526d57;--sage-soft:#eaf1e5;--line:#dce5d4;
  --shadow:0 16px 42px rgba(57,76,59,.09);--radius:28px;
}
*{box-sizing:border-box}
html{background:var(--cream);color-scheme:light}
body{margin:0;background:
 radial-gradient(circle at 88% 8%,rgba(183,198,164,.28),transparent 23rem),
 radial-gradient(circle at 8% 92%,rgba(234,226,202,.72),transparent 26rem),
 var(--cream);color:var(--ink);font-family:system-ui,-apple-system,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;line-height:1.65}
a{color:var(--sage-deep);text-decoration:none}.shell{width:min(760px,100%);margin:0 auto;padding:26px 18px 48px}
.hero{display:grid;grid-template-columns:92px 1fr;gap:20px;align-items:center;padding:18px 4px 22px}
.logo{width:88px;height:88px;border-radius:24px;box-shadow:0 12px 28px rgba(72,91,66,.14);background:#fff;object-fit:cover}
.hero h1{font-size:clamp(38px,9vw,58px);line-height:1;margin:0 0 12px;letter-spacing:.04em;color:#203a2f}
.hero p{margin:0;color:#53635a;font-size:17px;line-height:1.75}
.card{background:rgba(255,254,249,.94);border:1px solid rgba(207,218,194,.75);border-radius:var(--radius);box-shadow:var(--shadow);padding:22px;margin:16px 0}
.status{background:linear-gradient(135deg,#f7f9f2,#f1f5e9);border-color:#d6e0c8}
.status-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px 16px;align-items:center}.status-item{display:flex;gap:9px;align-items:center;min-width:0}.dot{width:28px;height:28px;border-radius:50%;display:grid;place-items:center;background:#79966b;color:white;font-weight:800;flex:0 0 auto}.dot.warn{background:#b5aa7b}.status-label{font-size:14px;color:#5f6c64;white-space:nowrap}.model{grid-column:1/-1;padding-top:9px;border-top:1px solid #dde6d4;color:#34483b;word-break:break-word;font-size:14px}
.msg{margin:14px 0;padding:13px 15px;background:#eef5e9;border:1px solid #d8e5d0;border-radius:16px;color:#38513f}
.upload{padding:28px 22px}.file-row{display:flex;gap:12px;align-items:center;flex-wrap:wrap}.file-label{display:inline-flex;align-items:center;gap:8px;padding:11px 16px;border:1.5px dashed #95aa88;border-radius:15px;color:#68825e;background:#fbfcf7;cursor:pointer;font-weight:650}.file-label:hover{background:#f2f6ed}.file-label input{position:absolute;opacity:0;pointer-events:none}.filename{color:#687168;font-size:14px;max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.divider{height:1px;background:linear-gradient(90deg,transparent,#ddd1b4 12%,#ddd1b4 88%,transparent);margin:24px 0 20px}.primary{width:100%;border:0;border-radius:19px;background:linear-gradient(135deg,#78956d,#5f7d61);color:white;font-size:20px;font-weight:800;letter-spacing:.08em;padding:15px 20px;box-shadow:0 10px 25px rgba(82,109,87,.22);cursor:pointer}.primary:active{transform:translateY(1px)}.privacy{margin:14px 0 0;text-align:center;color:#858c84;font-size:13px}
.section-title{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:16px}.section-title h2{font-size:23px;margin:0}.badge-icon{width:34px;height:34px;border-radius:50%;background:#e3eddc;display:grid;place-items:center;color:#66805f;margin-right:8px}.title-left{display:flex;align-items:center}.recent-list{display:grid;gap:10px}.recent-item{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:13px 14px;background:#f8faf5;border:1px solid #e3eadc;border-radius:16px}.recent-name{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#2e4637}.recent-meta{flex:0 0 auto;color:#899087;font-size:12px}.empty{text-align:center;padding:30px 10px 24px;color:#778078}.empty-icon{font-size:44px;line-height:1;margin-bottom:10px}.empty strong{display:block;color:#405445;font-size:18px;margin-bottom:6px}.footnote{display:flex;gap:12px;align-items:flex-start;background:rgba(244,247,237,.88);border:1px solid #d9e2cf;border-radius:22px;padding:17px 18px;color:#677168;font-size:14px;margin-top:18px}.info{width:26px;height:26px;border-radius:50%;background:#718c68;color:#fff;display:grid;place-items:center;font-weight:800;flex:0 0 auto}
.report-head{display:flex;align-items:center;gap:12px;margin:2px 0 16px}.back{display:inline-flex;align-items:center;gap:5px;padding:8px 12px;border-radius:14px;background:#eef3e9;color:#506a52}.report-title{font-size:26px;margin:8px 0 4px;word-break:break-word}.report-meta{color:#7b837b;font-size:13px;margin:0 0 18px;word-break:break-word}.report-section h3{margin:0 0 10px;font-size:19px}.report-section pre{margin:0;background:#f7f8f5;border:1px solid #e3e7df;border-radius:18px;padding:16px;white-space:pre-wrap;word-break:break-word;font-family:inherit;color:#314337;line-height:1.75}
@media(max-width:520px){.shell{padding:18px 14px 38px}.hero{grid-template-columns:72px 1fr;gap:14px}.logo{width:70px;height:70px;border-radius:20px}.hero p{font-size:15px}.card{border-radius:24px;padding:18px}.status-grid{grid-template-columns:1fr 1fr}.status-item:nth-child(3){grid-column:1/-1}.upload{padding:22px 18px}}
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
        recent_html = (
            '<div class="empty"><div class="empty-icon">▱</div>'
            '<strong>还没有分析记录</strong><span>上传视频，开启你的第一次共看吧</span></div>'
        )

    msg = f'<div class="msg">{html.escape(message)}</div>' if message else ""
    api_ok = bool((os.getenv("API_KEY", "") or os.getenv("GEMINI_API_KEY", "") or os.getenv("NEWAPI_API_KEY", "")).strip())
    api_mode = os.getenv("API_MODE", "gemini").strip().lower()
    model = (os.getenv("API_MODEL", "") or os.getenv("GEMINI_MODEL", "") or "未配置").strip()

    model_dot = "✓" if api_ok else "!"
    password_dot = "✓" if APP_PASSWORD else "!"
    mcp_dot = "✓" if MCP_PATH_TOKEN else "!"
    password_cls = "" if APP_PASSWORD else " warn"
    mcp_cls = "" if MCP_PATH_TOKEN else " warn"

    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#f7f3e9"><title>共看</title><style>{_base_css()}</style></head>
<body><main class="shell">
<section class="hero">{_icon_html()}<div><h1>共看</h1><p>上传视频，让 AI 帮你看画面、听声音，生成清晰总结。</p></div></section>
<section class="card status"><div class="status-grid">
  <div class="status-item"><span class="dot">{model_dot}</span><span class="status-label">视频理解</span></div>
  <div class="status-item"><span class="dot{password_cls}">{password_dot}</span><span class="status-label">网页保护</span></div>
  <div class="status-item"><span class="dot{mcp_cls}">{mcp_dot}</span><span class="status-label">MCP 通道</span></div>
  <div class="model">接口模式：{html.escape(api_mode)}　·　主模型：{html.escape(model)}</div>
</div></section>{msg}
<section class="card upload"><form action="/upload" method="post" enctype="multipart/form-data">
  <div class="file-row"><label class="file-label">▣ 选择视频<input id="videoInput" type="file" name="video" accept="video/*" required></label><span id="fileName" class="filename">未选择任何文件</span></div>
  <div class="divider"></div><button class="primary" type="submit">✦ 开始共看</button>
  <p class="privacy">♢ 文件仅用于本次分析，完成后会删除临时原视频</p>
</form></section>
<section class="card"><div class="section-title"><div class="title-left"><span class="badge-icon">◷</span><h2>最近的视频</h2></div></div>{recent_html}</section>
<div class="footnote"><span class="info">i</span><div>建议 60 秒以内，单个视频不超过 {MAX_UPLOAD_MB}MB。服务器会在需要时自动转换成适合模型读取的格式；原视频分析完成后删除，分析报告保存在部署实例的数据目录中。</div></div>
</main><script>const input=document.getElementById('videoInput');const name=document.getElementById('fileName');if(input)input.addEventListener('change',()=>{{name.textContent=input.files&&input.files[0]?input.files[0].name:'未选择任何文件';}});</script></body></html>"""


@app.get("/app-icon.png", include_in_schema=False)
def app_icon():
    if not ICON_PATH.exists():
        raise HTTPException(404, "icon not found")
    return FileResponse(ICON_PATH, media_type="image/png")


@app.get("/health")
def health():
    return {"ok": True, "name": "共看"}


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
