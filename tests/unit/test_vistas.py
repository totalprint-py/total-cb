"""Pruebas unitarias de las vistas de la UX híbrida (Fase 6 — RED).

Cubre exclusivamente los adaptadores HTTP delgados que deben implementarse en
``conciliacion/views.py`` y enrutarse en ``conciliacion/urls.py``:

* Vista de tablero / pantalla dividida (split-screen) que renderiza los
  movimientos bancarios e internos sin conciliar lado a lado.
* Vista de "Reporte de Verificación Manual" con su plantilla específica de
  impresión.
* Endpoints de acción (POST) que delegan en ``conciliacion/services.py``:
  ``match_movimientos``, ``commit_reconciliation`` y ``revert_conciliacion``.

Las vistas, las URLs y las plantillas todavía no existen; por eso estas pruebas
deben fallar en rojo (RED), típicamente con ``NoReverseMatch`` (URL inexistente)
o ``TemplateDoesNotExist`` (plantilla inexistente). Todas las descripciones,
funciones, clases y variables están en español.

Convenciones asumidas (contrato que la implementación GREEN debe cumplir):

* Nombres de URL: ``tablero``, ``reporte_manual``, ``emparejar_movimientos``,
  ``comprometer_conciliacion`` y ``revertir_conciliacion``.
* Claves de contexto del tablero: ``movimientos_bancarios`` y
  ``movimientos_internos`` (solo movimientos sin conciliar).
* Plantillas: ``conciliacion/matcher.html`` y
  ``conciliacion/reporte_manual.html``.
* Acciones POST exitosas → redirección 302; errores de dominio tipados
  (``AmountMismatchError`` / ``ZeroSumError``) → respuesta 400.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from conciliacion.models import (
    Conciliacion,
    CuentaBancaria,
    DetalleConciliacionBancaria,
    DetalleConciliacionInterna,
    LoteImportacion,
    MovimientoBancario,
    MovimientoInterno,
)

# ---------------------------------------------------------------------------
# Constantes de apoyo
# ---------------------------------------------------------------------------

FECHA_IMPORTACION = timezone.make_aware(datetime(2026, 9, 5, 10, 30, 0))
FECHA_MOVIMIENTO = date(2026, 9, 5)
FECHA_DESDE = date(2026, 9, 1)
FECHA_HASTA = date(2026, 9, 30)

NOMBRE_URL_TABLERO = "tablero"
NOMBRE_URL_REPORTE_MANUAL = "reporte_manual"
NOMBRE_URL_EMPAREJAR = "emparejar_movimientos"
NOMBRE_URL_COMPROMETER = "comprometer_conciliacion"
NOMBRE_URL_REVERTIR = "revertir_conciliacion"

PLANTILLA_TABLERO = "conciliacion/matcher.html"
PLANTILLA_REPORTE_MANUAL = "conciliacion/reporte_manual.html"

CLAVE_CONTEXTO_BANCARIOS = "movimientos_bancarios"
CLAVE_CONTEXTO_INTERNOS = "movimientos_internos"


# ---------------------------------------------------------------------------
# Factorías de apoyo (construyen el grafo de datos sin ser objeto de prueba)
# ---------------------------------------------------------------------------


def _crear_lote(**sobrescribir):
    """Crea y persiste un ``LoteImportacion`` de apoyo."""
    valores = {"fuente": "BANCO-X.csv", "fecha_importacion": FECHA_IMPORTACION}
    valores.update(sobrescribir)
    return LoteImportacion.objects.create(**valores)


def _crear_cuenta_bancaria(banco, tipo_cuenta, moneda, **sobrescribir):
    """Crea y persiste una ``CuentaBancaria`` de apoyo."""
    valores = {
        "numero_cuenta": "0001-2345-6789",
        "denominacion": "Cuenta Operativa",
        "banco": banco,
        "tipo_cuenta": tipo_cuenta,
        "moneda": moneda,
    }
    valores.update(sobrescribir)
    return CuentaBancaria.objects.create(**valores)


def _crear_movimiento_bancario(cuenta_bancaria, lote_importacion, tipo_operacion, moneda, **sobrescribir):
    """Crea y persiste un ``MovimientoBancario`` de apoyo."""
    valores = {
        "importe": Decimal("100.00"),
        "fecha": FECHA_MOVIMIENTO,
        "cuenta_bancaria": cuenta_bancaria,
        "lote_importacion": lote_importacion,
        "tipo_operacion": tipo_operacion,
        "moneda": moneda,
    }
    valores.update(sobrescribir)
    return MovimientoBancario.objects.create(**valores)


def _crear_movimiento_interno(lote_importacion, tipo_operacion, moneda, **sobrescribir):
    """Crea y persiste un ``MovimientoInterno`` de apoyo."""
    valores = {
        "importe": Decimal("100.00"),
        "fecha": FECHA_MOVIMIENTO,
        "lote_importacion": lote_importacion,
        "tipo_operacion": tipo_operacion,
        "moneda": moneda,
    }
    valores.update(sobrescribir)
    return MovimientoInterno.objects.create(**valores)


def _crear_conciliacion(cuenta_bancaria, **sobrescribir):
    """Crea y persiste una ``Conciliacion`` de apoyo en estado ``draft``."""
    valores = {
        "estado": Conciliacion.ESTADO_BORRADOR,
        "fecha_desde": FECHA_DESDE,
        "fecha_hasta": FECHA_HASTA,
        "cuenta_bancaria": cuenta_bancaria,
    }
    valores.update(sobrescribir)
    return Conciliacion.objects.create(**valores)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def cuenta_bancaria(banco_factory, tipo_cuenta_factory, moneda_factory):
    """Devuelve una ``CuentaBancaria`` persistida con su moneda asociada."""
    banco = banco_factory()
    tipo_cuenta = tipo_cuenta_factory()
    moneda = moneda_factory()
    return _crear_cuenta_bancaria(banco, tipo_cuenta, moneda)


@pytest.fixture
def lote_importacion():
    """Devuelve un ``LoteImportacion`` persistido y compartido por las pruebas."""
    return _crear_lote()


@pytest.fixture
def tipo_operacion(tipo_operacion_factory):
    """Devuelve un ``TipoOperacion`` persistido y compartido por las pruebas."""
    return tipo_operacion_factory()


@pytest.fixture
def movimiento_bancario(cuenta_bancaria, lote_importacion, tipo_operacion):
    """Devuelve un ``MovimientoBancario`` persistido y sin conciliar."""
    return _crear_movimiento_bancario(
        cuenta_bancaria, lote_importacion, tipo_operacion, cuenta_bancaria.moneda
    )


@pytest.fixture
def movimiento_interno(cuenta_bancaria, lote_importacion, tipo_operacion):
    """Devuelve un ``MovimientoInterno`` persistido y sin conciliar."""
    return _crear_movimiento_interno(
        lote_importacion, tipo_operacion, cuenta_bancaria.moneda
    )


@pytest.fixture
def conciliacion_balanceada(cuenta_bancaria, tipo_operacion_factory):
    """Devuelve una ``Conciliacion`` borrador con un par emparejado y equilibrado."""
    moneda = cuenta_bancaria.moneda
    tipo_operacion = tipo_operacion_factory()
    lote_importacion = _crear_lote()
    bancario = _crear_movimiento_bancario(
        cuenta_bancaria, lote_importacion, tipo_operacion, moneda, importe=Decimal("100.00")
    )
    interno = _crear_movimiento_interno(
        lote_importacion, tipo_operacion, moneda, importe=Decimal("100.00")
    )
    conciliacion = _crear_conciliacion(cuenta_bancaria)
    DetalleConciliacionBancaria.objects.create(
        conciliacion=conciliacion, movimiento_bancario=bancario
    )
    DetalleConciliacionInterna.objects.create(
        conciliacion=conciliacion, movimiento_interno=interno
    )
    return conciliacion


@pytest.fixture
def conciliacion_desequilibrada(cuenta_bancaria, tipo_operacion_factory):
    """Devuelve una ``Conciliacion`` borrador cuyos importes no suman cero."""
    moneda = cuenta_bancaria.moneda
    tipo_operacion = tipo_operacion_factory()
    lote_importacion = _crear_lote()
    bancario = _crear_movimiento_bancario(
        cuenta_bancaria, lote_importacion, tipo_operacion, moneda, importe=Decimal("100.00")
    )
    interno = _crear_movimiento_interno(
        lote_importacion, tipo_operacion, moneda, importe=Decimal("80.00")
    )
    conciliacion = _crear_conciliacion(cuenta_bancaria)
    DetalleConciliacionBancaria.objects.create(
        conciliacion=conciliacion, movimiento_bancario=bancario
    )
    DetalleConciliacionInterna.objects.create(
        conciliacion=conciliacion, movimiento_interno=interno
    )
    return conciliacion


@pytest.fixture
def conciliacion_comprometida(cuenta_bancaria):
    """Devuelve una ``Conciliacion`` persistida en estado ``committed``."""
    return _crear_conciliacion(cuenta_bancaria, estado=Conciliacion.ESTADO_COMPROMETIDA)


# ---------------------------------------------------------------------------
# Vista de tablero / pantalla dividida
# ---------------------------------------------------------------------------


class TestVistaTablero:
    """Pruebas de la vista de tablero / pantalla dividida (split-screen)."""

    @pytest.mark.django_db
    def test_tablero_devuelve_200(self, client):
        """Una petición GET al tablero responde con código 200."""
        respuesta = client.get(reverse(NOMBRE_URL_TABLERO))
        assert respuesta.status_code == 200

    @pytest.mark.django_db
    def test_tablero_usa_la_plantilla_matcher(self, client):
        """El tablero renderiza la plantilla de emparejamiento a pantalla dividida."""
        respuesta = client.get(reverse(NOMBRE_URL_TABLERO))
        nombres_plantillas = [plantilla.name for plantilla in respuesta.templates]
        assert PLANTILLA_TABLERO in nombres_plantillas

    @pytest.mark.django_db
    def test_tablero_expone_conteo_extractos_pendientes(self, client):
        """El tablero expone el conteo de extractos pendientes (motor nuevo)."""
        respuesta = client.get(reverse(NOMBRE_URL_TABLERO))
        assert respuesta.context["extractos_pendientes"] == 0

    @pytest.mark.django_db
    def test_tablero_expone_conteo_libros_pendientes(self, client):
        """El tablero expone el conteo de libros pendientes (motor nuevo)."""
        respuesta = client.get(reverse(NOMBRE_URL_TABLERO))
        assert respuesta.context["libros_pendientes"] == 0

    @pytest.mark.django_db
    def test_tablero_muestra_kpis_del_motor_nuevo(self, client):
        """El dashboard renderiza las etiquetas de extracto y libro pendientes."""
        respuesta = client.get(reverse(NOMBRE_URL_TABLERO))
        contenido = respuesta.content.decode("utf-8")
        assert "Extractos Pendientes" in contenido
        assert "Libros Pendientes" in contenido


# ---------------------------------------------------------------------------
# Vista de reporte de verificación manual (impresión)
# ---------------------------------------------------------------------------


class TestVistaReporteManual:
    """Pruebas de la vista del reporte de verificación manual (impresión)."""

    @pytest.mark.django_db
    def test_reporte_manual_devuelve_200(self, client):
        """Una petición GET al reporte manual responde con código 200."""
        respuesta = client.get(reverse(NOMBRE_URL_REPORTE_MANUAL))
        assert respuesta.status_code == 200

    @pytest.mark.django_db
    def test_reporte_manual_usa_plantilla_de_impresion(self, client):
        """El reporte manual renderiza su plantilla específica de impresión."""
        respuesta = client.get(reverse(NOMBRE_URL_REPORTE_MANUAL))
        nombres_plantillas = [plantilla.name for plantilla in respuesta.templates]
        assert PLANTILLA_REPORTE_MANUAL in nombres_plantillas


# ---------------------------------------------------------------------------
# Endpoints de acción (POST) que delegan en ``services.py``
# ---------------------------------------------------------------------------


class TestEndpointEmparejarMovimientos:
    """Pruebas del endpoint POST que delega en ``match_movimientos``."""

    @pytest.mark.django_db
    def test_post_empareja_movimientos_y_redirige(self, client, movimiento_bancario, movimiento_interno):
        """Un POST con importes coincidentes empareja los movimientos y redirige (302)."""
        respuesta = client.post(
            reverse(NOMBRE_URL_EMPAREJAR),
            {
                "bancario_id": movimiento_bancario.pk,
                "interno_id": movimiento_interno.pk,
            },
        )
        assert respuesta.status_code == 302

    @pytest.mark.django_db
    def test_post_con_importes_distintos_devuelve_400(self, client, movimiento_bancario, movimiento_interno):
        """Un desajuste de importes se traduce en un error 400 (sin lógica en la vista)."""
        movimiento_interno.importe = Decimal("80.00")
        movimiento_interno.save(update_fields=["importe"])
        respuesta = client.post(
            reverse(NOMBRE_URL_EMPAREJAR),
            {
                "bancario_id": movimiento_bancario.pk,
                "interno_id": movimiento_interno.pk,
            },
        )
        assert respuesta.status_code == 400


class TestEndpointComprometerConciliacion:
    """Pruebas del endpoint POST que delega en ``commit_reconciliation``."""

    @pytest.mark.django_db
    def test_post_compromete_conciliacion_balanceada_y_redirige(self, client, conciliacion_balanceada):
        """Un POST sobre una conciliación balanceada redirige (302)."""
        respuesta = client.post(
            reverse(NOMBRE_URL_COMPROMETER),
            {"conciliacion_id": conciliacion_balanceada.pk},
        )
        assert respuesta.status_code == 302

    @pytest.mark.django_db
    def test_post_conciliacion_desequilibrada_devuelve_400(self, client, conciliacion_desequilibrada):
        """Una ecuación de suma cero rota se traduce en un error 400."""
        respuesta = client.post(
            reverse(NOMBRE_URL_COMPROMETER),
            {"conciliacion_id": conciliacion_desequilibrada.pk},
        )
        assert respuesta.status_code == 400


class TestEndpointRevertirConciliacion:
    """Pruebas del endpoint POST que delega en ``revert_conciliacion``."""

    @pytest.mark.django_db
    def test_post_revierte_conciliacion_comprometida_y_redirige(self, client, conciliacion_comprometida):
        """Un POST sobre una conciliación comprometida la revierte y redirige (302)."""
        respuesta = client.post(
            reverse(NOMBRE_URL_REVERTIR),
            {"conciliacion_id": conciliacion_comprometida.pk},
        )
        assert respuesta.status_code == 302
