"""Pruebas unitarias del importador de extractos bancarios (Fase 3 — RED).

Cubre el contrato ``specs/004-conciliacion-bancaria/contracts/import-format.md``
para el módulo ``conciliacion/importadores.py``:

* encabezado canónico ``fecha,referencia,detalle,importe``;
* alias en español (``fecha``/``date``, ``detalle``/``descripcion``/``concepto``,
  ``importe``/``monto``, ``referencia``/``ref``/``numero``);
* layout de dos columnas ``debe`` + ``haber`` normalizado a
  ``importe = DEBE - HABER`` (DEBE entrada de dinero positiva; HABER salida de
  dinero negativa), con encabezados insensibles a mayúsculas e ignorando las
  columnas extra ``OPERACIÓN`` y ``SALDO``;
* salto de la fila de preámbulo ``Saldo Anterior`` y de la fila de totales de
  pie del fixture real ``1 Continental Guaranies.xlsx`` (hoja ``CONTINENTAL``);
* rechazo (error en español, todo-o-nada) de filas con ``fecha`` inválida,
  ``importe`` cero/nulo o un monto ``float`` antes de la coerción a ``Decimal``
  (Principio 5).

Estado esperado al escribir estas pruebas: el módulo
``conciliacion/importadores`` aún no existe, por lo que la importación falla y la
colección reporta un error (RED válido).
"""
from __future__ import annotations

import csv
from datetime import date
from decimal import Decimal
from io import BytesIO, StringIO
from pathlib import Path

import openpyxl
import pytest

from conciliacion.importadores import ErrorImportacion, parsear_extracto


# ---------------------------------------------------------------------------
# Fixtures de archivo.
# ---------------------------------------------------------------------------

# El benchmark vive en la raíz del repositorio (hoja ``CONTINENTAL``).
FIXTURA_CONTINENTAL = (
    Path(__file__).resolve().parents[2] / "1 Continental Guaranies.xlsx"
)


def _csv_contenido(cabecera, *filas) -> StringIO:
    """Construye un ``StringIO`` CSV UTF-8 con la cabecera y las filas dadas."""
    salida = StringIO()
    escritor = csv.writer(salida)
    escritor.writerow(cabecera)
    for fila in filas:
        escritor.writerow(fila)
    salida.seek(0)
    return salida


def _xlsx_contenido(cabecera, *filas) -> BytesIO:
    """Construye un ``BytesIO`` XLSX (openpyxl) con celdas nativas."""
    libro = openpyxl.Workbook()
    hoja = libro.active
    hoja.append(cabecera)
    for fila in filas:
        hoja.append(fila)
    salida = BytesIO()
    libro.save(salida)
    salida.seek(0)
    return salida


# ---------------------------------------------------------------------------
# 1) Encabezado canónico.
# ---------------------------------------------------------------------------


class TestCabeceraCanonica:
    """El encabezado ``fecha,referencia,detalle,importe`` se acepta tal cual."""

    def test_importa_fila_canonica(self):
        flujo = _csv_contenido(
            ["fecha", "referencia", "detalle", "importe"],
            ["2026-08-24", "REF-1", "Depósito BELLINI", "-120200000"],
        )
        filas = parsear_extracto(flujo, formato="csv")

        assert len(filas) == 1
        fila = filas[0]
        assert fila["fecha"] == date(2026, 8, 24)
        assert fila["referencia"] == "REF-1"
        assert fila["detalle"] == "Depósito BELLINI"
        assert fila["importe"] == Decimal("-120200000")


# ---------------------------------------------------------------------------
# 2) Alias en español.
# ---------------------------------------------------------------------------


class TestAliasEspanol:
    """Los alias en español/normalizados se resuelven al nombre canónico."""

    @pytest.mark.parametrize(
        "cabecera",
        [
            ["date", "referencia", "detalle", "importe"],
            ["fecha", "ref", "detalle", "importe"],
            ["fecha", "referencia", "descripcion", "importe"],
            ["fecha", "referencia", "concepto", "importe"],
            ["fecha", "referencia", "detalle", "monto"],
            ["fecha", "numero", "detalle", "importe"],
        ],
        ids=["date", "ref", "descripcion", "concepto", "monto", "numero"],
    )
    def test_alias_se_normaliza(self, cabecera):
        flujo = _csv_contenido(cabecera, ["2026-08-24", "REF-1", "Concepto X", "1500"])
        filas = parsear_extracto(flujo, formato="csv")

        assert len(filas) == 1
        fila = filas[0]
        # El resultado siempre usa las claves canónicas.
        assert set(fila) == {"fecha", "referencia", "detalle", "importe"}
        assert fila["fecha"] == date(2026, 8, 24)
        assert fila["referencia"] == "REF-1"
        assert fila["detalle"] == "Concepto X"
        assert fila["importe"] == Decimal("1500")


