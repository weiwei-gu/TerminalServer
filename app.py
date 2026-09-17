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
import json
import re
from flask import Flask, request, render_template, redirect, send_file, jsonify, make_response, Response
from flask_socketio import SocketIO, emit
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['SECRET_KEY'] = 'key'
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB 上传限制
socketio = SocketIO(app, cors_allowed_origins='*', async_mode='threading')

USERS = {'admin': 'admin123', 'user': 'password'}
tokens = {}
sessions = {}

# ===== ChatGraphic 会话导图集成 =====
# work 目录 = 含 sessions/ 与 current.json 的目录（与 chatgraphic/serve.js 同语义）。
# 解析链：--chatgraph-work 参数 > CHATGRAPHIC_WORK 环境变量（直接使用）
#        > CHATGRAPHIC_HOME 环境变量 → $CHATGRAPHIC_HOME/work（与 serve.js 一致）
#        > 本文件同级 ../chatgraphic/work（组合仓库布局）
#        > ~/.chatgraphic（扩展安装态）> None（功能禁用，前端隐藏开关）
_HERE = os.path.dirname(os.path.abspath(__file__))


def _resolve_chat_work(env=None):
    env = env or os.environ
    if env.get('CHATGRAPHIC_WORK'):
        return env['CHATGRAPHIC_WORK']
    if env.get('CHATGRAPHIC_HOME'):
        return os.path.join(env['CHATGRAPHIC_HOME'], 'work')
    p = os.path.join(_HERE, '..', 'chatgraphic', 'work')
    if os.path.isdir(p):
        return os.path.normpath(p)
    p = os.path.join(os.path.expanduser('~'), '.chatgraphic')
    if os.path.isdir(os.path.join(p, 'sessions')):
        return p
    return None


def _resolve_chat_viewer(env=None):
    env = env or os.environ
    if env.get('CHATGRAPHIC_VIEWER'):
        return env['CHATGRAPHIC_VIEWER']
    p = os.path.join(_HERE, '..', 'chatgraphic', 'viewer.html')
    if os.path.isfile(p):
        return os.path.normpath(p)
    return None


CHATGRAPHIC_WORK = _resolve_chat_work()
CHATGRAPHIC_VIEWER = _resolve_chat_viewer()

@app.route('/socket.io.min.js')
def socketio_js():
    return send_file('static/socket.io.min.js')

@app.route('/xterm.min.js')
def xterm_js():
    return send_file('static/xterm.min.js')

@app.route('/xterm.css')
def xterm_css():
    return send_file('static/xterm.css')

@app.route('/fit.min.js')
def fit_js():
    return send_file('static/fit.min.js')

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
            resp = make_response(render_template('index.html', token=tk, user=u, err='', cwd=tokens[tk]['cwd']))
            # 会话导图等只读路由凭此 cookie 鉴权（iframe 及其内部 fetch 自动携带）
            resp.set_cookie('wt', tk, httponly=True, samesite='Lax')
            return resp
        return render_template('index.html', token='', user='', err='Invalid', cwd='')
    return render_template('index.html', token='', user='', err='', cwd='')

@app.route('/logout')
def logout():
    tk = request.args.get('t', '')
    tokens.pop(tk, None)
    resp = redirect('/')
    resp.set_cookie('wt', '', expires=0)
    return resp

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

# ===== ChatGraphic 会话导图：只读数据路由（镜像 chatgraphic/serve.js，直接读磁盘，无需另跑 serve.js） =====
_SESSION_RE = re.compile(r'^[A-Za-z0-9_\-]+$')
_SESSION_FILES = {'graph.json': 'graph.json', 'transcript.json': 'transcript.json',
                  'version': 'version.txt', 'status': 'status.json'}
# viewer.html 缺失时的内建提示页（不中断终端功能）
_MISSING_VIEWER_PAGE = """<!DOCTYPE html><html><head><meta charset="utf-8"><title>会话导图</title>
<style>body{font-family:monospace;background:#000;color:#0f0;display:flex;align-items:center;justify-content:center;height:100vh;margin:0}
div{max-width:520px;padding:24px;border:2px solid #0f0;border-radius:8px;font-size:13px;line-height:1.8}</style></head>
<body><div><b>未找到 viewer.html</b><br>导图数据已就绪，但渲染页面缺失。<br>
请用 --chatgraph-viewer 参数或环境变量 CHATGRAPHIC_VIEWER 指向 ChatGraphic 的 viewer.html 路径后重启服务。</div></body></html>"""


