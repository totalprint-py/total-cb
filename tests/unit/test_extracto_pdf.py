"""Pruebas unitarias del parser de extractos bancarios PDF (Fase 6 — RED).

Cubre el contrato equivalente al de import-format.md pero para la fuente PDF
del extracto bancario CONTINENTAL:

* normalización de montos con notación paraguaya (``1.490.400``, ``-15.458.205``);
* reconstrucción de la fecha completa a partir del día y el mes/año del periodo;
* mapeo Debe/Haber a signo (DEBE positivo, HABER negativo) y salto de la fila
  de ``Totales`` del pie.

Estado esperado al escribir estas pruebas: los símbolos
``parsear_extracto_pdf``, ``_parsear_numero_es_py`` y ``_fecha_desde_dia``
aún no existen en ``conciliacion/importadores``, por lo que la importación falla
y la colección reporta un error (RED válido).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from io import BytesIO

from fpdf import FPDF
from fpdf.enums import XPos, YPos

from conciliacion.importadores import (
    _fecha_desde_dia,        # Missing -> RED
    _parsear_numero_es_py,   # Missing -> RED
    parsear_extracto_pdf,    # Missing -> RED
)


# ---------------------------------------------------------------------------
# 1) Normalización de montos en notación paraguaya.
# ---------------------------------------------------------------------------


def test_parsear_numero_es_py_formato_paraguayo():
    """Convierte montos con separador de millares ``.`` y coma decimal ``,``."""
    assert _parsear_numero_es_py("1.490.400") == Decimal("1490400.00")
    assert _parsear_numero_es_py("647.802") == Decimal("647802.00")
    assert _parsear_numero_es_py("0,0") == Decimal("0.00")
    assert _parsear_numero_es_py("-15.458.205") == Decimal("-15458205.00")
    assert _parsear_numero_es_py("1.234,56") == Decimal("1234.56")


# ---------------------------------------------------------------------------
# 2) Reconstrucción de la fecha completa.
# ---------------------------------------------------------------------------


def test_fecha_desde_dia_reconstruye_fecha_completa():
    """Reconstruye la fecha completa del movimiento a partir del día del extracto."""
    assert _fecha_desde_dia(1, date(2026, 9, 1)) == date(2026, 9, 1)
    assert _fecha_desde_dia(21, date(2026, 9, 1)) == date(2026, 9, 21)


# ---------------------------------------------------------------------------
# 3) Mapeo Debe/Haber y salto de totales en el PDF sintético.
# ---------------------------------------------------------------------------


def test_parsear_extracto_pdf_mapea_debe_haber_y_salta_totales():
    """Mapea Debe/Haber a signo y salta la fila de ``Totales`` del pie."""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=8)

    pdf.multi_cell(
        0, 5, "Desde el 01/09/2026 hasta el 21/09/2026", new_x=XPos.LMARGIN, new_y=YPos.NEXT
    )
    pdf.multi_cell(0, 5, "Saldo Anterior: -15.458.205", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.multi_cell(
        0, 5, "Dia Hora Movimiento Descripción Debe Haber Saldo", new_x=XPos.LMARGIN, new_y=YPos.NEXT
    )
    pdf.multi_cell(
        0, 5, "01 06:44:05 TRF.INTRBN 1.490.400 -13.967.805", new_x=XPos.LMARGIN, new_y=YPos.NEXT
    )
    pdf.multi_cell(
        0, 5, "01 11:16:26 TRANS.INTERB 647.802 -14.615.607", new_x=XPos.LMARGIN, new_y=YPos.NEXT
    )
    pdf.multi_cell(
        0, 5, "01 11:16:52 OP.ELEC 3.000.000 -17.615.607", new_x=XPos.LMARGIN, new_y=YPos.NEXT
    )
    pdf.multi_cell(0, 5, "Totales 761.005.296 794.658.848", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    flujo = BytesIO()
    pdf.output(flujo)
    flujo.seek(0)

    filas = parsear_extracto_pdf(flujo)

    assert len(filas) == 3                                     # "Totales" is skipped
    assert filas[0]["importe"] == Decimal("1490400.00")        # positive -> Debe
    assert filas[1]["importe"] == Decimal("-647802.00")        # negative -> Haber
    assert filas[2]["importe"] == Decimal("-3000000.00")       # negative -> Haber
    assert filas[0]["fecha"] == date(2026, 9, 1)


def test_parsear_extracto_pdf_recupera_fila_sin_saldo():
    """Recupera una fila cuyo saldo impreso se omite (saldo resultante 0)."""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=8)
    pdf.multi_cell(0, 5, "Desde el 01/09/2026 hasta el 21/09/2026", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.multi_cell(0, 5, "Saldo Anterior: 0,0", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.multi_cell(0, 5, "Dia Hora Movimiento Descripción Debe Haber Saldo", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.multi_cell(0, 5, "15 10:08:41 DEPOSITO 14.541.187 14.541.187", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.multi_cell(0, 5, "15 10:26:50 DB X CUOTA 2/2 OP. 34010525225 14.541.187", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.multi_cell(0, 5, "Totales 761.005.296 794.658.848", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    flujo = BytesIO()
    pdf.output(flujo)
    flujo.seek(0)

    filas = parsear_extracto_pdf(flujo)

    assert len(filas) == 2
    assert filas[0]["importe"] == Decimal("14541187.00")      # depósito (entrada)
    assert filas[1]["importe"] == Decimal("-14541187.00")     # DB X CUOTA (salida), saldo omitido