# ---------------------------------------------------------------------------
# 3) Layout de dos columnas debe + haber.
# ---------------------------------------------------------------------------


class TestDobleColumnaDebeHaber:
    """``debe``/``haber`` se normalizan a ``importe = DEBE - HABER``."""

    def test_normaliza_debe_positivo_y_haber_negativo_ignorando_extra(self):
        # Encabezado en MAYÚSCULAS (insensible a mayúsculas) con OPERACIÓN/SALDO.
        flujo = _csv_contenido(
            ["FECHA", "OPERACIÓN", "DETALLE", "DEBE", "HABER", "SALDO"],
            ["2026-08-24", "Deposito", "BELLINI", "980000", "", "-73625356"],
            ["2026-08-24", "EGRESO", "COMPRA", "", "120200000", "-193825356"],
        )
        filas = parsear_extracto(flujo, formato="csv")

        assert len(filas) == 2
        # Las columnas OPERACIÓN/SALDO no persisten.
        assert set(filas[0]) == {"fecha", "referencia", "detalle", "importe"}
        assert set(filas[1]) == {"fecha", "referencia", "detalle", "importe"}

        assert filas[0]["detalle"] == "BELLINI"
        assert filas[0]["importe"] == Decimal("980000")  # DEBE → entrada positiva

        assert filas[1]["detalle"] == "COMPRA"
        assert filas[1]["importe"] == Decimal("-120200000")  # HABER → salida negativa


# ---------------------------------------------------------------------------
# 4) Fixture real: hoja CONTINENTAL.
# ---------------------------------------------------------------------------


class TestFixtureContinental:
    """El benchmark ``1 Continental Guaranies.xlsx`` se importa correctamente."""

    @staticmethod
    def _cargar():
        with open(FIXTURA_CONTINENTAL, "rb") as archivo:
            return parsear_extracto(archivo, formato="xlsx", hoja="CONTINENTAL")

    def test_signo_ingreso_deposito_bellini(self):
        """``Deposito BELLINI`` (DEBE=980000) se importa como +980000."""
        fila = next(f for f in self._cargar() if f["detalle"] == "BELLINI")
        assert fila["importe"] == Decimal("980000")

    def test_signo_egreso_compra(self):
        """``EGRESO COMPRA $ 20,000*6.010`` (HABER=120200000) es -120200000."""
        fila = next(
            f for f in self._cargar() if f["detalle"] == "COMPRA $ 20,000*6.010"
        )
        assert fila["importe"] == Decimal("-120200000")

    def test_salta_preambulo_saldo_anterior(self):
        """La fila de apertura ``Saldo Anterior`` no se importa."""
        detalles = {f["detalle"] for f in self._cargar()}
        assert "Saldo Anterior" not in detalles

    def test_salta_pie_de_totales(self):
        """Las filas de totales de pie (detalle vacío) no se importan."""
        filas = self._cargar()
        assert all(f["detalle"] for f in filas)  # ninguna fila con detalle vacío
        assert all(f["importe"] != 0 for f in filas)


# ---------------------------------------------------------------------------
# 5) Filas inválidas: rechazo todo-o-nada en español.
# ---------------------------------------------------------------------------


class TestFilasInvalidas:
    """Filas inválidas rechazan todo el lote con un error en español."""

    def test_fecha_invalida(self):
        flujo = _csv_contenido(
            ["fecha", "referencia", "detalle", "importe"],
            ["no-es-una-fecha", "", "Concepto", "100"],
        )
        with pytest.raises(ErrorImportacion, match="fecha inválida"):
            parsear_extracto(flujo, formato="csv")

    def test_importe_cero(self):
        flujo = _csv_contenido(
            ["fecha", "referencia", "detalle", "importe"],
            ["2026-08-24", "", "Concepto", "0"],
        )
        with pytest.raises(ErrorImportacion, match="importe cero"):
            parsear_extracto(flujo, formato="csv")

    def test_importe_nulo(self):
        flujo = _csv_contenido(
            ["fecha", "referencia", "detalle", "importe"],
            ["2026-08-24", "", "Concepto", ""],
        )
        with pytest.raises(ErrorImportacion, match="importe vacío"):
            parsear_extracto(flujo, formato="csv")

    def test_importe_float_se_rechaza_antes_de_decimal(self):
        """Un ``float`` nativo (celda numérica XLSX) se rechaza (Principio 5)."""
        flujo = _xlsx_contenido(
            ["fecha", "referencia", "detalle", "importe"],
            ["2026-08-24", "", "Concepto", 1234.56],
        )
        with pytest.raises(ErrorImportacion, match="no admiten float"):
            parsear_extracto(flujo, formato="xlsx")
