# 共看

让 AI 真正“看见 + 听见”一段视频，再通过 MCP 把视频报告交给 ChatGPT、Claude 等 AI，一起聊刚才看到的内容。

当前版本：**v2.1**

---

## 共看能做什么

1. 上传一段短视频
2. AI 同时理解画面和声音
3. 自动生成结构化音画报告
4. 保存最近看过的视频
5. 通过 MCP 让聊天 AI 读取报告
6. 支持 ChatGPT、Claude、Gemini、Cursor、VS Code 等客户端标识
7. 支持奶油绿、雾粉、奶油蓝、杏仁黄、丁香紫、深夜绿等主题
8. 可以自定义你和 TA 的称呼与提示语

---

# 一、普通用户怎么开始

共看采用“每个人拥有自己的后端”的方式。

这样你的：

- 视频
- 报告
- API Key
- API 额度
- MCP 地址

都不会和其他人混在一起。

第一次使用需要做一次部署，之后正常打开共看使用即可。

---

# 二、创建自己的共看服务

## 1. Fork 这个仓库

点击本仓库右上角：

**Fork → Create fork**

GitHub 会在你的账号下复制一份共看。

以后 Render 使用的就是你自己的这一份仓库。

---

## 2. 注册 Render

打开 Render，使用 GitHub 登录。

然后选择：

**New → Blueprint**

连接刚刚 Fork 的共看仓库。

Render 会自动读取仓库里的：

`render.yaml`

---

## 3. 设置 MCP_PATH_TOKEN

第一次创建时，Render 会要求填写：

`MCP_PATH_TOKEN`

这是你的 MCP 私人入口密钥。

请自己生成一串至少 24 位的随机字符，例如：

```text
aB3xK8mQ2vN7sR4pT9zL6cW1
```

⚠️ 不要直接使用上面的示例。

不要把自己的 MCP_PATH_TOKEN 发给别人，也不要把带 token 的 MCP 地址公开截图。

---

## 4. 等待部署完成

进入 Render：

**你的服务 → Events**

看到绿色：

**Deploy live**

就表示部署成功。

你会得到一个自己的服务地址，例如：

```text
https://xxxx.onrender.com
```

先打开它看看。

如果能看到“共看”首页，说明后端已经正常运行。

> Render 免费实例长时间没人访问时可能会休眠，第一次打开可能需要等待几十秒。

---

# 三、连接自己的 API

API 不需要写进 GitHub，也不需要放进 APK。

打开共看：

**我的 → API 与服务**

填写：

### API 类型

推荐：

```text
Gemini-compatible
```

它可以直接理解视频画面和原始声音。

### API Base URL

填写你的 API 平台提供的地址，例如：

```text
https://api.example.com
```

必须是 `https://` 开头的公网地址。

### API Key

填写你自己的 API Key。

API Key 只保存在你当前使用的设备中，不会写进 GitHub，也不会写进视频报告。

### 模型名称

填写你的 API 平台实际支持的视频模型名称。

例如：

```text
gemini-2.5-flash
```

具体名称以你的 API 平台为准。

### 备用模型

可选。

主模型不可用时，共看可以尝试备用模型。

设置完成后点击：

**连接检查**

服务器和 API 都正常后，就可以开始上传视频。

---

# 四、第一次测试

建议第一次先选择一个：

- 5～20 秒
- MP4
- 文件不要太大

的视频。

点击：

**开始共看**

流程会显示：

```text
上传视频
↓
AI 看画面 + 听声音
↓
整理报告
↓
完成
```

完成后进入：

**记录**

即可看到刚才的视频报告。

---

# 五、连接 MCP

部署完成后，你自己的 MCP 地址格式是：

```text
https://你的服务地址/bridge-你的MCP_PATH_TOKEN/mcp
```

例如：

```text
https://xxxx.onrender.com/bridge-aB3xK8mQ2vN7sR4pT9zL6cW1/mcp
```

⚠️ 上面只是格式示例。

不要公开真实的 MCP 地址，因为其中包含你的私人 token。

## 共看目前提供的 MCP 工具

`list_recent_videos`：查看最近的视频报告。

`get_latest_video_report`：读取最近一次共看的报告。

`get_video_report`：读取指定的视频报告。

这些 MCP 工具目前是只读的。

---

# 六、接入聊天 AI

在支持远程 MCP 的客户端中添加自己的共看 MCP 地址。

连接成功以后，可以直接和 AI 说：

```text
看看我刚才那个视频
```

或者：

```text
读取我最近一次共看的内容
```

AI 就可以读取共看生成的报告，再和你继续聊天。

不同 AI 客户端的 MCP 设置入口可能不同，请以各客户端当前版本为准。

---

# 七、MCP 客户端标识

共看支持显示你把它接到了哪里。

目前可选择：

- ChatGPT
- Claude
- Gemini
- Cursor
- VS Code
- 自定义

位置：

**我的 → MCP 客户端**

也可以自定义：

- 名字
- 小标志
- 标志颜色

这个功能只负责显示客户端标识，不会自动创建 MCP 连接。

---

# 八、隐私说明

公开版共看不会内置作者的：

- Render 服务地址
- API Key
- MCP_PATH_TOKEN
- 私人报告

每个使用者自己部署自己的服务。

视频分析完成后，临时原视频会被删除。

免费 Render 实例的本地文件不适合永久保存重要资料，重新部署或实例重置后，部分历史数据可能丢失。

---

# 九、默认限制

默认配置：

```text
最大上传：80 MB
建议最长视频：60 秒
```

共看主要定位是短视频理解，而不是长视频云存储。

---

# 十、Android APK

Android 安装包会放在本仓库的：

**Releases**

正式发布后，普通用户只需要：

```text
下载 APK
↓
创建自己的 Render 服务
↓
把服务地址填进共看
↓
连接自己的 API
↓
开始使用
```

不需要修改任何 Python 文件。

---

# 十一、项目结构

主要文件：

```text
app.py
video_analyzer.py
mcp_bridge.py
render.yaml
Dockerfile
requirements.txt
app-icon-512.png
```

---

# 当前版本

**共看 v2.1**

目前已经包含：

- 首页 / 记录 / 收藏 / 我的四页
- 视频上传
- 后台分析任务
- Gemini-compatible 视频理解
- OpenAI-compatible 兼容模式
- MCP
- 自定义 API
- 自定义称呼
- 多套主题
- 深夜绿模式
- 收藏
- MCP 客户端标识

后续还会继续完善 Android 分享、首次连接引导、通知和更简单的部署流程。
