"""Fixtures compartidas (pytest-django) para las pruebas del proyecto.

Expone fábricas de las entidades de catálogo y el acceso a la base de datos de
pruebas mediante el fixture ``db`` de pytest-django.

Nota: las importaciones de los modelos se realizan de forma diferida dentro de
cada fábrica para que ``conftest.py`` pueda cargarse antes de que
``conciliacion/models.py`` esté implementado (Fase 2 — RED).
"""
from __future__ import annotations

import pytest


@pytest.fixture
def banco_factory(db):
    """Fábrica que crea un ``Banco`` válido, permitiendo sobreescribir campos."""
    from conciliacion.models import Banco

    def _crear(**sobrescribir):
        valores = {"codigo": "BCO-001", "nombre": "Banco de Prueba"}
        valores.update(sobrescribir)
        return Banco.objects.create(**valores)

    return _crear


@pytest.fixture
def tipo_cuenta_factory(db):
    """Fábrica que crea un ``TipoCuenta`` válido, permitiendo sobreescribir campos."""
    from conciliacion.models import TipoCuenta

    def _crear(**sobrescribir):
        valores = {"codigo": "CTA-001", "nombre": "Cuenta Corriente"}
        valores.update(sobrescribir)
        return TipoCuenta.objects.create(**valores)

    return _crear


@pytest.fixture
def moneda_factory(db):
    """Fábrica que crea una ``Moneda`` válida, permitiendo sobreescribir campos."""
    from conciliacion.models import Moneda

    def _crear(**sobrescribir):
        valores = {
            "codigo": "USD",
            "nombre": "Dólar Estadounidense",
            "cantidad_decimales": 2,
        }
        valores.update(sobrescribir)
        return Moneda.objects.create(**valores)

    return _crear


@pytest.fixture
def tipo_operacion_factory(db):
    """Fábrica que crea un ``TipoOperacion`` válido, permitiendo sobreescribir campos."""
    from conciliacion.models import TipoOperacion

    def _crear(**sobrescribir):
        valores = {"codigo": "DEP-001", "nombre": "Depósito"}
        valores.update(sobrescribir)
        return TipoOperacion.objects.create(**valores)

    return _crear


@pytest.fixture
def concepto_ajuste_factory(db):
    """Fábrica que crea un ``ConceptoAjuste`` válido, permitiendo sobreescribir campos."""
    from conciliacion.models import ConceptoAjuste

    def _crear(**sobrescribir):
        valores = {"codigo": "AJU-001", "nombre": "Ajuste Bancario"}
        valores.update(sobrescribir)
        return ConceptoAjuste.objects.create(**valores)

    return _crear
