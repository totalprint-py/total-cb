"""Renderizadores de exportación del Reporte del Libro Bancario (Fase 4 — GREEN).

Implementa los dos formatos descargables del reporte (US2 — P2) definidos en
``specs/003-reportes-libro-bancario/contracts/report-output.md`` y consume el
único dato canónico ``ReporteLibro`` producido por ``generar_reporte_libro``
(FR-007):

* ``exportar_csv`` → texto UTF-8 con BOM, delimitador ``;``, coma decimal y sin
  separador de millares (fechas ISO ``YYYY-MM-DD``), con encabezado y pie.
* ``exportar_xlsx`` → bytes de libro ``openpyxl`` con celdas numéricas nativas
  (sumables) y formato de visualización a 2 decimales, con encabezado y pie.
* ``exportar_pdf`` → bytes de documento ``fpdf2`` con título, datos de la cuenta,
  rango de fechas, tabla de movimientos y pie de totales. Al ser un formato
  visual, los importes se muestran localizados en español (punto de millares y
  coma decimal), igual que la plantilla HTML.

Ambos son funciones puras de presentación: no escriben en disco ni modifican la
base (PRINCIPIO 4 / FR-009).
"""
from __future__ import annotations

import csv
import io
from decimal import Decimal

from django.utils.formats import number_format
from fpdf import FPDF
from fpdf.enums import XPos, YPos
from openpyxl import Workbook

from conciliacion.reportes import ReporteLibro
from totalcb import paths

BOM_UTF8 = "\ufeff"
ENCABEZADO = ["Fecha", "Tipo", "Detalle", "Debe", "Haber", "Saldo"]
FMT_FECHA = "dd/mm/yyyy"
FMT_IMPORTE = "0.00"
ANCHO_COLUMNAS = [24, 24, 70, 24, 24, 24]  # suma 190 mm (A4, márgenes de 10 mm).
COLUMNAS_NUMERICAS = (3, 4, 5)  # Debe, Haber y Saldo se alinean a la derecha.
PDF_TITULO = "Senda S.R.L. - Reporte de Libro Bancario"


def _formatear_importe(valor: Decimal) -> str:
    """Convierte un importe ``Decimal`` a texto español sin millares (``1234,56``)."""
    return f"{valor:.2f}".replace(".", ",")


def _formatear_importe_localizado(valor: Decimal) -> str:
    """Convierte un importe a formato visual español (``1.500,50``).

    Reutiliza la localización activa del proyecto (``totalcb.formats.es``) vía
    ``django.utils.formats.number_format``: punto para millares y coma decimal.
    """
    return number_format(valor)


def exportar_csv(reporte: ReporteLibro) -> str:
    """Renderiza el reporte como CSV UTF-8 con BOM (``;`` y coma decimal)."""
    buffer = io.StringIO()
    escritor = csv.writer(buffer, delimiter=";", lineterminator="\r\n")

    escritor.writerow(ENCABEZADO)
    for movimiento in reporte.movimientos:
        escritor.writerow(
            [
                movimiento.fecha.isoformat(),
                str(movimiento.tipo_operacion),
                movimiento.detalle,
                _formatear_importe(movimiento.debe),
                _formatear_importe(movimiento.haber),
                _formatear_importe(movimiento.saldo),
            ]
        )

    for etiqueta, valor in _totales(reporte):
        escritor.writerow([etiqueta, _formatear_importe(valor)])

    return BOM_UTF8 + buffer.getvalue()


def exportar_xlsx(reporte: ReporteLibro) -> bytes:
    """Renderiza el reporte como libro ``openpyxl`` con celdas numéricas nativas."""
    libro = Workbook()
    hoja = libro.active
    hoja.title = "Libro Bancario"

    hoja.append(ENCABEZADO)
    for movimiento in reporte.movimientos:
        hoja.append(
            [
                movimiento.fecha,
                str(movimiento.tipo_operacion),
                movimiento.detalle,
                movimiento.debe,
                movimiento.haber,
                movimiento.saldo,
            ]
        )

    for etiqueta, valor in _totales(reporte):
        hoja.append([etiqueta, valor])

    _aplicar_formatos(hoja, len(reporte.movimientos))

    salida = io.BytesIO()
    libro.save(salida)
    return salida.getvalue()


def _totales(reporte: ReporteLibro):
    """Devuelve el bloque de totales en el orden canónico del pie del reporte."""
    return [
        ("Saldo Anterior", reporte.saldo_inicial_periodo),
        ("Total Debe", reporte.total_debe),
        ("Total Haber", reporte.total_haber),
        ("Saldo final", reporte.saldo_final),
    ]


