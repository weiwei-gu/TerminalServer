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
import secrets
import argparse
from flask import Flask, request, render_template, redirect, send_file, jsonify
from flask_socketio import SocketIO, emit
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['SECRET_KEY'] = 'key'
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB 上传限制
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
            tk = secrets.token_urlsafe(16)
            tokens[tk] = {'user': u, 'cwd': os.environ.get('HOME', '/tmp')}
            return render_template('index.html', token=tk, user=u, err='', cwd=tokens[tk]['cwd'])
        return render_template('index.html', token='', user='', err='Invalid', cwd='')
    return render_template('index.html', token='', user='', err='', cwd='')

@app.route('/logout')
def logout():
    tokens.pop(request.args.get('t', ''), None)
    return redirect('/')

@app.route('/upload', methods=['POST'])
def upload():
    token = request.form.get('token')
    if not token or token not in tokens:
        return jsonify({'ok': False, 'err': '未授权'})

    file = request.files.get('file')
    if not file:
        return jsonify({'ok': False, 'err': '无文件'})

    cwd = request.form.get('cwd', '')
    filename = secure_filename(file.filename)
    if not filename:
        return jsonify({'ok': False, 'err': '文件名无效'})

    # 如果 cwd 以 / 结尾，视为目录，拼接文件名
    # 否则视为完整路径，直接使用
    if cwd.endswith('/'):
        save_path = os.path.join(cwd, filename)
    else:
        save_path = cwd

    try:
        # 确保目录存在
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        file.save(save_path)
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'err': str(e)})

@app.route('/download')
def download():
    token = request.args.get('token')
    if not token or token not in tokens:
        return '未授权', 403

    path = request.args.get('path', '')
    if not path:
        return '缺少路径参数', 400

    # 安全检查：禁止路径穿越
    if '..' in path:
        return '非法路径', 403

    # 规范化路径
    path = os.path.normpath(path)

    # 检查文件是否存在
    if not os.path.isfile(path):
        return '文件不存在', 404

    try:
        return send_file(path)
    except Exception as e:
        return f'下载失败: {e}', 500

@socketio.on('auth')
def on_auth(tk):
    sid = request.sid
    if not tk or tk not in tokens:
        emit('err', 'Invalid token')
        return

    user = tokens[tk]['user']
    cwd = tokens[tk]['cwd']
    print(f"[{sid}] Authenticated: {user}")

    master, slave = pty.openpty()
    shell = os.environ.get('SHELL', '/bin/zsh')
    proc = subprocess.Popen([shell], preexec_fn=os.setsid,
        stdin=slave, stdout=slave, stderr=slave,
        cwd=cwd,
        env={**os.environ, 'TERM': 'xterm-256color', 'LANG': 'en_US.UTF-8'})
    os.close(slave)
    set_size(master, 40, 100)
    sessions[sid] = {'fd': master, 'proc': proc, 'token': tk, 'cwd': cwd}

    threading.Thread(target=read_fd, args=(master, sid), daemon=True).start()
    emit('ready')
    emit('cwd', cwd)

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
    parser = argparse.ArgumentParser(
        description='Web Terminal Server - 网页终端服务',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
示例:
  %(prog)s                  默认端口 5001 运行
  %(prog)s --port 8080      指定端口 8080 运行

默认账号: admin / admin123, user / password
'''
    )
    parser.add_argument('--port', type=int, default=5001, help='服务端口 (默认: 5001)')
    args = parser.parse_args()

    import socket as s
    ip = '127.0.0.1'
    try:
        for ifs in s.gethostbyname_ex(s.gethostname())[2]:
            if not ifs.startswith('127.'): ip = ifs; break
    except: pass
    print('='*50)
    print('Web Terminal')
    print('='*50)
    print(f'Local:   http://localhost:{args.port}')
    print(f'Network: http://{ip}:{args.port}')
    print('='*50)
    print('Users: admin / admin123')
    print('='*50)
    socketio.run(app, host='0.0.0.0', port=args.port, allow_unsafe_werkzeug=True)