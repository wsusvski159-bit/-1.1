# 共看 · 公开版 v1.0

一个“短视频 → 视频模型看+听 → 保存音画报告 → MCP 给聊天 AI 读取”的自部署小工具。

## 公开版和私人版的区别

- **不内置作者的 Render 地址、网页密码、MCP token 或 API Key。**
- 每位使用者自己部署后端，自己的视频、报告、API 额度彼此隔离。
- Android App 第一次启动时填写自己的服务地址、用户名和网页密码；之后可在右上角 ⚙ 修改。
- 页面、按钮、MCP 工具全部使用通用名称“共看”，没有私人称呼。

## 工作原理

1. 手机 App / 网页上传短视频。
2. 后端用 FFmpeg 在必要时压缩视频。
3. Gemini-compatible 视频 API 同时读取画面与原始音轨。
4. 后端保存结构化音画报告，并删除临时原视频。
5. ChatGPT 等支持远程 MCP 的客户端读取最近报告或指定报告。

## 自部署需要准备

- 一个 GitHub 仓库。
- 一个能运行 Docker 的公网服务（示例可用 Render）。
- 一个支持 Gemini `generateContent` + `inline_data` 视频输入的 API Key / Base URL / 模型名。
- ChatGPT 端：你的账号当前需要能创建或启用自定义 MCP App。不同套餐、工作区与 UI 可能不同，以你账号实际界面和 OpenAI 最新说明为准。

## Render 环境变量

至少设置：

- `APP_USERNAME`：网页用户名，默认 `gongkan`。
- `APP_PASSWORD`：网页密码，请使用自己的强密码。
- `MCP_PATH_TOKEN`：MCP 路径密钥，建议 24 位以上随机字符串，不要公开。
- `GEMINI_API_KEY`：你自己的 API Key。
- `GEMINI_BASE_URL`：API Base URL。官方 Google Gemini 可填写 `https://generativelanguage.googleapis.com`；第三方兼容网关填写它自己的地址。
- `GEMINI_MODEL`：你的 API 实际支持的视频模型名。
- `GEMINI_FALLBACK_MODEL`：可选备用模型。

默认还提供：

- `MAX_UPLOAD_MB=80`
- `MAX_DURATION_SECONDS=60`
- `GEMINI_INLINE_TARGET_MB=14`

## MCP 地址

部署完成后，MCP 地址是：

```text
https://你的服务域名/bridge-你的MCP_PATH_TOKEN/mcp
```

`MCP_PATH_TOKEN` 等同于一个入口密钥，不要发截图公开它。

## Android App

公开版 App **不写死任何人的服务地址**。第一次打开会要求填写：

1. 你自己的 `https://...` 服务地址；
2. `APP_USERNAME`；
3. `APP_PASSWORD`。

密码使用 Android Keystore 加密保存在本机。右上角 ⚙ 可以重新设置服务。

GitHub Actions 已包含 `.github/workflows/build-apk.yml`。仓库提交到 `main` 后可在 Actions 构建 `gongkan-public-apk`。

## 隐私与费用

- 不建议多人共用一个作者私人后端：会共享同一份报告列表，也会共同消耗同一个 API 额度。
- 公开版设计为“每人自部署”，因此数据和费用由各自部署者管理。
- Render 等免费实例的本地文件通常不是长期持久存储；重启/重新部署后历史报告可能丢失。要长期保存，后续应接数据库或对象存储。
- 原视频在分析结束后会删除临时文件，但请仍然只上传你有权处理的内容。

## 当前版本定位

这是第一版可分享的自部署工具，不是应用商店成品。后续可以继续做：独立账号、多用户隔离、数据库、对象存储、分享链接、自动更新和更完整的安装教程。

## v1.1 界面更新

- 网页标题与所有公开界面统一为「共看」；不包含私人称呼。
- 首页改为奶油色 + 低饱和绿色卡片式界面，与 App 图标统一。
- 上传区、状态区、最近视频与报告页重新排版，移动端更易用。
- 分析与 MCP 逻辑保持不变。
