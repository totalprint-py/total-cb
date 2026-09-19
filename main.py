"""Punto de entrada del ejecutable de escritorio (PyInstaller + Waitress + pywebview).

Arranca la aplicación Django dentro de una ventana nativa de escritorio (kiosk),
sin controles de navegador:

1. Fija ``DJANGO_SETTINGS_MODULE`` ANTES de tocar Django.
2. Siembra la base SQLite de trabajo (``%LOCALAPPDATA%\\total-cb\\db.sqlite3``)
   con el ``db.sqlite3`` empaquetado si aún no existe, de modo que la aplicación
   arranque con los datos reales y no en blanco.
3. Inicializa Django y aplica las migraciones pendientes.
4. Sirve la aplicación WSGI con Waitress en un ``threading.Thread(daemon=True)``.
5. Abre ``http://127.0.0.1:8000`` en una ventana nativa mediante ``pywebview``
   (WebView2/Chromium en Windows) y ejecuta el bucle de UI en el hilo principal.
"""

import os
import shutil
import sys
import tempfile
import threading
import traceback
import urllib.request
from pathlib import Path

# 1) Configuración ANTES de importar/ejecutar Django.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "totalcb.settings")

import django
from django.core.management import execute_from_command_line

from totalcb import paths

# Con ``--noconsole`` PyInstaller deja ``sys.stdout``/``sys.stderr`` en ``None``;
# redirigirlos a ``os.devnull`` evita ``AttributeError`` al imprimir o loguear.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

HOST = "127.0.0.1"
PORT = 8000
URL = f"http://{HOST}:{PORT}/"
WINDOW_TITLE = "Senda S.R.L. - Libro Bancario"


def _candidatos_semilla():
    """Candidatos (en orden) de dónde copiar el ``db.sqlite3`` de arranque."""
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent  # dist/SENDA_Bancario/
        candidatos = [exe_dir / "db.sqlite3"]
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidatos.append(Path(meipass) / "db.sqlite3")
        return candidatos
    return [paths.BASE_DIR / "db.sqlite3"]


def _sembrar_base_de_datos():
    """Copia la base empaquetada a ``%LOCALAPPDATA%\\total-cb\\db.sqlite3``."""
    destino = Path(paths.database_path())
    if destino.exists():
        return

    destino.parent.mkdir(parents=True, exist_ok=True)
    for fuente in _candidatos_semilla():
        if fuente.is_file():
            shutil.copy2(str(fuente), str(destino))
            print(f"Base de datos sembrada desde: {fuente}")
            return

    # Sin semilla: ``migrate`` más abajo creará un esquema vacío.
    print("Aviso: no se encontró db.sqlite3 empaquetado; se creará una base vacía.")


def _servir():
    """Sirve la aplicación WSGI con Waitress (hilo en segundo plano)."""
    from waitress import serve

    from totalcb.wsgi import application

    serve(application, host=HOST, port=PORT, threads=8)


def _registrar_error(exc):
    """Escribe el traceback a un archivo de diagnóstico (no hay consola en kiosk)."""
    try:
        log = Path(paths.data_dir()) / "app_error.log"
        log.write_text("".join(traceback.format_exception(exc)), encoding="utf-8")
    except Exception:
        pass


class ApiEscritorio:
    def _descargar(self, url):
        return urllib.request.urlopen(url, timeout=60).read()

    def guardar_archivo(self, url, nombre):
        try:
            datos = self._descargar(url)
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        ventana = webview.windows[0]
        rutas = ventana.create_file_dialog(
            webview.FileDialog.SAVE, save_filename=nombre
        )
        if not rutas:
            return {"ok": False, "cancelado": True}
        ruta = rutas[0] if isinstance(rutas, (list, tuple)) else str(rutas)
        Path(ruta).write_bytes(datos)
        return {"ok": True, "ruta": ruta}

    def abrir_pdf(self, url, nombre):
        try:
            datos = self._descargar(url)
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        destino = Path(tempfile.gettempdir()) / nombre
        destino.write_bytes(datos)
        os.startfile(str(destino))
        return {"ok": True, "ruta": str(destino)}


def main():
    # 2) Sembrar la base de datos ANTES de inicializar Django.
    _sembrar_base_de_datos()

    # 3) Inicializar Django y aplicar migraciones pendientes.
    django.setup()
    execute_from_command_line(["main.py", "migrate", "--noinput"])

    # 4) Servir con Waitress en un hilo daemon (se detiene al cerrar la ventana).
    threading.Thread(target=_servir, daemon=True, name="waitress").start()

    # 5) Abrir la ventana nativa (kiosk) y ejecutar el bucle de UI.
    import webview

    webview.create_window(
        WINDOW_TITLE,
        URL,
        width=1280,
        height=800,
        min_size=(800, 560),
        js_api=ApiEscritorio(),
    )
    webview.start()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        _registrar_error(exc)
        if sys.stdin is not None:
            try:
                input("Ocurrió un error. Presione Enter para salir...")
            except (EOFError, OSError):
                pass
