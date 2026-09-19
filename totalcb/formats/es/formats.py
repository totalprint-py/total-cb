"""Formatos de número regionales para el locale ``es``.

El módulo ``es`` de la distribución usa un espacio de no separación como
separador de millares. Para la UI financiera de este proyecto se fuerza el
formato regional exacto:

* Separador de millares: "."  →  1.500,50
* Separador decimal:     ","  →  1.500,50
* Agrupación:            3 dígitos.

Este módulo se registra mediante ``FORMAT_MODULE_PATH = ['totalcb.formats']`` y
tiene prioridad sobre ``django.conf.locale.es.formats``. Cualquier clave no
definida aquí (fechas, etc.) sigue resolviéndose por el módulo estándar.
"""

DECIMAL_SEPARATOR = ","
THOUSAND_SEPARATOR = "."
NUMBER_GROUPING = 3
