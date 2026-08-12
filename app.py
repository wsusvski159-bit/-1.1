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

from video_analyzer import (
    analyze_video,
    clear_reports,
    delete_report,
    get_report,
    list_reports,
)
from mcp_bridge import mcp as video_mcp

load_dotenv()
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("DATA_DIR", str(BASE_DIR / "data"))).resolve()
UPLOADS_DIR = DATA_DIR / "uploads"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "80"))
MAX_DURATION_SECONDS = int(os.getenv("MAX_DURATION_SECONDS", "60"))
APP_USERNAME = os.getenv("APP_USERNAME", "gongkan").strip() or "gongkan"
APP_PASSWORD = os.getenv("APP_PASSWORD", "").strip()
MCP_PATH_TOKEN = os.getenv("MCP_PATH_TOKEN", "").strip()
ICON_PATH = BASE_DIR / "app-icon-512.png"


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    async with video_mcp.session_manager.run():
        yield


app = FastAPI(title="共看", lifespan=lifespan)

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
    # v1.8 默认不需要网页密码；保留兼容旧部署的能力。
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
    return r"""
:root{
  --bg:#f8f4e9;--paper:#fffef9;--ink:#1f3b2f;--text:#415249;--muted:#7b847d;
  --sage:#78996f;--sage-2:#66865f;--sage-soft:#edf4e9;--sage-line:#d6e2cf;
  --danger:#9a5d53;--danger-soft:#fbefec;--sand:#e9dfc8;--shadow:0 18px 48px rgba(51,73,53,.10);--radius:28px;
}
*{box-sizing:border-box}html,body{margin:0;width:100%;max-width:100%;overflow-x:hidden;background:var(--bg);color-scheme:light}
body{min-height:100vh;color:var(--text);font-family:system-ui,-apple-system,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;background:radial-gradient(circle at 88% 8%,rgba(191,205,170,.30),transparent 20rem),radial-gradient(circle at 4% 85%,rgba(236,225,198,.62),transparent 25rem),linear-gradient(180deg,#faf7ef 0%,#f7f2e6 100%)}
a{color:inherit;text-decoration:none}button,input,textarea{font:inherit}.shell{width:min(100%,760px);margin:0 auto;padding:26px 18px calc(46px + env(safe-area-inset-bottom));position:relative;overflow:hidden}
.decor{position:absolute;right:6px;top:42px;width:150px;height:155px;opacity:.42;pointer-events:none;z-index:0}.hero{position:relative;display:grid;grid-template-columns:112px minmax(0,1fr);gap:24px;align-items:center;padding:24px 8px 30px;min-width:0;z-index:1}.hero>div{min-width:0}.logo{width:108px;height:108px;border-radius:30px;background:#fffaf0;object-fit:cover;box-shadow:0 14px 30px rgba(78,96,69,.15);border:1px solid rgba(220,210,188,.8)}
.hero h1{margin:0 0 12px;color:var(--ink);font-size:clamp(46px,12vw,66px);line-height:.98;letter-spacing:.05em;font-weight:850}.hero p{margin:0;max-width:430px;color:#506057;font-size:18px;line-height:1.75;padding-right:82px}
.card{width:100%;min-width:0;margin:16px 0;padding:22px;background:rgba(255,254,249,.96);border:1px solid rgba(215,225,204,.96);border-radius:var(--radius);box-shadow:var(--shadow);overflow:hidden}.status{padding:22px;background:linear-gradient(145deg,rgba(247,250,241,.98),rgba(240,246,233,.98));border-color:#d6e1c8}.status-top{display:grid;grid-template-columns:1fr 1fr auto;gap:13px 16px;align-items:center;min-width:0}.status-item{min-width:0;display:flex;align-items:center;gap:10px;font-size:16px;color:#31493a}.status-icon{width:34px;height:34px;flex:0 0 34px;border-radius:50%;display:grid;place-items:center;background:#7a9b6f;color:#fff;font-size:19px;font-weight:900}.model{margin-top:17px;padding-top:16px;border-top:1px solid #dce5d5;color:#3d5044;font-size:15px;line-height:1.65;overflow-wrap:anywhere;word-break:break-word}.status-actions{display:flex;justify-content:flex-end;gap:8px;flex-wrap:wrap}.mini-btn{border:1px solid #ccd9c7;background:#f9fbf6;color:#557152;border-radius:13px;padding:9px 12px;font-weight:700;cursor:pointer}.mini-btn.danger{color:#8b554d;border-color:#ead5cf;background:#fff9f7}
.msg{width:100%;min-width:0;margin:15px 0;padding:15px 17px;border-radius:18px;border:1px solid #d4e5cf;background:#eef6ea;color:#35503d;line-height:1.7;overflow-wrap:anywhere;word-break:break-word}.msg.error{background:var(--danger-soft);border-color:#edcfc8;color:#74463f}
.upload{padding:30px 26px}.file-row{display:flex;align-items:center;gap:14px;min-width:0}.file-label{flex:0 0 auto;display:inline-flex;align-items:center;gap:9px;padding:12px 16px;border:1.7px dashed #92aa85;border-radius:16px;background:#fbfcf7;color:#66815e;font-weight:750;cursor:pointer}.file-label input{position:absolute;opacity:0;width:1px;height:1px;pointer-events:none}.filename{min-width:0;flex:1;color:#67716a;font-size:15px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.divider{height:1px;margin:24px 0 20px;background:linear-gradient(90deg,transparent,#e0d6bd 12%,#e0d6bd 88%,transparent)}
.persona-line{margin:14px 0 0;padding:12px 14px;border-radius:16px;background:#f7f4e9;color:#5d665f;font-size:14px;line-height:1.6}.preflight{display:none;margin:14px 0 0;padding:14px;border-radius:16px;background:#f6f9f2;border:1px solid #e0e8da}.meta-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}.meta-chip{padding:10px;border-radius:13px;background:#fff;color:#526157;text-align:center;font-size:12px;overflow:hidden;text-overflow:ellipsis}.preflight-warn{display:none;margin-top:10px;color:#946251;font-size:12px;line-height:1.55}
.primary{width:100%;min-height:68px;border:0;border-radius:22px;background:linear-gradient(135deg,#7c9c71,#65895f);color:#fff;font-size:22px;font-weight:850;letter-spacing:.08em;box-shadow:0 12px 28px rgba(92,124,87,.23);cursor:pointer}.primary:active{transform:translateY(1px)}.privacy{display:flex;justify-content:center;align-items:center;gap:7px;margin:15px 0 0;color:#858d86;font-size:13px;text-align:center}.progress-wrap{display:none;margin-top:18px;padding:14px 15px;border-radius:18px;background:#f3f7ef;border:1px solid #dce6d6}.progress-head{display:flex;justify-content:space-between;gap:12px;margin-bottom:9px;color:#4c6352;font-size:13px}.progress-track{height:10px;border-radius:999px;background:#dfe8da;overflow:hidden}.progress-bar{width:0;height:100%;border-radius:999px;background:linear-gradient(90deg,#8bab7f,#668b61);transition:width .35s ease}.progress-note{margin-top:8px;color:#6d786f;font-size:13px;line-height:1.6}.primary[disabled]{opacity:.72;cursor:wait}.retry-row{display:none;margin-top:12px;gap:9px}.retry-row button{flex:1}.tech{display:none;margin-top:10px;padding:10px 12px;border-radius:12px;background:#fff9f7;border:1px solid #efd9d4;color:#75514b;font-size:12px;white-space:pre-wrap;overflow-wrap:anywhere}
.section-title{display:flex;justify-content:space-between;align-items:center;gap:12px;min-width:0;margin-bottom:16px}.title-left{display:flex;align-items:center;min-width:0;gap:10px}.badge-icon{width:38px;height:38px;flex:0 0 38px;border-radius:50%;display:grid;place-items:center;background:#e5efdf;color:#66845f;font-size:18px}.section-title h2{margin:0;color:#213c30;font-size:25px;line-height:1.2}.section-link{color:#6d8a64;font-size:14px;white-space:nowrap}
.recent-list{display:grid;grid-template-columns:minmax(0,1fr);gap:11px;width:100%;min-width:0}.recent-item{width:100%;min-width:0;display:grid;grid-template-columns:minmax(0,1fr) auto;gap:6px 10px;align-items:center;padding:15px 16px;border-radius:17px;background:#f8faf5;border:1px solid #e1e8dc;overflow:hidden}.recent-link{min-width:0}.recent-name{display:block;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#2f4938;font-weight:700}.recent-summary{display:block;margin-top:4px;color:#89918b;font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.recent-meta{color:#8c938d;font-size:12px;white-space:nowrap}.recent-delete{grid-column:2;grid-row:1/3;border:0;background:transparent;color:#a58c85;font-size:17px;padding:7px;cursor:pointer}
.empty{text-align:center;padding:28px 10px 18px;color:#7b837e}.empty-illus{width:110px;height:90px;margin:0 auto 10px}.empty strong{display:block;margin-bottom:5px;color:#3c5144;font-size:19px}.empty span{font-size:14px}.footnote{display:flex;align-items:flex-start;gap:12px;margin-top:18px;padding:17px 18px;border:1px solid #d7e1cf;border-radius:23px;background:rgba(244,247,237,.90);color:#69736b;font-size:14px;line-height:1.75}.info{width:30px;height:30px;flex:0 0 30px;border-radius:50%;display:grid;place-items:center;background:#73916b;color:#fff;font-weight:900}
.report-head{display:flex;align-items:center;margin:2px 0 14px}.back{display:inline-flex;align-items:center;gap:6px;padding:9px 13px;border-radius:14px;background:#edf3e8;color:#4e6950}.report-title{margin:0 0 7px;color:#213c30;font-size:26px;overflow-wrap:anywhere;word-break:break-word}.report-meta{margin:0;color:#7c857e;font-size:13px;line-height:1.7;overflow-wrap:anywhere;word-break:break-word}.report-section h3{margin:0 0 11px;color:#294334;font-size:19px}.report-section pre{margin:0;max-width:100%;padding:16px;border-radius:18px;background:#f7f8f4;border:1px solid #e2e7de;color:#34473a;white-space:pre-wrap;word-break:break-word;overflow-wrap:anywhere;overflow-x:auto;font-family:inherit;line-height:1.78}
.modal{position:fixed;inset:0;z-index:50;display:none;align-items:flex-end;justify-content:center;background:rgba(34,48,40,.28);padding:16px}.modal.open{display:flex}.sheet{width:min(100%,720px);max-height:88vh;overflow:auto;background:#fffef9;border:1px solid #dce5d5;border-radius:28px 28px 20px 20px;padding:22px;box-shadow:0 30px 80px rgba(31,51,39,.24)}.sheet-head{display:flex;align-items:center;justify-content:space-between;gap:12px}.sheet h2{margin:0;color:#244032}.close{border:0;background:#edf3e8;border-radius:50%;width:38px;height:38px;font-size:20px;color:#587052}.field{margin-top:16px}.field label{display:block;margin-bottom:7px;color:#526257;font-size:13px;font-weight:700}.field input[type=text],.field textarea{width:100%;border:1px solid #d7e1d2;background:#fbfcf8;border-radius:14px;padding:12px 13px;color:#34483a;outline:none}.field textarea{min-height:70px;resize:vertical}.two{display:grid;grid-template-columns:1fr 1fr;gap:12px}.switch-row{display:flex;justify-content:space-between;align-items:center;gap:14px;margin-top:16px;padding:12px 0;border-top:1px solid #eee8da}.copy-fields{display:none}.copy-fields.open{display:block}.diag{margin-top:16px;padding:14px;border-radius:16px;background:#f6f9f2;border:1px solid #e1e9dc}.diag-result{margin-top:9px;font-size:13px;line-height:1.7;color:#657169}.sheet-actions{display:flex;gap:10px;margin-top:18px}.sheet-actions button{flex:1}.secondary{border:1px solid #ccd9c7;background:#fff;color:#5a7256;border-radius:15px;padding:12px;font-weight:750}.save{border:0;background:#6f9068;color:#fff;border-radius:15px;padding:12px;font-weight:800}
.toast{position:fixed;left:50%;bottom:calc(24px + env(safe-area-inset-bottom));transform:translateX(-50%) translateY(18px);z-index:80;max-width:min(90vw,520px);padding:12px 16px;border-radius:16px;background:#294437;color:#fff;box-shadow:0 15px 40px rgba(24,42,31,.25);opacity:0;pointer-events:none;transition:.22s}.toast.show{opacity:1;transform:translateX(-50%) translateY(0)}
@media(max-width:560px){.shell{padding:18px 15px 38px}.decor{width:118px;height:128px;right:2px;top:42px;opacity:.34}.hero{grid-template-columns:90px minmax(0,1fr);gap:16px;padding:20px 4px 28px}.logo{width:88px;height:88px;border-radius:24px}.hero h1{font-size:46px}.hero p{font-size:16px;line-height:1.7;padding-right:52px}.card{padding:18px;border-radius:25px}.status{padding:18px}.status-top{grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:10px}.status-actions{grid-column:1/3}.status-item{font-size:14px;gap:7px}.status-icon{width:30px;height:30px;flex-basis:30px}.upload{padding:22px 18px}.file-row{gap:10px}.file-label{padding:11px 13px;font-size:14px}.filename{font-size:13px}.primary{font-size:20px;min-height:58px}.section-title h2{font-size:22px}.meta-grid{grid-template-columns:1fr 1fr 1fr}.two{grid-template-columns:1fr}}
@media(max-width:390px){.hero p{padding-right:0}.file-row{align-items:flex-start;flex-direction:column}.filename{width:100%}.meta-grid{grid-template-columns:1fr 1fr}.recent-delete{padding:4px}}
"""