def _cookie_ok():
    """导图路由鉴权：登录时种下的 wt cookie 必须有效"""
    tk = request.cookies.get('wt')
    return bool(tk and tk in tokens)


def _chat_json(data, code=200):
    resp = jsonify(data)
    resp.status_code = code
    resp.headers['Cache-Control'] = 'no-store'
    return resp


def _chat_file(path, fallback_body, err):
    """读 work 目录下的文件；缺失时按 serve.js 语义回退（version/status 有兜底值，graph/transcript 报 503）"""
    if os.path.isfile(path):
        resp = send_file(path)
        resp.headers['Cache-Control'] = 'no-store'
        return resp
    if fallback_body is not None:
        return Response(fallback_body, status=200, content_type='text/plain; charset=utf-8')
    return _chat_json({'error': err}, 503)


def _list_sessions():
    out = []
    root = os.path.join(CHATGRAPHIC_WORK, 'sessions')
    try:
        for d in os.listdir(root):
            try:
                with open(os.path.join(root, d, 'graph.json'), encoding='utf-8') as f:
                    g = json.load(f)
                out.append({'sessionId': d, 'goal': g.get('goal'), 'version': g.get('version'),
                            'roundCount': g.get('roundCount'), 'generatedAt': g.get('generatedAt')})
            except Exception:
                pass  # 无 graph.json 的目录跳过
    except Exception:
        pass  # sessions 目录不存在
    out.sort(key=lambda s: str(s.get('generatedAt') or ''), reverse=True)
    return out


@app.route('/chatgraph/config')
def chat_config():
    if not _cookie_ok():
        return _chat_json({'error': '未授权'}, 401)
    return _chat_json({'enabled': bool(CHATGRAPHIC_WORK), 'viewer': bool(CHATGRAPHIC_VIEWER)})


@app.route('/viewer')
def chat_viewer():
    if not _cookie_ok():
        return _chat_json({'error': '未授权'}, 401)
    if not CHATGRAPHIC_VIEWER or not os.path.isfile(CHATGRAPHIC_VIEWER):
        return Response(_MISSING_VIEWER_PAGE, status=200, content_type='text/html; charset=utf-8')
    resp = send_file(CHATGRAPHIC_VIEWER)
    resp.headers['Cache-Control'] = 'no-store'
    return resp


@app.route('/sessions')
def chat_sessions():
    if not _cookie_ok():
        return _chat_json({'error': '未授权'}, 401)
    return _chat_json(_list_sessions())


@app.route('/current')
def chat_current():
    if not _cookie_ok():
        return _chat_json({'error': '未授权'}, 401)
    sid = None
    try:
        with open(os.path.join(CHATGRAPHIC_WORK, 'current.json'), encoding='utf-8') as f:
            sid = json.load(f).get('sessionId')
    except Exception:
        sid = None
    return _chat_json({'sessionId': sid})


@app.route('/session/<sid>/<name>')
def chat_session_file(sid, name):
    if not _cookie_ok():
        return _chat_json({'error': '未授权'}, 401)
    if not CHATGRAPHIC_WORK or not _SESSION_RE.match(sid) or name not in _SESSION_FILES:
        return _chat_json({'error': '会话不存在'}, 404)
    path = os.path.join(CHATGRAPHIC_WORK, 'sessions', sid, _SESSION_FILES[name])
    # version/status 缺失给兜底值（与 serve.js 一致），graph/transcript 缺失 503
    fallback = '0' if name == 'version' else '{}' if name == 'status' else None
    return _chat_file(path, fallback, '尚未生成（先聊一轮或手动补跑）')

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
    parser.add_argument('--chatgraph-work', default=None,
                        help='ChatGraphic 数据目录（含 sessions/ 与 current.json），未指定按环境变量/默认链解析')
    parser.add_argument('--chatgraph-viewer', default=None,
                        help='ChatGraphic viewer.html 路径，未指定按环境变量/同级 chatgraphic/ 解析')
    args = parser.parse_args()

    # 显式参数优先于模块导入时的自动解析
    if args.chatgraph_work:
        CHATGRAPHIC_WORK = args.chatgraph_work
    if args.chatgraph_viewer:
        CHATGRAPHIC_VIEWER = args.chatgraph_viewer

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
    print('Chat 导图: ' + (CHATGRAPHIC_WORK or '未检测到数据（--chatgraph-work 可指定）'))
    print('Users: admin / admin123')
    print('='*50)
    socketio.run(app, host='0.0.0.0', port=args.port, allow_unsafe_werkzeug=True)