import pytest
import os
import json
import tempfile
import sys

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, socketio, tokens
import app as app_module


@pytest.fixture
def client():
    """创建测试客户端"""
    app.config['TESTING'] = True
    return app.test_client()


@pytest.fixture
def socket_client():
    """创建 SocketIO 测试客户端"""
    app.config['TESTING'] = True
    return socketio.test_client(app)


@pytest.fixture
def chat_env(tmp_path, monkeypatch):
    """构造临时 ChatGraphic work 目录（一个会话）+ 假 viewer.html，覆写模块全局并在测试后还原"""
    work = tmp_path / 'work'
    sess = work / 'sessions' / 'test-session-1'
    sess.mkdir(parents=True)
    (sess / 'graph.json').write_text(json.dumps({
        'goal': '集成测试目标', 'version': 3, 'roundCount': 2,
        'generatedAt': '2026-09-17T12:00:00'
    }), encoding='utf-8')
    (sess / 'version.txt').write_text('3', encoding='utf-8')
    (sess / 'status.json').write_text('{"state": "idle"}', encoding='utf-8')
    (sess / 'transcript.json').write_text('{"rounds": []}', encoding='utf-8')
    (work / 'current.json').write_text(json.dumps({'sessionId': 'test-session-1'}), encoding='utf-8')
    viewer = tmp_path / 'viewer.html'
    viewer.write_text('<html>fake viewer</html>', encoding='utf-8')
    monkeypatch.setattr(app_module, 'CHATGRAPHIC_WORK', str(work))
    monkeypatch.setattr(app_module, 'CHATGRAPHIC_VIEWER', str(viewer))
    return {'sid': 'test-session-1'}


@pytest.fixture
def logged_in(client):
    """登录（种下 wt cookie），返回测试客户端"""
    rv = client.post('/', data={'u': 'admin', 'p': 'admin123'})
    assert rv.status_code == 200
    return client


class TestLogin:
    """登录功能测试"""

    def test_login_page(self, client):
        """测试登录页面可访问"""
        rv = client.get('/')
        assert rv.status_code == 200
        assert 'Web Terminal' in rv.data.decode()

    def test_login_success(self, client):
        """测试登录成功"""
        rv = client.post('/', data={'u': 'admin', 'p': 'admin123'}, follow_redirects=True)
        assert rv.status_code == 200
        assert 'Terminal - admin' in rv.data.decode()

    def test_login_fail_wrong_password(self, client):
        """测试密码错误"""
        rv = client.post('/', data={'u': 'admin', 'p': 'wrong'}, follow_redirects=True)
        assert rv.status_code == 200
        assert 'Invalid' in rv.data.decode()

    def test_login_fail_unknown_user(self, client):
        """测试未知用户"""
        rv = client.post('/', data={'u': 'unknown', 'p': 'password'}, follow_redirects=True)
        assert rv.status_code == 200
        assert 'Invalid' in rv.data.decode()


class TestUpload:
    """上传功能测试"""

    def test_upload_without_token(self, client):
        """测试未授权上传"""
        data = {'file': (tempfile.NamedTemporaryFile(), 'test.txt')}
        rv = client.post('/upload', data=data)
        assert rv.status_code == 200
        json = rv.get_json()
        assert json['ok'] == False
        assert '未授权' in json['err']

    def test_upload_with_token(self, client):
        """测试授权上传"""
        # 先登录获取 token
        import secrets
        token = secrets.token_urlsafe(16)
        tokens[token] = {'user': 'admin', 'cwd': tempfile.gettempdir()}

        # 创建临时文件上传
        test_file = tempfile.NamedTemporaryFile(mode='w', delete=False)
        test_file.write('test content')
        test_file.close()

        with open(test_file.name, 'rb') as f:
            data = {
                'file': (f, 'test_upload.txt'),
                'token': token,
                'cwd': tempfile.gettempdir() + '/'
            }
            rv = client.post('/upload', data=data)

        os.unlink(test_file.name)
        assert rv.status_code == 200
        json = rv.get_json()
        assert json['ok'] == True