def _icon_html() -> str:
    if ICON_PATH.exists():
        return '<img class="logo" src="/app-icon.png" alt="共看图标">'
    return '<div class="logo" style="display:grid;place-items:center;font-size:38px">▶</div>'


def _display_name(name: str) -> str:
    stem = Path(name or "视频").stem.strip() or "视频"
    return stem if len(stem) <= 34 else stem[:31] + "…"


def _recent_html(reports: list[dict]) -> str:
    if not reports:
        return """
        <div class="empty" id="emptyState">
          <svg class="empty-illus" viewBox="0 0 140 110" aria-hidden="true">
            <path d="M30 48 70 26l40 22-40 22Z" fill="#e8efe1"/>
            <path d="M30 48v32l40 22V70Z" fill="#dbe7d2"/><path d="M110 48v32l-40 22V70Z" fill="#c6d5ba"/>
            <path d="M30 48 14 64l40 20 16-14Z" fill="#edf3e8"/><path d="m110 48 16 16-40 20-16-14Z" fill="#d7e3cf"/>
            <path d="M70 28c-4-12 8-17 13-8 5-9 17-4 13 8-3 8-13 13-13 13S73 36 70 28Z" fill="#a8bf98"/>
          </svg><strong>还没有分析记录</strong><span>上传视频，开启你的第一次共看吧</span>
        </div>"""
    items = []
    for r in reports:
        vid = html.escape(str(r.get("video_id") or ""))
        name = html.escape(_display_name(str(r.get("original_name") or vid)))
        summary = html.escape(str(r.get("summary") or ""))
        duration = float(r.get("duration_seconds") or 0)
        summary_html = f'<span class="recent-summary">{summary}</span>' if summary else '<span class="recent-summary">点击查看完整报告</span>'
        items.append(
            f'<div class="recent-item" data-id="{vid}"><a class="recent-link" href="/report/{vid}">'
            f'<span class="recent-name">{name}</span>{summary_html}</a>'
            f'<span class="recent-meta">{duration:.1f}s ›</span>'
            f'<button class="recent-delete" type="button" title="删除这条记录" data-delete="{vid}">×</button></div>'
        )
    return '<div class="recent-list" id="recentList">' + "".join(items) + "</div>"


