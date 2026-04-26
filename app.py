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
from flask import Flask, request, render_template_string, redirect, send_file, jsonify
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
.header .btn-group{display:flex;gap:8px}
.header button{background:#e94560;color:#fff;border:none;padding:6px 14px;border-radius:4px;cursor:pointer;font-size:12px}
.header button:hover{background:#c73e54}
#term{height:calc(100vh - 40px)}
.login{display:flex;justify-content:center;align-items:center;height:100vh;background:linear-gradient(135deg,#1a1a2e,#16213e);font-family:sans-serif}
.lb{background:#16213e;padding:40px;border-radius:12px;border:1px solid #0f3460}
.lb h2{color:#e94560;margin-bottom:30px;text-align:center}
.lb input[type=text],.lb input[type=password]{width:100%;padding:12px;margin-bottom:16px;border:1px solid #0f3460;border-radius:6px;background:#1a1a2e;color:#eee;font-size:14px}
.lb input:focus{outline:none;border-color:#e94560}
.lb button{width:100%;padding:12px;background:#e94560;color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:16px}
.err{color:#ff6b6b;font-size:12px;margin-bottom:16px;text-align:center}
#download-modal{display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.5);z-index:1000}
#download-modal .modal-box{position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);background:#16213e;padding:20px;border-radius:8px;border:1px solid #0f3460}
#download-modal input{width:300px;padding:10px;border:1px solid #0f3460;border-radius:4px;background:#1a1a2e;color:#eee;font-size:14px;margin-bottom:10px}
#download-modal .modal-btns{display:flex;gap:10px}
#download-modal button{padding:8px 16px;border-radius:4px;cursor:pointer}
#download-modal .ok{background:#e94560;color:#fff;border:none}
#download-modal .cancel{background:#333;color:#fff;border:none}
#upload-modal{display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.5);z-index:1000}
#upload-modal .modal-box{position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);background:#16213e;padding:20px;border-radius:8px;border:1px solid #0f3460;text-align:center}
#upload-modal input{width:300px;padding:10px;border:1px solid #0f3460;border-radius:4px;background:#1a1a2e;color:#eee;font-size:14px;margin-bottom:10px}
#upload-modal .modal-btns{display:flex;gap:10px;justify-content:center}
#upload-modal button{padding:8px 16px;border-radius:4px;cursor:pointer}
#upload-modal .ok{background:#e94560;color:#fff;border:none}
#upload-modal .cancel{background:#333;color:#fff;border:none}
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
<div class="btn-group">
<input type="file" id="upload-input" hidden onchange="doUpload()">
<button onclick="showUploadModal()">上传</button>
<button onclick="showDownloadModal()">下载</button>
<button onclick="location.href='/logout?t={{ token }}'">退出</button>
</div>
</div>
<div id="upload-modal">
<div class="modal-box">
<input type="text" id="upload-path" placeholder="上传目标路径（如 /tmp/）">
<div class="modal-btns">
<button class="ok" onclick="selectFile()">选择文件</button>
<button class="cancel" onclick="hideUploadModal()">取消</button>
</div>
</div>
</div>
<div id="download-modal">
<div class="modal-box">
<input type="text" id="download-path" placeholder="输入文件路径（如 /tmp/file.txt）">
<div class="modal-btns">
<button class="ok" onclick="doDownload()">下载</button>
<button class="cancel" onclick="hideDownloadModal()">取消</button>
</div>
</div>
</div>
<div id="term"></div>
<script src="/socket.io.min.js"></script>
<script src="/xterm.min.js"></script>
<script>
var token="{{ token }}";
var cwd="{{ cwd }}";
var sk=io();
var term=new Terminal({cursorBlink:true,fontSize:14,fontFamily:'monospace',cols:100,rows:30});
term.open(document.getElementById('term'));
term.onData(function(d){sk.emit('in',d)});
sk.on('connect',function(){sk.emit('auth',token)});
sk.on('out',function(d){term.write(d)});
sk.on('err',function(m){term.write('\\r\\nError: '+m+'\\r\\n')});
sk.on('dis',function(){term.write('\\r\\nDisconnected\\r\\n')});
sk.on('cwd',function(d){cwd=d});
function showUploadModal(){document.getElementById('upload-modal').style.display='block';document.getElementById('upload-path').value=cwd+'/';document.getElementById('upload-path').focus()}
function hideUploadModal(){document.getElementById('upload-modal').style.display='none'}
function selectFile(){hideUploadModal();document.getElementById('upload-input').click()}
function showDownloadModal(){document.getElementById('download-modal').style.display='block';document.getElementById('download-path').value=cwd+'/';document.getElementById('download-path').focus()}
function hideDownloadModal(){document.getElementById('download-modal').style.display='none'}
function doUpload(){
var f=document.getElementById('upload-input').files[0];
if(!f)return;
var uploadPath=document.getElementById('upload-path').value||cwd+'/';
var fd=new FormData();
fd.append('file',f);
fd.append('token',token);
fd.append('cwd',uploadPath);
fetch('/upload',{method:'POST',body:fd}).then(r=>r.json()).then(d=>{
if(d.ok){term.write('\\r\\n\\x1b[32m上传成功: '+uploadPath+f.name+'\\x1b[0m\\r\\n')}
else{term.write('\\r\\n\\x1b[31m上传失败: '+d.err+'\\x1b[0m\\r\\n')}
}).catch(e=>{term.write('\\r\\n\\x1b[31m上传失败\\x1b[0m\\r\\n')});
document.getElementById('upload-input').value='';
}
function doDownload(){
var p=document.getElementById('download-path').value;
if(!p)return;
hideDownloadModal();
var a=document.createElement('a');
a.href='/download?token='+token+'&path='+encodeURIComponent(p);
a.download=p.split('/').pop();
a.click();
}
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
            tk = secrets.token_urlsafe(16)
            tokens[tk] = {'user': u, 'cwd': os.environ.get('HOME', '/tmp')}
            return render_template_string(HTML, token=tk, user=u, err='', cwd=tokens[tk]['cwd'])
        return render_template_string(HTML, token='', user='', err='Invalid', cwd='')
    return render_template_string(HTML, token='', user='', err='', cwd='')

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