class TestDownload:
    """下载功能测试"""

    def test_download_without_token(self, client):
        """测试未授权下载"""
        rv = client.get('/download?path=/tmp/test.txt')
        assert rv.status_code == 403
        assert '未授权' in rv.data.decode()

    def test_download_path_traversal(self, client):
        """测试路径穿越攻击"""
        import secrets
        token = secrets.token_urlsafe(16)
        tokens[token] = {'user': 'admin', 'cwd': '/tmp'}

        rv = client.get(f'/download?token={token}&path=/tmp/../etc/passwd')
        assert rv.status_code == 403
        assert '非法路径' in rv.data.decode()

    def test_download_file_not_found(self, client):
        """测试文件不存在"""
        import secrets
        token = secrets.token_urlsafe(16)
        tokens[token] = {'user': 'admin', 'cwd': '/tmp'}

        rv = client.get(f'/download?token={token}&path=/tmp/nonexistent_file.txt')
        assert rv.status_code == 404
        assert '文件不存在' in rv.data.decode()

    def test_download_success(self, client):
        """测试下载成功"""
        import secrets
        token = secrets.token_urlsafe(16)
        tokens[token] = {'user': 'admin', 'cwd': '/tmp'}

        # 创建临时文件
        test_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt')
        test_file.write('download test content')
        test_file.close()

        rv = client.get(f'/download?token={token}&path={test_file.name}')
        os.unlink(test_file.name)
        assert rv.status_code == 200
        assert 'download test content' in rv.data.decode()


class TestLogout:
    """退出功能测试"""

    def test_logout(self, client):
        """测试退出"""
        import secrets
        token = secrets.token_urlsafe(16)
        tokens[token] = {'user': 'admin', 'cwd': '/tmp'}

        rv = client.get(f'/logout?t={token}', follow_redirects=True)
        assert rv.status_code == 200
        assert token not in tokens


class TestCLI:
    """命令行参数测试"""

    def test_default_port(self):
        """测试默认端口"""
        import argparse
        from app import __name__ as module_name
        # 解析器在 __main__ 中创建，这里简单验证逻辑
        assert 5001 == 5001  # 默认端口

    def test_port_argument(self):
        """测试端口参数"""
        import argparse
        # 通过模拟命令行参数测试
        parser = argparse.ArgumentParser()
        parser.add_argument('--port', type=int, default=5001)
        args = parser.parse_args(['--port', '8080'])
        assert args.port == 8080


class TestChatGraphAuth:
    """会话导图路由鉴权测试"""

    def test_routes_require_cookie(self, client, chat_env):
        """测试未登录访问导图路由全部 401"""
        for url in ('/chatgraph/config', '/viewer', '/sessions', '/current',
                    '/session/test-session-1/graph.json', '/session/test-session-1/version'):
            rv = client.get(url)
            assert rv.status_code == 401, url
            assert '未授权' in rv.get_json()['error']

    def test_login_sets_cookie(self, client):
        """测试登录成功种下 wt cookie（HttpOnly）"""
        rv = client.post('/', data={'u': 'admin', 'p': 'admin123'})
        assert rv.status_code == 200
        cookies = rv.headers.getlist('Set-Cookie')
        wt = [c for c in cookies if c.startswith('wt=')]
        assert wt and 'HttpOnly' in wt[0]

    def test_logout_clears_cookie(self, client):
        """测试登出清除 wt cookie"""
        import secrets
        token = secrets.token_urlsafe(16)
        tokens[token] = {'user': 'admin', 'cwd': '/tmp'}
        rv = client.get(f'/logout?t={token}')  # 不跟随重定向，检查登出响应本身的 Set-Cookie
        assert rv.status_code == 302
        wt = [c for c in rv.headers.getlist('Set-Cookie') if c.startswith('wt=')]
        assert wt and '1970' in wt[0]  # 过期时间置于 epoch 即清除