def page(message: str = "", error: bool = False) -> str:
    reports = list_reports(8)
    msg = f'<div class="msg{" error" if error else ""}">{html.escape(message)}</div>' if message else ""
    api_ok = bool((os.getenv("API_KEY", "") or os.getenv("GEMINI_API_KEY", "") or os.getenv("NEWAPI_API_KEY", "")).strip())
    api_mode = os.getenv("API_MODE", "gemini").strip().lower()
    model = (os.getenv("API_MODEL", "") or os.getenv("GEMINI_MODEL", "") or "未配置").strip()
    model_dot = "✓" if api_ok else "!"
    recent_html = _recent_html(reports)

    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#f8f4e9"><title>共看</title><style>{_base_css()}</style></head>
<body><main class="shell">
<svg class="decor" viewBox="0 0 150 160" aria-hidden="true"><path d="M83 150c11-38 23-69 52-102-4 40-18 73-52 102Z" fill="#9eb28e"/><path d="M72 128c-18-26-37-38-58-42 10 25 28 40 58 42Z" fill="#c9d5bb"/><path d="M92 99c-8-28-4-52 8-75 9 30 6 55-8 75Z" fill="#b5c7a6"/><path d="M46 48c-5-15 10-22 17-10 7-12 22-5 17 10-5 12-17 19-17 19S51 60 46 48Z" fill="#cbd6b8"/></svg>
<section class="hero">{_icon_html()}<div><h1>共看</h1><p>上传视频，让 AI 帮你看画面、听声音，生成清晰总结。</p></div></section>
<section class="card status"><div class="status-top">
  <div class="status-item"><span class="status-icon">{model_dot}</span><span>{"Gemini 看+听" if api_mode == "gemini" else "AI 看+听"}</span></div>
  <div class="status-item"><span class="status-icon">✓</span><span>称呼可自定义</span></div>
  <div class="status-actions"><button class="mini-btn" type="button" id="checkBtnTop">检查连接</button><button class="mini-btn" type="button" id="settingsBtn">个性设置</button></div>
