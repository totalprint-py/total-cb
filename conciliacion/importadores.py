"""Importador de extractos bancarios (Fase 3 — GREEN).

Implementa el contrato ``specs/004-conciliacion-bancaria/contracts/import-format.md``
para el módulo ``conciliacion/importadores.py``:

* ``parsear_extracto(flujo, *, formato, hoja=None) -> list[dict]`` convierte un
  archivo CSV/XLSX en una lista de filas canónicas
  ``{fecha, referencia, detalle, importe}``;
* ``ErrorImportacion`` con mensajes en español para rechazos todo-o-nada.

Reglas soportadas:

* encabezado canónico ``fecha,referencia,detalle,importe`` con alias en español;
* layout de dos columnas ``debe``/``haber`` normalizado a
  ``importe = debe - haber``, insensible a mayúsculas e ignorando columnas extra;
* detección de la fila de encabezado por contenido (no por posición), para el
  bloque de título del fixture real ``1 Continental Guaranies.xlsx``;
* salto de la fila de preámbulo ``Saldo Anterior`` y de las filas de totales/de
  pie (detalle vacío) para no emitir movimientos fantasma.

Los importes monetarios solo admiten ``decimal.Decimal`` (Principio 5 / FR-010);
cualquier ``float`` se rechaza antes de la coerción. Los identificadores y los
mensajes están en español.
"""
from __future__ import annotations

import csv
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

import openpyxl
import pdfplumber


# ---------------------------------------------------------------------------
# Excepción de dominio y constantes de encabezado.
# ---------------------------------------------------------------------------


class ErrorImportacion(Exception):
    """Error todo-o-nada al parsear un extracto bancario."""


CANONICAS = ("fecha", "referencia", "detalle", "importe")

ALIAS_COLUMNA = {
    "fecha": {"fecha", "date"},
    "referencia": {"referencia", "ref", "numero"},
    "detalle": {"detalle", "descripcion", "concepto"},
    "importe": {"importe", "monto"},
    "debe": {"debe"},
    "haber": {"haber"},
}

_FILA_PREAMBULO = "saldo anterior"


def _normalizar(valor) -> str:
    """Normaliza una celda para comparación por contenido (insensible a mayúsc.)."""
    if valor is None:
        return ""
    return str(valor).strip().lower()

# ---------------------------------------------------------------------------
# Parseo de fechas e importes.
# ---------------------------------------------------------------------------


def _parsear_fecha(valor, *, estricto=True):
    """Convierte la celda a ``datetime.date``.

    ``None``/vacío indica sin fecha. Con ``estricto=True`` (layout canónico de
    columna única) una cadena inválida eleva ``ErrorImportacion``; con
    ``estricto=False`` (layout bancario de dos columnas) devuelve ``None`` para
    que la fila del bloque de título sea omitida como ruido.
    """
    if valor is None:
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    if isinstance(valor, str):
        texto = valor.strip()
        if texto == "":
            return None
        try:
            return date.fromisoformat(texto)
        except ValueError:
            if estricto:
                raise ErrorImportacion("fecha inválida") from None
            return None
    if estricto:
        raise ErrorImportacion("fecha inválida")
    return None


def _importe_presente(valor) -> Decimal:
    """Importe de columna única: rechaza vacío/float y exige un número."""
    if valor is None or (isinstance(valor, str) and valor.strip() == ""):
        raise ErrorImportacion("importe vacío")
    if isinstance(valor, float):
        raise ErrorImportacion("Los importes monetarios no admiten float")
    try:
        return Decimal(str(valor))
    except (InvalidOperation, ValueError, TypeError):
        raise ErrorImportacion("importe inválido") from None


def _importe_ausente(valor) -> Decimal:
    """Importe de una columna debe/haber: ausente vale cero; float se rechaza."""
    if valor is None or (isinstance(valor, str) and valor.strip() == ""):
        return Decimal("0")
    if isinstance(valor, float):
        raise ErrorImportacion("Los importes monetarios no admiten float")
    try:
        return Decimal(str(valor))
    except (InvalidOperation, ValueError, TypeError):
        raise ErrorImportacion("importe inválido") from None


