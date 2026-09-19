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
        "Acciones",
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
def test_importes_con_formato_regional(client, banco_factory, tipo_cuenta_factory, moneda_factory, tipo_operacion_factory):
    """Los importes se muestran con separador de millares y decimal regionales."""
    cuenta = _crear_escenario(
        banco_factory, tipo_cuenta_factory, moneda_factory, tipo_operacion_factory
    )
    respuesta = client.get(reverse("libro_bancario"), {"cuenta": cuenta.pk})
    contenido = respuesta.content.decode()

    assert "1.000,00" in contenido  # saldo inicial (1000.00)
    assert "100,00" in contenido    # debe
    assert "1.100,00" in contenido  # saldo corrido (1000 + 100)


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


@pytest.mark.django_db
def test_boton_eliminar_apunta_a_la_vista_de_eliminacion(client, banco_factory, tipo_cuenta_factory, moneda_factory, tipo_operacion_factory):
    """Cada movimiento expone un enlace hacia su vista de eliminación."""
    cuenta = _crear_escenario(
        banco_factory, tipo_cuenta_factory, moneda_factory, tipo_operacion_factory
    )
    respuesta = client.get(reverse("libro_bancario"), {"cuenta": cuenta.pk})
    contenido = respuesta.content.decode()

    movimiento = MovimientoLibro.objects.get(cuenta=cuenta)
    url_eliminar = reverse("movimientolibro_delete", args=[movimiento.pk])
    assert url_eliminar in contenido


@pytest.mark.django_db
def test_boton_editar_apunta_a_la_vista_de_edicion(client, banco_factory, tipo_cuenta_factory, moneda_factory, tipo_operacion_factory):
    """Cada movimiento expone un enlace «Editar» hacia su vista de edición."""
    cuenta = _crear_escenario(
        banco_factory, tipo_cuenta_factory, moneda_factory, tipo_operacion_factory
    )
    respuesta = client.get(reverse("libro_bancario"), {"cuenta": cuenta.pk})
    contenido = respuesta.content.decode()

    movimiento = MovimientoLibro.objects.get(cuenta=cuenta)
    url_editar = reverse("movimientolibro_update", args=[movimiento.pk])
    assert url_editar in contenido
    assert "Editar" in contenido


@pytest.mark.django_db
def test_pagina_de_confirmacion_de_eliminacion(client, banco_factory, tipo_cuenta_factory, moneda_factory, tipo_operacion_factory):
    """La vista de eliminación muestra la confirmación con cancelar y eliminar."""
    cuenta = _crear_escenario(
        banco_factory, tipo_cuenta_factory, moneda_factory, tipo_operacion_factory
    )
    movimiento = MovimientoLibro.objects.get(cuenta=cuenta)
    respuesta = client.get(reverse("movimientolibro_delete", args=[movimiento.pk]))

    assert respuesta.status_code == 200
    nombres = [plantilla.name for plantilla in respuesta.templates]
    assert "conciliacion/confirm_delete.html" in nombres
    contenido = respuesta.content.decode()
    assert "Confirmar eliminación" in contenido
    assert "Sí, eliminar" in contenido
    # El enlace "Cancelar" devuelve al libro bancario de la cuenta.
    assert reverse("libro_bancario") in contenido


@pytest.mark.django_db
def test_eliminar_movimiento_redirige_al_libro_y_recalcula(client, banco_factory, tipo_cuenta_factory, moneda_factory, tipo_operacion_factory):
    """Eliminar por POST redirige al libro preservando la cuenta seleccionada."""
    cuenta = _crear_escenario(
        banco_factory, tipo_cuenta_factory, moneda_factory, tipo_operacion_factory
    )
    movimiento = MovimientoLibro.objects.get(cuenta=cuenta)
    respuesta = client.post(reverse("movimientolibro_delete", args=[movimiento.pk]))

    assert respuesta.status_code == 302
    assert respuesta.url == f"{reverse('libro_bancario')}?cuenta={cuenta.pk}"
    assert not MovimientoLibro.objects.filter(pk=movimiento.pk).exists()


@pytest.mark.django_db
def test_debe_y_haber_no_son_requeridos(client, banco_factory, tipo_cuenta_factory, moneda_factory, tipo_operacion_factory):
    """Los campos ``debe`` y ``haber`` no llevan el atributo HTML5 ``required``."""
    cuenta = _crear_escenario(
        banco_factory, tipo_cuenta_factory, moneda_factory, tipo_operacion_factory
    )
    respuesta = client.get(reverse("libro_bancario"), {"cuenta": cuenta.pk})
    contenido = respuesta.content.decode()

    debe_input = re.search(r'<input[^>]*name="debe"[^>]*>', contenido).group(0)
    haber_input = re.search(r'<input[^>]*name="haber"[^>]*>', contenido).group(0)
    assert "required" not in debe_input
    assert "required" not in haber_input
    assert "required" not in debe_input
    assert "required" not in haber_input


@pytest.mark.django_db
def test_fila_conciliada_no_muestra_editar_ni_eliminar(
    client, banco_factory, tipo_cuenta_factory, moneda_factory, tipo_operacion_factory
):
    """Una fila conciliada no expone los botones Editar/Eliminar; las no conciliadas si."""
    cuenta = _crear_escenario(
        banco_factory, tipo_cuenta_factory, moneda_factory, tipo_operacion_factory
    )
    tipo_operacion = MovimientoLibro.objects.get(cuenta=cuenta).tipo_operacion
    conciliado = MovimientoLibro.objects.create(
        cuenta=cuenta,
        fecha=date(2026, 9, 6),
        tipo_operacion=tipo_operacion,
        detalle="Depósito conciliado",
        debe=Decimal("50.00"),
        haber=Decimal("0.00"),
        conciliado=True,
    )
    no_conciliado = MovimientoLibro.objects.exclude(pk=conciliado.pk).get(cuenta=cuenta)

    respuesta = client.get(reverse("libro_bancario"), {"cuenta": cuenta.pk})
    contenido = respuesta.content.decode()

    url_editar_conciliado = reverse("movimientolibro_update", args=[conciliado.pk])
    url_eliminar_conciliado = reverse("movimientolibro_delete", args=[conciliado.pk])
    assert url_editar_conciliado not in contenido
    assert url_eliminar_conciliado not in contenido

    # los no conciliados siguen exponiendo sus acciones
    url_editar_nc = reverse("movimientolibro_update", args=[no_conciliado.pk])
    assert url_editar_nc in contenido