</div><div class="model">主模型：{html.escape(model)}</div></section>{msg}
<section class="card upload"><form id="uploadForm" enctype="multipart/form-data">
  <div class="file-row"><label class="file-label"><span style="font-size:20px">▱</span><span>选择文件</span><input id="videoInput" type="file" name="video" accept="video/*" required></label><span id="fileName" class="filename">未选择任何文件</span></div>
  <div id="preflight" class="preflight"><div class="meta-grid"><div class="meta-chip" id="metaDuration">时长 --</div><div class="meta-chip" id="metaSize">大小 --</div><div class="meta-chip" id="metaResolution">画面 --</div></div><div id="preflightWarn" class="preflight-warn"></div></div>
  <div id="personaLine" class="persona-line">老婆，把这个交给阿屿吧。</div>
  <div class="divider"></div><button id="submitBtn" class="primary" type="submit">✦ 开始共看</button>
  <div id="progressWrap" class="progress-wrap" aria-live="polite"><div class="progress-head"><span id="progressStage">准备上传</span><span id="progressPct">0%</span></div><div class="progress-track"><div id="progressBar" class="progress-bar"></div></div><div id="progressNote" class="progress-note">视频会先上传，必要时转码，然后交给 AI 看画面和听声音。</div><div id="retryRow" class="retry-row"><button type="button" class="secondary" id="retryBtn">重新试一次</button><button type="button" class="secondary" id="detailBtn">技术详情</button></div><div id="techDetail" class="tech"></div></div>
  <p class="privacy"><span>♢</span><span>文件仅用于本次分析，完成后会删除临时原视频</span></p>
