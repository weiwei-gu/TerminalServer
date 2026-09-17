# Web Terminal Server

Web-based terminal service - Access a real terminal from your browser.

## Features

- Remote terminal access via browser
- Support for interactive programs (vim, top, etc.)
- User authentication
- Multi-user session management
- File upload and download
- Chat map (ChatGraphic integration): expand a live AI session map from the terminal page with one toggle

## Architecture

```
┌─────────────┐     WebSocket      ┌─────────────┐     PTY      ┌─────────────┐
│   Browser   │  ←──────────────→  │Flask Server │ ←──────────→ │Shell Process│
│  (Frontend) │                    │ (app.py)    │             │  (zsh/bash) │
└─────────────┘                    └─────────────┘             └─────────────┘
```

**Core Workflow:**

1. **Login Authentication**: User submits credentials, server generates a token and returns the terminal page

2. **WebSocket Connection**: Frontend establishes real-time bidirectional communication with server via Socket.IO

3. **PTY Creation**: Server uses Python `pty` module to create a pseudo-terminal and spawn a shell process

4. **Data Flow**:
   - User keyboard input → WebSocket → Server writes to PTY → Shell receives
   - Shell output → PTY → Server reads → WebSocket → Browser displays

**Key Technical Points:**

- **PTY (Pseudo-Terminal)**: Create master/slave devices via `pty.openpty()`, shell connects to slave, server reads/writes master
- **Non-blocking Read**: Use `select` to monitor PTY output, avoiding blocking the main thread
- **Terminal Window Size**: Control terminal rows/columns via `fcntl.ioctl` with `TIOCSWINSZ`

## Installation

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

## Build Binary

```bash
source venv/bin/activate
pyinstaller web-terminal.spec --clean && rm -rf build/
```

Generates `dist/web-terminal` (~11MB), runs without Python environment.

## Usage

```bash
# Run from source
source venv/bin/activate
python app.py

# Or run binary directly
./dist/web-terminal

# Specify port
./dist/web-terminal --port 8080

# Show help
./dist/web-terminal --help
```

After starting, access at:

- Local: `http://localhost:<port>`
- Network: `http://<your-ip>:<port>`

Default accounts:

| Username | Password |
|----------|----------|
| admin | admin123 |
| user | password |

## File Upload and Download

### Upload

Click "Upload" button → Enter destination path → Select file to upload

Path rules:
- Ends with `/`: treated as directory, file saved to directory (original name preserved)
- Does not end with `/`: treated as full path, file saved to specified path

Examples:
- `/tmp/` → file saved as `/tmp/original_filename`
- `/tmp/test.txt` → file saved as `/tmp/test.txt`

### Download

Click "Download" button → Enter file path → Download file

Example: `/tmp/test.txt`

### Security Restrictions

- Upload file size limit: 100MB
- Path traversal forbidden (`..` not allowed)
- Login required for upload/download

## Chat Map (ChatGraphic Integration)

Use together with [ChatGraphic](https://github.com/weiwei-gu/ChatGraphic): a "Chat Map" toggle appears in the terminal toolbar. Click it to expand a graph panel on the right (live refresh every 2s, session switching, PNG/Markdown export) while the terminal auto-shrinks; click again to restore full width. Chat with Codely / Codex CLI / Claude Code inside the web terminal (with ChatGraphic hooks registered) and the map updates automatically after each turn — **no need to run `serve.js` separately**, this service reads the data directory on disk directly.

### Data Directory Resolution

| Priority | Source |
|---|---|
| 1 | `--chatgraph-work` argument (directory containing `sessions/` and `current.json`) |
| 2 | `CHATGRAPHIC_WORK` environment variable |
| 3 | `CHATGRAPHIC_HOME` environment variable → `$CHATGRAPHIC_HOME/work` (same as chatgraphic/serve.js) |
| 4 | `../chatgraphic/work` relative to app.py (combined ChatGraphic repo layout; the default when cloned together) |
| 5 | `~/.chatgraphic` (Codely extension install state) |
| None found | Feature auto-disabled, toggle hidden |

viewer.html render page path: `--chatgraph-viewer` argument / `CHATGRAPHIC_VIEWER` environment variable > sibling `../chatgraphic/viewer.html`; when missing the panel shows a built-in hint page.

### Examples

```bash
# Combined repo (TerminalServer sits next to chatgraphic/): auto-discovered, just run
python app.py

# Standalone deployment / binary: specify explicitly
python app.py --chatgraph-work ~/myproject/chatgraphic/work \
              --chatgraph-viewer ~/myproject/chatgraphic/viewer.html
```

### Notes and Limitations

- Chat map routes are authenticated via the login cookie (HttpOnly), same lifetime as the terminal login
- The data directory is a single directory resolved at startup: switch via arguments for multiple projects; cross-project aggregation is not supported yet
- The UI now follows ChatGraphic viewer's light design language (top bar / buttons / modals / light terminal theme); the map panel width is adjustable by dragging the splitter and remembered per browser
- The panel embeds the viewer in `?embed=1` mode: sidebars (sessions / node details) become on-demand drawers over a full-width canvas — clicking a node opens its details, clicking empty canvas dismisses them, so nothing is lost in a narrow panel

## Workspace Bootstrap (--workspace)

Pass `--workspace <dir>` at startup to auto-configure the Codely environment for that project directory; the terminal opens directly in it after login:

```bash
python app.py --workspace ~/code/myproject
```

Executed automatically (idempotent, safe to re-run):

1. Check that `codely` / `node` are available
2. If the extension is not installed yet, run `codely extensions install https://github.com/weiwei-gu/ChatGraphic --scope workspace --consent` (installs into `<dir>/.codely-cli/extensions/`; `--consent` auto-acknowledges the third-party extension prompt — without it, a non-interactive environment silently skips the install)
3. Run the extension's `install.js` to register the project-level AfterAgent hook

One **manual step** remains: start Codely in that project and run `/hooks trust-project` once (Codely's project-trust security mechanism — deliberately not automated). After that, chat with Codely inside the web terminal and the map panel grows live.

The map data directory is resolved per workspace: `<workspace>/chatgraphic/work` (clone layout) if present, otherwise the extension install state `~/.chatgraphic`; explicit `--chatgraph-work` / `CHATGRAPHIC_WORK` / `CHATGRAPHIC_HOME` always take precedence.

Notes:

- Bootstrap failure does not block the terminal; the server still starts and the reason is printed in the startup banner
- Codex / Claude Code hook registration is user-level global (each writes its own config file) and unrelated to the project directory — still done manually via their install scripts

## Directory Structure

```
TerminalServer/
├── app.py              # Flask main program
├── templates/
│   └── index.html      # HTML template
├── tests/
│   └── test_app.py     # Test code
├── requirements.txt    # Python dependencies
├── README.md           # Project documentation (Chinese)
├── README_EN.md        # Project documentation (English)
├── CLAUDE.md           # Claude Code guide file
└── venv/               # Python virtual environment
```

## Testing

```bash
source venv/bin/activate
pytest tests/ -v
```

## Code Structure

Main components in `app.py`:

- `USERS` - User account dictionary
- `tokens` - Login token storage
- `sessions` - Session PTY process management
- `/` route - Login page and terminal page
- `/upload` route - File upload
- `/download` route - File download
- `/chatgraph/config`, `/viewer`, `/sessions`, `/current`, `/session/<sid>/...` routes - ChatGraphic read-only map data (cookie-authenticated)
- `socketio.on('auth')` - Validate token, create PTY process
- `socketio.on('in')` - Receive user input, write to PTY
- `read_fd()` - Background thread reading PTY output, pushing to frontend