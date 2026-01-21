# 🌏 ChatNow - 极简实时聊天室

这是一个基于 Flask + Socket.IO + Gevent 的高并发实时聊天室项目。
集成了 DeepSeek AI 智能助手，支持 Markdown 渲染和代码高亮。

## ✨ 功能特性

- **实时通讯**：基于 WebSocket，消息毫秒级同步。
- **智能 AI**：内置 DeepSeek-V3/R1，支持群聊 (@AI) 和私聊。
- **极致体验**：Telegram 风格 UI，秒级时间戳，输入状态提示。
- **高性能**：Gevent 异步架构，解决 Python 阻塞问题。
- **数据持久化**：SQLite 存储历史消息。

## 🛠️ 技术栈

- **后端**：Python, Flask, Flask-SocketIO, Gevent
- **前端**：HTML5, CSS3, Socket.IO-Client, Marked.js, Highlight.js
- **数据库**：SQLite3

## 🚀 快速开始

### 1. 安装依赖
```bash
pip install -r requirements.txt
