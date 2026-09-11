"""Pruebas de la plantilla del Libro Bancario (Fase 6 — RED).

Verifican el contrato de presentación de ``conciliacion/libro_bancario.html``:
etiquetas en español, columnas del libro mayor, orden horizontal de los campos
del formulario, datos identificativos de la cuenta y ausencia de un campo
editable de ``saldo``.

Estado esperado al escribir estas pruebas: la plantilla aún es un esqueleto
mínimo, por lo que las aserciones de contenido fallan en rojo (RED).
"""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from conciliacion.models import CuentaBancaria, MovimientoLibro

FECHA = date(2026, 9, 5)


def _crear_escenario(banco_factory, tipo_cuenta_factory, moneda_factory, tipo_operacion_factory):
    """Crea una cuenta con datos identificativos y un movimiento de apoyo."""
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
        fecha=FECHA,
        tipo_operacion=tipo_operacion,
        detalle="Depósito inicial",
        debe=Decimal("100.00"),
        haber=Decimal("0.00"),
    )
    return cuenta


@pytest.mark.django_db
def test_etiquetas_en_espanol(client, banco_factory, tipo_cuenta_factory, moneda_factory, tipo_operacion_factory):
    """La página expone las etiquetas del libro en español y la acción de recálculo."""
    cuenta = _crear_escenario(
        banco_factory, tipo_cuenta_factory, moneda_factory, tipo_operacion_factory
    )
    respuesta = client.get(reverse("libro_bancario"), {"cuenta": cuenta.pk})
    contenido = respuesta.content.decode()

    for etiqueta in ("Fecha", "Tipo de operación", "Detalle", "Debe", "Haber", "Saldo"):
        assert etiqueta in contenido
    assert "Recalcular saldos" in contenido


@pytest.mark.django_db
def test_columnas_del_libro_en_orden(client, banco_factory, tipo_cuenta_factory, moneda_factory, tipo_operacion_factory):
    """La tabla del libro mayor tiene las columnas en el orden esperado."""
    cuenta = _crear_escenario(
        banco_factory, tipo_cuenta_factory, moneda_factory, tipo_operacion_factory
    )
    respuesta = client.get(reverse("libro_bancario"), {"cuenta": cuenta.pk})
    contenido = respuesta.content.decode()

    encabezados = [
        celda.strip()
        for celda in re.findall(r"<th\b[^>]*>(.*?)</th>", contenido, flags=re.DOTALL)
    ]
    assert encabezados == [
        "Fecha",
        "Tipo de operación",
        "Detalle",
        "Debe",
        "Haber",
        "Saldo",
    ]


@pytest.mark.django_db
def test_orden_campos_formulario_horizontal(client, banco_factory, tipo_cuenta_factory, moneda_factory, tipo_operacion_factory):
    """Los campos del formulario aparecen en orden horizontal fecha → tipo → detalle → debe → haber."""
    cuenta = _crear_escenario(
        banco_factory, tipo_cuenta_factory, moneda_factory, tipo_operacion_factory
    )
    respuesta = client.get(reverse("libro_bancario"), {"cuenta": cuenta.pk})
    contenido = respuesta.content.decode()

    orden = [
        contenido.index('for="id_fecha"'),
        contenido.index('for="id_tipo_operacion"'),
        contenido.index('for="id_detalle"'),
        contenido.index('for="id_debe"'),
        contenido.index('for="id_haber"'),
    ]
    assert orden == sorted(orden)


@pytest.mark.django_db
def test_muestra_datos_identificativos_de_la_cuenta(client, banco_factory, tipo_cuenta_factory, moneda_factory, tipo_operacion_factory):
    """La página muestra banco, tipo de cuenta, moneda y denominación de la cuenta."""
    cuenta = _crear_escenario(
        banco_factory, tipo_cuenta_factory, moneda_factory, tipo_operacion_factory
    )
    respuesta = client.get(reverse("libro_bancario"), {"cuenta": cuenta.pk})
    contenido = respuesta.content.decode()

    assert "Banco de Prueba" in contenido
    assert "Cuenta Corriente" in contenido
    assert "Dólar Estadounidense" in contenido
    assert "Cuenta Operativa" in contenido


@pytest.mark.django_db
def test_saldo_no_es_editable(client, banco_factory, tipo_cuenta_factory, moneda_factory, tipo_operacion_factory):
    """La columna ``saldo`` es de solo lectura: no existe un input editable de saldo."""
    cuenta = _crear_escenario(
        banco_factory, tipo_cuenta_factory, moneda_factory, tipo_operacion_factory
    )
    respuesta = client.get(reverse("libro_bancario"), {"cuenta": cuenta.pk})
    contenido = respuesta.content.decode()

    assert 'name="saldo"' not in contenido
    assert 'id="id_saldo"' not in contenido