# ---------------------------------------------------------------------------
# Parseo de cabecera.
# ---------------------------------------------------------------------------


def _mapear_columnas(cabecera) -> dict:
    """Mapea cada columna normalizada a su nombre canónico (o ``debe``/``haber``)."""
    mapeo = {}
    for indice, celda in enumerate(cabecera):
        nombre = _normalizar(celda)
        if not nombre:
            continue
        for canonico, aliases in ALIAS_COLUMNA.items():
            if nombre in aliases:
                # La primera aparición gana; alias repetidos no pisan.
                mapeo.setdefault(canonico, indice)
                break
    return mapeo


def _es_cabecera_valida(mapeo) -> bool:
    tiene_fecha = "fecha" in mapeo
    tiene_detalle = "detalle" in mapeo
    tiene_importe = "importe" in mapeo
    tiene_debe_haber = "debe" in mapeo and "haber" in mapeo
    return tiene_fecha and tiene_detalle and (tiene_importe or tiene_debe_haber)


def _buscar_cabecera(filas):
    """Localiza la primera fila que contiene las columnas requeridas."""
    for indice, fila in enumerate(filas):
        mapeo = _mapear_columnas(fila)
        if _es_cabecera_valida(mapeo):
            return indice, mapeo
    raise ErrorImportacion("no se encontró la fila de encabezado")


# ---------------------------------------------------------------------------
# Procesamiento de filas.
# ---------------------------------------------------------------------------


def _procesar_fila(fila, mapeo):
    """Convierte una fila de datos a su forma canónica; ``None`` si se omite."""

    def _valor(canonico):
        indice = mapeo.get(canonico)
        if indice is None or indice >= len(fila):
            return None
        return fila[indice]

    detalle_crudo = _valor("detalle")
    detalle = "" if detalle_crudo is None else str(detalle_crudo).strip()
    if detalle == "" or _normalizar(detalle) == _FILA_PREAMBULO:
        return None  # pie de totales o preámbulo ``Saldo Anterior``.

    es_dos_columnas = "importe" not in mapeo

    fecha = _parsear_fecha(_valor("fecha"), estricto=not es_dos_columnas)
    if fecha is None:
        return None  # sin fecha no es un movimiento válido.

    referencia_crudo = _valor("referencia")
    referencia = "" if referencia_crudo is None else str(referencia_crudo).strip()

    if "importe" in mapeo:
        importe = _importe_presente(_valor("importe"))
        if importe == 0:
            raise ErrorImportacion("importe cero")
    else:
        importe = _importe_ausente(_valor("debe")) - _importe_ausente(_valor("haber"))
        if importe == 0:
            return None  # movimiento fantasma (debe=haber=0) en layout de dos columnas.

    return {
        "fecha": fecha,
        "referencia": referencia,
        "detalle": detalle,
        "importe": importe,
    }


# ---------------------------------------------------------------------------
# API pública.
# ---------------------------------------------------------------------------


def parsear_extracto(flujo, *, formato: str, hoja=None) -> list:
    """Convierte un extracto CSV/XLSX en una lista de diccionarios canónicos.

    ``flujo`` es un stream de texto (CSV) o un ``Path``/objeto binario similar a
    archivo (XLSX). Falla de forma todo-o-nada con ``ErrorImportacion`` ante
    cualquier fila inválida.
    """
    if formato == "csv":
        filas = [fila for fila in csv.reader(flujo)]
    elif formato == "xlsx":
        libro = openpyxl.load_workbook(flujo, data_only=True)
        hoja_objeto = libro[hoja] if hoja else libro.active
        filas = [list(fila) for fila in hoja_objeto.iter_rows(values_only=True)]
    else:
        raise ErrorImportacion(f"formato no soportado: {formato}")

    if not filas:
        return []

    indice_cabecera, mapeo = _buscar_cabecera(filas)
    resultado = []
    for fila in filas[indice_cabecera + 1:]:
        registro = _procesar_fila(fila, mapeo)
        if registro is not None:
            resultado.append(registro)
    return resultado


