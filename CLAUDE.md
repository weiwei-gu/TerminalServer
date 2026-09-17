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
- 会话导图：Flask 直接读磁盘上的 ChatGraphic work 目录（默认 `../chatgraphic/work`，`--chatgraph-work` / `CHATGRAPHIC_WORK` / `CHATGRAPHIC_HOME` 可覆盖），`/viewer` + `/sessions` 等只读路由凭登录 cookie 鉴权；终端页「会话导图」开关经 iframe 展开面板，FitAddon 随面板开合同步终端尺寸
- 工作目录初始化：`--workspace <dir>` 启动时自动 `codely extensions install --scope workspace` + 扩展内 `install.js` 注册项目级 Hook（幂等），终端落在该目录；项目信任 `/hooks trust-project` 需人工执行一次，不自动代做