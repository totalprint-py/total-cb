"""Pruebas unitarias de la vista del Reporte del Libro Bancario (Fase 3 — RED).

Cubren el adaptador HTTP ``reporte_libro`` (US1 — HTML MVP) definido en
``specs/003-reportes-libro-bancario/contracts/http-api.md``:

* GET sin parámetros → 200 con formulario vacío (``reporte=None``).
* GET con ``cuenta`` + ``desde`` + ``hasta`` válidos → 200 con un
  ``ReporteLibro`` en contexto y los movimientos filtrados/ordenados.
* ``cuenta`` inexistente o no numérica → 404 (``get_object_or_404``).
* ``desde > hasta`` o fecha malformada → 200 re-renderizando el formulario con
  error en línea y ``reporte=None``.
* método no GET → 405.

Estado esperado al escribir estas pruebas: la URL ``reporte_libro`` y la vista
no existen todavía, por lo que ``reverse(...)`` lanza ``NoReverseMatch`` y todas
las pruebas fallan en rojo (RED).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from conciliacion.models import CuentaBancaria, MovimientoLibro
from conciliacion.reportes import ReporteLibro

NOMBRE_URL = "reporte_libro"
NOMBRE_URL_CSV = "reporte_libro_csv"
NOMBRE_URL_EXCEL = "reporte_libro_excel"
NOMBRE_URL_PDF = "reporte_libro_pdf"
DESDE = date(2026, 1, 1)
HASTA = date(2026, 1, 31)


def _crear_cuenta(banco_factory, tipo_cuenta_factory, moneda_factory, **sobrescribir):
    """Crea y persiste una ``CuentaBancaria`` de apoyo con saldo inicial 1000.00."""
    banco = banco_factory()
    tipo_cuenta = tipo_cuenta_factory()
    moneda = moneda_factory()
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


def _crear_movimiento(cuenta, tipo_operacion, fecha, **sobrescribir):
    """Crea y persiste un ``MovimientoLibro`` de apoyo."""
    valores = {
        "cuenta": cuenta,
        "fecha": fecha,
        "tipo_operacion": tipo_operacion,
        "detalle": "Movimiento de prueba",
        "debe": Decimal("0.00"),
        "haber": Decimal("0.00"),
    }
    valores.update(sobrescribir)
    return MovimientoLibro.objects.create(**valores)


@pytest.fixture
def cuenta(banco_factory, tipo_cuenta_factory, moneda_factory):
    """Devuelve una ``CuentaBancaria`` persistida sin movimientos."""
    return _crear_cuenta(banco_factory, tipo_cuenta_factory, moneda_factory)


@pytest.fixture
def cuenta_con_movimientos(cuenta, tipo_operacion_factory):
    """Cuenta con tres movimientos cronológicos (para verificar filtro y orden).

    Cronología (saldo corrido calculado por ``MovimientoLibro.save``):

    * 2026-01-05  debe 100.00  → saldo 1100.00
    * 2026-01-10  haber 50.00  → saldo 1050.00
    * 2026-02-02  debe 200.00  → saldo 1250.00
    """
    tipo = tipo_operacion_factory()
    _crear_movimiento(
        cuenta,
        tipo,
        date(2026, 1, 5),
        detalle="Depósito de apertura",
        debe=Decimal("100.00"),
    )
    _crear_movimiento(
        cuenta,
        tipo,
        date(2026, 1, 10),
        detalle="Pago de proveedor",
        haber=Decimal("50.00"),
    )
    _crear_movimiento(
        cuenta,
        tipo,
        date(2026, 2, 2),
        detalle="Depósito mensual",
        debe=Decimal("200.00"),
    )
    return cuenta


class TestReporteLibroGet:
    """Pruebas de la vista ``reporte_libro`` (GET)."""

    @pytest.mark.django_db
    def test_get_sin_parametros_muestra_formulario_vacio(self, client, cuenta):
        """Un GET sin parámetros responde 200 con formulario no vinculado."""
        respuesta = client.get(reverse(NOMBRE_URL))

        assert respuesta.status_code == 200
        contexto = respuesta.context
        for clave in ("form", "reporte", "cuentas"):
            assert clave in contexto
        assert contexto["reporte"] is None
        assert contexto["form"].is_bound is False
        assert "conciliacion/reporte_libro.html" in [
            plantilla.name for plantilla in respuesta.templates
        ]

    @pytest.mark.django_db
    def test_get_rango_valido_devuelve_200_y_reporte(
        self, client, cuenta_con_movimientos
    ):
        """Un rango válido devuelve 200 con un ``ReporteLibro`` en contexto."""
        respuesta = client.get(
            reverse(NOMBRE_URL),
            {
                "cuenta": cuenta_con_movimientos.pk,
                "desde": DESDE.isoformat(),
                "hasta": HASTA.isoformat(),
            },
        )

        assert respuesta.status_code == 200
        reporte = respuesta.context["reporte"]
        assert isinstance(reporte, ReporteLibro)
        assert reporte.cuenta.pk == cuenta_con_movimientos.pk
        assert len(reporte.movimientos) == 2
        assert reporte.saldo_inicial_periodo == Decimal("1000.00")
        assert reporte.total_debe == Decimal("100.00")
        assert reporte.total_haber == Decimal("50.00")
        assert reporte.saldo_final == Decimal("1050.00")

    @pytest.mark.django_db
    def test_get_filtra_rango_inclusivo(self, client, cuenta_con_movimientos):
        """Solo se incluyen los movimientos dentro de ``desde`` y ``hasta``."""
        respuesta = client.get(
            reverse(NOMBRE_URL),
            {
                "cuenta": cuenta_con_movimientos.pk,
                "desde": date(2026, 2, 1).isoformat(),
                "hasta": date(2026, 2, 28).isoformat(),
            },
        )

        reporte = respuesta.context["reporte"]
        assert len(reporte.movimientos) == 1
        assert reporte.movimientos[0].detalle == "Depósito mensual"
        # El saldo inicial del periodo es el saldo del último movimiento previo.
        assert reporte.saldo_inicial_periodo == Decimal("1050.00")

    @pytest.mark.django_db
    def test_get_ordena_por_fecha_e_id(self, client, cuenta_con_movimientos):
        """Los movimientos se devuelven ordenados cronológicamente."""
        respuesta = client.get(
            reverse(NOMBRE_URL),
            {
                "cuenta": cuenta_con_movimientos.pk,
                "desde": DESDE.isoformat(),
                "hasta": HASTA.isoformat(),
            },
        )

        detalles = [m.detalle for m in respuesta.context["reporte"].movimientos]
        assert detalles == ["Depósito de apertura", "Pago de proveedor"]

    @pytest.mark.django_db
    def test_get_cuenta_inexistente_devuelve_404(self, client):
        """Una ``cuenta`` que no existe responde 404."""
        respuesta = client.get(
            reverse(NOMBRE_URL),
            {
                "cuenta": 999999,
                "desde": DESDE.isoformat(),
                "hasta": HASTA.isoformat(),
            },
        )

        assert respuesta.status_code == 404

    @pytest.mark.django_db
    def test_get_cuenta_no_numerica_devuelve_404(self, client, cuenta):
        """Una ``cuenta`` con valor no numérico responde 404."""
        respuesta = client.get(
            reverse(NOMBRE_URL),
            {
                "cuenta": "no-numerica",
                "desde": DESDE.isoformat(),
                "hasta": HASTA.isoformat(),
            },
        )

        assert respuesta.status_code == 404

    @pytest.mark.django_db
    def test_get_desde_mayor_que_hasta_rerenderiza_con_error(
        self, client, cuenta_con_movimientos
    ):
        """Un rango invertido re-renderiza (200) con error y sin reporte."""
        respuesta = client.get(
            reverse(NOMBRE_URL),
            {
                "cuenta": cuenta_con_movimientos.pk,
                "desde": HASTA.isoformat(),
                "hasta": DESDE.isoformat(),
            },
        )

        assert respuesta.status_code == 200
        assert respuesta.context["reporte"] is None
        assert respuesta.context["form"].errors

    @pytest.mark.django_db
    def test_get_fecha_invalida_rerenderiza_con_error(
        self, client, cuenta_con_movimientos
    ):
        """Una fecha malformada re-renderiza (200) con error y sin reporte."""
        respuesta = client.get(
            reverse(NOMBRE_URL),
            {
                "cuenta": cuenta_con_movimientos.pk,
                "desde": "2026-13-40",
                "hasta": HASTA.isoformat(),
            },
        )

        assert respuesta.status_code == 200
        assert respuesta.context["reporte"] is None
        assert respuesta.context["form"].errors


class TestReporteLibroMetodo:
    """Pruebas de rechazo de métodos no permitidos."""

    @pytest.mark.django_db
    def test_post_devuelve_405(self, client, cuenta):
        """Un POST a la vista del reporte responde 405."""
        respuesta = client.post(reverse(NOMBRE_URL))

        assert respuesta.status_code == 405


class TestReporteLibroExportacion:
    """Pruebas de las vistas de exportación CSV/XLSX (US2 — Fase 4)."""

    MIME_CSV = "text/csv; charset=utf-8"
    MIME_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    MIME_PDF = "application/pdf"

    @pytest.mark.django_db
    def test_csv_200_headers_y_nombre(self, client, cuenta_con_movimientos):
        """El CSV responde 200 con MIME, disposición de descarga y BOM UTF-8."""
        respuesta = client.get(
            reverse(NOMBRE_URL_CSV),
            {
                "cuenta": cuenta_con_movimientos.pk,
                "desde": DESDE.isoformat(),
                "hasta": HASTA.isoformat(),
            },
        )

        assert respuesta.status_code == 200
        assert respuesta["Content-Type"].startswith("text/csv")
        assert "utf-8" in respuesta["Content-Type"]
        disposicion = respuesta["Content-Disposition"]
        assert disposicion.startswith("attachment")
        nombre = "reporte_libro_%d_%s_%s.csv" % (
            cuenta_con_movimientos.pk,
            DESDE.isoformat(),
            HASTA.isoformat(),
        )
        assert nombre in disposicion
        assert respuesta.content.startswith(b"\xef\xbb\xbf")  # BOM UTF-8

    @pytest.mark.django_db
    def test_excel_200_headers_y_nombre(self, client, cuenta_con_movimientos):
        """El Excel responde 200 con MIME XLSX y disposición de descarga."""
        respuesta = client.get(
            reverse(NOMBRE_URL_EXCEL),
            {
                "cuenta": cuenta_con_movimientos.pk,
                "desde": DESDE.isoformat(),
                "hasta": HASTA.isoformat(),
            },
        )

        assert respuesta.status_code == 200
        assert respuesta["Content-Type"].startswith(self.MIME_XLSX)
        disposicion = respuesta["Content-Disposition"]
        assert disposicion.startswith("attachment")
        assert ".xlsx" in disposicion
        assert respuesta.content[:2] == b"PK"

    @pytest.mark.django_db
    def test_csv_cuenta_inexistente_404(self, client):
        """Una ``cuenta`` inexistente responde 404 en el CSV."""
        respuesta = client.get(
            reverse(NOMBRE_URL_CSV),
            {"cuenta": 999999, "desde": DESDE.isoformat(), "hasta": HASTA.isoformat()},
        )

        assert respuesta.status_code == 404

    @pytest.mark.django_db
    def test_excel_cuenta_no_numerica_404(self, client):
        """Una ``cuenta`` no numérica responde 404 en el Excel."""
        respuesta = client.get(
            reverse(NOMBRE_URL_EXCEL),
            {"cuenta": "abc", "desde": DESDE.isoformat(), "hasta": HASTA.isoformat()},
        )

        assert respuesta.status_code == 404

    @pytest.mark.django_db
    def test_csv_rango_invalido_400(self, client, cuenta_con_movimientos):
        """Un rango invertido responde 400 en el CSV, sin cuerpo útil."""
        respuesta = client.get(
            reverse(NOMBRE_URL_CSV),
            {
                "cuenta": cuenta_con_movimientos.pk,
                "desde": HASTA.isoformat(),
                "hasta": DESDE.isoformat(),
            },
        )

        assert respuesta.status_code == 400

    @pytest.mark.django_db
    def test_excel_fecha_invalida_400(self, client, cuenta_con_movimientos):
        """Una fecha malformada responde 400 en el Excel."""
        respuesta = client.get(
            reverse(NOMBRE_URL_EXCEL),
            {
                "cuenta": cuenta_con_movimientos.pk,
                "desde": "2026-13-40",
                "hasta": HASTA.isoformat(),
            },
        )

        assert respuesta.status_code == 400

    @pytest.mark.django_db
    def test_csv_post_405(self, client):
        """Un POST a la vista CSV responde 405."""
        respuesta = client.post(reverse(NOMBRE_URL_CSV))

        assert respuesta.status_code == 405

    @pytest.mark.django_db
    def test_excel_post_405(self, client):
        """Un POST a la vista Excel responde 405."""
        respuesta = client.post(reverse(NOMBRE_URL_EXCEL))

        assert respuesta.status_code == 405

    @pytest.mark.django_db
    def test_pdf_200_headers_y_nombre(self, client, cuenta_con_movimientos):
        """El PDF responde 200 con MIME application/pdf y disposición de descarga."""
        respuesta = client.get(
            reverse(NOMBRE_URL_PDF),
            {
                "cuenta": cuenta_con_movimientos.pk,
                "desde": DESDE.isoformat(),
                "hasta": HASTA.isoformat(),
            },
        )

        assert respuesta.status_code == 200
        assert respuesta["Content-Type"].startswith(self.MIME_PDF)
        disposicion = respuesta["Content-Disposition"]
        assert disposicion.startswith("attachment")
        nombre = "reporte_libro_%d_%s_%s.pdf" % (
            cuenta_con_movimientos.pk,
            DESDE.isoformat(),
            HASTA.isoformat(),
        )
        assert nombre in disposicion
        assert respuesta.content.startswith(b"%PDF-")

    @pytest.mark.django_db
    def test_pdf_cuenta_inexistente_404(self, client):
        """Una ``cuenta`` inexistente responde 404 en el PDF."""
        respuesta = client.get(
            reverse(NOMBRE_URL_PDF),
            {"cuenta": 999999, "desde": DESDE.isoformat(), "hasta": HASTA.isoformat()},
        )

        assert respuesta.status_code == 404

    @pytest.mark.django_db
    def test_pdf_rango_invalido_400(self, client, cuenta_con_movimientos):
        """Un rango invertido responde 400 en el PDF, sin cuerpo útil."""
        respuesta = client.get(
            reverse(NOMBRE_URL_PDF),
            {
                "cuenta": cuenta_con_movimientos.pk,
                "desde": HASTA.isoformat(),
                "hasta": DESDE.isoformat(),
            },
        )

        assert respuesta.status_code == 400

    @pytest.mark.django_db
    def test_pdf_post_405(self, client):
        """Un POST a la vista PDF responde 405."""
        respuesta = client.post(reverse(NOMBRE_URL_PDF))

        assert respuesta.status_code == 405