def _parsear_numero_es_py(valor):
    """Convierte notación es-PY (miles '.', decimal ',') a Decimal."""
    if valor is None:
        raise ErrorImportacion("importe vacío")
    if isinstance(valor, float):
        raise ErrorImportacion("Los importes monetarios no admiten float")
    if isinstance(valor, Decimal):
        return valor
    if isinstance(valor, int):
        return Decimal(valor)
    texto = str(valor).strip()
    if not texto:
        raise ErrorImportacion("importe vacío")
    negativo = texto.startswith("-")
    texto = texto.lstrip("+-").strip()
    if "," in texto:
        # La coma es el separador decimal en es-PY; los puntos son de millares.
        texto = texto.replace(".", "").replace(",", ".")
    elif "." in texto:
        # Sin coma, todo punto es separador de millares (convención es-PY).
        texto = texto.replace(".", "")
    try:
        numero = Decimal(texto)
    except InvalidOperation:
        raise ErrorImportacion(f"importe inválido: {valor}") from None
    return -numero if negativo else numero


def _fecha_desde_dia(dia, desde):
    """Combina el día del movimiento con el mes/año del inicio del periodo."""
    return date(desde.year, desde.month, dia)


def parsear_extracto_pdf(flujo):
    """Parsea un extracto PDF (giro Continental) a filas canónicas.

    Detecta el rango ``Desde el ...`` y el ``Saldo Anterior``, y reconstruye cada
    movimiento desde las líneas de texto: los dos últimos números de la línea son
    monto y saldo; el signo del importe se deriva del saldo corrido (sube → debe
    positivo, baja → haber negativo). Se salta cabeceras, ``Saldo``\\ * y ``Totales``.
    """
    lineas = []
    with pdfplumber.open(flujo) as pdf_doc:
        for pagina in pdf_doc.pages:
            texto = pagina.extract_text() or ""
            for linea in texto.split("\n"):
                if linea.strip():
                    lineas.append(linea.strip())

    desde = None
    saldo_anterior = Decimal("0.00")
    for linea in lineas:
        m = re.search(r"Desde\s*el\s*(\d{2})/(\d{2})/(\d{4})", linea, re.I)
        if m:
            desde = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        m = re.search(r"Saldo Anterior[:\s]*([+-]?[0-9.,]+)", linea, re.I)
        if m:
            saldo_anterior = _parsear_numero_es_py(m.group(1))

    if desde is None:
        raise ErrorImportacion("No se encontró el rango de fechas del extracto.")

    saldo_previo = saldo_anterior
    resultado = []
    for linea in lineas:
        bajo = linea.lower()
        if bajo.startswith("dia hora") or "descripción" in bajo or "descripcin" in bajo:
            continue
        if bajo.startswith("totales") or bajo.startswith("saldo") or bajo.startswith("desde el"):
            continue
        tokens = linea.split()
        if len(tokens) < 4:
            continue
        try:
            dia = int(tokens[0])
        except ValueError:
            continue
        try:
            ultimo = _parsear_numero_es_py(tokens[-1])
        except ErrorImportacion:
            continue
        if ultimo == saldo_previo:
            # Fila sin saldo impreso (el banco omite el saldo 0 al saltar de página):
            # el último token es el IMPORTE real, no el saldo.
            if "db" in bajo:            # débito = salida de dinero
                importe = -abs(ultimo)
            else:                       # crédito = entrada de dinero
                importe = abs(ultimo)
            saldo = saldo_previo + importe
        else:
            saldo = ultimo
            importe = saldo - saldo_previo
        resultado.append({
            "fecha": _fecha_desde_dia(dia, desde),
            "referencia": "",
            "detalle": " ".join(tokens[2:-2]),
            "importe": importe,
        })
        saldo_previo = saldo
    return resultado