</form></section>
<section class="card"><div class="section-title"><div class="title-left"><span class="badge-icon">◷</span><h2>最近的视频</h2></div><button class="mini-btn danger" type="button" id="clearHistoryBtn">清空记录</button></div><div id="recentArea">{recent_html}</div></section>
<div class="footnote" style="position:relative;overflow:hidden"><span class="info">i</span><div style="position:relative;z-index:1;padding-right:72px">建议 {MAX_DURATION_SECONDS} 秒以内，单个视频不超过 {MAX_UPLOAD_MB}MB。支持从相册选择；Android 公共版也可以直接从其他 App 的“分享”菜单把视频交给共看。</div><svg viewBox="0 0 110 90" aria-hidden="true" style="position:absolute;right:-4px;bottom:-10px;width:105px;opacity:.34"><path d="M58 84c8-28 18-51 40-73-3 29-13 54-40 73Z" fill="#91a982"/><path d="M47 72c-16-20-29-28-44-29 9 19 22 28 44 29Z" fill="#bacaaa"/><path d="M66 49c-3-18 1-32 10-44 5 19 2 34-10 44Z" fill="#a6b999"/></svg></div>
</main>

<div class="modal" id="settingsModal"><section class="sheet" role="dialog" aria-modal="true" aria-label="个性设置"><div class="sheet-head"><h2>把共看改成你们的叫法</h2><button class="close" id="closeSettings" type="button">×</button></div>
<div class="two"><div class="field"><label for="youName">TA 怎么叫你</label><input id="youName" type="text" maxlength="20" placeholder="例如：老婆"></div><div class="field"><label for="aiName">你怎么叫 TA</label><input id="aiName" type="text" maxlength="20" placeholder="例如：阿屿"></div></div>
<div class="switch-row"><div><strong>自定义整套句子</strong><div style="font-size:12px;color:#879088;margin-top:4px">关掉时只替换两个名字；打开后每句话都能改。</div></div><input id="customCopy" type="checkbox"></div>
<div class="copy-fields" id="copyFields">
  <div class="field"><label>选好视频</label><textarea id="copySelected"></textarea></div>
  <div class="field"><label>上传中</label><textarea id="copyUploading"></textarea></div>
  <div class="field"><label>开始分析</label><textarea id="copyAnalyzing"></textarea></div>
  <div class="field"><label>分析中</label><textarea id="copyWatching"></textarea></div>
  <div class="field"><label>快完成</label><textarea id="copyAlmost"></textarea></div>
  <div class="field"><label>完成</label><textarea id="copyDone"></textarea></div>
  <div class="field"><label>失败</label><textarea id="copyError"></textarea></div>
