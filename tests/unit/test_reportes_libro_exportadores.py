"""Pruebas de los exportadores CSV/XLSX del Reporte del Libro Bancario (Fase 4 — RED).

Verifican el contrato de salida de ``conciliacion/exportadores.py`` (US2 — P2)
según ``contracts/report-output.md``:

* ``exportar_csv`` → texto UTF-8 con BOM, delimitado por ``;``, coma decimal,
  sin separador de millares, con encabezado y pie de totales (incluso vacío).
* ``exportar_xlsx`` → bytes de libro ``openpyxl`` con celdas numéricas nativas
  (sumables, formato a 2 decimales), encabezado y pie de totales (incluso vacío).

Ambos consumen el mismo ``ReporteLibro`` producido por ``generar_reporte_libro``
(FR-007). Estado esperado al escribir estas pruebas: ``conciliacion.exportadores``
aún no existe, por lo que la importación falla y todas las pruebas quedan en rojo.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from io import BytesIO

import openpyxl
import pytest

from conciliacion.exportadores import exportar_csv, exportar_pdf, exportar_xlsx
from conciliacion.models import CuentaBancaria, MovimientoLibro
from conciliacion.reportes import generar_reporte_libro

DESDE = date(2026, 1, 1)
HASTA = date(2026, 1, 31)


def _crear_cuenta(banco_factory, tipo_cuenta_factory, moneda_factory):
    """Crea y persiste una ``CuentaBancaria`` con saldo inicial 1000.00."""
    banco = banco_factory()
    tipo_cuenta = tipo_cuenta_factory()
    moneda = moneda_factory()
    return CuentaBancaria.objects.create(
        numero_cuenta="0001-2345-6789",
        denominacion="Cuenta Operativa",
        banco=banco,
        tipo_cuenta=tipo_cuenta,
        moneda=moneda,
        saldo_inicial=Decimal("1000.00"),
    )


@pytest.fixture
def reporte(banco_factory, tipo_cuenta_factory, moneda_factory, tipo_operacion_factory):
    """``ReporteLibro`` canónico con un depósito (250.00) y un pago (50.50)."""
    cuenta = _crear_cuenta(banco_factory, tipo_cuenta_factory, moneda_factory)
    tipo = tipo_operacion_factory()
    MovimientoLibro.objects.create(
        cuenta=cuenta,
        fecha=date(2026, 1, 5),
        tipo_operacion=tipo,
        detalle="Depósito inicial",
        debe=Decimal("250.00"),
        haber=Decimal("0.00"),
    )
    MovimientoLibro.objects.create(
        cuenta=cuenta,
        fecha=date(2026, 1, 10),
        tipo_operacion=tipo,
        detalle="Pago a proveedor",
        debe=Decimal("0.00"),
        haber=Decimal("50.50"),
    )
    return generar_reporte_libro(cuenta=cuenta, fecha_desde=DESDE, fecha_hasta=HASTA)


@pytest.fixture
def reporte_vacio(banco_factory, tipo_cuenta_factory, moneda_factory):
    """``ReporteLibro`` sin movimientos (rango vacío) sobre una cuenta nueva."""
    cuenta = _crear_cuenta(banco_factory, tipo_cuenta_factory, moneda_factory)
    return generar_reporte_libro(cuenta=cuenta, fecha_desde=DESDE, fecha_hasta=HASTA)


class TestExportarCsv:
    """Contrato del exportador CSV (text/csv; UTF-8 BOM; ``;``; coma decimal)."""

    @staticmethod
    def _lineas(reporte):
        return exportar_csv(reporte).lstrip("\ufeff").splitlines()

    @pytest.mark.django_db
    def test_devuelve_texto_con_bom(self, reporte):
        resultado = exportar_csv(reporte)

        assert resultado.startswith("\ufeff")

    @pytest.mark.django_db
    def test_encabezado(self, reporte):
        assert self._lineas(reporte)[0] == "Fecha;Tipo;Detalle;Debe;Haber;Saldo"

    @pytest.mark.django_db
    def test_fechas_iso_y_coma_decimal(self, reporte):
        fila = self._lineas(reporte)[1]

        assert fila.startswith("2026-01-05;")
        assert "250,00" in fila
        assert "1250,00" in fila
        assert "250.00" not in fila  # sin separador de millares

    @pytest.mark.django_db
    def test_pie_de_totales(self, reporte):
        lineas = self._lineas(reporte)

        assert lineas[-4:] == [
            "Saldo Anterior;1000,00",
            "Total Debe;250,00",
            "Total Haber;50,50",
            "Saldo final;1199,50",
        ]

    @pytest.mark.django_db
    def test_rango_vacio_preserva_encabezado_y_pie(self, reporte_vacio):
        lineas = self._lineas(reporte_vacio)

        assert lineas[0] == "Fecha;Tipo;Detalle;Debe;Haber;Saldo"
        assert lineas[-4:] == [
            "Saldo Anterior;1000,00",
            "Total Debe;0,00",
            "Total Haber;0,00",
            "Saldo final;1000,00",
        ]


class TestExportarXlsx:
    """Contrato del exportador XLSX (openpyxl; celdas numéricas a 2 decimales)."""

    @staticmethod
    def _hoja(reporte):
        return openpyxl.load_workbook(BytesIO(exportar_xlsx(reporte))).active

    @pytest.mark.django_db
    def test_devuelve_bytes_de_libro_xlsx(self, reporte):
        resultado = exportar_xlsx(reporte)

        assert isinstance(resultado, bytes)
        assert resultado[:2] == b"PK"

    @pytest.mark.django_db
    def test_encabezado_y_pie(self, reporte):
        hoja = self._hoja(reporte)

        assert [hoja.cell(1, c).value for c in range(1, 7)] == [
            "Fecha", "Tipo", "Detalle", "Debe", "Haber", "Saldo",
        ]
        # 1 encabezado + 2 detalle + 4 pie.
        assert hoja.max_row == 7
        assert hoja.cell(4, 1).value == "Saldo Anterior"
        assert hoja.cell(7, 1).value == "Saldo final"

    @pytest.mark.django_db
    def test_celdas_numericas_nativas_a_dos_decimales(self, reporte):
        hoja = self._hoja(reporte)

        debe = hoja.cell(2, 4)
        assert debe.value == 250
        assert debe.number_format == "0.00"

        haber = hoja.cell(3, 5)
        assert isinstance(haber.value, float)
        assert haber.value == pytest.approx(50.5)
        assert haber.number_format == "0.00"

        saldo_final = hoja.cell(7, 2)
        assert saldo_final.value == pytest.approx(1199.5)
        assert saldo_final.number_format == "0.00"

    @pytest.mark.django_db
    def test_fechas_como_celdas_nativas(self, reporte):
        hoja = self._hoja(reporte)

        fecha = hoja.cell(2, 1)
        assert fecha.number_format == "dd/mm/yyyy"
        assert (fecha.value.year, fecha.value.month, fecha.value.day) == (
            2026, 1, 5,
        )

    @pytest.mark.django_db
    def test_rango_vacio_preserva_encabezado_y_pie(self, reporte_vacio):
        hoja = self._hoja(reporte_vacio)

        assert hoja.max_row == 5  # encabezado + 4 pie, sin detalle.
        assert hoja.cell(2, 1).value == "Saldo Anterior"
        assert hoja.cell(2, 2).value == 1000
        assert hoja.cell(5, 1).value == "Saldo final"
        assert hoja.cell(5, 2).value == 1000


class TestExportarPdf:
    """Contrato del exportador PDF (``fpdf2``; bytes con número mágico ``%PDF-``)."""

    @pytest.mark.django_db
    def test_devuelve_bytes_pdf(self, reporte):
        resultado = exportar_pdf(reporte)

        assert isinstance(resultado, bytes)
        assert resultado.startswith(b"%PDF-")

    @pytest.mark.django_db
    def test_pdf_de_rango_vacio(self, reporte_vacio):
        resultado = exportar_pdf(reporte_vacio)

        assert isinstance(resultado, bytes)
        assert resultado.startswith(b"%PDF-")
