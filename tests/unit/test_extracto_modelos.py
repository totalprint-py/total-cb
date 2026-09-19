"""Pruebas unitarias de los modelos ``MovimientoExtracto``, ``Punteo`` y
``AuditoriaPunteo`` (Fase 2 — RED).

Verifican:

* el esquema de campos de ``MovimientoExtracto`` (``cuenta_bancaria`` FK
  PROTECT, ``fecha``, ``referencia`` blank, ``detalle``, ``importe`` vía
  ``ImporteDecimalField`` rechazando ``float``, ``origen`` con default
  ``manual`` y ``conciliado`` con default ``False``);
* las restricciones ``CheckConstraint(condition=Q(...))`` (``importe`` no cero,
  ``origen`` en ``manual|importacion``) y ``UniqueConstraint`` sobre cada FK de
  ``Punteo`` (estricto 1:1);
* el esquema de ``AuditoriaPunteo`` (``fecha_hora`` automático, ``accion`` en
  ``puntear|despuntear``, FKs PROTECT hacia ambos lados y ``usuario``).

Estado esperado al escribir estas pruebas: los tres modelos aún no existen en
``conciliacion/models.py``, por lo que la importación falla y la colección
reporta un error (RED válido).
"""
from __future__ import annotations

import pytest
from django.db import models
from django.db.models import Q
from django.db.models.constraints import CheckConstraint, UniqueConstraint

from conciliacion.models import (
    AuditoriaPunteo,
    CuentaBancaria,
    ImporteDecimalField,
    MovimientoExtracto,
    MovimientoLibro,
    Punteo,
)


# ---------------------------------------------------------------------------
# Helpers de introspección de restricciones.
# ---------------------------------------------------------------------------


def _check_constraints(modelo):
    """Devuelve las ``CheckConstraint`` del modelo."""
    return [c for c in modelo._meta.constraints if isinstance(c, CheckConstraint)]


def _unique_constraints(modelo):
    """Devuelve las ``UniqueConstraint`` del modelo."""
    return [c for c in modelo._meta.constraints if isinstance(c, UniqueConstraint)]


def _hojas_de_check(modelo):
    """Aplana los objetos ``Q`` de todas las CHECK devolviendo pares ``(lookup, valor)``."""
    hojas = []

    def _recolectar(q):
        for hijo in q.children:
            if isinstance(hijo, Q):
                _recolectar(hijo)
            else:
                hojas.append(hijo)

    for restriccion in _check_constraints(modelo):
        _recolectar(restriccion.condition)
    return hojas


# ---------------------------------------------------------------------------
# MovimientoExtracto — esquema de campos.
# ---------------------------------------------------------------------------


class TestMovimientoExtractoEsquema:
    """Pruebas del esquema de campos de ``MovimientoExtracto``."""

    def test_cuenta_bancaria_es_fk_protect(self):
        """``cuenta_bancaria`` debe ser FK a ``CuentaBancaria`` con PROTECT."""
        campo = MovimientoExtracto._meta.get_field("cuenta_bancaria")
        assert campo.many_to_one is True
        assert campo.remote_field.model is CuentaBancaria
        assert campo.remote_field.on_delete is models.PROTECT

    def test_fecha_es_datefield(self):
        """El campo ``fecha`` debe ser un ``DateField``."""
        campo = MovimientoExtracto._meta.get_field("fecha")
        assert isinstance(campo, models.DateField)

    def test_referencia_es_charfield_blank(self):
        """El campo ``referencia`` debe ser ``CharField`` de 100 y ``blank=True``."""
        campo = MovimientoExtracto._meta.get_field("referencia")
        assert isinstance(campo, models.CharField)
        assert campo.max_length == 100
        assert campo.blank is True

    def test_detalle_es_charfield(self):
        """El campo ``detalle`` debe ser ``CharField`` de 255."""
        campo = MovimientoExtracto._meta.get_field("detalle")
        assert isinstance(campo, models.CharField)
        assert campo.max_length == 255

    def test_importe_es_importedecimalfield_18_2(self):
        """El campo ``importe`` debe ser ``ImporteDecimalField`` 18,2."""
        campo = MovimientoExtracto._meta.get_field("importe")
        assert isinstance(campo, ImporteDecimalField)
        assert campo.max_digits == 18
        assert campo.decimal_places == 2

    def test_importe_rechaza_float(self):
        """El campo ``importe`` debe rechazar valores ``float``."""
        campo = MovimientoExtracto._meta.get_field("importe")
        with pytest.raises(TypeError):
            campo.to_python(1.5)

    def test_origen_tiene_default_manual(self):
        """El campo ``origen`` debe tener default ``manual``."""
        campo = MovimientoExtracto._meta.get_field("origen")
        assert isinstance(campo, models.CharField)
        assert campo.default == "manual"

    def test_conciliado_es_booleano_con_default_false(self):
        """El campo ``conciliado`` debe ser ``BooleanField`` con default ``False``."""
        campo = MovimientoExtracto._meta.get_field("conciliado")
        assert isinstance(campo, models.BooleanField)
        assert campo.default is False

    def test_ordering_es_fecha_id(self):
        """El orden por defecto debe ser ``['fecha', 'id']``."""
        assert MovimientoExtracto._meta.ordering == ["fecha", "id"]


