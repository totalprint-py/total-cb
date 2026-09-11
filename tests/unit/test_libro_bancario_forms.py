"""Pruebas del formulario ``MovimientoLibroForm`` (FR-007) — RED.

Verifican que ``MovimientoLibroForm.clean()`` rechace importes negativos en
``debe``/``haber`` y ambos en cero, mostrando errores en línea en español.

Estado esperado al escribir estas pruebas: ``MovimientoLibroForm`` aún no declara
``clean()``, por lo que el formulario acepta los importes inválidos y las pruebas
fallan en rojo (RED).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from conciliacion.forms import MovimientoLibroForm

FECHA = date(2026, 9, 5)


class TestMovimientoLibroFormClean:
    """Pruebas de la validación FR-007 del formulario del movimiento de libro."""

    @pytest.mark.django_db
    def test_debe_negativo_es_invalido(self, tipo_operacion_factory):
        """Un ``debe`` negativo debe invalidar el formulario con error en ``debe``."""
        tipo_operacion = tipo_operacion_factory()
        form = MovimientoLibroForm(
            data={
                "fecha": FECHA.isoformat(),
                "tipo_operacion": tipo_operacion.pk,
                "detalle": "Depósito inválido",
                "debe": "-10.00",
                "haber": "0.00",
            }
        )
        assert not form.is_valid()
        assert "debe" in form.errors

    @pytest.mark.django_db
    def test_haber_negativo_es_invalido(self, tipo_operacion_factory):
        """Un ``haber`` negativo debe invalidar el formulario con error en ``haber``."""
        tipo_operacion = tipo_operacion_factory()
        form = MovimientoLibroForm(
            data={
                "fecha": FECHA.isoformat(),
                "tipo_operacion": tipo_operacion.pk,
                "detalle": "Depósito inválido",
                "debe": "0.00",
                "haber": "-10.00",
            }
        )
        assert not form.is_valid()
        assert "haber" in form.errors

    @pytest.mark.django_db
    def test_debe_y_haber_cero_es_invalido(self, tipo_operacion_factory):
        """``debe`` y ``haber`` en cero debe invalidar el formulario (error no-campo)."""
        tipo_operacion = tipo_operacion_factory()
        form = MovimientoLibroForm(
            data={
                "fecha": FECHA.isoformat(),
                "tipo_operacion": tipo_operacion.pk,
                "detalle": "Movimiento nulo",
                "debe": "0.00",
                "haber": "0.00",
            }
        )
        assert not form.is_valid()
        assert form.errors  # hay al menos un error (no-campo)

    @pytest.mark.django_db
    def test_debe_positivo_es_valido(self, tipo_operacion_factory):
        """Un ``debe`` positivo (con ``haber`` cero) debe ser válido."""
        tipo_operacion = tipo_operacion_factory()
        form = MovimientoLibroForm(
            data={
                "fecha": FECHA.isoformat(),
                "tipo_operacion": tipo_operacion.pk,
                "detalle": "Depósito válido",
                "debe": "100.00",
                "haber": "0.00",
            }
        )
        assert form.is_valid()
