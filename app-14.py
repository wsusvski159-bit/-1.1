# 共看公开版 v2.1 · 四页切换 / 深夜绿 / MCP客户端标识 / 后台分析任务
from __future__ import annotations

import base64
import contextlib
import html
import json
import os
import secrets
import time
import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastapi import BackgroundTasks, Depends, FastAPI, File, Header, HTTPException, UploadFile, status
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

# v2.1: 上传结束后立即返回任务 ID，AI 分析在后台执行。
JOBS: dict[str, dict] = {}
JOB_TTL_SECONDS = 6 * 60 * 60


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
    # 公开版默认无网页密码；仅保留旧部署兼容。
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
  --bg:#f8f4e9;--paper:#fffef9;--paper-2:#fffaf1;--ink:#203c30;--text:#53635a;--muted:#89918b;
  --accent:#7f9f71;--accent-2:#66865f;--accent-soft:#edf4e9;--line:#d8e2d1;
  --warm:#f5f0df;--danger:#9d655d;--danger-soft:#fff5f2;--shadow:0 16px 42px rgba(51,73,53,.095);
  --glow-a:rgba(192,208,174,.30);--glow-b:rgba(238,226,197,.62);
}
html[data-theme="matcha"]{--bg:#f8f4e9;--paper:#fffef9;--paper-2:#fffaf1;--ink:#203c30;--text:#53635a;--muted:#89918b;--accent:#7f9f71;--accent-2:#66865f;--accent-soft:#edf4e9;--line:#d8e2d1;--warm:#f5f0df;--glow-a:rgba(192,208,174,.30);--glow-b:rgba(238,226,197,.62)}
html[data-theme="rose"]{--bg:#faf0f1;--paper:#fffafb;--paper-2:#fff7f8;--ink:#593d45;--text:#6d555c;--muted:#99868c;--accent:#b98792;--accent-2:#a56f7b;--accent-soft:#f6e5e8;--line:#e8d2d7;--warm:#f8eeee;--glow-a:rgba(222,176,187,.30);--glow-b:rgba(242,219,222,.62)}
html[data-theme="mist"]{--bg:#eef4f6;--paper:#fbfdfe;--paper-2:#f7fbfc;--ink:#2b4852;--text:#4d646c;--muted:#82949a;--accent:#769ba7;--accent-2:#5f8390;--accent-soft:#e5eff2;--line:#d0dfe3;--warm:#edf3f1;--glow-a:rgba(168,200,210,.30);--glow-b:rgba(217,231,235,.65)}
html[data-theme="apricot"]{--bg:#fbf1e6;--paper:#fffaf4;--paper-2:#fff8ef;--ink:#583f33;--text:#685248;--muted:#96847a;--accent:#c28e6f;--accent-2:#aa7358;--accent-soft:#fae8dc;--line:#ead5c5;--warm:#f7eadc;--glow-a:rgba(235,191,160,.31);--glow-b:rgba(247,221,190,.64)}
html[data-theme="lilac"]{--bg:#f3f0f8;--paper:#fdfbff;--paper-2:#faf7ff;--ink:#483e5b;--text:#60566f;--muted:#8d8799;--accent:#9185aa;--accent-2:#766c94;--accent-soft:#ece8f4;--line:#ddd6e9;--warm:#f1edf5;--glow-a:rgba(193,184,216,.31);--glow-b:rgba(228,222,239,.66)}
html[data-theme="night"]{--bg:#101712;--paper:#18221b;--paper-2:#121b15;--ink:#e4eee5;--text:#b8c6ba;--muted:#819085;--accent:#789b72;--accent-2:#9abb92;--accent-soft:#243329;--line:#34453a;--warm:#2a2e24;--danger:#d59a90;--danger-soft:#33201e;--shadow:0 16px 42px rgba(0,0,0,.28);--glow-a:rgba(92,132,88,.22);--glow-b:rgba(112,94,55,.17)}
*{box-sizing:border-box}
html,body{margin:0;width:100%;max-width:100%;overflow-x:hidden;background:var(--bg);color-scheme:light}
html{scroll-behavior:smooth}
body{min-height:100vh;color:var(--text);font-family:system-ui,-apple-system,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;background:radial-gradient(circle at 86% 7%,var(--glow-a),transparent 20rem),radial-gradient(circle at 4% 86%,var(--glow-b),transparent 25rem),linear-gradient(180deg,var(--paper-2) 0%,var(--bg) 100%)}
a{color:inherit;text-decoration:none}button,input,textarea,select{font:inherit}button{touch-action:manipulation}
.shell{width:min(100%,760px);margin:0 auto;padding:calc(24px + env(safe-area-inset-top)) 18px calc(112px + env(safe-area-inset-bottom));position:relative;overflow:hidden}
.header{position:relative;z-index:2;display:grid;grid-template-columns:88px minmax(0,1fr) auto;gap:16px;align-items:center;padding:8px 4px 18px;min-width:0}
.logo{width:84px;height:84px;border-radius:26px;background:var(--paper-2);object-fit:cover;box-shadow:0 12px 28px rgba(74,92,69,.15);border:1px solid rgba(220,210,188,.72)}
.header-copy{min-width:0}.header h1{margin:0 0 7px;color:var(--ink);font-size:clamp(39px,10vw,53px);line-height:1;letter-spacing:.06em;font-weight:880}.header p{margin:0;color:var(--text);font-size:15px;line-height:1.7;max-width:430px}
.header-actions{display:flex;gap:10px;align-self:start;padding-top:8px}.cute-icon-btn{width:50px;height:50px;border:1px solid rgba(218,224,213,.82);border-radius:17px;background:rgba(255,255,255,.90);box-shadow:0 9px 22px rgba(55,70,56,.09);display:grid;place-items:center;color:var(--ink);cursor:pointer;position:relative;padding:0}.cute-icon-btn svg{width:27px;height:27px;overflow:visible}.cute-icon-btn:active{transform:translateY(1px)}.cute-icon-btn.settings:after{content:'';position:absolute;width:8px;height:8px;border-radius:50%;right:3px;top:3px;background:#7eaa5d;box-shadow:0 0 0 2px rgba(255,255,255,.86)}
.header-leaf{position:absolute;right:104px;top:7px;width:46px;height:52px;color:var(--accent);opacity:.45;pointer-events:none}.sparkles{position:absolute;right:134px;top:50px;color:#eadc9f;opacity:.8;pointer-events:none}
.card{width:100%;min-width:0;margin:15px 0;padding:20px;background:rgba(255,254,249,.95);border:1px solid var(--line);border-radius:25px;box-shadow:var(--shadow);overflow:hidden}.msg{margin:12px 0;padding:12px 14px;border-radius:16px;border:1px solid var(--line);background:var(--accent-soft);color:var(--text);font-size:12px;line-height:1.6}.msg.error{background:var(--danger-soft);border-color:#efd6d1;color:#774a43}.status{background:linear-gradient(145deg,color-mix(in srgb,var(--accent-soft) 62%,#fff),color-mix(in srgb,var(--accent-soft) 88%,var(--paper)));padding:20px}.status-top{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr) auto;gap:12px;align-items:center}.status-item{display:flex;align-items:center;gap:10px;min-width:0}.status-icon{width:34px;height:34px;flex:0 0 34px;border-radius:50%;display:grid;place-items:center;background:#79a75f;color:#fff;font-weight:900;font-size:19px;box-shadow:0 7px 18px rgba(92,127,78,.16)}.status-main{min-width:0}.status-main strong{display:block;color:var(--ink);font-size:15px;white-space:nowrap}.status-sub{display:block;margin-top:3px;color:var(--muted);font-size:11px;white-space:nowrap}.check-btn{border:1px solid color-mix(in srgb,var(--line) 85%,#fff);background:rgba(255,255,255,.62);color:var(--ink);border-radius:16px;padding:10px 12px;font-size:12px;font-weight:780;cursor:pointer;white-space:nowrap}.check-btn svg{width:15px;height:15px;vertical-align:-2px;margin-left:3px}.model-row{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-top:16px;padding-top:14px;border-top:1px solid color-mix(in srgb,var(--line) 86%,#fff);font-size:13px}.model-name{color:var(--ink);font-weight:800;max-width:48%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.pill{display:inline-flex;align-items:center;padding:5px 8px;border-radius:999px;background:var(--accent-soft);color:var(--accent-2);font-size:10px;font-weight:800}.detail-link{margin-left:auto;border:0;background:transparent;color:var(--accent-2);font-size:12px;font-weight:750;padding:6px;cursor:pointer}.api-source{display:none}
.upload{padding:20px}.file-row{display:block}.file-label{width:100%;min-height:142px;display:flex;align-items:center;justify-content:center;flex-direction:column;gap:7px;border:1.7px dashed color-mix(in srgb,var(--accent) 64%,#cfd6ca);border-radius:22px;background:rgba(255,255,255,.52);color:var(--accent-2);font-weight:800;cursor:pointer}.file-label input{position:absolute;opacity:0;width:1px;height:1px;pointer-events:none}.upload-cloud{width:43px;height:43px;color:var(--accent)}.file-label strong{font-size:15px}.file-label small{font-size:11px;color:var(--text);font-weight:550}.filename{display:block;padding:9px 4px 0;text-align:center;color:var(--muted);font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.preflight{display:none;margin-top:12px;padding:12px;border-radius:16px;background:color-mix(in srgb,var(--accent-soft) 48%,#fff);border:1px solid var(--line)}.meta-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}.meta-chip{padding:9px 7px;border-radius:12px;background:rgba(255,255,255,.75);color:var(--text);text-align:center;font-size:11px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.preflight-warn{display:none;margin-top:9px;color:#936251;font-size:11px;line-height:1.55}
.persona-line{position:relative;display:flex;align-items:center;gap:10px;margin-top:14px;padding:10px 44px 10px 10px;border-radius:18px;background:linear-gradient(90deg,color-mix(in srgb,var(--warm) 86%,#fff),color-mix(in srgb,var(--accent-soft) 35%,#fff));border:1px solid rgba(225,218,195,.48);font-size:12px;color:var(--text);overflow:hidden}.persona-mini-logo{width:38px;height:38px;flex:0 0 38px;border-radius:12px;object-fit:cover;background:#fff;box-shadow:0 4px 10px rgba(65,78,60,.13)}.persona-line:after{content:'❧';position:absolute;right:10px;bottom:-4px;font-size:31px;color:color-mix(in srgb,var(--accent) 35%,transparent)}
.primary{width:100%;min-height:60px;margin-top:14px;border:0;border-radius:22px;background:linear-gradient(135deg,var(--accent),var(--accent-2));color:#fff;font-size:20px;font-weight:880;letter-spacing:.06em;box-shadow:0 12px 28px color-mix(in srgb,var(--accent) 25%,transparent);cursor:pointer}.primary:active{transform:translateY(1px)}.primary[disabled]{opacity:.72;cursor:wait}.privacy{display:flex;justify-content:center;align-items:center;gap:6px;margin:11px 0 0;color:var(--muted);font-size:10px;text-align:center}
.progress-wrap{display:none;margin-top:14px;padding:13px 14px;border-radius:17px;background:color-mix(in srgb,var(--accent-soft) 54%,#fff);border:1px solid var(--line)}.progress-head{display:flex;justify-content:space-between;gap:12px;margin-bottom:8px;color:var(--text);font-size:12px}.progress-track{height:9px;border-radius:999px;background:color-mix(in srgb,var(--accent-soft) 80%,#d7dfd3);overflow:hidden;position:relative}.progress-bar{width:0;height:100%;border-radius:999px;background:linear-gradient(90deg,color-mix(in srgb,var(--accent) 78%,#fff),var(--accent-2));transition:width .3s ease}.progress-bar.indeterminate{width:35%!important;animation:watching 1.15s ease-in-out infinite}.progress-note{margin-top:8px;color:var(--muted);font-size:12px;line-height:1.55}.retry-row{display:none;margin-top:10px;gap:8px}.retry-row button{flex:1}.tech{display:none;margin-top:9px;padding:9px 11px;border-radius:12px;background:var(--danger-soft);border:1px solid #efd9d4;color:#75514b;font-size:11px;white-space:pre-wrap;overflow-wrap:anywhere}@keyframes watching{0%{transform:translateX(-120%)}50%{transform:translateX(90%)}100%{transform:translateX(290%)}}
.section-title{display:flex;justify-content:space-between;align-items:center;gap:10px;margin-bottom:14px}.title-left{display:flex;align-items:center;gap:9px;min-width:0}.badge-icon{width:35px;height:35px;flex:0 0 35px;border-radius:50%;display:grid;place-items:center;background:var(--accent-soft);color:var(--accent-2)}.badge-icon svg{width:19px;height:19px}.section-title h2{margin:0;color:var(--ink);font-size:19px}.mini-btn{border:1px solid var(--line);background:#fff;color:var(--accent-2);border-radius:14px;padding:9px 11px;font-size:11px;font-weight:750;cursor:pointer}.mini-btn.danger{border-color:#ead6d3;background:#fff9f8;color:#a16a64}.secondary{border:1px solid var(--line);background:#fff;color:var(--accent-2);border-radius:14px;padding:11px;font-weight:780;cursor:pointer}.save{border:0;background:var(--accent);color:#fff;border-radius:14px;padding:11px;font-weight:820;cursor:pointer}
.recent-list{display:grid;gap:10px}.recent-item{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:5px 10px;align-items:center;padding:13px 14px;border-radius:16px;background:color-mix(in srgb,var(--accent-soft) 31%,#fff);border:1px solid var(--line)}.recent-link{min-width:0}.recent-name{display:block;color:var(--ink);font-weight:760;font-size:13px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.recent-summary{display:block;margin-top:3px;color:var(--muted);font-size:10px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.recent-actions{grid-column:2;grid-row:1/3;display:flex;align-items:center;gap:2px}.recent-meta{font-size:10px;color:var(--muted);white-space:nowrap}.recent-fav,.recent-delete{border:0;background:transparent;padding:6px;color:#9a9486;font-size:18px;cursor:pointer}.recent-fav.on{color:#c1a15c}.recent-delete{color:#ad8b85}.empty{text-align:center;padding:23px 10px 15px}.empty-illus{width:92px;height:72px;margin:0 auto 7px}.empty strong{display:block;color:var(--ink);font-size:16px;margin-bottom:5px}.empty span{font-size:11px;color:var(--muted)}
.footnote{position:relative;overflow:hidden;display:flex;gap:10px;align-items:flex-start;margin-top:16px;padding:15px 16px;border:1px solid var(--line);border-radius:22px;background:color-mix(in srgb,var(--accent-soft) 48%,#fff);font-size:11px;line-height:1.72}.info{width:30px;height:30px;flex:0 0 30px;border-radius:50%;display:grid;place-items:center;background:var(--accent);color:#fff;font-weight:900}.footnote-copy{position:relative;z-index:1;padding-right:54px}.foot-leaf{position:absolute;right:-7px;bottom:-12px;width:92px;height:88px;color:var(--accent);opacity:.20}
.bottom-nav{position:fixed;left:50%;bottom:calc(10px + env(safe-area-inset-bottom));transform:translateX(-50%);z-index:35;width:min(calc(100% - 28px),720px);height:72px;padding:7px;background:rgba(255,255,255,.91);border:1px solid rgba(231,231,222,.95);border-radius:28px;box-shadow:0 14px 35px rgba(45,58,47,.13);display:grid;grid-template-columns:repeat(4,1fr);backdrop-filter:blur(12px)}.nav-btn{border:0;background:transparent;border-radius:21px;color:#777f79;font-size:10px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:3px;cursor:pointer}.nav-btn svg{width:22px;height:22px}.nav-btn.active{background:linear-gradient(135deg,color-mix(in srgb,var(--accent-soft) 88%,#fff),color-mix(in srgb,var(--accent-soft) 68%,#fff));color:var(--accent-2);font-weight:800}
.modal{position:fixed;inset:0;z-index:60;display:none;align-items:flex-end;justify-content:center;background:rgba(34,48,40,.28);padding:14px}.modal.open{display:flex}.sheet{width:min(100%,720px);max-height:88vh;overflow:auto;background:var(--paper);border:1px solid var(--line);border-radius:28px 28px 20px 20px;padding:20px;box-shadow:0 30px 80px rgba(31,51,39,.24)}.sheet-head{display:flex;align-items:center;justify-content:space-between;gap:12px}.sheet h2{margin:0;color:var(--ink);font-size:20px}.close{border:0;background:var(--accent-soft);border-radius:50%;width:37px;height:37px;font-size:20px;color:var(--accent-2);cursor:pointer}.api-note{margin-top:12px;padding:11px 12px;border-radius:14px;background:var(--accent-soft);color:var(--text);font-size:11px;line-height:1.65}.field{margin-top:14px}.field label{display:block;margin-bottom:6px;color:var(--text);font-size:11px;font-weight:760}.field input[type=text],.field input[type=password],.field textarea,.field select{width:100%;border:1px solid var(--line);background:#fbfcf8;border-radius:13px;padding:11px 12px;color:var(--ink);outline:none}.field textarea{min-height:68px;resize:vertical}.two{display:grid;grid-template-columns:1fr 1fr;gap:10px}.switch-row{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-top:14px;padding:11px 0;border-top:1px solid #eee8da}.switch-row strong{font-size:12px;color:var(--ink)}.copy-fields{display:none}.copy-fields.open{display:block}.connection-row{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-top:14px;padding:12px;border:1px solid var(--line);border-radius:15px;background:color-mix(in srgb,var(--accent-soft) 35%,#fff)}.connection-row strong{font-size:12px;color:var(--ink)}.connection-row small{display:block;margin-top:3px;font-size:10px;color:var(--muted)}.inline-actions,.sheet-actions{display:grid;grid-template-columns:1fr 1fr;gap:9px;margin-top:14px}.diag{margin-top:14px;padding:12px;border-radius:15px;background:color-mix(in srgb,var(--accent-soft) 43%,#fff);border:1px solid var(--line)}.diag strong{font-size:12px;color:var(--ink)}.diag-result{margin-top:8px;font-size:11px;line-height:1.65;color:var(--text)}.theme-grid{display:grid;grid-template-columns:repeat(5,1fr);gap:8px;margin-top:15px}.theme-choice{border:1px solid #e5e0d5;background:#fff;border-radius:16px;padding:9px 5px;text-align:center;color:#5f665f;cursor:pointer}.theme-choice.active{outline:2px solid var(--accent);outline-offset:2px}.swatch{width:34px;height:34px;border-radius:50%;margin:0 auto 6px;border:3px solid rgba(255,255,255,.85);box-shadow:0 0 0 1px rgba(70,80,70,.10)}.theme-choice small{display:block;font-size:9px}.favorite-list{display:grid;gap:9px;margin-top:14px}.favorite-empty{padding:25px 8px;text-align:center;color:var(--muted);font-size:12px}.favorite-row{padding:12px 13px;border-radius:15px;border:1px solid var(--line);background:color-mix(in srgb,var(--accent-soft) 30%,#fff)}.favorite-row strong{display:block;color:var(--ink);font-size:12px}.favorite-row small{display:block;margin-top:4px;color:var(--muted);font-size:10px}.toast{position:fixed;left:50%;bottom:calc(94px + env(safe-area-inset-bottom));transform:translateX(-50%) translateY(18px);z-index:90;max-width:min(90vw,520px);padding:11px 15px;border-radius:15px;background:#294437;color:#fff;box-shadow:0 15px 40px rgba(24,42,31,.25);opacity:0;pointer-events:none;transition:.22s;font-size:12px}.toast.show{opacity:1;transform:translateX(-50%) translateY(0)}
.report-head{display:flex;align-items:center;margin:2px 0 14px}.back{display:inline-flex;align-items:center;gap:6px;padding:9px 13px;border-radius:14px;background:var(--accent-soft);color:var(--accent-2)}.report-title{margin:0 0 7px;color:var(--ink);font-size:24px;overflow-wrap:anywhere}.report-meta{margin:0;color:var(--muted);font-size:11px;line-height:1.7;overflow-wrap:anywhere}.report-section h3{margin:0 0 10px;color:var(--ink);font-size:17px}.report-section pre{margin:0;max-width:100%;padding:14px;border-radius:16px;background:#f7f8f4;border:1px solid #e2e7de;color:#34473a;white-space:pre-wrap;word-break:break-word;overflow-wrap:anywhere;overflow-x:auto;font-family:inherit;line-height:1.75;font-size:13px}

/* v2.1 · 真分页 + 深夜绿 + MCP 客户端标识 */
.page-view{display:none;min-height:calc(100vh - 145px)}.page-view.active{display:block}.page-heading{display:flex;align-items:flex-end;justify-content:space-between;gap:12px;padding:12px 4px 8px}.page-heading h2{margin:0;color:var(--ink);font-size:28px}.page-heading p{margin:5px 0 0;color:var(--muted);font-size:11px}.page-heading .page-mark{width:44px;height:44px;border-radius:16px;display:grid;place-items:center;background:var(--accent-soft);color:var(--accent-2);font-size:20px}
.mcp-client-chip{margin-left:auto;border:1px solid var(--line);background:color-mix(in srgb,var(--accent-soft) 45%,var(--paper));color:var(--text);border-radius:999px;padding:5px 9px 5px 6px;display:inline-flex;align-items:center;gap:6px;font-size:10px;font-weight:780;cursor:pointer}.mcp-client-icon{width:23px;height:23px;border-radius:8px;display:grid;place-items:center;background:var(--mcp-color,var(--accent));color:#fff;font-size:10px;font-weight:900}.mcp-card{display:grid;grid-template-columns:auto minmax(0,1fr) auto;align-items:center;gap:12px}.mcp-big-icon{width:48px;height:48px;border-radius:16px;display:grid;place-items:center;background:var(--mcp-color,var(--accent));color:#fff;font-size:18px;font-weight:900}.mcp-card strong{display:block;color:var(--ink);font-size:14px}.mcp-card small{display:block;color:var(--muted);font-size:10px;margin-top:3px;line-height:1.5}.settings-menu{display:grid;gap:10px}.settings-row{width:100%;border:1px solid var(--line);background:color-mix(in srgb,var(--accent-soft) 30%,var(--paper));border-radius:18px;padding:14px;display:flex;align-items:center;justify-content:space-between;gap:10px;color:var(--ink);cursor:pointer;text-align:left}.settings-row span{display:block;font-size:11px;color:var(--muted);margin-top:3px}.client-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:14px}.client-choice{border:1px solid var(--line);background:var(--paper);color:var(--text);border-radius:16px;padding:10px 6px;text-align:center;cursor:pointer}.client-choice.active{outline:2px solid var(--accent);outline-offset:2px}.client-logo{width:36px;height:36px;border-radius:12px;margin:0 auto 6px;display:grid;place-items:center;background:var(--client-color,var(--accent));color:#fff;font-size:11px;font-weight:900}.client-choice small{font-size:9px}.custom-client{display:none}.custom-client.open{display:block}.field input[type=color]{width:100%;height:44px;border:1px solid var(--line);background:var(--paper);border-radius:13px;padding:5px}
html[data-theme="night"]{color-scheme:dark}html[data-theme="night"] .card,html[data-theme="night"] .sheet{background:rgba(24,34,27,.96)}html[data-theme="night"] .cute-icon-btn,html[data-theme="night"] .bottom-nav,html[data-theme="night"] .mini-btn,html[data-theme="night"] .secondary,html[data-theme="night"] .theme-choice,html[data-theme="night"] .file-label,html[data-theme="night"] .field input[type=text],html[data-theme="night"] .field input[type=password],html[data-theme="night"] .field textarea,html[data-theme="night"] .field select{background:#1b261f;color:var(--ink);border-color:var(--line)}html[data-theme="night"] .recent-item,html[data-theme="night"] .favorite-row,html[data-theme="night"] .connection-row,html[data-theme="night"] .diag,html[data-theme="night"] .preflight{background:#1c2921}html[data-theme="night"] .persona-line{background:linear-gradient(90deg,#282b22,#1c2921)}html[data-theme="night"] .status{background:linear-gradient(145deg,#1e2c23,#18231c)}html[data-theme="night"] .check-btn{background:#1d2a22;color:var(--ink)}html[data-theme="night"] .bottom-nav{border-color:#34453a}html[data-theme="night"] .nav-btn{color:#91a097}html[data-theme="night"] .nav-btn.active{background:#25352a;color:#b5d1ae}html[data-theme="night"] .toast{background:#dfeadf;color:#1b2a20}
@media(max-width:560px){.shell{padding-left:15px;padding-right:15px}.header{grid-template-columns:78px minmax(0,1fr) auto;gap:12px}.logo{width:74px;height:74px;border-radius:23px}.header h1{font-size:38px}.header p{font-size:12px;line-height:1.65}.header-actions{gap:7px}.cute-icon-btn{width:46px;height:46px;border-radius:16px}.cute-icon-btn svg{width:25px;height:25px}.header-leaf{right:96px;top:5px;width:39px}.sparkles{right:122px;top:45px}.status{padding:17px}.status-top{grid-template-columns:1fr 1fr}.status-check{grid-column:1/3}.check-btn{width:100%}.model-name{max-width:55%}.upload{padding:17px}.file-label{min-height:132px}.card{border-radius:23px;padding:17px}.theme-grid{grid-template-columns:repeat(3,1fr)}.sheet{padding-bottom:calc(20px + env(safe-area-inset-bottom))}}
@media(max-width:390px){.header{grid-template-columns:68px minmax(0,1fr) auto;gap:9px}.logo{width:64px;height:64px;border-radius:20px}.header h1{font-size:32px}.header p{font-size:11px}.header-actions{gap:5px;padding-top:6px}.cute-icon-btn{width:41px;height:41px;border-radius:14px}.cute-icon-btn svg{width:22px;height:22px}.header-leaf,.sparkles{display:none}.status-main strong{font-size:13px}.status-sub{font-size:9px}.model-name{max-width:48%}.meta-grid{grid-template-columns:1fr 1fr}.two{grid-template-columns:1fr}.theme-grid{grid-template-columns:repeat(3,1fr)}}
"""


def _icon_html() -> str:
    if ICON_PATH.exists():
        return '<img class="logo" src="/app-icon.png" alt="共看图标">'
    return '<div class="logo" style="display:grid;place-items:center;font-size:34px">▶</div>'


def _mini_icon_html() -> str:
    if ICON_PATH.exists():
        return '<img class="persona-mini-logo" src="/app-icon.png" alt="">'
    return '<span class="persona-mini-logo" style="display:grid;place-items:center">▶</span>'


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
            <path d="m37 24 2 6 6 2-6 2-2 6-2-6-6-2 6-2Z" fill="#eadca9"/><path d="m108 38 1.5 4.5 4.5 1.5-4.5 1.5-1.5 4.5-1.5-4.5-4.5-1.5 4.5-1.5Z" fill="#eadca9"/>
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
            f'<span class="recent-meta">{duration:.1f}s</span>'
            f'<span class="recent-actions"><button class="recent-fav" type="button" title="收藏" data-fav="{vid}">☆</button>'
            f'<button class="recent-delete" type="button" title="删除这条记录" data-delete="{vid}">×</button></span></div>'
        )
    return '<div class="recent-list" id="recentList">' + "".join(items) + "</div>"


def _pretty_model(model: str) -> str:
    value = (model or "").strip()
    if value.startswith("[") and "]" in value:
        value = value.split("]", 1)[1].strip()
    return value or "等待连接自己的 API"


def page(message: str = "", error: bool = False) -> str:
    reports = list_reports(8)
    msg = f'<div class="msg{" error" if error else ""}">{html.escape(message)}</div>' if message else ""
    api_ok = bool((os.getenv("API_KEY", "") or os.getenv("GEMINI_API_KEY", "") or os.getenv("NEWAPI_API_KEY", "")).strip())
    api_mode = os.getenv("API_MODE", "gemini").strip().lower()
    model = (os.getenv("API_MODEL", "") or os.getenv("GEMINI_MODEL", "") or "").strip()
    model_dot = "✓" if api_ok else "○"
    recent_html = _recent_html(reports)
    pretty_model = html.escape(_pretty_model(model))
    server_source = "服务器 API" if api_ok else "等待本机 API"

    template = r"""<!doctype html>
<html lang="zh-CN" data-theme="matcha"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#f8f4e9" id="themeMeta"><title>共看</title><style>__CSS__</style></head>
<body><main class="shell" id="homeTop">
<section class="page-view active" id="pageHome">
<header class="header">
  __ICON__
  <div class="header-copy"><h1>共看</h1><p>上传视频，让 AI 帮你看画面、听声音，生成清晰总结。</p></div>
  <div class="header-actions">
    <button class="cute-icon-btn" type="button" id="themeBtn" aria-label="换颜色" title="换颜色">
      <svg viewBox="0 0 32 32" fill="none" aria-hidden="true"><path d="M16 5.2c-6.5 0-11.5 4.4-11.5 10.1 0 5.4 4.4 9.4 9.2 9.4h1.7c1.2 0 1.9-.9 1.6-1.9-.3-1.2.5-2.3 1.8-2.3h2.7c3.6 0 6-2.5 6-6C27.5 9.3 22.5 5.2 16 5.2Z" stroke="currentColor" stroke-width="2"/><circle cx="10" cy="13" r="2" fill="#9bb58d"/><circle cx="15.5" cy="9.8" r="2" fill="#d8bc98"/><circle cx="21.3" cy="12.4" r="2" fill="#b79aaa"/><path d="m24.7 5.1.7 2 2 .7-2 .7-.7 2-.7-2-2-.7 2-.7Z" fill="#e6d58f"/></svg>
    </button>
    <button class="cute-icon-btn settings" type="button" id="settingsBtn" aria-label="个性设置" title="个性设置">
      <svg viewBox="0 0 32 32" fill="none" aria-hidden="true"><path d="M16 6.8c2.2-3.1 6.7-1.5 6.4 2.2 3.7-.3 5.3 4.2 2.2 6.4 3.1 2.2 1.5 6.7-2.2 6.4.3 3.7-4.2 5.3-6.4 2.2-2.2 3.1-6.7 1.5-6.4-2.2-3.7.3-5.3-4.2-2.2-6.4-3.1-2.2-1.5-6.7 2.2-6.4-.3-3.7 4.2-5.3 6.4-2.2Z" stroke="currentColor" stroke-width="1.9"/><circle cx="16" cy="15.4" r="3.5" fill="#f4eddb" stroke="currentColor" stroke-width="1.7"/><path d="m24 24 1.1 2.5 2.5 1.1-2.5 1.1L24 31l-1.1-2.3-2.5-1.1 2.5-1.1L24 24Z" fill="#9bb58d"/></svg>
    </button>
  </div>
  <svg class="header-leaf" viewBox="0 0 50 58" aria-hidden="true"><path d="M23 55C25 35 31 19 45 5c-2 20-8 37-22 50Z" fill="currentColor"/><path d="M20 42C9 32 5 23 5 13c10 7 16 17 15 29Z" fill="currentColor" opacity=".65"/></svg>
  <svg class="sparkles" width="35" height="30" viewBox="0 0 35 30" aria-hidden="true"><path d="m12 0 2.5 7.5L22 10l-7.5 2.5L12 20l-2.5-7.5L2 10l7.5-2.5Z" fill="currentColor"/><path d="m29 16 1.4 4.1 4.1 1.4-4.1 1.4L29 27l-1.4-4.1-4.1-1.4 4.1-1.4Z" fill="currentColor" opacity=".7"/></svg>
</header>

<section class="card status"><div class="status-top">
  <div class="status-item"><span class="status-icon" id="apiStatusDot">__MODEL_DOT__</span><div class="status-main"><strong id="aiStatusLabel">__AI_LABEL__</strong><span class="status-sub">画面理解 + 声音识别</span></div></div>
  <div class="status-item"><span class="status-icon">✓</span><div class="status-main"><strong>服务正常</strong><span class="status-sub">连接稳定</span></div></div>
  <div class="status-check"><button class="check-btn" type="button" id="checkBtnTop">检查连接 <svg viewBox="0 0 18 18" fill="none"><path d="M2.5 14.5h2v-4h-2v4Zm5.5 0h2V7h-2v7.5Zm5.5 0h2V3.5h-2v11Z" fill="currentColor"/></svg></button></div>
</div>
<div class="model-row"><span>当前模型：</span><span class="model-name" id="modelName">__PRETTY_MODEL__</span><span class="pill">按次计费</span><span class="api-source" id="apiSource">__API_SOURCE__</span><button class="mcp-client-chip" type="button" id="mcpClientBtn"><span class="mcp-client-icon" id="mcpClientIcon">M</span><span id="mcpClientName">MCP 未设置</span></button><button class="detail-link" type="button" id="apiBtn">查看详情 ›</button></div>
</section>__MSG__

<section class="card upload"><form id="uploadForm" enctype="multipart/form-data">
  <div class="file-row"><label class="file-label"><svg class="upload-cloud" viewBox="0 0 48 48" fill="none" aria-hidden="true"><path d="M14.5 36.5h20c6.1 0 10.5-3.7 10.5-8.8 0-5.2-4.2-8.7-9.2-8.7C34.3 12.9 29.3 9 23.6 9c-7.3 0-12.4 5.4-12.8 12C6.2 21.7 3 24.7 3 28.8c0 4.6 3.8 7.7 11.5 7.7Z" stroke="currentColor" stroke-width="2.2"/><path d="M24 32V20m0 0-5 5m5-5 5 5" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg><strong>选择视频文件</strong><small>支持 MP4 / MOV / MKV 等格式</small><input id="videoInput" type="file" name="video" accept="video/*" required></label><span id="fileName" class="filename">未选择任何文件</span></div>
  <div id="preflight" class="preflight"><div class="meta-grid"><div class="meta-chip" id="metaDuration">时长 --</div><div class="meta-chip" id="metaSize">大小 --</div><div class="meta-chip" id="metaResolution">画面 --</div></div><div id="preflightWarn" class="preflight-warn"></div></div>
  <div id="personaLine" class="persona-line">__MINI_ICON__<span id="personaText">老婆，把这个交给阿屿吧。</span></div>
  <button id="submitBtn" class="primary" type="submit">✦ 开始共看</button>
  <div id="progressWrap" class="progress-wrap" aria-live="polite"><div class="progress-head"><span id="progressStage">准备上传</span><span id="progressPct">0%</span></div><div class="progress-track"><div id="progressBar" class="progress-bar"></div></div><div id="progressNote" class="progress-note">视频会先上传，必要时转码，然后交给 AI 看画面和听声音。</div><div id="retryRow" class="retry-row"><button type="button" class="secondary" id="retryBtn">重新试一次</button><button type="button" class="secondary" id="detailBtn">技术详情</button></div><div id="techDetail" class="tech"></div></div>
  <p class="privacy"><span>♢</span><span>文件仅用于本次分析，完成后会删除临时原视频</span></p>
</form></section>

<div class="footnote"><span class="info">i</span><div class="footnote-copy"><div>建议 __MAX_SECONDS__ 秒以内，单个视频不超过 __MAX_MB__MB</div><div>支持从相册选择；Android 公共版可以直接从其他 App 的“分享”菜单把视频交给共看。</div><div>上传完成后 AI 会在后台分析，不需要一直维持上传连接。</div></div><svg class="foot-leaf" viewBox="0 0 110 90" aria-hidden="true"><path d="M58 84c8-28 18-51 40-73-3 29-13 54-40 73Z" fill="currentColor"/><path d="M47 72c-16-20-29-28-44-29 9 19 22 28 44 29Z" fill="currentColor" opacity=".62"/><path d="M66 49c-3-18 1-32 10-44 5 19 2 34-10 44Z" fill="currentColor" opacity=".78"/></svg></div>
</section>

<section class="page-view" id="pageRecords"><div class="page-heading"><div><h2>记录</h2><p>以前一起看过的视频，都放在这里。</p></div><span class="page-mark">◷</span></div><section class="card" id="recentSection"><div class="section-title"><div class="title-left"><span class="badge-icon"><svg viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="8.2" stroke="currentColor" stroke-width="1.8"/><path d="M12 7.5V12l3 2" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg></span><h2>最近的共看</h2></div><button class="mini-btn danger" type="button" id="clearHistoryBtn">清空记录</button></div><div id="recentArea">__RECENT__</div></section></section>

<section class="page-view" id="pageFavorites"><div class="page-heading"><div><h2>收藏</h2><p>把想反复聊的视频留在这里。</p></div><span class="page-mark">☆</span></div><section class="card"><div id="favoriteListPage" class="favorite-list"></div></section></section>

<section class="page-view" id="pageMine"><div class="page-heading"><div><h2>我的</h2><p>连接、称呼和共看的小习惯。</p></div><span class="page-mark">♡</span></div>
<section class="card mcp-card" style="--mcp-color:var(--accent)"><div class="mcp-big-icon" id="mcpBigIcon">M</div><div><strong id="mcpBigName">MCP 客户端未设置</strong><small>选择你把共看接到哪个 AI / 软件；也可以自己定义。</small></div><button class="mini-btn" type="button" id="mcpManageBtn">设置</button></section>
<section class="card settings-menu"><button class="settings-row" type="button" id="mineApiBtn"><div><strong>连接 API</strong><span>自己的 Key、模型和后端</span></div><b>›</b></button><button class="settings-row" type="button" id="minePersonaBtn"><div><strong>称呼与句子</strong><span>TA 怎么叫你、你怎么叫 TA</span></div><b>›</b></button><button class="settings-row" type="button" id="mineThemeBtn"><div><strong>界面颜色</strong><span>奶油绿、雾粉、深夜绿等</span></div><b>›</b></button></section>
</section>
</main>

<nav class="bottom-nav" aria-label="共看导航">
  <button class="nav-btn active" type="button" id="navHome"><svg viewBox="0 0 24 24" fill="none"><path d="m4 11 8-7 8 7v8.5H14v-5h-4v5H4V11Z" fill="currentColor"/></svg><span>首页</span></button>
  <button class="nav-btn" type="button" id="navRecords"><svg viewBox="0 0 24 24" fill="none"><path d="M7 3.5h8l3 3V20H7V3.5Z" stroke="currentColor" stroke-width="1.7"/><path d="M15 3.5V7h3M10 11h5m-5 3h5m-5 3h3" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg><span>记录</span></button>
  <button class="nav-btn" type="button" id="navFavorites"><svg viewBox="0 0 24 24" fill="none"><path d="m12 3.5 2.5 5.1 5.6.8-4 3.9.9 5.5-5-2.6-5 2.6.9-5.5-4-3.9 5.6-.8L12 3.5Z" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/></svg><span>收藏</span></button>
  <button class="nav-btn" type="button" id="navMine"><svg viewBox="0 0 24 24" fill="none"><circle cx="12" cy="8" r="3.2" stroke="currentColor" stroke-width="1.7"/><path d="M5.5 20c.6-4.2 3-6.3 6.5-6.3s5.9 2.1 6.5 6.3" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/></svg><span>我的</span></button>
</nav>

<div class="modal" id="themeModal"><section class="sheet" role="dialog" aria-modal="true" aria-label="界面换色"><div class="sheet-head"><h2>换一个共看的颜色</h2><button class="close" id="closeTheme" type="button">×</button></div><div class="api-note">会整套更换主色、背景、按钮和装饰，不会只换一个突兀的颜色。</div><div class="theme-grid" id="themeGrid">
<button class="theme-choice" data-theme="matcha"><span class="swatch" style="background:#7f9f71"></span><small>奶油绿</small></button>
<button class="theme-choice" data-theme="rose"><span class="swatch" style="background:#b98792"></span><small>雾粉</small></button>
<button class="theme-choice" data-theme="mist"><span class="swatch" style="background:#769ba7"></span><small>奶油蓝</small></button>
<button class="theme-choice" data-theme="apricot"><span class="swatch" style="background:#c28e6f"></span><small>杏仁黄</small></button>
<button class="theme-choice" data-theme="lilac"><span class="swatch" style="background:#9185aa"></span><small>淡紫</small></button>
<button class="theme-choice" data-theme="night"><span class="swatch" style="background:linear-gradient(135deg,#101712,#789b72)"></span><small>深夜绿</small></button>
</div></section></div>

<div class="modal" id="apiModal"><section class="sheet" role="dialog" aria-modal="true" aria-label="API 设置"><div class="sheet-head"><h2>连接自己的 API</h2><button class="close" id="closeApi" type="button">×</button></div>
<div class="api-note"><strong>新手直接在这里填就可以。</strong> API Key 只保存在当前设备，本次分析时通过 HTTPS 发给当前共看后端，不写进 GitHub，也不会写进视频报告。</div>
<div class="connection-row"><div><strong>当前共看服务</strong><small id="serviceOrigin">正在读取地址…</small></div><button class="mini-btn" type="button" id="serviceSettingsBtn">更换服务</button></div>
<div class="field"><label>API 类型</label><select id="apiMode"><option value="gemini">Gemini-compatible（推荐，直接看视频+听声音）</option><option value="openai">OpenAI-compatible（抽帧+转写模式）</option></select></div>
<div class="field"><label>API Base URL</label><input id="apiBase" type="text" maxlength="500" placeholder="例如：https://api.example.com"></div>
<div class="field"><label>API Key</label><input id="apiKey" type="password" maxlength="1200" autocomplete="off" placeholder="只保存在这台设备"></div>
<div class="field"><label>模型名称</label><input id="apiModel" type="text" maxlength="240" placeholder="例如：gemini-2.5-flash"></div>
<div class="field"><label>备用模型（可选）</label><input id="apiFallback" type="text" maxlength="240" placeholder="主模型失败时再使用"></div>
<div class="two"><div class="field"><label>Gemini 鉴权</label><select id="apiAuth"><option value="query_key">?key= API Key</option><option value="bearer">Bearer Token</option></select></div><div class="field"><label>音频模型（OpenAI 模式）</label><input id="apiAudio" type="text" maxlength="120" placeholder="whisper-1"></div></div>
<div class="inline-actions"><button class="secondary" id="clearApi" type="button">清除本机 API</button><button class="save" id="saveApi" type="button">保存 API</button></div>
<div class="diag"><strong>连接检查</strong><div class="diag-result" id="diagResultApi">服务器、API 和 MCP 会一起检查。</div><button class="mini-btn" style="margin-top:9px" id="diagBtnApi" type="button">开始检查</button></div>
</section></div>

<div class="modal" id="settingsModal"><section class="sheet" role="dialog" aria-modal="true" aria-label="个性设置"><div class="sheet-head"><h2>把共看改成你们的叫法</h2><button class="close" id="closeSettings" type="button">×</button></div>
<div class="two"><div class="field"><label for="youName">TA 怎么叫你</label><input id="youName" type="text" maxlength="20" placeholder="例如：老婆"></div><div class="field"><label for="aiName">你怎么叫 TA</label><input id="aiName" type="text" maxlength="20" placeholder="例如：阿屿"></div></div>
<div class="switch-row"><div><strong>自定义整套句子</strong><div style="font-size:10px;color:var(--muted);margin-top:3px">关掉时只替换两个名字；打开后每句话都能改。</div></div><input id="customCopy" type="checkbox"></div>
<div class="copy-fields" id="copyFields"><div class="field"><label>选好视频</label><textarea id="copySelected"></textarea></div><div class="field"><label>上传中</label><textarea id="copyUploading"></textarea></div><div class="field"><label>开始分析</label><textarea id="copyAnalyzing"></textarea></div><div class="field"><label>分析中</label><textarea id="copyWatching"></textarea></div><div class="field"><label>快完成</label><textarea id="copyAlmost"></textarea></div><div class="field"><label>完成</label><textarea id="copyDone"></textarea></div><div class="field"><label>失败</label><textarea id="copyError"></textarea></div></div>
<div class="switch-row"><div><strong>分析完成后通知我</strong><div style="font-size:10px;color:var(--muted);margin-top:3px">Android 版会用系统通知提醒。</div></div><input id="notifyDone" type="checkbox"></div>
<div class="diag"><strong>连接检查</strong><div class="diag-result" id="diagResult">还没有检查</div><button class="mini-btn" style="margin-top:9px" id="diagBtn" type="button">开始检查</button></div>
<div class="sheet-actions"><button class="secondary" id="resetCopy" type="button">恢复默认</button><button class="save" id="saveSettings" type="button">保存设置</button></div></section></div>

<div class="modal" id="mcpClientModal"><section class="sheet" role="dialog" aria-modal="true" aria-label="MCP 客户端标识"><div class="sheet-head"><h2>MCP 客户端标识</h2><button class="close" id="closeMcpClient" type="button">×</button></div><div class="api-note">这里显示“你把共看接到了哪里”。当前版本先由你选择；以后如果客户端身份能可靠传到共看，再自动识别。</div><div class="client-grid" id="clientGrid"><button class="client-choice" data-client="chatgpt"><span class="client-logo" style="--client-color:#2f7d67">GPT</span><small>ChatGPT</small></button><button class="client-choice" data-client="claude"><span class="client-logo" style="--client-color:#9b6d50">C</span><small>Claude</small></button><button class="client-choice" data-client="gemini"><span class="client-logo" style="--client-color:#657bb5">G</span><small>Gemini</small></button><button class="client-choice" data-client="cursor"><span class="client-logo" style="--client-color:#30343a">⌁</span><small>Cursor</small></button><button class="client-choice" data-client="vscode"><span class="client-logo" style="--client-color:#477ea4">VS</span><small>VS Code</small></button><button class="client-choice" data-client="custom"><span class="client-logo" style="--client-color:#7f9f71">＋</span><small>自定义</small></button></div><div class="custom-client" id="customClientFields"><div class="two"><div class="field"><label>显示名称</label><input id="customClientName" type="text" maxlength="24" placeholder="例如：我的 AI"></div><div class="field"><label>小标志</label><input id="customClientIcon" type="text" maxlength="4" placeholder="例如：AI"></div></div><div class="field"><label>标志颜色</label><input id="customClientColor" type="color" value="#7f9f71"></div></div><div class="sheet-actions"><button class="secondary" id="clearMcpClient" type="button">清除标识</button><button class="save" id="saveMcpClient" type="button">保存</button></div></section></div>

<div class="modal" id="favoritesModal"><section class="sheet" role="dialog" aria-modal="true" aria-label="收藏"><div class="sheet-head"><h2>收藏的共看</h2><button class="close" id="closeFavorites" type="button">×</button></div><div class="api-note">收藏只记在当前设备，换设备不会自动同步。</div><div id="favoriteList" class="favorite-list"></div></section></div>
<div class="toast" id="toast"></div>

<script>
const MAX_MB=__MAX_MB__; const MAX_SECONDS=__MAX_SECONDS__;
const DEFAULTS={you:'老婆',ai:'阿屿',custom:false,notify:false,copies:{selected:'{you}，把这个交给{ai}吧。',uploading:'正在把视频送给{ai}…',analyzing:'{you}，{ai}正在看视频。',watching:'{ai}正在看画面，也在认真听声音…',almost:'快好啦，{ai}正在整理刚刚看到的内容。',done:'看完啦，{you}可以去找{ai}聊这个视频了。',error:'{ai}刚刚没看成功，再试一次好吗？'}};
const STORE='gongkan_persona_v19', THEME_STORE='gongkan_theme_v21', API_STORE='gongkan_api_v19', FAV_STORE='gongkan_favorites_v20', MCP_CLIENT_STORE='gongkan_mcp_client_v21';
const THEME_META={matcha:'#f8f4e9',rose:'#faf0f1',mist:'#eef4f6',apricot:'#fbf1e6',lilac:'#f3f0f8',night:'#101712'};
let cfg=loadCfg(), apiCfg=loadApiCfg(), lastError='', lastRecent=[], currentJobId=null;
const $=id=>document.getElementById(id);
function loadCfg(){try{const x=JSON.parse(localStorage.getItem(STORE)||'{}');return {...DEFAULTS,...x,copies:{...DEFAULTS.copies,...(x.copies||{})}};}catch(e){return JSON.parse(JSON.stringify(DEFAULTS));}}
function saveCfg(){localStorage.setItem(STORE,JSON.stringify(cfg));}
function loadApiCfg(){try{return JSON.parse(localStorage.getItem(API_STORE)||'{}')||{};}catch(e){return {};}}
function apiComplete(){return !!(apiCfg&&apiCfg.api_key&&apiCfg.base_url&&apiCfg.model);}
function apiHeaderValue(){if(!apiComplete())return '';try{const json=JSON.stringify(apiCfg);return btoa(unescape(encodeURIComponent(json))).replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,'');}catch(e){return '';}}
function apiFetchOptions(extra={}){const h=new Headers(extra.headers||{});const v=apiHeaderValue();if(v)h.set('X-GongKan-API-Config',v);return {...extra,headers:h};}
function t(key){const raw=(cfg.custom?cfg.copies[key]:DEFAULTS.copies[key])||'';return raw.replaceAll('{you}',cfg.you||DEFAULTS.you).replaceAll('{ai}',cfg.ai||DEFAULTS.ai);}
function toast(s){const el=$('toast');el.textContent=s;el.classList.add('show');setTimeout(()=>el.classList.remove('show'),2200);}
const MCP_PRESETS={chatgpt:{name:'ChatGPT',icon:'GPT',color:'#2f7d67'},claude:{name:'Claude',icon:'C',color:'#9b6d50'},gemini:{name:'Gemini',icon:'G',color:'#657bb5'},cursor:{name:'Cursor',icon:'⌁',color:'#30343a'},vscode:{name:'VS Code',icon:'VS',color:'#477ea4'}};
function loadMcpClient(){try{return JSON.parse(localStorage.getItem(MCP_CLIENT_STORE)||'null')}catch(e){return null}}
function updateMcpClient(){const c=loadMcpClient();const name=c?.name||'MCP 未设置',icon=c?.icon||'M',color=c?.color||'#7f9f71';$('mcpClientName').textContent=name;$('mcpClientIcon').textContent=icon;$('mcpClientIcon').style.setProperty('--mcp-color',color);$('mcpBigName').textContent=c?`${name} · MCP 标识`:'MCP 客户端未设置';$('mcpBigIcon').textContent=icon;$('mcpBigIcon').style.background=color;}
let mcpDraft='';function openMcpClient(){const c=loadMcpClient();mcpDraft=c?.type||'';document.querySelectorAll('.client-choice').forEach(b=>b.classList.toggle('active',b.dataset.client===mcpDraft));$('customClientFields').classList.toggle('open',mcpDraft==='custom');$('customClientName').value=c?.type==='custom'?(c.name||''):'';$('customClientIcon').value=c?.type==='custom'?(c.icon||''):'';$('customClientColor').value=c?.type==='custom'?(c.color||'#7f9f71'):'#7f9f71';openModal('mcpClientModal')}
function closeMcpClient(){closeModal('mcpClientModal')}
document.querySelectorAll('.client-choice').forEach(b=>b.onclick=()=>{mcpDraft=b.dataset.client;document.querySelectorAll('.client-choice').forEach(x=>x.classList.toggle('active',x===b));$('customClientFields').classList.toggle('open',mcpDraft==='custom')});
$('mcpClientBtn').onclick=openMcpClient;$('mcpManageBtn').onclick=openMcpClient;$('closeMcpClient').onclick=closeMcpClient;$('mcpClientModal').addEventListener('click',e=>{if(e.target===$('mcpClientModal'))closeMcpClient()});
$('saveMcpClient').onclick=()=>{if(!mcpDraft)return toast('先选一个客户端');let c;if(mcpDraft==='custom'){const name=$('customClientName').value.trim(),icon=$('customClientIcon').value.trim()||'AI',color=$('customClientColor').value||'#7f9f71';if(!name)return toast('给这个客户端起个名字');c={type:'custom',name,icon,color}}else c={type:mcpDraft,...MCP_PRESETS[mcpDraft]};localStorage.setItem(MCP_CLIENT_STORE,JSON.stringify(c));updateMcpClient();closeMcpClient();toast('MCP 标识已经保存')};
$('clearMcpClient').onclick=()=>{localStorage.removeItem(MCP_CLIENT_STORE);updateMcpClient();closeMcpClient();toast('MCP 标识已清除')};
function simpleModel(s){s=String(s||'').trim();if(s.startsWith('[')&&s.includes(']'))s=s.split(']').slice(1).join(']').trim();return s||'等待连接自己的 API';}
function updateApiBadge(){if(apiComplete()){$('apiStatusDot').textContent='✓';$('aiStatusLabel').textContent=apiCfg.mode==='openai'?'AI 看 + 听':'Gemini 看 + 听';$('modelName').textContent=simpleModel(apiCfg.model);$('apiSource').textContent='本机 API';}else{$('apiSource').textContent='__API_SOURCE__';}}
function setProgress(v,label,detail,displayPct){const n=Math.max(0,Math.min(100,Math.round(v)));$('progressBar').classList.remove('indeterminate');$('progressBar').style.width=n+'%';$('progressPct').textContent=displayPct===undefined?n+'%':displayPct;if(label)$('progressStage').textContent=label;if(detail)$('progressNote').textContent=detail;}
function setWatching(label,detail){$('progressBar').style.width='35%';$('progressBar').classList.add('indeterminate');$('progressPct').textContent='分析中';$('progressStage').textContent=label;$('progressNote').textContent=detail;}
function applyTheme(name){name=THEME_META[name]?name:'matcha';document.documentElement.dataset.theme=name;localStorage.setItem(THEME_STORE,name);$('themeMeta').setAttribute('content',THEME_META[name]);document.querySelectorAll('.theme-choice').forEach(b=>b.classList.toggle('active',b.dataset.theme===name));}
applyTheme(localStorage.getItem(THEME_STORE)||'matcha');
function openModal(id){$(id).classList.add('open')} function closeModal(id){$(id).classList.remove('open')}
$('themeBtn').onclick=()=>openModal('themeModal');$('closeTheme').onclick=()=>closeModal('themeModal');$('themeModal').addEventListener('click',e=>{if(e.target===$('themeModal'))closeModal('themeModal')});document.querySelectorAll('.theme-choice').forEach(b=>b.onclick=()=>{applyTheme(b.dataset.theme);toast('颜色已经换好');});
$('mineApiBtn').onclick=()=>openApi();$('minePersonaBtn').onclick=()=>openSettings();$('mineThemeBtn').onclick=()=>openModal('themeModal');
function applyPersona(){$('personaText').textContent=t('selected');$('youName').value=cfg.you;$('aiName').value=cfg.ai;$('customCopy').checked=!!cfg.custom;$('notifyDone').checked=!!cfg.notify;for(const k of ['selected','uploading','analyzing','watching','almost','done','error']){const id='copy'+k[0].toUpperCase()+k.slice(1);$(id).value=cfg.copies[k]||DEFAULTS.copies[k];}$('copyFields').classList.toggle('open',!!cfg.custom);}
function openSettings(){applyPersona();openModal('settingsModal')} function closeSettings(){closeModal('settingsModal')}
$('settingsBtn').onclick=openSettings;$('closeSettings').onclick=closeSettings;$('settingsModal').addEventListener('click',e=>{if(e.target===$('settingsModal'))closeSettings()});$('customCopy').onchange=()=>$('copyFields').classList.toggle('open',$('customCopy').checked);
$('resetCopy').onclick=()=>{cfg=JSON.parse(JSON.stringify(DEFAULTS));applyPersona();toast('已经恢复默认文案')};
$('saveSettings').onclick=()=>{cfg.you=$('youName').value.trim()||DEFAULTS.you;cfg.ai=$('aiName').value.trim()||DEFAULTS.ai;cfg.custom=$('customCopy').checked;cfg.notify=$('notifyDone').checked;for(const k of ['selected','uploading','analyzing','watching','almost','done','error']){const id='copy'+k[0].toUpperCase()+k.slice(1);cfg.copies[k]=$(id).value.trim()||DEFAULTS.copies[k];}saveCfg();applyPersona();closeSettings();if(window.GongKanAndroid&&GongKanAndroid.setNotifyEnabled)GongKanAndroid.setNotifyEnabled(!!cfg.notify);if(cfg.notify&&window.GongKanAndroid&&GongKanAndroid.requestNotifications)GongKanAndroid.requestNotifications();toast('个性设置已经保存')};
function fillApi(){apiCfg=loadApiCfg();$('apiMode').value=apiCfg.mode||'gemini';$('apiBase').value=apiCfg.base_url||'';$('apiKey').value=apiCfg.api_key||'';$('apiModel').value=apiCfg.model||'';$('apiFallback').value=apiCfg.fallback||'';$('apiAuth').value=apiCfg.auth_style||'query_key';$('apiAudio').value=apiCfg.audio_model||'whisper-1';$('serviceOrigin').textContent=location.origin;}
function openApi(){fillApi();openModal('apiModal')} function closeApi(){closeModal('apiModal')}
$('apiBtn').onclick=openApi;$('closeApi').onclick=closeApi;$('apiModal').addEventListener('click',e=>{if(e.target===$('apiModal'))closeApi()});
$('saveApi').onclick=()=>{const next={mode:$('apiMode').value,base_url:$('apiBase').value.trim().replace(/\/$/,''),api_key:$('apiKey').value.trim(),model:$('apiModel').value.trim(),fallback:$('apiFallback').value.trim(),auth_style:$('apiAuth').value,audio_model:$('apiAudio').value.trim()||'whisper-1'};if(!next.base_url.startsWith('https://'))return toast('API Base URL 要以 https:// 开头');if(!next.api_key)return toast('还没有填写 API Key');if(!next.model)return toast('还没有填写模型名称');apiCfg=next;localStorage.setItem(API_STORE,JSON.stringify(apiCfg));if(window.GongKanAndroid&&GongKanAndroid.saveApiConfig)GongKanAndroid.saveApiConfig(JSON.stringify(apiCfg));updateApiBadge();closeApi();toast('自己的 API 已经保存')};
$('clearApi').onclick=()=>{apiCfg={};localStorage.removeItem(API_STORE);if(window.GongKanAndroid&&GongKanAndroid.saveApiConfig)GongKanAndroid.saveApiConfig('');fillApi();updateApiBadge();toast('已改回使用服务器 API')};
$('serviceSettingsBtn').onclick=()=>{if(window.GongKanAndroid&&GongKanAndroid.openConnectionSettings){GongKanAndroid.openConnectionSettings()}else{toast('网页版当前服务就是 '+location.origin)}};
async function runDiag(target='diagResult'){const box=$(target);box.textContent='正在检查…';try{const r=await fetch('/api/diagnostics',apiFetchOptions({cache:'no-store'}));const d=await r.json();box.innerHTML=`服务器 ${d.server?'✓':'×'}　API ${d.api_configured?'✓':'×'}　MCP ${d.mcp_configured?'✓':'×'}<br>来源：${d.api_source||'-'}　模式：${d.mode||'-'}　模型：${simpleModel(d.model||'-')}`;}catch(e){box.textContent='检查失败：'+e}}
$('diagBtn').onclick=()=>runDiag('diagResult');$('diagBtnApi').onclick=()=>runDiag('diagResultApi');$('checkBtnTop').onclick=()=>{openApi();runDiag('diagResultApi')};
const input=$('videoInput'),nameEl=$('fileName'),form=$('uploadForm'),btn=$('submitBtn');
input.addEventListener('change',()=>{btn.onclick=null;btn.textContent='✦ 开始共看';const f=input.files&&input.files[0];if(!f){nameEl.textContent='未选择任何文件';$('preflight').style.display='none';return}nameEl.textContent=f.name;$('personaText').textContent=t('selected');$('preflight').style.display='block';const sizeMB=f.size/1024/1024;$('metaSize').textContent=sizeMB.toFixed(1)+' MB';$('metaDuration').textContent='读取时长…';$('metaResolution').textContent='读取画面…';let warns=[];if(sizeMB>MAX_MB)warns.push(`文件超过 ${MAX_MB}MB 上限，不能上传。`);const url=URL.createObjectURL(f);const v=document.createElement('video');v.preload='metadata';v.onloadedmetadata=()=>{const dur=Number(v.duration||0);$('metaDuration').textContent=(dur?dur.toFixed(1):'--')+' 秒';$('metaResolution').textContent=`${v.videoWidth||'--'}×${v.videoHeight||'--'}`;if(dur>MAX_SECONDS)warns.push(`建议 ${MAX_SECONDS} 秒以内；这个视频可能会被后端拒绝。`);if((v.videoWidth%2)||(v.videoHeight%2))warns.push('画面尺寸含奇数像素，共看会自动补齐后再交给 AI。');const w=$('preflightWarn');w.textContent=warns.join(' ');w.style.display=warns.length?'block':'none';URL.revokeObjectURL(url)};v.onerror=()=>{URL.revokeObjectURL(url);$('metaDuration').textContent='时长未知';$('metaResolution').textContent='画面未知'};v.src=url});
function clearFailure(){$('retryRow').style.display='none';$('techDetail').style.display='none';lastError=''}function showFailure(detail){lastError=detail||'没有更多技术信息';$('progressWrap').style.display='block';$('progressBar').classList.remove('indeterminate');setProgress(0,'没有看成功',t('error'),'失败');$('retryRow').style.display='flex';$('techDetail').textContent=lastError;btn.disabled=false;btn.textContent='✦ 开始共看'}
$('retryBtn').onclick=()=>form.requestSubmit();$('detailBtn').onclick=()=>{$('techDetail').style.display=$('techDetail').style.display==='block'?'none':'block'};
function notifyDone(msg){if(!cfg.notify)return;try{if(window.GongKanAndroid&&GongKanAndroid.notifyDone){GongKanAndroid.notifyDone('共看看完啦',String(msg||''));return}}catch(e){console.warn('Android completion notification failed:',e)}try{if('Notification'in window&&Notification.permission==='granted')new Notification('共看完成',{body:msg})}catch(e){console.warn('Browser completion notification failed:',e)}}
async function pollJob(jobId){currentJobId=jobId;let tries=0;while(currentJobId===jobId){tries++;try{const r=await fetch('/api/jobs/'+encodeURIComponent(jobId),{cache:'no-store'});const d=await r.json();if(!r.ok)throw new Error(d.detail||('HTTP '+r.status));if(d.status==='done'){$('progressBar').classList.remove('indeterminate');setProgress(100,'看完啦',t('done'));btn.disabled=false;btn.textContent='查看这次报告';const id=d.video_id;btn.onclick=e=>{e.preventDefault();location.href='/report/'+encodeURIComponent(id)};currentJobId=null;refreshRecent();notifyDone(t('done'));return}if(d.status==='error'){currentJobId=null;showFailure(d.error||'AI 分析失败');return}setWatching(d.status==='queued'?'排队准备中':t('analyzing'),d.status==='queued'?'视频已上传，正在准备交给 AI。':t('watching'));}catch(e){if(tries>8){currentJobId=null;showFailure('查询分析状态失败：'+e);return}}await new Promise(r=>setTimeout(r,1500));}}
form.addEventListener('submit',ev=>{ev.preventDefault();if(!input.files||!input.files[0])return;clearFailure();btn.onclick=null;$('progressWrap').style.display='block';btn.disabled=true;btn.textContent='正在上传…';setProgress(1,'正在上传视频',t('uploading'));const xhr=new XMLHttpRequest();xhr.open('POST','/api/jobs',true);const hv=apiHeaderValue();if(hv)xhr.setRequestHeader('X-GongKan-API-Config',hv);xhr.upload.onprogress=e=>{if(e.lengthComputable){const real=Math.max(1,Math.min(100,(e.loaded/e.total)*100));setProgress(real,'正在上传视频',`${t('uploading')}　${Math.round(e.loaded/1024/1024*10)/10} / ${Math.round(e.total/1024/1024*10)/10} MB`)}};xhr.upload.onload=()=>{setProgress(100,'上传完成','视频已经到达你的共看服务，正在创建分析任务…')};xhr.onerror=()=>showFailure('视频上传连接中断，请重试一次。');xhr.onload=()=>{let data=null;try{data=JSON.parse(xhr.responseText||'{}')}catch(e){}if(xhr.status>=200&&xhr.status<300&&data&&data.ok&&data.job_id){setWatching('AI 正在看 + 听',t('watching'));pollJob(data.job_id)}else showFailure((data&&data.detail)||xhr.responseText||`HTTP ${xhr.status}`)};xhr.send(new FormData(form))});
function esc(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}function shortName(s){s=String(s||'视频').replace(/\.[^.]+$/,'');return s.length<=34?s:s.slice(0,31)+'…'}
function getFavs(){try{return new Set(JSON.parse(localStorage.getItem(FAV_STORE)||'[]'))}catch(e){return new Set()}}function saveFavs(s){localStorage.setItem(FAV_STORE,JSON.stringify([...s]))}
function emptyRecent(){return `<div class="empty"><svg class="empty-illus" viewBox="0 0 140 110"><path d="M30 48 70 26l40 22-40 22Z" fill="#e8efe1"/><path d="M30 48v32l40 22V70Z" fill="#dbe7d2"/><path d="M110 48v32l-40 22V70Z" fill="#c6d5ba"/><path d="M70 28c-4-12 8-17 13-8 5-9 17-4 13 8-3 8-13 13-13 13S73 36 70 28Z" fill="#a8bf98"/></svg><strong>还没有分析记录</strong><span>上传视频，开启你的第一次共看吧</span></div>`}
function renderRecent(rows){lastRecent=Array.isArray(rows)?rows:[];if(!lastRecent.length)return emptyRecent();const favs=getFavs();return `<div class="recent-list">`+lastRecent.slice(0,8).map(r=>`<div class="recent-item" data-id="${esc(r.video_id)}"><a class="recent-link" href="/report/${encodeURIComponent(r.video_id)}"><span class="recent-name">${esc(shortName(r.original_name))}</span><span class="recent-summary">${esc(r.summary||'点击查看完整报告')}</span></a><span class="recent-meta">${Number(r.duration_seconds||0).toFixed(1)}s</span><span class="recent-actions"><button class="recent-fav ${favs.has(String(r.video_id))?'on':''}" type="button" data-fav="${esc(r.video_id)}">${favs.has(String(r.video_id))?'★':'☆'}</button><button class="recent-delete" type="button" data-delete="${esc(r.video_id)}">×</button></span></div>`).join('')+`</div>`}
async function refreshRecent(){try{const r=await fetch('/api/recent',{cache:'no-store'});const rows=await r.json();$('recentArea').innerHTML=renderRecent(rows);bindRecent()}catch(e){}}
function bindRecent(){document.querySelectorAll('[data-delete]').forEach(b=>b.onclick=async e=>{e.preventDefault();e.stopPropagation();if(!confirm('删除这条共看记录吗？'))return;const id=b.dataset.delete;const r=await fetch('/api/report/'+encodeURIComponent(id),{method:'DELETE'});if(r.ok){const favs=getFavs();favs.delete(String(id));saveFavs(favs);toast('已经删除');refreshRecent()}});document.querySelectorAll('[data-fav]').forEach(b=>b.onclick=e=>{e.preventDefault();e.stopPropagation();const favs=getFavs(),id=String(b.dataset.fav);if(favs.has(id)){favs.delete(id);toast('已取消收藏')}else{favs.add(id);toast('已经收藏')}saveFavs(favs);refreshRecent()})}
bindRecent();
$('clearHistoryBtn').onclick=async()=>{if(!confirm('清空全部共看记录吗？这个操作不能撤销。'))return;const r=await fetch('/api/reports',{method:'DELETE'});if(r.ok){localStorage.removeItem(FAV_STORE);toast('记录已经清空');refreshRecent()}};
function setNav(active){document.querySelectorAll('.nav-btn').forEach(b=>b.classList.toggle('active',b.id===active))}
function switchPage(page,nav){document.querySelectorAll('.page-view').forEach(p=>p.classList.toggle('active',p.id===page));setNav(nav);window.scrollTo({top:0,behavior:'auto'});if(page==='pageRecords')refreshRecent();if(page==='pageFavorites'){if(!lastRecent.length)refreshRecent().then(renderFavorites);else renderFavorites()}if(page==='pageMine')updateMcpClient()}
$('navHome').onclick=()=>switchPage('pageHome','navHome');$('navRecords').onclick=()=>switchPage('pageRecords','navRecords');$('navFavorites').onclick=()=>switchPage('pageFavorites','navFavorites');$('navMine').onclick=()=>switchPage('pageMine','navMine');
function renderFavorites(){const favs=getFavs();const rows=lastRecent.filter(r=>favs.has(String(r.video_id)));const html=rows.length?rows.map(r=>`<a class="favorite-row" href="/report/${encodeURIComponent(r.video_id)}"><strong>★ ${esc(shortName(r.original_name))}</strong><small>${esc(r.summary||'点击查看完整报告')}</small></a>`).join(''):`<div class="favorite-empty">还没有收藏。去“记录”页点 ☆，就能收进这里。</div>`;if($('favoriteList'))$('favoriteList').innerHTML=html;if($('favoriteListPage'))$('favoriteListPage').innerHTML=html}

applyPersona();updateApiBadge();updateMcpClient();refreshRecent().then(renderFavorites);
</script></body></html>"""

    return (template
        .replace("__CSS__", _base_css())
        .replace("__ICON__", _icon_html())
        .replace("__MINI_ICON__", _mini_icon_html())
        .replace("__MODEL_DOT__", model_dot)
        .replace("__AI_LABEL__", "Gemini 看 + 听" if api_mode == "gemini" else "AI 看 + 听")
        .replace("__PRETTY_MODEL__", pretty_model)
        .replace("__API_SOURCE__", server_source)
        .replace("__MSG__", msg)
        .replace("__RECENT__", recent_html)
        .replace("__MAX_MB__", str(MAX_UPLOAD_MB))
        .replace("__MAX_SECONDS__", str(MAX_DURATION_SECONDS)))


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


def _decode_client_api_config(raw: str | None) -> dict[str, str] | None:
    if not raw:
        return None
    if len(raw) > 12000:
        raise HTTPException(400, "API 配置数据太长")
    try:
        padded = raw + "=" * ((4 - len(raw) % 4) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
    except Exception:
        raise HTTPException(400, "API 配置无法读取")
    if not isinstance(data, dict):
        raise HTTPException(400, "API 配置格式不正确")
    allowed = {"mode", "api_key", "base_url", "model", "fallback", "audio_model", "auth_style"}
    clean: dict[str, str] = {}
    for key in allowed:
        value = data.get(key)
        if value is not None:
            clean[key] = str(value).strip()
    return clean or None


def client_api_config(x_gongkan_api_config: str | None = Header(default=None, alias="X-GongKan-API-Config")) -> dict[str, str] | None:
    return _decode_client_api_config(x_gongkan_api_config)


def _analyze_upload(video: UploadFile, api_config: dict[str, str] | None = None) -> dict:
    temp_path = _save_upload(video)
    try:
        return analyze_video(temp_path, video.filename or "video", api_config=api_config)
    finally:
        try:
            temp_path.unlink(missing_ok=True)
        except Exception:
            pass


def _prune_jobs() -> None:
    now = time.time()
    stale = [jid for jid, job in JOBS.items() if now - float(job.get("created_at", now)) > JOB_TTL_SECONDS]
    for jid in stale:
        JOBS.pop(jid, None)


def _run_analysis_job(job_id: str, temp_path: Path, original_name: str, api_config: dict[str, str] | None) -> None:
    job = JOBS.get(job_id)
    if not job:
        temp_path.unlink(missing_ok=True)
        return
    job["status"] = "analyzing"
    job["updated_at"] = time.time()
    try:
        report = analyze_video(temp_path, original_name, api_config=api_config)
        job.update({
            "status": "done",
            "video_id": report.get("video_id"),
            "original_name": report.get("original_name"),
            "duration_seconds": report.get("duration_seconds"),
            "model": (report.get("models") or {}).get("video_audio_understanding") or "AI",
            "updated_at": time.time(),
        })
    except Exception as exc:
        job.update({"status": "error", "error": str(exc), "updated_at": time.time()})
    finally:
        temp_path.unlink(missing_ok=True)


@app.get("/app-icon.png", include_in_schema=False)
def app_icon():
    if not ICON_PATH.exists():
        raise HTTPException(404, "icon not found")
    return FileResponse(ICON_PATH, media_type="image/png")


@app.get("/health")
def health():
    return {"ok": True, "name": "共看", "ui": "v2.1-tabs-night-mcp-jobs"}


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


@app.post("/api/jobs", dependencies=[Depends(require_auth)])
def create_analysis_job(
    background_tasks: BackgroundTasks,
    video: UploadFile = File(...),
    api_config: dict[str, str] | None = Depends(client_api_config),
):
    _prune_jobs()
    temp_path = _save_upload(video)
    job_id = uuid.uuid4().hex
    now = time.time()
    JOBS[job_id] = {
        "job_id": job_id,
        "status": "queued",
        "original_name": video.filename or "video",
        "created_at": now,
        "updated_at": now,
    }
    background_tasks.add_task(_run_analysis_job, job_id, temp_path, video.filename or "video", api_config)
    return JSONResponse({"ok": True, "job_id": job_id, "status": "queued"}, status_code=202)


@app.get("/api/jobs/{job_id}", dependencies=[Depends(require_auth)])
def get_analysis_job(job_id: str):
    _prune_jobs()
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "分析任务不存在或已经过期")
    return JSONResponse({k: v for k, v in job.items() if k not in {"api_config"}})


@app.post("/api/upload", dependencies=[Depends(require_auth)])
def api_upload(video: UploadFile = File(...), api_config: dict[str, str] | None = Depends(client_api_config)):
    try:
        report = _analyze_upload(video, api_config)
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
    return HTMLResponse(f"""<!doctype html><html lang="zh-CN" data-theme="matcha"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><meta name="theme-color" content="#f8f4e9"><title>{name} · 共看</title><style>{_base_css()}</style></head><body><main class="shell">
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
def api_diagnostics(api_config: dict[str, str] | None = Depends(client_api_config)):
    env_key = (os.getenv("API_KEY", "") or os.getenv("GEMINI_API_KEY", "") or os.getenv("NEWAPI_API_KEY", "")).strip()
    env_base = (os.getenv("API_BASE_URL", "") or os.getenv("GEMINI_BASE_URL", "") or os.getenv("NEWAPI_BASE_URL", "")).strip()
    env_model = (os.getenv("API_MODEL", "") or os.getenv("GEMINI_MODEL", "")).strip()
    env_mode = os.getenv("API_MODE", "gemini").strip().lower()
    local_ok = bool(api_config and api_config.get("api_key") and api_config.get("base_url") and api_config.get("model"))
    return {
        "server": True,
        "api_configured": local_ok or bool(env_key and env_base and env_model),
        "api_source": "本机 API" if local_ok else ("服务器 API" if env_key and env_base and env_model else "未配置"),
        "mcp_configured": bool(MCP_PATH_TOKEN),
        "mode": (api_config or {}).get("mode") or env_mode,
        "model": (api_config or {}).get("model") or env_model or "未配置",
        "max_upload_mb": MAX_UPLOAD_MB,
        "max_duration_seconds": MAX_DURATION_SECONDS,
    }
