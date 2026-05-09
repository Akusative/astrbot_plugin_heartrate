# astrbot_plugin_heartrate 💓

一款专为 AstrBot 打造的实时心率监测插件。它可以将你在智能手环/手表上的心跳同步注入到与机器人的对话中，让 AI 感知你的每一次“心动”。

## 🌟 最新特性 (v1.3.0)

- 🤖 **全协议兼容重构**：从旧版单一支持 Apple Watch HDS (HTTP PUT)，全面升级为支持 GET/POST/PUT 及 URL Param、JSON、Form-Data 多种传参格式。
- ⌚ **多设备无缝支持**：
  - **Apple Watch** (通过 HDS App 推送)
  - **小米手环** (配合 `CatlabPing` 安卓伴侣 App 拦截 Notify for Mi Band 广播)
  - **华为手表** (通过 Health Sync 第三方同步推送)
- 🚀 **开箱即用，零配置**：插件加载时会自动在数据目录释放并后台启动 `heartrate_receiver_v2.py` 监听服务，无需手动配置环境变量或繁琐的文件路径。
- 🛠️ **跨平台进程管理**：支持 Windows / Linux 环境。在聊天窗口发送 `/重启心率服务` 即可随时拉起掉线的服务端进程。

## 📊 核心能力

- **`get_heartrate` 工具**：大模型可以通过该工具获取你的实时心率、趋势分析以及当前状态判定。
- **状态区间诊断**：
  - `<60`: 静息状态
  - `60-80`: 放松状态
  - `80-100`: 轻度兴奋
  - `100-120`: 中度兴奋
  - `120-140`: 高度兴奋
  - `140-160`: 剧烈运动
  - `160+`: 极限状态

## 🔌 硬件接入指南

本插件支持多款智能手表/手环，推荐通过以下非收费方案进行配置，**完全无需使用 Tasker 等收费或复杂的自动化软件**。

### 🍊 小米手环 / 华米 Amazfit (推荐采用 CatlabPing 广播联动)
由于官方 App 数据封闭，推荐使用 **Notify for Mi Band / Notify for Amazfit** 配合本作者开发的 **CatlabPing** 伴侣应用使用：
1. **安装软件**：在手机上安装 `Notify for Mi Band` 以及 `CatlabPing` (v3.4.0+)。
2. **开启广播**：在 Notify 设置中开启“广播心率数据 (Broadcast Heart Rate)”选项（这会向安卓系统发送 `com.mc.miband.heartRate` 广播）。
3. **CatlabPing 设置**：在 CatlabPing 的“💖 心率自动监听”模块中填入装有 AstrBot 插件的公网 IP 及端口（例如：`http://your-ip:3476`），并打开监听开关。CatlabPing 将在底层静默拦截心跳，并自动上报给你的机器人。

### 🌸 华为手表 / 手环
华为运动健康生态同样高度封闭，不支持本地广播。你可以选择以下两种方案之一：

- **方案 A：利用 Health Sync (健康同步) 直连服务端**
  如果你使用 Health Sync 同步数据，且该软件支持 HTTP Webhook 或 REST API 推送功能，你**完全不需要借助 CatlabPing**。只需在 Health Sync 的推送地址中直接填入电脑端 AstrBot 心率服务的公网 IP（例如：`http://你的公网IP:3476/api/push`）。本插件已支持多协议无缝解析，可直接吞吐同步过来的数据。

- **方案 B：利用 Gadgetbridge (开源伴侣) 联动 CatlabPing**
  Gadgetbridge 是一款支持部分华为/荣耀手环的纯开源替代软件。如果你用它替代了官方 App，可以在其设置中允许心率数据的系统广播。只要广播被发出，`CatlabPing` 就能像拦截小米手环一样，瞬间捕获并上传。

## 🔧 开发依赖

- 语言：Python 3.9+
- 依赖：纯内置库（`http.server`, `json`, `os`, `subprocess` 等），**无需 pip install** 任何额外包。