</div>
<div class="switch-row"><div><strong>分析完成后通知我</strong><div style="font-size:12px;color:#879088;margin-top:4px">Android 版会用系统通知提醒，不用一直盯着进度条。</div></div><input id="notifyDone" type="checkbox"></div>
<div class="diag"><strong>连接检查</strong><div style="font-size:12px;color:#879088;margin-top:4px">一次看服务器、API 配置和 MCP 通道是否准备好。</div><button class="mini-btn" style="margin-top:10px" id="diagBtn" type="button">开始检查</button><div class="diag-result" id="diagResult">还没有检查</div></div>
<div class="sheet-actions"><button class="secondary" id="resetCopy" type="button">恢复默认</button><button class="save" id="saveSettings" type="button">保存设置</button></div></section></div>
<div class="toast" id="toast"></div>
<script>
const MAX_MB={MAX_UPLOAD_MB}; const MAX_SECONDS={MAX_DURATION_SECONDS};
const DEFAULTS={{you:'老婆',ai:'阿屿',custom:false,notify:false,copies:{{
  selected:'{{you}}，把这个交给{{ai}}吧。',
  uploading:'正在把视频送给{{ai}}…',
  analyzing:'{{you}}，{{ai}}正在看视频。',
  watching:'{{ai}}正在看画面，也在认真听声音…',
  almost:'快好啦，{{ai}}正在整理刚刚看到的内容。',
  done:'看完啦，{{you}}可以去找{{ai}}聊这个视频了。',
  error:'{{ai}}刚刚没看成功，再试一次好吗？'
}}}};
const STORE='gongkan_persona_v18';
let cfg=loadCfg(); let analysisTimer=null; let lastError='';
const $=id=>document.getElementById(id);
function loadCfg(){{try{{const x=JSON.parse(localStorage.getItem(STORE)||'{{}}');return {{...DEFAULTS,...x,copies:{{...DEFAULTS.copies,...(x.copies||{{}})}}}};}}catch(e){{return (typeof structuredClone==='function')?structuredClone(DEFAULTS):JSON.parse(JSON.stringify(DEFAULTS));}}}}
function saveCfg(){{localStorage.setItem(STORE,JSON.stringify(cfg));}}
function t(key){{const raw=(cfg.custom?cfg.copies[key]:DEFAULTS.copies[key])||'';return raw.replaceAll('{{you}}',cfg.you||DEFAULTS.you).replaceAll('{{ai}}',cfg.ai||DEFAULTS.ai);}}
function toast(s){{const el=$('toast');el.textContent=s;el.classList.add('show');setTimeout(()=>el.classList.remove('show'),2200);}}
function setProgress(v,label,detail){{const n=Math.max(0,Math.min(100,Math.round(v)));$('progressBar').style.width=n+'%';$('progressPct').textContent=n+'%';if(label)$('progressStage').textContent=label;if(detail)$('progressNote').textContent=detail;}}
function applyPersona(){{$('personaLine').textContent=t('selected');$('youName').value=cfg.you;$('aiName').value=cfg.ai;$('customCopy').checked=!!cfg.custom;$('notifyDone').checked=!!cfg.notify;for(const k of ['selected','uploading','analyzing','watching','almost','done','error']){{const id='copy'+k[0].toUpperCase()+k.slice(1);$(id).value=cfg.copies[k]||DEFAULTS.copies[k];}}$('copyFields').classList.toggle('open',!!cfg.custom);}}
function openSettings(){{applyPersona();$('settingsModal').classList.add('open');}}
function closeSettings(){{$('settingsModal').classList.remove('open');}}
$('settingsBtn').onclick=openSettings;$('closeSettings').onclick=closeSettings;$('settingsModal').addEventListener('click',e=>{{if(e.target===$('settingsModal'))closeSettings();}});$('customCopy').onchange=()=>$('copyFields').classList.toggle('open',$('customCopy').checked);
$('resetCopy').onclick=()=>{{cfg=JSON.parse(JSON.stringify(DEFAULTS));applyPersona();toast('已经恢复默认文案');}};
$('saveSettings').onclick=()=>{{cfg.you=$('youName').value.trim()||DEFAULTS.you;cfg.ai=$('aiName').value.trim()||DEFAULTS.ai;cfg.custom=$('customCopy').checked;cfg.notify=$('notifyDone').checked;for(const k of ['selected','uploading','analyzing','watching','almost','done','error']){{const id='copy'+k[0].toUpperCase()+k.slice(1);cfg.copies[k]=$(id).value.trim()||DEFAULTS.copies[k];}}saveCfg();applyPersona();closeSettings();if(window.GongKanAndroid&&GongKanAndroid.setNotifyEnabled){{GongKanAndroid.setNotifyEnabled(!!cfg.notify);}}if(cfg.notify&&window.GongKanAndroid&&GongKanAndroid.requestNotifications){{GongKanAndroid.requestNotifications();}}toast('个性设置已经保存');}};

async function runDiag(){{const box=$('diagResult');box.textContent='正在检查…';try{{const r=await fetch('/api/diagnostics',{{cache:'no-store'}});const d=await r.json();box.innerHTML=`服务器 ${{d.server?'✓':'×'}}　API 配置 ${{d.api_configured?'✓':'×'}}　MCP ${{d.mcp_configured?'✓':'×'}}<br>模式：${{d.mode||'-'}}　模型：${{d.model||'-'}}`;}}catch(e){{box.textContent='检查失败：'+e;}}}}
$('diagBtn').onclick=runDiag;$('checkBtnTop').onclick=()=>{{openSettings();runDiag();}};

