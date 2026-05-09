# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('templates', 'templates'),
        ('static/socket.io.min.js', 'static'),
        ('static/xterm.min.js', 'static'),
        ('static/xterm.css', 'static'),
        ('static/fit.min.js', 'static'),
    ],
    hiddenimports=[
        'flask', 'flask_socketio', 'werkzeug', 'werkzeug.utils',
        'engineio', 'engineio.async_drivers.threading',
        'socketio', 'socketio.async_drivers.threading',
        'simple_websocket', 'wsproto', 'h11',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='web-terminal',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)