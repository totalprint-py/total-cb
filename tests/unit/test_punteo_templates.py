"""Pruebas unitarias de la plantilla dual-list de punteo (T012 — RED).

Cubre la vista ``punteo`` (``reverse("punteo")`` con ``?cuenta=<pk>``) definida en
``conciliacion/views.py`` según ``specs/004-conciliacion-bancaria/contracts/http-api.md``:

* ``extractos`` contiene solo los ``MovimientoExtracto`` ``conciliado=False`` de la
  cuenta seleccionada;
* ``libros`` contiene solo los ``MovimientoLibro`` ``conciliado=False`` de esa misma
  cuenta;
* los ya conciliados (extracto y libro) quedan excluidos de ambas listas;
* con la cuenta vacía de pendientes se sigue respondiendo 200 con listas vacías.

Estado esperado al escribir estas pruebas: ``punteo`` aún no existe en
``conciliacion/views.py``, por lo que la importación del callable falla y la
colección reporta un ``ImportError`` (RED válido).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from conciliacion.models import CuentaBancaria, MovimientoExtracto, MovimientoLibro
from conciliacion.views import punteo


FECHA = date(2026, 8, 24)


@pytest.fixture
def cuenta_bancaria(db, banco_factory, tipo_cuenta_factory, moneda_factory):
    """Devuelve una ``CuentaBancaria`` persistida con sus catálogos asociados."""
    banco = banco_factory()
    tipo_cuenta = tipo_cuenta_factory()
    moneda = moneda_factory()
    return CuentaBancaria.objects.create(
        numero_cuenta="0001-2345-6789",
        denominacion="Cuenta Operativa",
        banco=banco,
        tipo_cuenta=tipo_cuenta,
        moneda=moneda,
    )


@pytest.fixture
def tipo_operacion(db, tipo_operacion_factory):
    """Devuelve un ``TipoOperacion`` persistido para los movimientos del libro."""
    return tipo_operacion_factory()


def _crear_extracto(cuenta_bancaria, **sobrescribir):
    valores = {
        "cuenta_bancaria": cuenta_bancaria,
        "fecha": FECHA,
        "referencia": "REF-1",
        "detalle": "Movimiento manual",
        "importe": Decimal("100.00"),
        "origen": MovimientoExtracto.ORIGEN_MANUAL,
    }
    valores.update(sobrescribir)
    return MovimientoExtracto.objects.create(**valores)


def _crear_libro(cuenta_bancaria, tipo_operacion, **sobrescribir):
    valores = {
        "cuenta": cuenta_bancaria,
        "fecha": FECHA,
        "tipo_operacion": tipo_operacion,
        "detalle": "Depósito libro",
        "debe": Decimal("100.00"),
        "haber": Decimal("0.00"),
    }
    valores.update(sobrescribir)
    return MovimientoLibro.objects.create(**valores)


def _get_punteo(client, cuenta=None):
    """Hace GET a ``punteo`` con el filtro opcional ``cuenta``."""
    return client.get(reverse("punteo"), {"cuenta": cuenta.pk} if cuenta else {})


# ---------------------------------------------------------------------------
# Dual-list de punteo: filtrado por cuenta y por estado ``conciliado``.
# ---------------------------------------------------------------------------


class TestPunteoDualList:
    """``extractos`` y ``libros`` exponen únicamente pendientes de la cuenta."""

    @pytest.mark.django_db
    def test_extractos_solo_pendientes_de_la_cuenta(
        self, client, cuenta_bancaria, tipo_operacion
    ):
        pendiente = _crear_extracto(cuenta_bancaria, detalle="Pendiente")
        _crear_libro(cuenta_bancaria, tipo_operacion)

        respuesta = _get_punteo(client, cuenta_bancaria)

        assert respuesta.status_code == 200
        extractos = list(respuesta.context["extractos"])
        assert pendiente in extractos
        assert all(e.conciliado is False for e in extractos)
        assert all(e.cuenta_bancaria_id == cuenta_bancaria.pk for e in extractos)

    @pytest.mark.django_db
    def test_libros_solo_pendientes_de_la_cuenta(
        self, client, cuenta_bancaria, tipo_operacion
    ):
        _crear_extracto(cuenta_bancaria)
        pendiente = _crear_libro(cuenta_bancaria, tipo_operacion, detalle="Libro pendiente")

        respuesta = _get_punteo(client, cuenta_bancaria)

        assert respuesta.status_code == 200
        libros = list(respuesta.context["libros"])
        assert pendiente in libros
        assert all(l.conciliado is False for l in libros)
        assert all(l.cuenta_id == cuenta_bancaria.pk for l in libros)

    @pytest.mark.django_db
    def test_conciliados_excluidos_de_ambas_listas(
        self, client, cuenta_bancaria, tipo_operacion
    ):
        extracto_conciliado = _crear_extracto(
            cuenta_bancaria, detalle="Extracto conciliado", conciliado=True
        )
        libro_conciliado = _crear_libro(
            cuenta_bancaria,
            tipo_operacion,
            detalle="Libro conciliado",
            conciliado=True,
        )

        respuesta = _get_punteo(client, cuenta_bancaria)

        assert respuesta.status_code == 200
        extractos = list(respuesta.context["extractos"])
        libros = list(respuesta.context["libros"])
        assert extracto_conciliado not in extractos
        assert libro_conciliado not in libros

    @pytest.mark.django_db
    def test_sin_pendientes_renderiza_200_con_listas_vacias(
        self, client, cuenta_bancaria, tipo_operacion
    ):
        respuesta = _get_punteo(client, cuenta_bancaria)

        assert respuesta.status_code == 200
        assert list(respuesta.context["extractos"]) == []
        assert list(respuesta.context["libros"]) == []