const input=$('videoInput'), nameEl=$('fileName'), form=$('uploadForm'), btn=$('submitBtn');
input.addEventListener('change',async()=>{{const f=input.files&&input.files[0];if(!f){{nameEl.textContent='未选择任何文件';$('preflight').style.display='none';return;}}nameEl.textContent=f.name;$('personaLine').textContent=t('selected');$('preflight').style.display='block';const sizeMB=f.size/1024/1024;$('metaSize').textContent=sizeMB.toFixed(1)+' MB';$('metaDuration').textContent='读取时长…';$('metaResolution').textContent='读取画面…';let warns=[];if(sizeMB>MAX_MB)warns.push(`文件超过 ${{MAX_MB}}MB 上限，不能上传。`);const url=URL.createObjectURL(f);const v=document.createElement('video');v.preload='metadata';v.onloadedmetadata=()=>{{const dur=Number(v.duration||0);$('metaDuration').textContent=(dur?dur.toFixed(1):'--')+' 秒';$('metaResolution').textContent=`${{v.videoWidth||'--'}}×${{v.videoHeight||'--'}}`;if(dur>MAX_SECONDS)warns.push(`建议 ${{MAX_SECONDS}} 秒以内；这个视频可能会被后端拒绝。`);if((v.videoWidth%2)||(v.videoHeight%2))warns.push('画面尺寸含奇数像素，共看会自动补齐后再交给 AI。');const w=$('preflightWarn');w.textContent=warns.join(' ');w.style.display=warns.length?'block':'none';URL.revokeObjectURL(url);}};v.onerror=()=>{{URL.revokeObjectURL(url);$('metaDuration').textContent='时长未知';$('metaResolution').textContent='画面未知';}};v.src=url;}});

function clearFailure(){{$('retryRow').style.display='none';$('techDetail').style.display='none';lastError='';}}
function showFailure(detail){{lastError=detail||'没有更多技术信息';$('progressWrap').style.display='block';setProgress(0,'没有看成功',t('error'));$('retryRow').style.display='flex';$('techDetail').textContent=lastError;btn.disabled=false;btn.textContent='✦ 开始共看';}}
$('retryBtn').onclick=()=>form.requestSubmit();$('detailBtn').onclick=()=>{{$('techDetail').style.display=$('techDetail').style.display==='block'?'none':'block';}};
function notifyDone(msg){{if(!cfg.notify)return;if(window.GongKanAndroid&&GongKanAndroid.notifyDone){{GongKanAndroid.notifyDone(msg);return;}}if('Notification'in window&&Notification.permission==='granted')new Notification('共看完成',{{body:msg}});}}
form.addEventListener('submit',ev=>{{ev.preventDefault();if(!input.files||!input.files[0])return;clearFailure();$('progressWrap').style.display='block';btn.disabled=true;btn.textContent='正在共看…';setProgress(2,'正在上传视频',t('uploading'));const xhr=new XMLHttpRequest();xhr.open('POST','/api/upload',true);xhr.upload.onprogress=e=>{{if(e.lengthComputable){{const p=Math.max(2,Math.min(58,(e.loaded/e.total)*58));setProgress(p,'正在上传视频',`${{t('uploading')}}　${{Math.round(e.loaded/1024/1024*10)/10}} / ${{Math.round(e.total/1024/1024*10)/10}} MB`);}}}};xhr.upload.onload=()=>{{setProgress(62,t('analyzing'),t('watching'));let v=62;analysisTimer=setInterval(()=>{{if(v<92){{v+=Math.max(1,(92-v)*.08);setProgress(v,v>84?t('almost'):t('analyzing'),v>84?t('almost'):t('watching'));}}}},900);}};xhr.onerror=()=>{{if(analysisTimer)clearInterval(analysisTimer);showFailure('上传时网络连接中断。');}};xhr.onload=()=>{{if(analysisTimer)clearInterval(analysisTimer);let data=null;try{{data=JSON.parse(xhr.responseText||'{{}}');}}catch(e){{}}if(xhr.status>=200&&xhr.status<300&&data&&data.ok){{setProgress(100,'看完啦',t('done'));btn.disabled=false;btn.textContent='查看这次报告';const id=data.video_id;notifyDone(t('done'));refreshRecent();btn.onclick=e=>{{e.preventDefault();location.href='/report/'+encodeURIComponent(id);}};}}else{{showFailure((data&&data.detail)||xhr.responseText||`HTTP ${{xhr.status}}`);}}}};xhr.send(new FormData(form));}});

