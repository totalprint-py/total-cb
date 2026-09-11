# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('templates', 'templates'), ('conciliacion/templates', 'conciliacion/templates'), ('static', 'static')],
    hiddenimports=['django', 'django.core', 'django.core.management', 'django.urls', 'django.utils', 'django.db', 'django.template', 'django.views', 'conciliacion', 'conciliacion.apps', 'conciliacion.admin', 'conciliacion.forms', 'conciliacion.models', 'conciliacion.services', 'conciliacion.urls', 'conciliacion.views', 'conciliacion.migrations', 'totalcb', 'totalcb.settings', 'totalcb.paths', 'totalcb.urls', 'totalcb.wsgi', 'django.contrib.admin', 'django.contrib.auth', 'django.contrib.contenttypes', 'django.contrib.sessions', 'django.contrib.messages', 'django.contrib.staticfiles', 'django.middleware.security', 'django.contrib.sessions.middleware', 'django.middleware.common', 'django.middleware.csrf', 'django.contrib.auth.middleware', 'django.contrib.messages.middleware', 'django.middleware.clickjacking'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='TotalPrint_Conciliacion',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
