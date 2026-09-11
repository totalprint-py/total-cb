@echo off
REM =====================================================================
REM   Compila la aplicacion Django en un unico ejecutable de Windows (.exe)
REM   usando PyInstaller.
REM
REM   Requisitos:
REM     1. Instalar las dependencias:  pip install -r requirements.txt
REM     2. Ejecutar este script desde la raiz del proyecto (total-cb).
REM
REM   El ejecutable se genera en:  dist\TotalPrint_Conciliacion.exe
REM =====================================================================
setlocal

REM Limpiar compilaciones previas para partir de un estado conocido.
if exist build rmdir /s /q build
if exist dist  rmdir /s /q dist

REM Compilar main.py usando python -m PyInstaller para garantizar que 
REM se ejecute dentro del entorno virtual activo.
REM Las migraciones se incluyen de forma dinamica con --collect-submodules
REM para que PyInstaller recoja todos los submodulos (0001_initial, etc.)
REM y no solo el paquete ``conciliacion.migrations``.
python -m PyInstaller ^
    --noconfirm ^
    --clean ^
    --onefile ^
    --name "TotalPrint_Conciliacion" ^
    --noconsole ^
    --add-data "templates;templates" ^
    --add-data "conciliacion/templates;conciliacion/templates" ^
    --add-data "static;static" ^
    --hidden-import django ^
    --hidden-import django.core ^
    --hidden-import django.core.management ^
    --hidden-import django.urls ^
    --hidden-import django.utils ^
    --hidden-import django.db ^
    --hidden-import django.template ^
    --hidden-import django.views ^
    --hidden-import conciliacion ^
    --hidden-import conciliacion.apps ^
    --hidden-import conciliacion.admin ^
    --hidden-import conciliacion.forms ^
    --hidden-import conciliacion.models ^
    --hidden-import conciliacion.services ^
    --hidden-import conciliacion.urls ^
    --hidden-import conciliacion.views ^
    --collect-submodules conciliacion.migrations ^
    --hidden-import totalcb ^
    --hidden-import totalcb.settings ^
    --hidden-import totalcb.paths ^
    --hidden-import totalcb.urls ^
    --hidden-import totalcb.wsgi ^
    --hidden-import django.contrib.admin ^
    --hidden-import django.contrib.auth ^
    --hidden-import django.contrib.contenttypes ^
    --hidden-import django.contrib.sessions ^
    --hidden-import django.contrib.messages ^
    --hidden-import django.contrib.staticfiles ^
    --hidden-import django.middleware.security ^
    --hidden-import django.contrib.sessions.middleware ^
    --hidden-import django.middleware.common ^
    --hidden-import django.middleware.csrf ^
    --hidden-import django.contrib.auth.middleware ^
    --hidden-import django.contrib.messages.middleware ^
    --hidden-import django.middleware.clickjacking ^
    main.py

REM Informar del resultado de la compilacion.
if errorlevel 1 (
    echo.
    echo [ERROR] La compilacion fallo. Revise los mensajes anteriores.
) else (
    echo.
    echo [OK] Ejecutable generado en: dist\TotalPrint_Conciliacion.exe
)

endlocal