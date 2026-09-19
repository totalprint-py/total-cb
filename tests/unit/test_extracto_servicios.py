"""Pruebas unitarias del servicio de punteo de extracto bancario (T011 — RED).

Cubre ``puntear(*, extracto, libro)`` y ``despuntear(*, extracto)`` definidos en
``conciliacion/punteo.py`` según el contrato descrito en
``specs/004-conciliacion-bancaria/plan.md``:

* igualdad exacta ``extracto.importe == libro.debe - libro.haber`` después de
  aplicar ``quantize_to_moneda`` a ambos operandos (FR-005 / Principio 5);
* misma ``CuentaBancaria`` en ambos lados (rechazo en español para pares de
  cuentas distintas);
* creación del vínculo 1:1 ``Punteo`` y bandera ``conciliado=True`` en ambos
  movimientos;
* ``despuntear`` que elimina el vínculo, reinicia las banderas y escribe una
  entrada de auditoría ``AuditoriaPunteo`` (``accion=despuntear``);
* respeto del ``UniqueConstraint`` 1:1 de ``Punteo`` (``IntegrityError`` al
  reutilizar cualquiera de los dos lados);
* bitácora ``AuditoriaPunteo`` con ``accion`` en ``puntear|despuntear`` dentro
  del mismo bloque ``transaction.atomic``.

Estado esperado al escribir estas pruebas: ``puntear``, ``despuntear`` y
``ImporteNoCoincideError`` aún no existen en ``conciliacion/punteo.py``, por lo
que la importación falla y la colección reporta un ``ImportError`` (RED válido).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction

from conciliacion.models import (
    AuditoriaPunteo,
    CuentaBancaria,
    MovimientoExtracto,
    MovimientoLibro,
    Punteo,
    TipoOperacion,
    ConciliadoBloqueadoError,
)
from conciliacion.punteo import (
    ImporteNoCoincideError,
    crear_asiento_desde_extracto,
    despuntear,
    puntear,
)


FECHA = date(2026, 9, 10)


# ---------------------------------------------------------------------------
# Factorías de datos de apoyo.
# ---------------------------------------------------------------------------


def _cuenta_bancaria(banco, tipo_cuenta, moneda, **sobrescribir):
    """Crea una ``CuentaBancaria`` de apoyo con ``saldo_inicial=1000.00``."""
    valores = {
        "numero_cuenta": "0001-2345-6789",
        "denominacion": "Cuenta Operativa",
        "banco": banco,
        "tipo_cuenta": tipo_cuenta,
        "moneda": moneda,
        "saldo_inicial": Decimal("1000.00"),
    }
    valores.update(sobrescribir)
    return CuentaBancaria.objects.create(**valores)


def _crear_extracto(cuenta, **sobrescribir):
    """Crea un ``MovimientoExtracto`` de apoyo con default de ingreso."""
    valores = {
        "cuenta_bancaria": cuenta,
        "fecha": FECHA,
        "referencia": "REF-EXT",
        "detalle": "Depósito extracto",
        "importe": Decimal("100.00"),
        "origen": MovimientoExtracto.ORIGEN_MANUAL,
    }
    valores.update(sobrescribir)
    return MovimientoExtracto.objects.create(**valores)


def _crear_libro(cuenta, tipo_operacion, **sobrescribir):
    """Crea un ``MovimientoLibro`` de apoyo con default ``debe=100.00``."""
    valores = {
        "cuenta": cuenta,
        "fecha": FECHA,
        "tipo_operacion": tipo_operacion,
        "detalle": "Depósito libro",
        "debe": Decimal("100.00"),
        "haber": Decimal("0.00"),
    }
    valores.update(sobrescribir)
    return MovimientoLibro.objects.create(**valores)


# ---------------------------------------------------------------------------
# Fixtures que arman el grafo mínimo necesario.
# ---------------------------------------------------------------------------


@pytest.fixture
def cuenta(
    db, banco_factory, tipo_cuenta_factory, moneda_factory
) -> CuentaBancaria:
    """Devuelve una ``CuentaBancaria`` persistida con sus catálogos."""
    return _cuenta_bancaria(
        banco_factory(),
        tipo_cuenta_factory(),
        moneda_factory(),
    )


@pytest.fixture
def otra_cuenta(
    db, banco_factory, tipo_cuenta_factory, moneda_factory
) -> CuentaBancaria:
    """Segunda ``CuentaBancaria`` (distinta de ``cuenta``) para casos cruzados."""
    return _cuenta_bancaria(
        banco_factory(codigo="BCO-OTR", nombre="Banco Distinto"),
        tipo_cuenta_factory(codigo="CTA-OTR", nombre="Cuenta Distinta"),
        moneda_factory(codigo="EUR", nombre="Euro"),
        numero_cuenta="9999-0000-1111",
        denominacion="Cuenta Ajena",
    )


@pytest.fixture
def tipo_operacion(db, tipo_operacion_factory):
    """``TipoOperacion`` reutilizable para los movimientos del libro."""
    return tipo_operacion_factory(codigo="DEP-SVC", nombre="Depósito Servicio")
# ---------------------------------------------------------------------------
# ``puntear(*, extracto, libro)`` — camino feliz.
# ---------------------------------------------------------------------------


class TestPuntearExito:
    """Igualdad exacta ``Decimal`` + misma cuenta crea ``Punteo`` 1:1."""

    @pytest.mark.django_db
    def test_crea_punteo_y_marca_ambos_conciliado(self, cuenta, tipo_operacion):
        """Un par válido debe crear ``Punteo`` y marcar ``conciliado`` ambos."""
        extracto = _crear_extracto(cuenta, importe=Decimal("250.00"))
        libro = _crear_libro(
            cuenta, tipo_operacion, debe=Decimal("250.00"), haber=Decimal("0.00")
        )

        puntear(extracto=extracto, libro=libro)

        extracto.refresh_from_db()
        libro.refresh_from_db()

        assert Punteo.objects.filter(
            movimiento_extracto=extracto, movimiento_libro=libro
        ).exists()
        assert extracto.conciliado is True
        assert libro.conciliado is True

    @pytest.mark.django_db
    def test_registro_de_auditoria_con_accion_puntear(self, cuenta, tipo_operacion):
        """Un punteo exitoso escribe una ``AuditoriaPunteo`` con ``accion=puntear``."""
        extracto = _crear_extracto(cuenta, importe=Decimal("123.45"))
        libro = _crear_libro(
            cuenta, tipo_operacion, debe=Decimal("123.45"), haber=Decimal("0.00")
        )

        puntear(extracto=extracto, libro=libro)

        registro = AuditoriaPunteo.objects.filter(
            movimiento_extracto=extracto,
            movimiento_libro=libro,
        ).get()
        assert registro.accion == AuditoriaPunteo.ACCION_PUNTEAR

    @pytest.mark.django_db
    def test_importe_coincide_exacto_tras_quantize(
        self, cuenta, tipo_operacion, moneda_factory
    ):
        """La igualdad se valida con ``Decimal`` exacto (sin tolerancia)."""
        extracto = _crear_extracto(cuenta, importe=Decimal("100.50"))
        libro = _crear_libro(
            cuenta, tipo_operacion, debe=Decimal("100.50"), haber=Decimal("0.00")
        )

        puntear(extracto=extracto, libro=libro)

        assert Punteo.objects.filter(movimiento_extracto=extracto).exists()


# ---------------------------------------------------------------------------
# ``puntear`` — rechazos de dominio.
# ---------------------------------------------------------------------------


class TestPuntearRechazos:
    """Pares inválidos no deben persistir ``Punteo`` ni mutar banderas."""

    @pytest.mark.django_db
    def test_importe_no_coincide_levanta_error(self, cuenta, tipo_operacion):
        """Diferencia de importe → ``ImporteNoCoincideError`` sin persistir."""
        extracto = _crear_extracto(cuenta, importe=Decimal("100.00"))
        libro = _crear_libro(
            cuenta, tipo_operacion, debe=Decimal("99.99"), haber=Decimal("0.00")
        )

        with pytest.raises(ImporteNoCoincideError):
            puntear(extracto=extracto, libro=libro)

        assert not Punteo.objects.filter(movimiento_extracto=extracto).exists()
        extracto.refresh_from_db()
        libro.refresh_from_db()
        assert extracto.conciliado is False
        assert libro.conciliado is False

    @pytest.mark.django_db
    def test_importe_no_coincide_mensaje_en_espanol(self, cuenta, tipo_operacion):
        """El mensaje del error debe estar en español."""
        extracto = _crear_extracto(cuenta, importe=Decimal("50.00"))
        libro = _crear_libro(
            cuenta, tipo_operacion, debe=Decimal("49.00"), haber=Decimal("0.00")
        )

        with pytest.raises(ImporteNoCoincideError) as contexto:
            puntear(extracto=extracto, libro=libro)

        assert "coincid" in str(contexto.value).lower()

    @pytest.mark.django_db
    def test_punteo_entre_cuentas_distintas_es_rechazado(
        self, cuenta, otra_cuenta, tipo_operacion
    ):
        """Un par de cuentas distintas es rechazado sin persistir ``Punteo``."""
        extracto = _crear_extracto(otra_cuenta, importe=Decimal("100.00"))
        libro = _crear_libro(
            cuenta, tipo_operacion, debe=Decimal("100.00"), haber=Decimal("0.00")
        )

        with pytest.raises(ValueError):
            puntear(extracto=extracto, libro=libro)

        assert Punteo.objects.count() == 0
        extracto.refresh_from_db()
        libro.refresh_from_db()
        assert extracto.conciliado is False
        assert libro.conciliado is False

    @pytest.mark.django_db
    def test_diferencia_de_un_centavo_es_rechazada(self, cuenta, tipo_operacion):
        """Una diferencia de un centavo es suficiente para rechazar el punteo."""
        extracto = _crear_extracto(cuenta, importe=Decimal("100.01"))
        libro = _crear_libro(
            cuenta, tipo_operacion, debe=Decimal("100.00"), haber=Decimal("0.00")
        )

        with pytest.raises(ImporteNoCoincideError):
            puntear(extracto=extracto, libro=libro)


# ---------------------------------------------------------------------------
# ``UniqueConstraint`` 1:1 de ``Punteo``.
# ---------------------------------------------------------------------------


class TestPunteoUnicidad:
    """Cada lado del punteo admite un solo vínculo activo."""

    @pytest.mark.django_db
    def test_extracto_ya_punteado_levanta_integrity_error(
        self, cuenta, tipo_operacion
    ):
        """Reutilizar el mismo ``MovimientoExtracto`` viola la restricción 1:1."""
        extracto = _crear_extracto(cuenta, importe=Decimal("100.00"))
        libro_a = _crear_libro(
            cuenta,
            tipo_operacion,
            detalle="Libro A",
            debe=Decimal("100.00"),
            haber=Decimal("0.00"),
        )
        libro_b = _crear_libro(
            cuenta,
            tipo_operacion,
            detalle="Libro B",
            fecha=date(2026, 9, 11),
            debe=Decimal("100.00"),
            haber=Decimal("0.00"),
        )

        puntear(extracto=extracto, libro=libro_a)

        with pytest.raises(IntegrityError):
            with transaction.atomic():
                Punteo.objects.create(
                    movimiento_extracto=extracto, movimiento_libro=libro_b
                )

    @pytest.mark.django_db
    def test_libro_ya_punteado_levanta_integrity_error(
        self, cuenta, tipo_operacion
    ):
        """Reutilizar el mismo ``MovimientoLibro`` viola la restricción 1:1."""
        libro = _crear_libro(
            cuenta, tipo_operacion, debe=Decimal("100.00"), haber=Decimal("0.00")
        )
        extracto_a = _crear_extracto(
            cuenta, detalle="Extracto A", importe=Decimal("100.00")
        )
        extracto_b = _crear_extracto(
            cuenta,
            detalle="Extracto B",
            fecha=date(2026, 9, 11),
            importe=Decimal("100.00"),
        )

        puntear(extracto=extracto_a, libro=libro)

        with pytest.raises(IntegrityError):
            with transaction.atomic():
                Punteo.objects.create(
                    movimiento_extracto=extracto_b, movimiento_libro=libro
                )


# ---------------------------------------------------------------------------
# ``despuntear(*, extracto)``.
# ---------------------------------------------------------------------------


class TestDespuntear:
    """Elimina el vínculo y reinicia ambas banderas con auditoría."""

    @pytest.mark.django_db
    def test_elimina_punteo_y_resetea_banderas(self, cuenta, tipo_operacion):
        """``despuntear`` quita el ``Punteo`` y deja ambos ``conciliado=False``."""
        extracto = _crear_extracto(cuenta, importe=Decimal("75.00"))
        libro = _crear_libro(
            cuenta, tipo_operacion, debe=Decimal("75.00"), haber=Decimal("0.00")
        )
        puntear(extracto=extracto, libro=libro)

        despuntear(extracto=extracto)

        extracto.refresh_from_db()
        libro.refresh_from_db()
        assert not Punteo.objects.filter(movimiento_extracto=extracto).exists()
        assert extracto.conciliado is False
        assert libro.conciliado is False

    @pytest.mark.django_db
    def test_auditoria_con_accion_despuntear(self, cuenta, tipo_operacion):
        """``despuntear`` escribe ``AuditoriaPunteo`` con ``accion=despuntear``."""
        extracto = _crear_extracto(cuenta, importe=Decimal("33.33"))
        libro = _crear_libro(
            cuenta, tipo_operacion, debe=Decimal("33.33"), haber=Decimal("0.00")
        )
        puntear(extracto=extracto, libro=libro)

        despuntear(extracto=extracto)

        registro = AuditoriaPunteo.objects.filter(
            movimiento_extracto=extracto,
            movimiento_libro=libro,
            accion=AuditoriaPunteo.ACCION_DESPUNTEAR,
        ).get()
        assert registro.accion == AuditoriaPunteo.ACCION_DESPUNTEAR

    @pytest.mark.django_db
    def test_bitacora_acumula_puntear_y_despuntear(self, cuenta, tipo_operacion):
        """La bitácora conserva ambas transiciones en el mismo ``transaction``."""
        extracto = _crear_extracto(cuenta, importe=Decimal("44.44"))
        libro = _crear_libro(
            cuenta, tipo_operacion, debe=Decimal("44.44"), haber=Decimal("0.00")
        )

        puntear(extracto=extracto, libro=libro)
        despuntear(extracto=extracto)

        acciones = list(
            AuditoriaPunteo.objects.filter(
                movimiento_extracto=extracto,
                movimiento_libro=libro,
            )
            .order_by("fecha_hora")
            .values_list("accion", flat=True)
        )
        assert acciones == [
            AuditoriaPunteo.ACCION_PUNTEAR,
            AuditoriaPunteo.ACCION_DESPUNTEAR,
        ]


class TestCrearAsientoDesdeExtracto:
    """crear_asiento_desde_extracto convierte un extracto pendiente en asiento conciliado."""

    @pytest.mark.django_db
    def test_importe_positivo_mapea_a_debe(self, cuenta):
        extracto = _crear_extracto(cuenta, importe=Decimal("100.00"))
        libro = crear_asiento_desde_extracto(extracto=extracto)
        assert libro.debe == Decimal("100.00")
        assert libro.haber == Decimal("0.00")

    @pytest.mark.django_db
    def test_importe_negativo_mapea_a_haber(self, cuenta):
        extracto = _crear_extracto(cuenta, importe=Decimal("-50.00"))
        libro = crear_asiento_desde_extracto(extracto=extracto)
        assert libro.debe == Decimal("0.00")
        assert libro.haber == Decimal("50.00")

    @pytest.mark.django_db
    def test_crea_punteo_y_marca_ambos_conciliado(self, cuenta):
        extracto = _crear_extracto(cuenta, importe=Decimal("100.00"))
        libro = crear_asiento_desde_extracto(extracto=extracto)
        extracto.refresh_from_db(); libro.refresh_from_db()
        assert Punteo.objects.filter(movimiento_extracto=extracto, movimiento_libro=libro).exists()
        assert extracto.conciliado is True
        assert libro.conciliado is True
        assert AuditoriaPunteo.objects.filter(
            movimiento_extracto=extracto, movimiento_libro=libro,
            accion=AuditoriaPunteo.ACCION_PUNTEAR,
        ).exists()

    @pytest.mark.django_db
    def test_recalcula_saldo_corrido_cronologicamente(self, cuenta, tipo_operacion):
        # movement BEFORE the extracto date establishes saldo_base
        previo = _crear_libro(cuenta, tipo_operacion, fecha=date(2026, 9, 8),
                              detalle="Anterior", debe=Decimal("100.00"), haber=Decimal("0.00"))
        extracto = _crear_extracto(cuenta, fecha=date(2026, 9, 10),
                                   detalle="Asiento desde extracto", importe=Decimal("75.00"))
        libro = crear_asiento_desde_extracto(extracto=extracto)
        libro.refresh_from_db()
        # saldo_inicial fixture = 1000.00; previo saldo = 1100.00; nuevo = 1100.00 + 75.00 - 0.00
        assert libro.saldo == Decimal("1175.00")

    @pytest.mark.django_db
    def test_rechaza_extracto_ya_conciliado(self, cuenta):
        extracto = _crear_extracto(cuenta, importe=Decimal("100.00"), conciliado=True)
        with pytest.raises(ConciliadoBloqueadoError):
            crear_asiento_desde_extracto(extracto=extracto)
        assert MovimientoLibro.objects.filter(detalle="Asiento desde extracto").count() == 0

    @pytest.mark.django_db
    def test_tipo_operacion_se_resuelve_ajuste_bancario(self, cuenta):
        extracto = _crear_extracto(cuenta, importe=Decimal("100.00"))
        libro = crear_asiento_desde_extracto(extracto=extracto)
        # resolves via TipoOperacion.objects.get_or_create(codigo="AJUSTE-BANCARIO")
        assert libro.tipo_operacion.codigo == "AJUSTE-BANCARIO"
        assert libro.tipo_operacion.nombre == "Ajuste Bancario"