def _aplicar_formatos(hoja, cantidad_movimientos: int) -> None:
    """Aplica formatos de celda: fecha para la columna A y 2 dp para importes."""
    for fila in range(2, 2 + cantidad_movimientos):
        hoja.cell(row=fila, column=1).number_format = FMT_FECHA
        for columna in (4, 5, 6):
            hoja.cell(row=fila, column=columna).number_format = FMT_IMPORTE

    fila_pie = 2 + cantidad_movimientos
    for desplazamiento in range(4):
        hoja.cell(row=fila_pie + desplazamiento, column=2).number_format = FMT_IMPORTE


def exportar_pdf(reporte: ReporteLibro) -> bytes:
    """Renderiza el reporte como PDF (``fpdf2``) y devuelve sus bytes.

    Incluye el título corporativo, los datos de la cuenta, el rango de fechas,
    la tabla de movimientos y el pie de totales. Los importes se muestran con
    localización española (``1.500,50``) por ser un formato visual (FR-008).
    No escribe en disco (PRINCIPIO 4 / FR-009).
    """
    pdf = FPDF(format="A4", unit="mm")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    _encabezado_pdf(pdf, reporte)
    _tabla_pdf(pdf, reporte)

    return bytes(pdf.output())


def _ruta_logo():
    """Devuelve la ruta del logo corporativo (None si no está disponible).

    Resuelve la ubicación del asset tanto en desarrollo (BASE_DIR/static)
    como en el ejecutable empaquetado (sys._MEIPASS/static), sin lanzar
    excepción si el archivo falta: el PDF se genera igual, solo sin logo.
    """
    ruta = paths.static_root() / "img" / "logo_senda.png"
    return str(ruta) if ruta.is_file() else None


def _encabezado_pdf(pdf: FPDF, reporte: ReporteLibro) -> None:
    """Dibuja el logo corporativo, el título, la cuenta y el rango de fechas."""
    logo = _ruta_logo()
    if logo is not None:
        # El logo es 360x60 px (relación 6:1); se muestra a 60 mm de ancho,
        # centrado horizontalmente sobre una hoja A4 de 210 mm de ancho.
        ancho_logo = 60.0
        alto_logo = ancho_logo * (60 / 360)
        x = (210 - ancho_logo) / 2
        pdf.image(logo, x=x, y=pdf.get_y(), w=ancho_logo, h=alto_logo)
        pdf.ln(alto_logo + 2)

    pdf.set_font("helvetica", "B", 16)
    pdf.cell(0, 10, PDF_TITULO, align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_font("helvetica", "", 10)
    cuenta = f"{reporte.cuenta.denominacion} ({reporte.cuenta.numero_cuenta})"
    pdf.cell(0, 6, f"Cuenta: {cuenta}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    periodo = (
        f"Periodo: {reporte.fecha_desde.strftime('%d/%m/%Y')} al "
        f"{reporte.fecha_hasta.strftime('%d/%m/%Y')}"
    )
    pdf.cell(0, 6, periodo, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(
        0,
        10,
        "Saldo Anterior: " + _formatear_importe_localizado(reporte.saldo_inicial_periodo),
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
    )
    pdf.ln(4)


def _tabla_pdf(pdf: FPDF, reporte: ReporteLibro) -> None:
    """Dibuja el encabezado de columnas, las filas y el pie de totales."""
    anchos = ANCHO_COLUMNAS

    pdf.set_font("helvetica", "B", 9)
    for indice, encabezado in enumerate(ENCABEZADO):
        alineacion = "R" if indice in COLUMNAS_NUMERICAS else "L"
        pdf.cell(anchos[indice], 7, encabezado, border=1, align=alineacion)
    pdf.ln()

    pdf.set_font("helvetica", "", 9)
    for movimiento in reporte.movimientos:
        _fila_pdf(
            pdf,
            anchos,
            [
                movimiento.fecha.strftime("%d/%m/%Y"),
                str(movimiento.tipo_operacion),
                movimiento.detalle,
                _formatear_importe_localizado(movimiento.debe),
                _formatear_importe_localizado(movimiento.haber),
                _formatear_importe_localizado(movimiento.saldo),
            ],
        )

    pdf.set_font("helvetica", "B", 9)
    for etiqueta, valor in _totales(reporte):
        ancho_etiqueta = sum(anchos[:-1])
        pdf.cell(ancho_etiqueta, 7, etiqueta, border=1, align="R")
        pdf.cell(
            anchos[-1],
            7,
            _formatear_importe_localizado(valor),
            border=1,
            align="R",
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )


def _fila_pdf(pdf: FPDF, anchos, celdas) -> None:
    """Dibuja una fila de la tabla; las columnas numéricas van alineadas a la derecha."""
    for indice, (texto, ancho) in enumerate(zip(celdas, anchos)):
        alineacion = "R" if indice in COLUMNAS_NUMERICAS else "L"
        pdf.cell(ancho, 7, texto, border=1, align=alineacion)
    pdf.ln()
