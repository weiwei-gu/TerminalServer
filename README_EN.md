# Web Terminal Server

Web-based terminal service - Access a real terminal from your browser.

## Features

- Remote terminal access via browser
- Support for interactive programs (vim, top, etc.)
- User authentication
- Multi-user session management
- File upload and download

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
- `socketio.on('auth')` - Validate token, create PTY process
- `socketio.on('in')` - Receive user input, write to PTY
- `read_fd()` - Background thread reading PTY output, pushing to frontend