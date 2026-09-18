# Web Terminal Server

网页终端服务 - 在浏览器中访问真实终端。

## 功能

- 浏览器远程终端访问
- 支持交互式程序（vim、top 等）
- 用户登录认证
- 多用户会话管理
- 文件上传下载
- ChatDeck 工作台（ChatGraphic 集成）：登录后进入 AI 协作台仪表盘，终端与会话导图为可拖动、可缩放的独立浮动窗口，导图随对话实时生长

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

## 会话导图（ChatGraphic 集成）

与 [ChatGraphic](https://github.com/weiwei-gu/ChatGraphic) 组合使用：登录后进入 **ChatDeck** 工作台（AI 协作台，背景页——会话列表、导图就绪状态、终端与导图的唤出卡），终端与会话导图为**独立浮动窗口**：标题栏拖动、右下角拖角缩放、点击置顶、可关闭后从底部 dock 唤回，窗口几何按浏览器记忆。导图窗内嵌 viewer 的 embed 模式（会话抽屉默认展开、点节点弹详情）；点工作台会话卡可**固定查看指定会话**（`?session=` 直达）。在终端窗里用 Codely / Codex CLI / Claude Code 聊天（需已注册 ChatGraphic Hook），每轮结束后导图自动更新——**无需另跑 `serve.js`**，本服务直接读取磁盘上的数据目录。

### 数据目录解析

| 优先级 | 来源 |
|---|---|
| 1 | `--chatgraph-work` 参数（含 `sessions/` 与 `current.json` 的目录） |
| 2 | 环境变量 `CHATGRAPHIC_WORK` |
| 3 | 环境变量 `CHATGRAPHIC_HOME` → `$CHATGRAPHIC_HOME/work`（与 chatgraphic/serve.js 一致） |
| 4 | 本文件同级 `../chatgraphic/work`（ChatGraphic 组合仓库布局，组合克隆时默认即用） |
| 5 | `~/.chatgraphic`（Codely 扩展安装态） |
| 都没有 | 功能自动禁用，开关隐藏 |

viewer.html 渲染页路径：`--chatgraph-viewer` 参数 / 环境变量 `CHATGRAPHIC_VIEWER` > 同级 `../chatgraphic/viewer.html`；均缺失时面板显示内建提示页。

### 示例

```bash
# 组合仓库（TerminalServer 与 chatgraphic/ 同级）直接运行即自动发现
python app.py

# 独立部署 / 二进制运行时显式指定
python app.py --chatgraph-work ~/myproject/chatgraphic/work \
              --chatgraph-viewer ~/myproject/chatgraphic/viewer.html
```

### 说明与限制

- 导图数据路由凭登录 cookie（HttpOnly）鉴权，与终端登录同生命周期
- 数据目录为启动时解析的单一目录：多项目需换参数启动，跨项目聚合暂不支持
- 界面已整体对齐 ChatGraphic viewer 的浅色设计语言（顶栏 / 按钮 / 弹窗 / 浅色终端主题）；终端与导图为独立浮动窗口，可拖动、拖角缩放、点击置顶，几何按浏览器记忆
- 导图窗内嵌 viewer 的 `?embed=1` 模式：侧栏（会话列表 / 节点详情）抽屉化、画布全宽，会话抽屉默认展开，点节点自动弹出详情，点画布空白只收起详情（会话保持）——窗口再窄也不丢功能

## 工作目录初始化（--workspace）

运行时用 `--workspace` 指定一个项目目录，服务启动时自动完成该目录的 Codely 环境配置，登录后终端直接落在该目录：

```bash
python app.py --workspace ~/code/myproject
```

自动执行（幂等，重复启动安全）：

1. 检查 `codely` / `node` 命令可用
2. 该目录未装扩展时执行 `codely extensions install https://github.com/weiwei-gu/ChatGraphic --scope workspace --consent`（装入 `<目录>/.codely-cli/extensions/`；`--consent` 为自动化自动确认第三方扩展安装提示——无交互环境下不带此参数会被静默跳过、实际不安装）
3. 执行扩展内 `install.js` 注册项目级 AfterAgent Hook

初始化后只剩**一步人工确认**：在该项目里启动 Codely，执行一次 `/hooks trust-project`（Codely 的项目信任安全机制，不可也不应由脚本代做）。之后在网页终端里用 Codely 正常聊天，会话导图面板即实时生长。

导图数据目录随 workspace 自动判定：项目内有 `chatgraphic/work`（clone 布局）则读它，否则读项目级扩展数据目录 `<workspace>/.chatgraphic`（ChatGraphic 规则：workspace 作用域扩展的数据随项目走）；显式 `--chatgraph-work` 参数或 `CHATGRAPHIC_WORK` / `CHATGRAPHIC_HOME` 环境变量始终优先。

说明：

- 初始化失败不影响终端功能，服务照常启动，原因见启动横幅
- workspace 的导图数据写在 `<workspace>/.chatgraphic/`，建议在项目 `.gitignore` 加一行 `.chatgraphic/`；旧版项目级扩展的历史会话仍在 `~/.chatgraphic`（不自动迁移），需要时手动 `mv`
- Codex / Claude Code 的 Hook 注册为用户级全局注册（各写各的配置文件），与项目目录无关，仍按其安装脚本手动执行

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
- `/chatgraph/config` `/viewer` `/sessions` `/current` `/session/<sid>/...` 路由 - ChatGraphic 会话导图只读数据（凭 cookie 鉴权）
- `socketio.on('auth')` - 验证 token，创建 PTY 进程
- `socketio.on('in')` - 接收用户输入，写入 PTY
- `read_fd()` - 后台线程读取 PTY 输出，推送到前端