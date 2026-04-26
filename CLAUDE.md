# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Web Terminal Server - 网页终端服务，提供浏览器端的终端访问。

主实现：**Python Flask** (`app.py`)

## 运行服务

```bash
source venv/bin/activate
python app.py
```

服务端口：**5001**，访问 `http://localhost:5001`

默认账号：`admin / admin123` 或 `user / password`

## 依赖

Python venv 环境：
- Flask
- Flask-SocketIO
- requests

激活环境后直接运行即可。

## 架构

```
浏览器 <--WebSocket--> Flask-SocketIO <--PTY--> Shell进程
```

- 认证：简单 token 机制
- 通信：Socket.IO 双向传输终端 I/O
- PTY：使用 Python pty 模块创建伪终端