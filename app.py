#!/usr/bin/env python3
"""Web Terminal - 使用 xterm.js 渲染 ANSI"""

import os
import pty
import fcntl
import struct
import termios
import select
import subprocess
import threading
from flask import Flask, request, render_template_string, redirect, send_file
from flask_socketio import SocketIO, emit

app = Flask(__name__)
app.config['SECRET_KEY'] = 'key'
socketio = SocketIO(app, cors_allowed_origins='*', async_mode='threading')

USERS = {'admin': 'admin123', 'user': 'password'}
tokens = {}
sessions = {}

@app.route('/socket.io.min.js')
def socketio_js():
    return send_file('venv/socket.io.min.js')

@app.route('/xterm.min.js')
def xterm_js():
    return send_file('venv/xterm.min.js')

@app.route('/xterm.css')
def xterm_css():
    return send_file('venv/xterm.css')

@app.route('/fit.min.js')
def fit_js():
    return send_file('venv/fit.min.js')

HTML = '''
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>Web Terminal</title>
<link rel="stylesheet" href="/xterm.css">
<style>
*{margin:0;padding:0;box-sizing:border-box}
html,body{height:100%;background:#000}
.header{background:#16213e;padding:8px 20px;display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid #0f3460;font-family:sans-serif}
.header h1{font-size:14px;color:#e94560}
.header button{background:#e94560;color:#fff;border:none;padding:6px 14px;border-radius:4px;cursor:pointer}
#term{height:calc(100vh - 40px)}
.login{display:flex;justify-content:center;align-items:center;height:100vh;background:linear-gradient(135deg,#1a1a2e,#16213e);font-family:sans-serif}
.lb{background:#16213e;padding:40px;border-radius:12px;border:1px solid #0f3460}
.lb h2{color:#e94560;margin-bottom:30px;text-align:center}
.lb input{width:100%;padding:12px;margin-bottom:16px;border:1px solid #0f3460;border-radius:6px;background:#1a1a2e;color:#eee;font-size:14px}
.lb input:focus{outline:none;border-color:#e94560}
.lb button{width:100%;padding:12px;background:#e94560;color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:16px}
.err{color:#ff6b6b;font-size:12px;margin-bottom:16px;text-align:center}
</style>
</head>
<body>
{% if not token %}
<div class="login">
<div class="lb">
<h2>Web Terminal</h2>
{% if err %}<p class="err">{{ err }}</p>{% endif %}
<form method="post">
<input type="text" name="u" placeholder="Username" required autofocus>
<input type="password" name="p" placeholder="Password" required>
<button>Login</button>
</form>
</div>
</div>
{% else %}
<div class="header">
<h1>Terminal - {{ user }}</h1>
<button onclick="location.href='/logout?t={{ token }}'">Logout</button>
</div>
<div id="term"></div>
<script src="/socket.io.min.js"></script>
<script src="/xterm.min.js"></script>
<script>
var token="{{ token }}";
var sk=io();
var term=new Terminal({cursorBlink:true,fontSize:14,fontFamily:'monospace',cols:100,rows:30});
term.open(document.getElementById('term'));
term.onData(function(d){sk.emit('in',d)});
sk.on('connect',function(){sk.emit('auth',token)});
sk.on('out',function(d){term.write(d)});
sk.on('err',function(m){term.write('\\r\\nError: '+m+'\\r\\n')});
sk.on('dis',function(){term.write('\\r\\nDisconnected\\r\\n')});
</script>
{% endif %}
</body>
</html>
'''

def set_size(fd, r, c):
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", r, c, 0, 0))

def read_fd(fd, sid):
    while True:
        try:
            r, _, _ = select.select([fd], [], [], 0.1)
            if r:
                d = os.read(fd, 65536)
                if d:
                    socketio.emit('out', d.decode('utf-8', errors='replace'), to=sid)
        except:
            break

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        u, p = request.form.get('u'), request.form.get('p')
        if USERS.get(u) == p:
            import secrets
            tk = secrets.token_urlsafe(16)
            tokens[tk] = u
            return render_template_string(HTML, token=tk, user=u, err='')
        return render_template_string(HTML, token='', user='', err='Invalid')
    return render_template_string(HTML, token='', user='', err='')

@app.route('/logout')
def logout():
    tokens.pop(request.args.get('t', ''), None)
    return redirect('/')

@socketio.on('auth')
def on_auth(tk):
    sid = request.sid
    print(f"[DEBUG] auth: {tk}, tokens: {list(tokens.keys())}")
    if not tk or tk not in tokens:
        print(f"[DEBUG] rejected")
        emit('err', 'Invalid token')
        return

    print(f"[{sid}] Authenticated: {tokens[tk]}")

    master, slave = pty.openpty()
    shell = os.environ.get('SHELL', '/bin/zsh')
    proc = subprocess.Popen([shell], preexec_fn=os.setsid,
        stdin=slave, stdout=slave, stderr=slave,
        env={**os.environ, 'TERM': 'xterm-256color', 'LANG': 'en_US.UTF-8'})
    os.close(slave)
    set_size(master, 40, 100)
    sessions[sid] = {'fd': master, 'proc': proc, 'token': tk}

    threading.Thread(target=read_fd, args=(master, sid), daemon=True).start()
    emit('ready')

@socketio.on('disconnect')
def on_disconnect():
    sid = request.sid
    print(f"[{sid}] Disconnect")
    if sid in sessions:
        s = sessions.pop(sid)
        try: s['proc'].kill(); os.close(s['fd'])
        except: pass

@socketio.on('in')
def on_input(data):
    sid = request.sid
    if sid in sessions:
        try:
            os.write(sessions[sid]['fd'], data.encode('utf-8'))
        except Exception as e:
            print(f"Write error: {e}")

@socketio.on('resize')
def on_resize(d):
    sid = request.sid
    if sid in sessions:
        try:
            set_size(sessions[sid]['fd'], d.get('rows', 40), d.get('cols', 100))
        except: pass

if __name__ == '__main__':
    import socket as s
    ip = '127.0.0.1'
    try:
        for ifs in s.gethostbyname_ex(s.gethostname())[2]:
            if not ifs.startswith('127.'): ip = ifs; break
    except: pass
    print('='*50)
    print('Web Terminal')
    print('='*50)
    print(f'Local:   http://localhost:5001')
    print(f'Network: http://{ip}:5001')
    print('='*50)
    print('Users: admin / admin123')
    print('='*50)
    socketio.run(app, host='0.0.0.0', port=5001, allow_unsafe_werkzeug=True)