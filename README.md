# Web Terminal Server

网页终端服务 - 在浏览器中访问真实终端。

## 功能

- 浏览器远程终端访问
- 支持交互式程序（vim、top 等）
- 用户登录认证
- 多用户会话管理
- 文件上传下载

## 原理

```
┌─────────────┐     WebSocket      ┌─────────────┐     PTY      ┌─────────────┐
│   浏览器    │  ←──────────────→  │  Flask服务器 │ ←──────────→ │  Shell进程  │
│  (前端UI)   │                    │ (app.py)    │             │  (zsh/bash) │
└─────────────┘                    └─────────────┘             └─────────────┘
```

**核心流程：**

1. **登录认证**：用户提交账号密码，服务器生成 token 并返回终端页面

2. **WebSocket 连接**：前端通过 Socket.IO 与服务器建立实时双向通信

3. **PTY 创建**：服务器使用 Python `pty` 模块创建伪终端，启动 shell 进程

4. **数据流转**：
   - 用户键盘输入 → WebSocket → 服务器写入 PTY → Shell 接收
   - Shell 输出 → PTY → 服务器读取 → WebSocket → 浏览器显示

**关键技术点：**

- **PTY (伪终端)**：通过 `pty.openpty()` 创建主/从设备，shell 连接到从端，服务器读写主端
- **非阻塞读取**：使用 `select` 监听 PTY 输出，避免阻塞主线程
- **终端窗口大小**：通过 `fcntl.ioctl` 设置 `TIOCSWINSZ` 控制终端行列数

## 安装

```bash
# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

## 打包二进制

```bash
source venv/bin/activate
pyinstaller web-terminal.spec --clean && rm -rf build/
```

生成 `dist/web-terminal`（约11MB），可直接运行无需 Python 环境。

## 使用

```bash
# 源码运行
source venv/bin/activate
python app.py

# 或使用二进制直接运行
./dist/web-terminal

# 指定端口
./dist/web-terminal --port 8080

# 查看帮助
./dist/web-terminal --help
```

启动后访问：

- 本地：`http://localhost:<端口>`
- 网络：`http://<本机IP>:<端口>`

默认账号：

| 用户名 | 密码 |
|-------|------|
| admin | admin123 |
| user | password |

## 文件上传下载

### 上传

点击"上传"按钮 → 输入目标路径 → 选择文件上传

路径规则：
- 以 `/` 结尾：视为目录，文件保存到该目录（保留原名）
- 不以 `/` 结尾：视为完整路径，文件保存到指定路径

示例：
- `/tmp/` → 文件保存为 `/tmp/原文件名`
- `/tmp/test.txt` → 文件保存为 `/tmp/test.txt`

### 下载

点击"下载"按钮 → 输入文件路径 → 下载文件

示例：`/tmp/test.txt`

### 安全限制

- 上传文件大小限制：100MB
- 禁止路径穿越（不允许 `..`）
- 需要登录认证才能上传下载

## 目录结构

```
TerminalServer/
├── app.py              # Flask 主程序
├── templates/
│   └── index.html      # HTML 模板
├── tests/
│   └── test_app.py     # 测试代码
├── requirements.txt    # Python 依赖
├── README.md           # 项目说明
├── CLAUDE.md           # Claude Code 指导文件
└── venv/               # Python 虚拟环境
```

## 测试

```bash
source venv/bin/activate
pytest tests/ -v
```

## 代码结构

`app.py` 主要组件：

- `USERS` - 用户账号字典
- `tokens` - 登录 token 存储
- `sessions` - 会话 PTY 进程管理
- `/` 路由 - 登录页面和终端页面
- `/upload` 路由 - 文件上传
- `/download` 路由 - 文件下载
- `socketio.on('auth')` - 验证 token，创建 PTY 进程
- `socketio.on('in')` - 接收用户输入，写入 PTY
- `read_fd()` - 后台线程读取 PTY 输出，推送到前端