async function refreshRecent(){{try{{const r=await fetch('/api/recent');const rows=await r.json();$('recentArea').innerHTML=renderRecent(rows);bindRecent();}}catch(e){{}}}}
function esc(s){{return String(s??'').replace(/[&<>"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));}}
function shortName(s){{s=String(s||'视频').replace(/\.[^.]+$/,'');return s.length<=34?s:s.slice(0,31)+'…';}}
function renderRecent(rows){{if(!rows.length)return `<div class="empty"><strong>还没有分析记录</strong><span>上传视频，开启你的第一次共看吧</span></div>`;return `<div class="recent-list">`+rows.slice(0,8).map(r=>`<div class="recent-item" data-id="${{esc(r.video_id)}}"><a class="recent-link" href="/report/${{encodeURIComponent(r.video_id)}}"><span class="recent-name">${{esc(shortName(r.original_name))}}</span><span class="recent-summary">${{esc(r.summary||'点击查看完整报告')}}</span></a><span class="recent-meta">${{Number(r.duration_seconds||0).toFixed(1)}}s ›</span><button class="recent-delete" type="button" data-delete="${{esc(r.video_id)}}">×</button></div>`).join('')+`</div>`;}}
function bindRecent(){{document.querySelectorAll('[data-delete]').forEach(b=>b.onclick=async e=>{{e.preventDefault();e.stopPropagation();if(!confirm('删除这条共看记录吗？'))return;const id=b.dataset.delete;const r=await fetch('/api/report/'+encodeURIComponent(id),{{method:'DELETE'}});if(r.ok){{toast('已经删除');refreshRecent();}}}});}}
bindRecent();
$('clearHistoryBtn').onclick=async()=>{{if(!confirm('清空全部共看记录吗？这个操作不能撤销。'))return;const r=await fetch('/api/reports',{{method:'DELETE'}});if(r.ok){{toast('记录已经清空');refreshRecent();}}}};
applyPersona();
</script></body></html>"""


def _save_upload(video: UploadFile) -> Path:
    suffix = Path(video.filename or "video.mp4").suffix.lower() or ".mp4"
    temp_path = UPLOADS_DIR / f"upload-{uuid.uuid4().hex}{suffix}"
    size = 0
    max_bytes = MAX_UPLOAD_MB * 1024 * 1024
    try:
        with temp_path.open("wb") as f:
            while True:
                chunk = video.file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > max_bytes:
                    raise HTTPException(413, f"视频超过 {MAX_UPLOAD_MB}MB 上限")
                f.write(chunk)
        return temp_path
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


def _analyze_upload(video: UploadFile) -> dict:
    temp_path = _save_upload(video)
    try:
        return analyze_video(temp_path, video.filename or "video")
    finally:
        try:
            temp_path.unlink(missing_ok=True)
        except Exception:
            pass


@app.get("/app-icon.png", include_in_schema=False)
def app_icon():
    if not ICON_PATH.exists():
        raise HTTPException(404, "icon not found")
    return FileResponse(ICON_PATH, media_type="image/png")


@app.get("/health")
def health():
    return {"ok": True, "name": "共看", "ui": "v1.8-personalized-all-in-one"}


@app.get("/", response_class=HTMLResponse, dependencies=[Depends(require_auth)])
def home():
    return page()


@app.post("/upload", response_class=HTMLResponse, dependencies=[Depends(require_auth)])
def upload(video: UploadFile = File(...)):
    try:
        report = _analyze_upload(video)
        return HTMLResponse(page(f"分析完成：{report['original_name']}。报告 ID：{report['video_id']}"))
    except HTTPException:
        raise
    except Exception as e:
        return HTMLResponse(page(f"分析失败：{e}", error=True), status_code=500)


@app.post("/api/upload", dependencies=[Depends(require_auth)])
def api_upload(video: UploadFile = File(...)):
    try:
        report = _analyze_upload(video)
        return JSONResponse({
            "ok": True,
            "video_id": report.get("video_id"),
            "original_name": report.get("original_name"),
            "duration_seconds": report.get("duration_seconds"),
            "model": (report.get("models") or {}).get("video_audio_understanding") or "AI",
        })
    except HTTPException as e:
        return JSONResponse({"ok": False, "detail": str(e.detail)}, status_code=e.status_code)
    except Exception as e:
        return JSONResponse({"ok": False, "detail": str(e)}, status_code=500)


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


@app.delete("/api/report/{video_id}", dependencies=[Depends(require_auth)])
def api_delete_report(video_id: str):
    if not delete_report(video_id):
        raise HTTPException(404, "report not found")
    return {"ok": True}


@app.delete("/api/reports", dependencies=[Depends(require_auth)])
def api_clear_reports():
    return {"ok": True, "deleted": clear_reports()}


@app.get("/api/diagnostics", dependencies=[Depends(require_auth)])
def api_diagnostics():
    api_key = (os.getenv("API_KEY", "") or os.getenv("GEMINI_API_KEY", "") or os.getenv("NEWAPI_API_KEY", "")).strip()
    base = (os.getenv("API_BASE_URL", "") or os.getenv("GEMINI_BASE_URL", "") or os.getenv("NEWAPI_BASE_URL", "")).strip()
    model = (os.getenv("API_MODEL", "") or os.getenv("GEMINI_MODEL", "")).strip()
    mode = os.getenv("API_MODE", "gemini").strip().lower()
    return {
        "server": True,
        "api_configured": bool(api_key and base and model),
        "mcp_configured": bool(MCP_PATH_TOKEN),
        "mode": mode,
        "model": model or "未配置",
        "max_upload_mb": MAX_UPLOAD_MB,
        "max_duration_seconds": MAX_DURATION_SECONDS,
    }