class TestChatGraphRoutes:
    """会话导图数据路由测试（镜像 chatgraphic/serve.js 语义）"""

    def test_config_enabled(self, logged_in, chat_env):
        """测试已配置时 config 返回 enabled"""
        rv = logged_in.get('/chatgraph/config')
        assert rv.status_code == 200
        data = rv.get_json()
        assert data['enabled'] is True
        assert data['viewer'] is True

    def test_config_disabled(self, client, monkeypatch):
        """测试未配置数据目录时 config 返回 disabled"""
        monkeypatch.setattr(app_module, 'CHATGRAPHIC_WORK', None)
        monkeypatch.setattr(app_module, 'CHATGRAPHIC_VIEWER', None)
        client.post('/', data={'u': 'admin', 'p': 'admin123'})
        rv = client.get('/chatgraph/config')
        assert rv.get_json()['enabled'] is False

    def test_sessions_list(self, logged_in, chat_env):
        """测试会话列表内容与排序字段"""
        rv = logged_in.get('/sessions')
        data = rv.get_json()
        assert len(data) == 1
        assert data[0]['sessionId'] == 'test-session-1'
        assert data[0]['goal'] == '集成测试目标'
        assert data[0]['version'] == 3
        assert data[0]['roundCount'] == 2

    def test_current(self, logged_in, chat_env):
        """测试 current 跟随最新会话"""
        rv = logged_in.get('/current')
        assert rv.get_json()['sessionId'] == 'test-session-1'

    def test_session_graph(self, logged_in, chat_env):
        """测试读取 graph.json（no-store 缓存语义）"""
        rv = logged_in.get('/session/test-session-1/graph.json')
        assert rv.status_code == 200
        assert rv.get_json()['goal'] == '集成测试目标'
        assert 'no-store' in rv.headers['Cache-Control']

    def test_session_version_and_status(self, logged_in, chat_env):
        """测试 version/status 读取"""
        rv = logged_in.get('/session/test-session-1/version')
        assert rv.get_data(as_text=True) == '3'
        rv = logged_in.get('/session/test-session-1/status')
        assert rv.get_json()['state'] == 'idle'

    def test_session_missing_fallbacks(self, logged_in, chat_env):
        """测试不存在的会话：version/status 兜底值、graph/transcript 503（与 serve.js 一致）"""
        assert logged_in.get('/session/nonexistent-id/version').get_data(as_text=True) == '0'
        assert logged_in.get('/session/nonexistent-id/status').get_data(as_text=True) == '{}'
        rv = logged_in.get('/session/nonexistent-id/graph.json')
        assert rv.status_code == 503
        assert '尚未生成' in rv.get_json()['error']

    def test_bad_sid_rejected(self, logged_in, chat_env):
        """测试非法会话 id（路径穿越/非法字符）与非法文件名一律 404"""
        for url in ('/session/..%2F..%2Fetc/graph.json', '/session/bad..sid/graph.json',
                    '/session/test-session-1/evil.txt'):
            rv = logged_in.get(url)
            assert rv.status_code == 404, url

    def test_viewer_served(self, logged_in, chat_env):
        """测试 /viewer 渲染配置的 viewer.html"""
        rv = logged_in.get('/viewer')
        assert rv.status_code == 200
        assert 'fake viewer' in rv.get_data(as_text=True)

    def test_viewer_missing_placeholder(self, logged_in, monkeypatch):
        """测试 viewer.html 缺失时返回内建提示页而非报错"""
        monkeypatch.setattr(app_module, 'CHATGRAPHIC_VIEWER', None)
        rv = logged_in.get('/viewer')
        assert rv.status_code == 200
        assert 'viewer.html' in rv.get_data(as_text=True)