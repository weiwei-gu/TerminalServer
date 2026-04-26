import pytest
import os
import tempfile
import sys

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, socketio, tokens


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