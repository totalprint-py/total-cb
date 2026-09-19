"""Pruebas unitarias de las vistas del Libro Bancario (Fase 4 — RED).

Cubren los adaptadores HTTP delgados que deben implementarse en
``conciliacion/views.py`` y enrutarse en ``conciliacion/urls.py``:

* ``libro_bancario`` (GET): Maestro-Detalle — lista de cuentas, cuenta
  seleccionada, movimientos ordenados, formulario y ``saldo_inicial``.
* ``libro_bancario_crear`` (POST): registra un movimiento y delega el cálculo
  del saldo en el motor del modelo.
* ``libro_bancario_recalcular`` (POST): reconstruye los saldos corridos.

Estado esperado al escribir estas pruebas: las URLs no existen aún, por lo que
``reverse(...)`` lanza ``NoReverseMatch`` y todas las pruebas fallan en rojo
(RED). Todas las descripciones y los nombres están en español.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from conciliacion.models import CuentaBancaria, MovimientoLibro

FECHA = date(2026, 9, 5)

NOMBRE_URL_LIBRO = "libro_bancario"
NOMBRE_URL_CREAR = "libro_bancario_crear"
NOMBRE_URL_RECALCULAR = "libro_bancario_recalcular"
NOMBRE_URL_EDITAR = "movimientolibro_update"


def _crear_cuenta_bancaria(banco, tipo_cuenta, moneda, **sobrescribir):
    """Crea y persiste una ``CuentaBancaria`` de apoyo."""
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


@pytest.fixture
def banco(banco_factory):
    """Devuelve un ``Banco`` persistido."""
    return banco_factory()


@pytest.fixture
def tipo_cuenta(tipo_cuenta_factory):
    """Devuelve un ``TipoCuenta`` persistido."""
    return tipo_cuenta_factory()


@pytest.fixture
def moneda(moneda_factory):
    """Devuelve una ``Moneda`` persistida."""
    return moneda_factory()


@pytest.fixture
def cuenta(banco, tipo_cuenta, moneda):
    """Devuelve una ``CuentaBancaria`` persistida con ``saldo_inicial=1000.00``."""
    return _crear_cuenta_bancaria(banco, tipo_cuenta, moneda)


@pytest.fixture
def tipo_operacion(tipo_operacion_factory):
    """Devuelve un ``TipoOperacion`` persistido."""
    return tipo_operacion_factory()


# ---------------------------------------------------------------------------
# GET: Maestro-Detalle del libro bancario
# ---------------------------------------------------------------------------


class TestLibroBancarioGet:
    """Pruebas de la vista ``libro_bancario`` (GET)."""

    @pytest.mark.django_db
    def test_get_devuelve_200(self, client, cuenta):
        """Un GET al libro bancario responde con código 200."""
        respuesta = client.get(reverse(NOMBRE_URL_LIBRO))
        assert respuesta.status_code == 200

    @pytest.mark.django_db
    def test_contexto_contiene_claves_requeridas(self, client, cuenta):
        """El contexto expone ``cuentas``, ``cuenta``, ``movimientos``, ``form`` y ``saldo_inicial``."""
        respuesta = client.get(reverse(NOMBRE_URL_LIBRO))
        contexto = respuesta.context
        for clave in ("cuentas", "cuenta", "movimientos", "form", "saldo_inicial"):
            assert clave in contexto

    @pytest.mark.django_db
    def test_selecciona_cuenta_por_query_param(self, client, cuenta, banco, tipo_cuenta, moneda):
        """Un ``?cuenta=<id>`` selecciona la cuenta indicada."""
        otra = _crear_cuenta_bancaria(
            banco, tipo_cuenta, moneda,
            numero_cuenta="9999-0000-1111",
            denominacion="Cuenta Secundaria",
        )
        respuesta = client.get(reverse(NOMBRE_URL_LIBRO), {"cuenta": otra.pk})
        assert respuesta.context["cuenta"].pk == otra.pk

    @pytest.mark.django_db
    def test_movimientos_ordenados_por_fecha_id(self, client, cuenta, tipo_operacion):
        """Los movimientos se devuelven en orden cronológico (fecha, id)."""
        _crear_movimiento(cuenta, tipo_operacion, fecha=date(2026, 9, 6), debe=Decimal("200.00"))
        _crear_movimiento(cuenta, tipo_operacion, fecha=date(2026, 9, 5), debe=Decimal("100.00"))
        respuesta = client.get(reverse(NOMBRE_URL_LIBRO), {"cuenta": cuenta.pk})
        movimientos = list(respuesta.context["movimientos"])
        assert [m.fecha for m in movimientos] == [date(2026, 9, 5), date(2026, 9, 6)]

    @pytest.mark.django_db
    def test_saldo_inicial_del_contexto(self, client, cuenta):
        """El contexto expone el ``saldo_inicial`` de la cuenta seleccionada."""
        respuesta = client.get(reverse(NOMBRE_URL_LIBRO), {"cuenta": cuenta.pk})
        assert respuesta.context["saldo_inicial"] == Decimal("1000.00")

    @pytest.mark.django_db
    def test_sin_cuentas_muestra_estado_vacio(self, client):
        """Sin cuentas, el contexto expone ``cuenta=None`` y ``movimientos`` vacíos."""
        respuesta = client.get(reverse(NOMBRE_URL_LIBRO))
        contexto = respuesta.context
        assert list(contexto["cuentas"]) == []
        assert contexto["cuenta"] is None
        assert list(contexto["movimientos"]) == []
        assert "form" in contexto


# ---------------------------------------------------------------------------
# POST: alta de un movimiento del libro
# ---------------------------------------------------------------------------


class TestLibroBancarioCrear:
    """Pruebas de la vista ``libro_bancario_crear`` (POST)."""

    @pytest.mark.django_db
    def test_post_crea_movimiento_y_calcula_saldo(self, client, cuenta, tipo_operacion):
        """Un POST válido persiste el movimiento con el saldo corrido y redirige (302)."""
        respuesta = client.post(
            reverse(NOMBRE_URL_CREAR),
            {
                "cuenta": cuenta.pk,
                "fecha": FECHA.isoformat(),
                "tipo_operacion": tipo_operacion.pk,
                "detalle": "Depósito bancario",
                "debe": "250.00",
                "haber": "0.00",
            },
        )
        assert respuesta.status_code == 302
        assert respuesta.url == f"/libro-bancario/?cuenta={cuenta.pk}"
        movimiento = MovimientoLibro.objects.get(cuenta=cuenta)
        assert movimiento.saldo == Decimal("1250.00")

    @pytest.mark.django_db
    def test_post_formulario_invalido_rerenderiza_con_errores(self, client, cuenta, tipo_operacion):
        """Un POST inválido re-renderiza (200) con el contexto completo y errores en línea."""
        respuesta = client.post(
            reverse(NOMBRE_URL_CREAR),
            {
                "cuenta": cuenta.pk,
                "fecha": FECHA.isoformat(),
                "tipo_operacion": tipo_operacion.pk,
                "detalle": "Depósito inválido",
                "debe": "-10.00",
                "haber": "0.00",
            },
        )
        assert respuesta.status_code == 200
        contexto = respuesta.context
        for clave in ("cuentas", "cuenta", "movimientos", "form", "saldo_inicial"):
            assert clave in contexto
        assert contexto["cuenta"].pk == cuenta.pk
        assert contexto["form"].errors

    @pytest.mark.django_db
    def test_get_crear_devuelve_405(self, client):
        """Un GET al endpoint de alta responde con 405 (solo POST)."""
        respuesta = client.get(reverse(NOMBRE_URL_CREAR))
        assert respuesta.status_code == 405


# ---------------------------------------------------------------------------
# POST: recálculo de saldos corridos
# ---------------------------------------------------------------------------


class TestLibroBancarioRecalcular:
    """Pruebas de la vista ``libro_bancario_recalcular`` (POST)."""

    @pytest.mark.django_db
    def test_post_recalcula_saldos_y_redirige(self, client, cuenta, tipo_operacion):
        """Un POST reconstruye los saldos corruptos y redirige (302)."""
        primero = _crear_movimiento(
            cuenta, tipo_operacion, fecha=FECHA, debe=Decimal("100.00")
        )
        segundo = _crear_movimiento(
            cuenta, tipo_operacion, fecha=date(2026, 9, 6), debe=Decimal("200.00")
        )
        MovimientoLibro.objects.filter(
            pk__in=[primero.pk, segundo.pk]
        ).update(saldo=Decimal("9999.99"))

        respuesta = client.post(
            reverse(NOMBRE_URL_RECALCULAR), {"cuenta": cuenta.pk}
        )
        assert respuesta.status_code == 302
        primero.refresh_from_db()
        segundo.refresh_from_db()
        assert primero.saldo == Decimal("1100.00")
        assert segundo.saldo == Decimal("1300.00")

    @pytest.mark.django_db
    def test_post_cuenta_inexistente_devuelve_404(self, client):
        """Un POST con cuenta inexistente responde con 404."""
        respuesta = client.post(
            reverse(NOMBRE_URL_RECALCULAR), {"cuenta": 999999}
        )
        assert respuesta.status_code == 404

    @pytest.mark.django_db
    def test_get_recalcular_devuelve_405(self, client):
        """Un GET al endpoint de recálculo responde con 405 (solo POST)."""
        respuesta = client.get(reverse(NOMBRE_URL_RECALCULAR))
        assert respuesta.status_code == 405


class TestLibroBancarioEditar:
    """Pruebas de la vista ``movimientolibro_update`` para editar movimientos."""

    @pytest.mark.django_db
    def test_get_editar_devuelve_200_y_carga_el_formulario(
        self, client, cuenta, tipo_operacion
    ):
        """Un GET carga la plantilla de edición con el movimiento a editar."""
        movimiento = _crear_movimiento(
            cuenta, tipo_operacion, haber=Decimal("50.00")
        )
        respuesta = client.get(reverse(NOMBRE_URL_EDITAR, args=[movimiento.pk]))

        assert respuesta.status_code == 200
        nombres = [plantilla.name for plantilla in respuesta.templates]
        assert "conciliacion/movimiento_libro_form.html" in nombres
        assert respuesta.context["form"].instance.pk == movimiento.pk

    @pytest.mark.django_db
    def test_post_editar_cambia_haber_y_recalcula_saldos(
        self, client, cuenta, tipo_operacion
    ):
        """Editar el primer movimiento recalcula su saldo y el de los siguientes."""
        primero = _crear_movimiento(
            cuenta, tipo_operacion, haber=Decimal("50.00")
        )
        segundo = _crear_movimiento(
            cuenta,
            tipo_operacion,
            fecha=date(2026, 9, 6),
            debe=Decimal("100.00"),
        )

        respuesta = client.post(
            reverse(NOMBRE_URL_EDITAR, args=[primero.pk]),
            {
                "fecha": FECHA.isoformat(),
                "tipo_operacion": tipo_operacion.pk,
                "detalle": primero.detalle,
                "debe": "0.00",
                "haber": "150.00",
            },
        )

        assert respuesta.status_code == 302
        assert respuesta.url == f"{reverse('libro_bancario')}?cuenta={cuenta.pk}"
        primero.refresh_from_db()
        segundo.refresh_from_db()
        assert primero.haber == Decimal("150.00")
        assert primero.saldo == Decimal("850.00")  # 1000 - 150
        assert segundo.saldo == Decimal("950.00")  # 850 + 100

    @pytest.mark.django_db
    def test_post_editar_formulario_invalido_rerenderiza_con_errores(
        self, client, cuenta, tipo_operacion
    ):
        """Un POST inválido re-renderiza (200) con errores y sin guardar cambios."""
        movimiento = _crear_movimiento(
            cuenta, tipo_operacion, haber=Decimal("50.00")
        )
        respuesta = client.post(
            reverse(NOMBRE_URL_EDITAR, args=[movimiento.pk]),
            {
                "fecha": FECHA.isoformat(),
                "tipo_operacion": tipo_operacion.pk,
                "detalle": "Detalle sin importe",
                "debe": "0.00",
                "haber": "0.00",
            },
        )

        assert respuesta.status_code == 200
        assert respuesta.context["form"].errors
        movimiento.refresh_from_db()
        # El importe original no se modificó al fallar la validación.
        assert movimiento.haber == Decimal("50.00")


# ---------------------------------------------------------------------------
# Fábrica de movimientos de apoyo (no es objeto de prueba)
# ---------------------------------------------------------------------------


def _crear_movimiento(cuenta, tipo_operacion, **sobrescribir):
    """Crea y persiste un ``MovimientoLibro`` de apoyo."""
    valores = {
        "cuenta": cuenta,
        "fecha": FECHA,
        "tipo_operacion": tipo_operacion,
        "detalle": "Movimiento de prueba",
        "debe": Decimal("0.00"),
        "haber": Decimal("0.00"),
    }
    valores.update(sobrescribir)
    return MovimientoLibro.objects.create(**valores)



