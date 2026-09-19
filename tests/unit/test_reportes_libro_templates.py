"""Pruebas de plantilla del Reporte del Libro Bancario (Fase 3 — RED).

Verifican el contrato de presentación de ``conciliacion/reporte_libro.html``
(US1 — HTML MVP): columnas en español, totales al pie, números localizados
(separador de millares ``.`` y decimal ``,``), columna ``saldo`` no editable,
barra de filtros no imprimible, fila de rango vacío, acción de impresión y la
marca ``SENDA S.A.``.

Estado esperado al escribir estas pruebas: la plantilla aún no existe, por lo
que el GET arroja ``TemplateDoesNotExist`` y todas las pruebas fallan (RED).
"""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from conciliacion.models import CuentaBancaria, MovimientoLibro

DESDE = date(2026, 1, 1)
HASTA = date(2026, 1, 31)


def _crear_escenario(
    banco_factory, tipo_cuenta_factory, moneda_factory, tipo_operacion_factory
):
    """Crea una cuenta (saldo inicial 1000.00) con un depósito de 100.00."""
    banco = banco_factory()
    tipo_cuenta = tipo_cuenta_factory()
    moneda = moneda_factory()
    tipo_operacion = tipo_operacion_factory()
    cuenta = CuentaBancaria.objects.create(
        numero_cuenta="0001-2345-6789",
        denominacion="Cuenta Operativa",
        banco=banco,
        tipo_cuenta=tipo_cuenta,
        moneda=moneda,
        saldo_inicial=Decimal("1000.00"),
    )
    MovimientoLibro.objects.create(
        cuenta=cuenta,
        fecha=date(2026, 1, 5),
        tipo_operacion=tipo_operacion,
        detalle="Depósito inicial",
        debe=Decimal("100.00"),
        haber=Decimal("0.00"),
    )
    return cuenta


def _get_reporte(client, cuenta, desde=DESDE, hasta=HASTA):
    """Ejecuta un GET del reporte para la cuenta y rango indicados."""
    return client.get(
        reverse("reporte_libro"),
        {"cuenta": cuenta.pk, "desde": desde.isoformat(), "hasta": hasta.isoformat()},
    )


@pytest.mark.django_db
def test_etiquetas_columnas_y_pie_en_espanol(
    client, banco_factory, tipo_cuenta_factory, moneda_factory, tipo_operacion_factory
):
    """La página expone columnas y totales del pie con etiquetas en español."""
    cuenta = _crear_escenario(
        banco_factory, tipo_cuenta_factory, moneda_factory, tipo_operacion_factory
    )
    contenido = _get_reporte(client, cuenta).content.decode()

    for etiqueta in ("Fecha", "Tipo", "Detalle", "Debe", "Haber", "Saldo"):
        assert etiqueta in contenido
    for etiqueta in ("Saldo Anterior", "Total Debe", "Total Haber", "Saldo final"):
        assert etiqueta in contenido


@pytest.mark.django_db
def test_columnas_de_la_tabla_en_orden(
    client, banco_factory, tipo_cuenta_factory, moneda_factory, tipo_operacion_factory
):
    """La tabla del reporte tiene las columnas en el orden esperado."""
    cuenta = _crear_escenario(
        banco_factory, tipo_cuenta_factory, moneda_factory, tipo_operacion_factory
    )
    contenido = _get_reporte(client, cuenta).content.decode()

    encabezados = [
        celda.strip()
        for celda in re.findall(r"<th\b[^>]*>(.*?)</th>", contenido, flags=re.DOTALL)
    ]
    assert encabezados == ["Fecha", "Tipo", "Detalle", "Debe", "Haber", "Saldo"]


@pytest.mark.django_db
def test_numeros_localizados_con_separador_regional(
    client, banco_factory, tipo_cuenta_factory, moneda_factory, tipo_operacion_factory
):
    """Los importes usan separador de millares ``.`` y decimal ``,``."""
    cuenta = _crear_escenario(
        banco_factory, tipo_cuenta_factory, moneda_factory, tipo_operacion_factory
    )
    contenido = _get_reporte(client, cuenta).content.decode()

    # Saldo inicial 1000.00 → "1.000,00"; saldo corrido 1100.00 → "1.100,00".
    assert "1.000,00" in contenido
    assert "1.100,00" in contenido


@pytest.mark.django_db
def test_columna_saldo_no_es_editable(
    client, banco_factory, tipo_cuenta_factory, moneda_factory, tipo_operacion_factory
):
    """La columna ``saldo`` se muestra como texto plano, sin inputs editables."""
    cuenta = _crear_escenario(
        banco_factory, tipo_cuenta_factory, moneda_factory, tipo_operacion_factory
    )
    contenido = _get_reporte(client, cuenta).content.decode()

    assert 'name="saldo"' not in contenido


@pytest.mark.django_db
def test_barra_de_filtros_no_imprimible(
    client, banco_factory, tipo_cuenta_factory, moneda_factory, tipo_operacion_factory
):
    """La barra de filtros lleva la clase ``no-print``."""
    cuenta = _crear_escenario(
        banco_factory, tipo_cuenta_factory, moneda_factory, tipo_operacion_factory
    )
    contenido = _get_reporte(client, cuenta).content.decode()

    formulario = re.search(r"<form\b[^>]*>", contenido).group(0)
    assert "no-print" in formulario


@pytest.mark.django_db
def test_rango_vacio_muestra_fila_esperada(
    client, banco_factory, tipo_cuenta_factory, moneda_factory, tipo_operacion_factory
):
    """Un rango sin movimientos muestra la fila de estado vacío y el pie."""
    cuenta = _crear_escenario(
        banco_factory, tipo_cuenta_factory, moneda_factory, tipo_operacion_factory
    )
    contenido = _get_reporte(
        client,
        cuenta,
        desde=date(2026, 6, 1),
        hasta=date(2026, 6, 30),
    ).content.decode()

    assert "Sin movimientos en el rango seleccionado." in contenido
    assert "Saldo Anterior" in contenido
    assert "Saldo final" in contenido


@pytest.mark.django_db
def test_accion_de_impresion(
    client, banco_factory, tipo_cuenta_factory, moneda_factory, tipo_operacion_factory
):
    """La página ofrece la acción ``window.print()`` (FR-011)."""
    cuenta = _crear_escenario(
        banco_factory, tipo_cuenta_factory, moneda_factory, tipo_operacion_factory
    )
    contenido = _get_reporte(client, cuenta).content.decode()

    assert "window.print()" in contenido


@pytest.mark.django_db
def test_marca_senda(
    client, banco_factory, tipo_cuenta_factory, moneda_factory, tipo_operacion_factory
):
    """La página lleva la marca ``Senda S.R.L.``."""
    cuenta = _crear_escenario(
        banco_factory, tipo_cuenta_factory, moneda_factory, tipo_operacion_factory
    )
    contenido = _get_reporte(client, cuenta).content.decode()

    assert "Senda S.R.L." in contenido
