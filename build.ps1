# =============================================================================
#  build.ps1 — Empaqueta el proyecto Django como ejecutable standalone de
#  Windows usando PyInstaller (modo --onedir, estable para depurar imports).
#
#  Uso (desde la raíz del proyecto):
#    .\build.ps1
#
#  Requisito previo (una vez):
#    python -m pip install -r requirements.txt
#
#  Resultado:
#    dist\SENDA_Bancario\SENDA_Bancario.exe
# =============================================================================

$ErrorActionPreference = "Continue"

# Resolver el intérprete: preferir el entorno virtual del proyecto si existe.
$Python = "python"
if (Test-Path ".\venv\Scripts\python.exe") { $Python = ".\venv\Scripts\python.exe" }

Write-Host "==> Recopilando archivos estáticos (collectstatic)..." -ForegroundColor Cyan
& $Python manage.py collectstatic --noinput
if ($LASTEXITCODE -ne 0) { throw "collectstatic falló" }

# Limpiar artefactos previos para partir de un estado conocido.
if (Test-Path "build") { Remove-Item -Recurse -Force "build" -ErrorAction Stop }
if (Test-Path "dist")  { Remove-Item -Recurse -Force "dist" -ErrorAction Stop }

Write-Host "==> Ejecutando PyInstaller (modo --onedir)..." -ForegroundColor Cyan
& $Python -m PyInstaller `
    --noconfirm `
    --clean `
    --onedir `
    --noconsole `
    --name "SENDA_Bancario" `
    --add-data "templates;templates" `
    --add-data "conciliacion/templates;conciliacion/templates" `
    --add-data "static;static" `
    --add-data "staticfiles;staticfiles" `
    --add-data "db.sqlite3;." `
    --hidden-import django `
    --hidden-import django.core `
    --hidden-import django.core.management `
    --hidden-import django.urls `
    --hidden-import django.utils `
    --hidden-import django.db `
    --hidden-import django.template `
    --hidden-import django.views `
    --hidden-import django.contrib.admin `
    --hidden-import django.contrib.auth `
    --hidden-import django.contrib.contenttypes `
    --hidden-import django.contrib.sessions `
    --hidden-import django.contrib.messages `
    --hidden-import django.contrib.staticfiles `
    --hidden-import django.middleware.security `
    --hidden-import django.contrib.sessions.middleware `
    --hidden-import django.middleware.common `
    --hidden-import django.middleware.csrf `
    --hidden-import django.contrib.auth.middleware `
    --hidden-import django.contrib.messages.middleware `
    --hidden-import django.middleware.clickjacking `
    --hidden-import whitenoise `
    --hidden-import whitenoise.middleware `
    --hidden-import waitress `
    --hidden-import webview `
    --hidden-import webview.platforms.winforms `
    --hidden-import webview.platforms.edgechromium `
    --hidden-import clr `
    --hidden-import clr_loader `
    --collect-all pythonnet `
    --hidden-import conciliacion `
    --hidden-import conciliacion.apps `
    --hidden-import conciliacion.admin `
    --hidden-import conciliacion.forms `
    --hidden-import conciliacion.models `
    --hidden-import conciliacion.services `
    --hidden-import conciliacion.reportes `
    --hidden-import conciliacion.exportadores `
    --hidden-import conciliacion.urls `
    --hidden-import conciliacion.views `
    --collect-submodules conciliacion.migrations `
    --hidden-import totalcb `
    --hidden-import totalcb.settings `
    --hidden-import totalcb.paths `
    --hidden-import totalcb.urls `
    --hidden-import totalcb.wsgi `
    --collect-submodules totalcb.formats `
    --hidden-import openpyxl `
    --hidden-import fpdf `
    main.py

$ExePath = "dist\SENDA_Bancario\SENDA_Bancario.exe"
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "[AVISO] PyInstaller terminó con código $LASTEXITCODE." -ForegroundColor Yellow
    if (Test-Path $ExePath) {
        Write-Host "        (Común por avisos de módulos opcionales; el ejecutable sí se generó.)" -ForegroundColor Yellow
    } else {
        Write-Host "[ERROR] La compilación falló y no se generó el ejecutable." -ForegroundColor Red
        exit 1
    }
}

Write-Host ""
Write-Host "==> Copiando la base de datos existente (db.sqlite3) al directorio de salida..." -ForegroundColor Cyan
if (Test-Path "db.sqlite3") {
    Copy-Item -Path "db.sqlite3" -Destination "dist\SENDA_Bancario\db.sqlite3" -Force -ErrorAction Stop
    Write-Host "[OK] Base de datos copiada a: dist\SENDA_Bancario\db.sqlite3" -ForegroundColor Green
} else {
    Write-Host "[AVISO] No se encontró db.sqlite3 en la raíz del proyecto; se omitió la copia." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "[OK] Ejecutable generado en: dist\SENDA_Bancario\SENDA_Bancario.exe" -ForegroundColor Green
