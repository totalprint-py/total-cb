"""Punto de entrada del ejecutable empaquetado con PyInstaller.

Este módulo sustituye a ``manage.py runserver`` en el entorno de escritorio:
configura Django, abre el navegador predeterminado en la URL local y arranca
el servidor de desarrollo en segundo plano.
"""

import os
import subprocess
import sys
import threading
import webbrowser

# Establecer el módulo de configuración ANTES de cargar Django para que
# ``django.setup()`` y ``execute_from_command_line`` lo resuelvan correctamente.
os.environ["DJANGO_SETTINGS_MODULE"] = "totalcb.settings"

import django
from django.core.management import execute_from_command_line

# Al compilar el ejecutable con ``--noconsole``, PyInstaller deja ``sys.stdout``
# y ``sys.stderr`` en ``None``: cualquier ``print`` o log que intente escribir en
# ellos lanzaría ``AttributeError``. Se redirigen a ``os.devnull`` para descartar
# la salida de forma segura.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

# URL local donde se sirve la aplicación.
URL_APLICACION = "http://127.0.0.1:8002/"

# Retardo (en segundos) para abrir el navegador y dar tiempo al servidor a
# empezar a escuchar antes de cargar la página.
RETARDO_NAVEGADOR = 1.5


def abrir_navegador() -> None:
    """Abre la aplicación con apariencia de app nativa (sin barras ni menús).

    Busca Microsoft Edge y Google Chrome en las rutas de instalación estándar de
    Windows y, si encuentra alguno, lo lanza en modo ``--app`` maximizado. Si no
    hay ningún navegador soportado, recurre al navegador predeterminado.
    """
    url = "http://127.0.0.1:8002/"

    # Directorios estándar de instalación en Windows. Se obtienen de las
    # variables de entorno y se usan las rutas clásicas como respaldo.
    program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
    program_files_x86 = os.environ.get(
        "ProgramFiles(x86)", r"C:\Program Files (x86)"
    )

    # Rutas de los ejecutables de Edge y Chrome en ambos directorios.
    rutas_navegadores = [
        # Microsoft Edge
        os.path.join(program_files, "Microsoft", "Edge", "Application", "msedge.exe"),
        os.path.join(program_files_x86, "Microsoft", "Edge", "Application", "msedge.exe"),
        # Google Chrome
        os.path.join(program_files, "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(program_files_x86, "Google", "Chrome", "Application", "chrome.exe"),
    ]

    for ruta in rutas_navegadores:
        if os.path.isfile(ruta):
            # ``--app`` oculta menús y barras de navegación; ``--start-maximized``
            # abre la ventana maximizada para simular una aplicación de escritorio.
            subprocess.Popen([ruta, f"--app={url}", "--start-maximized"])
            return

    # Respaldo: abrir con el navegador predeterminado del sistema.
    webbrowser.open(url)


def main() -> None:
    """Configura Django, abre el navegador y arranca el servidor local."""
    # Inicializar el registro de aplicaciones y la configuración de Django.
    django.setup()

    # Auto-aplicar migraciones para crear la DB si no existe o esta vacia
    execute_from_command_line(["main.py", "migrate"])

    # Programar la apertura del navegador en un hilo separado para no bloquear
    # el arranque del servidor y evitar que el navegador cargue antes de que
    # ``runserver`` esté escuchando.
    threading.Timer(RETARDO_NAVEGADOR, abrir_navegador).start()

    # ``--noreload`` es obligatorio en un ejecutable congelado: el recargador
    # automático lanza subprocesos que no existen dentro del paquete .exe.
    execute_from_command_line(
        ["main.py", "runserver", "127.0.0.1:8002", "--noreload"]
    )


if __name__ == "__main__":
    main()