class TestMovimientoExtractoConstraints:
    """Pruebas de las restricciones CHECK de ``MovimientoExtracto``."""

    def test_importe_no_cero_tiene_check_constraint(self):
        """Debe existir una CHECK que exija ``importe`` distinto de cero."""
        lookups = {lookup for lookup, _ in _hojas_de_check(MovimientoExtracto)}
        assert "importe__lt" in lookups
        assert "importe__gt" in lookups

    def test_origen_tiene_check_constraint(self):
        """Debe existir una CHECK que limite ``origen`` a ``manual|importacion``."""
        hojas = _hojas_de_check(MovimientoExtracto)
        assert any(
            lookup == "origen__in" and set(valor) == {"manual", "importacion"}
            for lookup, valor in hojas
        )


# ---------------------------------------------------------------------------
# Punteo — vínculo estricto 1:1.
# ---------------------------------------------------------------------------


class TestPunteoEsquema:
    """Pruebas del esquema de ``Punteo`` (FKs PROTECT y unicidad 1:1)."""

    @pytest.mark.parametrize(
        "nombre_campo, modelo_destino",
        [
            ("movimiento_extracto", MovimientoExtracto),
            ("movimiento_libro", MovimientoLibro),
        ],
        ids=["movimiento_extracto", "movimiento_libro"],
    )
    def test_relaciones_fk_protect(self, nombre_campo, modelo_destino):
        """Cada FK debe apuntar a su modelo con ``on_delete=PROTECT``."""
        campo = Punteo._meta.get_field(nombre_campo)
        assert campo.many_to_one is True
        assert campo.remote_field.model is modelo_destino
        assert campo.remote_field.on_delete is models.PROTECT

    def test_unique_constraint_en_movimiento_extracto(self):
        """``movimiento_extracto`` debe tener una ``UniqueConstraint`` propia."""
        campos = [tuple(c.fields) for c in _unique_constraints(Punteo)]
        assert ("movimiento_extracto",) in campos

    def test_unique_constraint_en_movimiento_libro(self):
        """``movimiento_libro`` debe tener una ``UniqueConstraint`` propia."""
        campos = [tuple(c.fields) for c in _unique_constraints(Punteo)]
        assert ("movimiento_libro",) in campos


# ---------------------------------------------------------------------------
# AuditoriaPunteo — bitácora de transiciones.
# ---------------------------------------------------------------------------


class TestAuditoriaPunteoEsquema:
    """Pruebas del esquema de ``AuditoriaPunteo``."""

    def test_fecha_hora_es_datetime_auto(self):
        """``fecha_hora`` debe ser ``DateTimeField`` con ``auto_now_add=True``."""
        campo = AuditoriaPunteo._meta.get_field("fecha_hora")
        assert isinstance(campo, models.DateTimeField)
        assert campo.auto_now_add is True

    def test_accion_es_charfield(self):
        """``accion`` debe ser ``CharField`` de 20."""
        campo = AuditoriaPunteo._meta.get_field("accion")
        assert isinstance(campo, models.CharField)
        assert campo.max_length == 20

    @pytest.mark.parametrize(
        "nombre_campo, modelo_destino",
        [
            ("movimiento_extracto", MovimientoExtracto),
            ("movimiento_libro", MovimientoLibro),
        ],
        ids=["movimiento_extracto", "movimiento_libro"],
    )
    def test_relaciones_fk_set_null(self, nombre_campo, modelo_destino):
        """Cada FK debe apuntar a su modelo con on_delete=SET_NULL y null=True."""
        campo = AuditoriaPunteo._meta.get_field(nombre_campo)
        assert campo.many_to_one is True
        assert campo.remote_field.model is modelo_destino
        assert campo.remote_field.on_delete is models.SET_NULL
        assert campo.null is True

    def test_usuario_es_charfield(self):
        """``usuario`` debe ser ``CharField`` de 150 y ``blank=True``."""
        campo = AuditoriaPunteo._meta.get_field("usuario")
        assert isinstance(campo, models.CharField)
        assert campo.max_length == 150
        assert campo.blank is True


class TestAuditoriaPunteoConstraints:
    """Pruebas de la restricción CHECK de ``AuditoriaPunteo``."""

    def test_accion_tiene_check_constraint(self):
        """Debe existir una CHECK que limite ``accion`` a ``puntear|despuntear``."""
        hojas = _hojas_de_check(AuditoriaPunteo)
        assert any(
            lookup == "accion__in" and set(valor) == {"puntear", "despuntear"}
            for lookup, valor in hojas
        )
