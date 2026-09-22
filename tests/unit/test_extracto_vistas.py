"""Pruebas unitarias de las vistas de importación y CRUD del extracto bancario
(Fase 3 — RED; User Story 1).

Cubre el contrato ``specs/004-conciliacion-bancaria/contracts/http-api.md`` y la
historia US1 para los adaptadores HTTP delgados que deben implementarse en
``conciliacion/views.py`` y enrutarse en ``conciliacion/urls.py``:

* ``extracto_importar`` (GET/POST): carga ``.xlsx``/``.csv`` todo-o-nada (cualquier
  fila inválida revierte la transacción y re-renderiza el formulario con los
  errores por fila en español); un lote válido redirige (302) y persiste
  exactamente las filas esperadas con ``origen="importacion"``.
* CRUD manual: ``extracto_list``, ``extracto_create``, ``extracto_update`` y
  ``extracto_delete``; un extracto ya ``conciliado`` queda bloqueado (400) tanto
  para edición como para eliminación.

Estado esperado al escribir estas pruebas: las vistas todavía no existen en
``conciliacion/views.py``, por lo que la importación de los callables falla y la
colección reporta un ``ImportError`` (RED válido).

Convenciones asumidas (contrato que la implementación GREEN debe cumplir):

* Nombres de URL: ``extracto_list``, ``extracto_create``, ``extracto_update``,
  ``extracto_delete`` y ``extracto_importar`` (sin ``app_name``).
* Ruta del listado ``/extracto/`` con filtro opcional ``?cuenta=<pk>``.
* ``extracto_importar`` recibe multipart con ``cuenta`` (pk) + ``archivo``; al
  fallar re-renderiza con la clave de contexto ``errores`` (lista de cadenas por
  fila en español) sin persistir ninguna fila; al tener éxito redirige (302) a
  ``extracto_list``.
* Los formularios de alta/edición exponen ``cuenta_bancaria``, ``fecha``,
  ``referencia``, ``detalle`` e ``importe``.
* ``extracto_list`` entrega ``movimientos`` y los desgloses ``pendientes`` y
  ``conciliados`` en el contexto.
* El bloqueo de un ``conciliado`` responde 400 con el mensaje
  ``"El movimiento conciliado no puede editarse ni eliminarse."``.
"""
from __future__ import annotations

import csv
from datetime import date
from decimal import Decimal
from io import BytesIO, StringIO

import openpyxl
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from conciliacion.models import CuentaBancaria, MovimientoExtracto, MovimientoLibro, Punteo
from conciliacion.punteo import puntear as puntear_servicio
from conciliacion.views import (
    crear_asiento_extracto,
    despuntear,
    extracto_create,
    extracto_delete,
    extracto_importar,
    extracto_list,
    extracto_update,
    puntear,
    punteo,
)

# ---------------------------------------------------------------------------
# Constantes de apoyo (contrato HTTP).
# ---------------------------------------------------------------------------

NOMBRE_URL_LIST = "extracto_list"
NOMBRE_URL_CREATE = "extracto_create"
NOMBRE_URL_UPDATE = "extracto_update"
NOMBRE_URL_DELETE = "extracto_delete"
NOMBRE_URL_IMPORTAR = "extracto_importar"
NOMBRE_URL_CREAR_ASIENTO = "crear_asiento_extracto"

PLANTILLA_LIST = "conciliacion/extracto_list.html"
PLANTILLA_FORM = "conciliacion/extracto_form.html"
PLANTILLA_IMPORTAR = "conciliacion/extracto_importar.html"

MENSAJE_BLOQUEO = "El movimiento conciliado no puede editarse ni eliminarse."


# ---------------------------------------------------------------------------
# Factorías de archivo de apoyo (CSV / XLSX) para el endpoint de importación.
# ---------------------------------------------------------------------------


def _csv_contenido(cabecera, *filas) -> str:
    """Serializa una cabecera y filas a un CSV UTF-8 en memoria."""
    salida = StringIO()
    escritor = csv.writer(salida)
    escritor.writerow(cabecera)
    for fila in filas:
        escritor.writerow(fila)
    return salida.getvalue()


def _csv_archivo(cabecera, *filas) -> SimpleUploadedFile:
    """Construye un ``SimpleUploadedFile`` CSV listo para ``client.post``."""
    return SimpleUploadedFile(
        "extracto.csv",
        _csv_contenido(cabecera, *filas).encode("utf-8"),
        content_type="text/csv",
    )


def _xlsx_archivo(cabecera, *filas) -> SimpleUploadedFile:
    """Construye un ``SimpleUploadedFile`` XLSX (openpyxl) con celdas nativas."""
    libro = openpyxl.Workbook()
    hoja = libro.active
    hoja.append(cabecera)
    for fila in filas:
        hoja.append(fila)
    salida = BytesIO()
    libro.save(salida)
    return SimpleUploadedFile(
        "extracto.xlsx",
        salida.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


# ---------------------------------------------------------------------------
# Factorías de datos de apoyo.
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Helper factories for MovimientoExtracto rows.
# ---------------------------------------------------------------------------


def _crear_extracto(cuenta_bancaria, **sobrescribir):
    valores = {
        "cuenta_bancaria": cuenta_bancaria,
        "fecha": date(2026, 8, 24),
        "referencia": "REF-1",
        "detalle": "Movimiento manual",
        "importe": Decimal("100.00"),
        "origen": MovimientoExtracto.ORIGEN_MANUAL,
    }
    valores.update(sobrescribir)
    return MovimientoExtracto.objects.create(**valores)


def _crear_libro(cuenta_bancaria, tipo_operacion, **sobrescribir):
    """Crea un ``MovimientoLibro`` con ``debe=100.00`` y ``haber=0.00`` por defecto."""
    valores = {
        "cuenta": cuenta_bancaria,
        "fecha": date(2026, 8, 24),
        "tipo_operacion": tipo_operacion,
        "detalle": "Depósito libro",
        "debe": Decimal("100.00"),
        "haber": Decimal("0.00"),
    }
    valores.update(sobrescribir)
    return MovimientoLibro.objects.create(**valores)


def _datos_formulario(cuenta_bancaria, **sobrescribir):
    datos = {
        "cuenta_bancaria": cuenta_bancaria.pk,
        "fecha": "2026-08-24",
        "referencia": "REF-1",
        "detalle": "Movimiento manual",
        "importe": "100.00",
    }
    datos.update(sobrescribir)
    return datos

# ---------------------------------------------------------------------------
# Importación todo-o-nada (extracto_importar).
# ---------------------------------------------------------------------------


class TestExtractoImportar:
    """POST multipart ``cuenta`` + ``archivo`` — todo-o-nada, errores en español."""

    @pytest.mark.django_db
    def test_import_valido_redirige_y_crea_filas(self, client, cuenta_bancaria):
        archivo = _csv_archivo(
            ["fecha", "referencia", "detalle", "importe"],
            ["2026-08-24", "REF-1", "Depósito BELLINI", "980000"],
            ["2026-08-25", "", "EGRESO COMPRA", "-120200000"],
        )
        respuesta = client.post(
            reverse(NOMBRE_URL_IMPORTAR),
            {"cuenta": cuenta_bancaria.pk, "archivo": archivo},
        )
        assert respuesta.status_code == 302

        filas = list(
            MovimientoExtracto.objects.filter(
                cuenta_bancaria=cuenta_bancaria
            ).order_by("fecha", "id")
        )
        assert len(filas) == 2
        assert all(f.origen == MovimientoExtracto.ORIGEN_IMPORTACION for f in filas)
        assert all(f.cuenta_bancaria_id == cuenta_bancaria.pk for f in filas)
        assert {f.detalle for f in filas} == {"Depósito BELLINI", "EGRESO COMPRA"}
        assert {f.importe for f in filas} == {
            Decimal("980000"),
            Decimal("-120200000"),
        }

    @pytest.mark.django_db
    def test_cabecera_invalida_rerenderiza_y_no_persiste(self, client, cuenta_bancaria):
        archivo = _csv_archivo(
            ["fecha", "referencia", "detalle"],  # falta ``importe``
            ["2026-08-24", "REF-1", "Concepto"],
        )
        respuesta = client.post(
            reverse(NOMBRE_URL_IMPORTAR),
            {"cuenta": cuenta_bancaria.pk, "archivo": archivo},
        )
        assert respuesta.status_code == 200
        assert MovimientoExtracto.objects.filter(
            cuenta_bancaria=cuenta_bancaria
        ).count() == 0

    @pytest.mark.django_db
    def test_archivo_vacio_rerenderiza_y_no_persiste(self, client, cuenta_bancaria):
        archivo = _csv_archivo(["fecha", "referencia", "detalle", "importe"])
        respuesta = client.post(
            reverse(NOMBRE_URL_IMPORTAR),
            {"cuenta": cuenta_bancaria.pk, "archivo": archivo},
        )
        assert respuesta.status_code == 200
        assert MovimientoExtracto.objects.filter(
            cuenta_bancaria=cuenta_bancaria
        ).count() == 0

    @pytest.mark.django_db
    def test_fila_importe_cero_rerenderiza_y_rollback(self, client, cuenta_bancaria):
        archivo = _csv_archivo(
            ["fecha", "referencia", "detalle", "importe"],
            ["2026-08-24", "REF-1", "Válido", "100.00"],
            ["2026-08-25", "", "Inválido cero", "0"],
        )
        respuesta = client.post(
            reverse(NOMBRE_URL_IMPORTAR),
            {"cuenta": cuenta_bancaria.pk, "archivo": archivo},
        )
        assert respuesta.status_code == 200
        assert MovimientoExtracto.objects.filter(
            cuenta_bancaria=cuenta_bancaria
        ).count() == 0

    @pytest.mark.django_db
    def test_fila_float_rerenderiza_y_rollback(self, client, cuenta_bancaria):
        archivo = _xlsx_archivo(
            ["fecha", "referencia", "detalle", "importe"],
            ["2026-08-24", "REF-1", "Válido", "100.00"],
            ["2026-08-25", "", "float nativo", 1234.56],
        )
        respuesta = client.post(
            reverse(NOMBRE_URL_IMPORTAR),
            {"cuenta": cuenta_bancaria.pk, "archivo": archivo},
        )
        assert respuesta.status_code == 200
        assert MovimientoExtracto.objects.filter(
            cuenta_bancaria=cuenta_bancaria
        ).count() == 0

    @pytest.mark.django_db
    def test_fila_fecha_invalida_rerenderiza_y_rollback(self, client, cuenta_bancaria):
        archivo = _csv_archivo(
            ["fecha", "referencia", "detalle", "importe"],
            ["2026-08-24", "REF-1", "Válido", "100.00"],
            ["no-es-una-fecha", "", "Fecha inválida", "50.00"],
        )
        respuesta = client.post(
            reverse(NOMBRE_URL_IMPORTAR),
            {"cuenta": cuenta_bancaria.pk, "archivo": archivo},
        )
        assert respuesta.status_code == 200
        assert MovimientoExtracto.objects.filter(
            cuenta_bancaria=cuenta_bancaria
        ).count() == 0

    @pytest.mark.django_db
    def test_error_rerenderiza_con_errores_en_espanol(self, client, cuenta_bancaria):
        archivo = _csv_archivo(
            ["fecha", "referencia", "detalle", "importe"],
            ["2026-08-25", "", "Inválido cero", "0"],
        )
        respuesta = client.post(
            reverse(NOMBRE_URL_IMPORTAR),
            {"cuenta": cuenta_bancaria.pk, "archivo": archivo},
        )
        assert respuesta.status_code == 200
        errores = respuesta.context["errores"]
        assert isinstance(errores, list)
        assert any("importe cero" in error for error in errores)

    @pytest.mark.django_db
    def test_reimport_no_duplica_filas_existentes(self, client, cuenta_bancaria):
        """Re-importar un archivo con filas ya existentes no crea duplicados."""
        archivo = _csv_archivo(
            ["fecha", "referencia", "detalle", "importe"],
            ["2026-08-24", "REF-1", "Depósito BELLINI", "980000"],
            ["2026-08-25", "", "EGRESO COMPRA", "-120200000"],
        )
        client.post(reverse(NOMBRE_URL_IMPORTAR), {"cuenta": cuenta_bancaria.pk, "archivo": archivo})
        assert MovimientoExtracto.objects.filter(cuenta_bancaria=cuenta_bancaria).count() == 2

        # Re-importar el mismo contenido (archivo nuevo, puntero en cero).
        archivo_repetido = _csv_archivo(
            ["fecha", "referencia", "detalle", "importe"],
            ["2026-08-24", "REF-1", "Depósito BELLINI", "980000"],
            ["2026-08-25", "", "EGRESO COMPRA", "-120200000"],
        )
        respuesta = client.post(
            reverse(NOMBRE_URL_IMPORTAR), {"cuenta": cuenta_bancaria.pk, "archivo": archivo_repetido}
        )
        assert respuesta.status_code == 302
        assert MovimientoExtracto.objects.filter(cuenta_bancaria=cuenta_bancaria).count() == 2

    @pytest.mark.django_db
    def test_import_salta_solo_las_filas_duplicadas(self, client, cuenta_bancaria):
        """Un lote con filas nuevas y repetidas persiste únicamente las nuevas."""
        inicial = _csv_archivo(
            ["fecha", "referencia", "detalle", "importe"],
            ["2026-08-24", "REF-1", "Depósito BELLINI", "980000"],
        )
        client.post(reverse(NOMBRE_URL_IMPORTAR), {"cuenta": cuenta_bancaria.pk, "archivo": inicial})

        mixto = _csv_archivo(
            ["fecha", "referencia", "detalle", "importe"],
            ["2026-08-24", "REF-1", "Depósito BELLINI", "980000"],  # duplicada
            ["2026-08-26", "", "NUEVA OPERACIÓN", "50000"],          # nueva
        )
        respuesta = client.post(
            reverse(NOMBRE_URL_IMPORTAR), {"cuenta": cuenta_bancaria.pk, "archivo": mixto}
        )
        assert respuesta.status_code == 302
        filas = MovimientoExtracto.objects.filter(cuenta_bancaria=cuenta_bancaria)
        assert filas.count() == 2
        assert {f.detalle for f in filas} == {"Depósito BELLINI", "NUEVA OPERACIÓN"}

    @pytest.mark.django_db
    def test_import_dedup_dentro_del_mismo_lote(self, client, cuenta_bancaria):
        """Dos filas idénticas dentro del mismo archivo se importan una sola vez."""
        archivo = _csv_archivo(
            ["fecha", "referencia", "detalle", "importe"],
            ["2026-08-24", "REF-1", "Depósito BELLINI", "980000"],
            ["2026-08-24", "REF-1", "Depósito BELLINI", "980000"],
        )
        respuesta = client.post(
            reverse(NOMBRE_URL_IMPORTAR), {"cuenta": cuenta_bancaria.pk, "archivo": archivo}
        )
        assert respuesta.status_code == 302
        assert MovimientoExtracto.objects.filter(cuenta_bancaria=cuenta_bancaria).count() == 1

    @pytest.mark.django_db
    def test_get_muestra_formulario(self, client, cuenta_bancaria):
        respuesta = client.get(reverse(NOMBRE_URL_IMPORTAR))
        assert respuesta.status_code == 200

# ---------------------------------------------------------------------------
# CRUD manual — extracto_list.
# ---------------------------------------------------------------------------


class TestExtractoList:
    """GET ``/extracto/`` lista los movimientos con desglose pendientes/conciliados."""

    @pytest.mark.django_db
    def test_list_renderea_con_movimientos_de_la_cuenta(self, client, cuenta_bancaria):
        movimiento = _crear_extracto(cuenta_bancaria)
        respuesta = client.get(
            reverse(NOMBRE_URL_LIST), {"cuenta": cuenta_bancaria.pk}
        )
        assert respuesta.status_code == 200
        movimientos = list(respuesta.context["movimientos"])
        assert movimiento in movimientos

    @pytest.mark.django_db
    def test_list_pasa_pendientes_y_conciliados(self, client, cuenta_bancaria):
        pendiente = _crear_extracto(cuenta_bancaria, detalle="Pendiente")
        conciliado = _crear_extracto(
            cuenta_bancaria, detalle="Conciliado", conciliado=True
        )
        respuesta = client.get(
            reverse(NOMBRE_URL_LIST), {"cuenta": cuenta_bancaria.pk}
        )
        assert respuesta.status_code == 200
        assert pendiente in list(respuesta.context["pendientes"])
        assert conciliado in list(respuesta.context["conciliados"])

# ---------------------------------------------------------------------------
# CRUD manual — extracto_create (GET/POST).
# ---------------------------------------------------------------------------


class TestExtractoCreate:
    """``extracto_create`` muestra el formulario y crea un ``MovimientoExtracto``."""

    @pytest.mark.django_db
    def test_get_muestra_formulario(self, client, cuenta_bancaria):
        respuesta = client.get(reverse(NOMBRE_URL_CREATE))
        assert respuesta.status_code == 200

    @pytest.mark.django_db
    def test_post_crea_movimiento_y_redirige(self, client, cuenta_bancaria):
        respuesta = client.post(
            reverse(NOMBRE_URL_CREATE), _datos_formulario(cuenta_bancaria)
        )
        assert respuesta.status_code == 302
        movimiento = MovimientoExtracto.objects.get(
            cuenta_bancaria=cuenta_bancaria
        )
        assert movimiento.origen == MovimientoExtracto.ORIGEN_MANUAL
        assert movimiento.importe == Decimal("100.00")
        assert movimiento.detalle == "Movimiento manual"

    @pytest.mark.django_db
    def test_post_invalido_rerenderiza_sin_crear(self, client, cuenta_bancaria):
        respuesta = client.post(
            reverse(NOMBRE_URL_CREATE),
            _datos_formulario(cuenta_bancaria, importe="0"),
        )
        assert respuesta.status_code == 200
        assert MovimientoExtracto.objects.filter(
            cuenta_bancaria=cuenta_bancaria
        ).count() == 0

# ---------------------------------------------------------------------------
# CRUD manual — extracto_update (GET/POST).
# ---------------------------------------------------------------------------


class TestExtractoUpdate:
    """``extracto_update`` edita solo filas sin conciliar; 400 si ``conciliado``."""

    @pytest.mark.django_db
    def test_get_muestra_formulario(self, client, cuenta_bancaria):
        movimiento = _crear_extracto(cuenta_bancaria)
        respuesta = client.get(
            reverse(NOMBRE_URL_UPDATE, args=[movimiento.pk])
        )
        assert respuesta.status_code == 200

    @pytest.mark.django_db
    def test_post_edita_fila_sin_conciliar_y_redirige(self, client, cuenta_bancaria):
        movimiento = _crear_extracto(cuenta_bancaria)
        datos = _datos_formulario(cuenta_bancaria, detalle="Editado", importe="-50.00")
        respuesta = client.post(
            reverse(NOMBRE_URL_UPDATE, args=[movimiento.pk]), datos
        )
        assert respuesta.status_code == 302
        movimiento.refresh_from_db()
        assert movimiento.detalle == "Editado"
        assert movimiento.importe == Decimal("-50.00")

    @pytest.mark.django_db
    def test_post_editando_conciliado_devuelve_400_sin_mutar(
        self, client, cuenta_bancaria
    ):
        movimiento = _crear_extracto(
            cuenta_bancaria, detalle="Original", conciliado=True
        )
        datos = _datos_formulario(cuenta_bancaria, detalle="Modificado")
        respuesta = client.post(
            reverse(NOMBRE_URL_UPDATE, args=[movimiento.pk]), datos
        )
        assert respuesta.status_code == 400
        movimiento.refresh_from_db()
        assert movimiento.detalle == "Original"

# ---------------------------------------------------------------------------
# CRUD manual — extracto_delete (POST).
# ---------------------------------------------------------------------------


class TestExtractoDelete:
    """``extracto_delete`` elimina solo filas sin conciliar; 400 si ``conciliado``."""

    @pytest.mark.django_db
    def test_post_elimina_fila_sin_conciliar_y_redirige(self, client, cuenta_bancaria):
        movimiento = _crear_extracto(cuenta_bancaria)
        respuesta = client.post(
            reverse(NOMBRE_URL_DELETE, args=[movimiento.pk])
        )
        assert respuesta.status_code == 302
        assert not MovimientoExtracto.objects.filter(
            pk=movimiento.pk
        ).exists()

    @pytest.mark.django_db
    def test_post_eliminando_conciliado_devuelve_400_sin_mutar(
        self, client, cuenta_bancaria
    ):
        movimiento = _crear_extracto(cuenta_bancaria, conciliado=True)
        respuesta = client.post(
            reverse(NOMBRE_URL_DELETE, args=[movimiento.pk])
        )
        assert respuesta.status_code == 400
        assert MovimientoExtracto.objects.filter(pk=movimiento.pk).exists()


# ---------------------------------------------------------------------------
# Punteo — vista dual-list (GET /punteo/).
# ---------------------------------------------------------------------------


NOMBRE_URL_PUNTEO = "punteo"
NOMBRE_URL_PUNTEAR = "puntear"
NOMBRE_URL_DESPUNTEAR = "despuntear"


class TestPunteoVista:
    """``punteo`` renderiza la vista dual-list con estado 200."""

    @pytest.mark.django_db
    def test_get_devuelve_200(self, client, cuenta_bancaria):
        respuesta = client.get(reverse(NOMBRE_URL_PUNTEO))
        assert respuesta.status_code == 200


# ---------------------------------------------------------------------------
# Punteo — POST /punteo/puntear/.
# ---------------------------------------------------------------------------


class TestPuntearVista:
    """``puntear`` vincula extracto y libro con ``conciliado=True`` o responde 400."""

    @pytest.mark.django_db
    def test_post_puntea_y_marca_ambos_conciliado(
        self, client, cuenta_bancaria, tipo_operacion
    ):
        extracto = _crear_extracto(cuenta_bancaria, importe=Decimal("100.00"))
        libro = _crear_libro(
            cuenta_bancaria, tipo_operacion, debe=Decimal("100.00"), haber=Decimal("0.00")
        )

        respuesta = client.post(
            reverse(NOMBRE_URL_PUNTEAR),
            {"extracto_id": extracto.pk, "libro_id": libro.pk},
        )

        assert respuesta.status_code == 302
        extracto.refresh_from_db()
        libro.refresh_from_db()
        assert extracto.conciliado is True
        assert libro.conciliado is True
        assert Punteo.objects.filter(
            movimiento_extracto=extracto, movimiento_libro=libro
        ).exists()

    @pytest.mark.django_db
    def test_post_con_importes_distintos_devuelve_400_sin_persistir(
        self, client, cuenta_bancaria, tipo_operacion
    ):
        extracto = _crear_extracto(cuenta_bancaria, importe=Decimal("100.00"))
        libro = _crear_libro(
            cuenta_bancaria, tipo_operacion, debe=Decimal("99.99"), haber=Decimal("0.00")
        )

        respuesta = client.post(
            reverse(NOMBRE_URL_PUNTEAR),
            {"extracto_id": extracto.pk, "libro_id": libro.pk},
        )

        assert respuesta.status_code == 400
        assert not Punteo.objects.filter(
            movimiento_extracto=extracto, movimiento_libro=libro
        ).exists()
        extracto.refresh_from_db()
        libro.refresh_from_db()
        assert extracto.conciliado is False
        assert libro.conciliado is False


# ---------------------------------------------------------------------------
# Despunteo — POST /punteo/despuntear/<extracto_id>/.
# ---------------------------------------------------------------------------


class TestDespuntearVista:
    """``despuntear`` elimina el vínculo y reinicia las banderas, o responde 400."""

    @pytest.mark.django_db
    def test_post_despuntea_y_reinicia_banderas(
        self, client, cuenta_bancaria, tipo_operacion
    ):
        extracto = _crear_extracto(cuenta_bancaria, importe=Decimal("100.00"))
        libro = _crear_libro(
            cuenta_bancaria, tipo_operacion, debe=Decimal("100.00"), haber=Decimal("0.00")
        )
        puntear_servicio(extracto=extracto, libro=libro)

        respuesta = client.post(
            reverse(NOMBRE_URL_DESPUNTEAR, args=[extracto.pk])
        )

        assert respuesta.status_code == 302
        assert not Punteo.objects.filter(
            movimiento_extracto=extracto, movimiento_libro=libro
        ).exists()
        extracto.refresh_from_db()
        libro.refresh_from_db()
        assert extracto.conciliado is False
        assert libro.conciliado is False

    @pytest.mark.django_db
    def test_post_sin_punteo_devuelve_400(self, client, cuenta_bancaria):
        extracto = _crear_extracto(cuenta_bancaria, importe=Decimal("100.00"))

        respuesta = client.post(
            reverse(NOMBRE_URL_DESPUNTEAR, args=[extracto.pk])
        )

        assert respuesta.status_code == 400

    @pytest.mark.django_db
    def test_despuntear_es_la_unica_via_de_liberacion(
        self, client, cuenta_bancaria, tipo_operacion
    ):
        """``despuntear`` es la única vía para liberar un extracto conciliado."""
        # 1. Semilla extracto + libro y vincúlalos vía el SERVICIO (puntear_servicio);
        #    ambos quedan conciliado.
        extracto = _crear_extracto(cuenta_bancaria, importe=Decimal("100.00"))
        libro = _crear_libro(
            cuenta_bancaria, tipo_operacion, debe=Decimal("100.00"), haber=Decimal("0.00")
        )
        puntear_servicio(extracto=extracto, libro=libro)

        # 2. Mientras está conciliado, eliminar vía la VISTA queda bloqueado (400, sin mutación).
        respuesta = client.post(reverse(NOMBRE_URL_DELETE, args=[extracto.pk]))
        assert respuesta.status_code == 400
        assert MovimientoExtracto.objects.filter(pk=extracto.pk).exists()

        # 3. POST despuntear (la ÚNICA vía de liberación) -> 302 y ambas banderas se reinician.
        respuesta = client.post(reverse(NOMBRE_URL_DESPUNTEAR, args=[extracto.pk]))
        assert respuesta.status_code == 302
        extracto.refresh_from_db()
        libro.refresh_from_db()
        assert extracto.conciliado is False and libro.conciliado is False

        # 4. AHORA la eliminación tiene éxito (302, la fila desaparece).
        respuesta = client.post(reverse(NOMBRE_URL_DELETE, args=[extracto.pk]))
        assert respuesta.status_code == 302
        assert not MovimientoExtracto.objects.filter(pk=extracto.pk).exists()


class TestCrearAsientoExtractoVista:
    """GET crea-asiento precarga el asiento; POST crea, concilia y redirige a punteo."""

    @pytest.mark.django_db
    def test_get_precarga_debe_para_importe_positivo(self, client, cuenta_bancaria):
        extracto = _crear_extracto(cuenta_bancaria, importe=Decimal("100.00"))
        respuesta = client.get(reverse(NOMBRE_URL_CREAR_ASIENTO, args=[extracto.pk]))
        assert respuesta.status_code == 200
        contenido = respuesta.content.decode()
        assert extracto.detalle in contenido
        assert 'name="debe"' in contenido
        assert "100.00" in contenido

    @pytest.mark.django_db
    def test_get_precarga_haber_para_importe_negativo(self, client, cuenta_bancaria):
        extracto = _crear_extracto(cuenta_bancaria, importe=Decimal("-50.00"))
        respuesta = client.get(reverse(NOMBRE_URL_CREAR_ASIENTO, args=[extracto.pk]))
        assert respuesta.status_code == 200
        contenido = respuesta.content.decode()
        assert 'name="haber"' in contenido
        assert "50.00" in contenido

    @pytest.mark.django_db
    def test_post_crea_libro_punteo_y_redirige(self, client, cuenta_bancaria):
        extracto = _crear_extracto(cuenta_bancaria, importe=Decimal("100.00"))
        respuesta = client.post(reverse(NOMBRE_URL_CREAR_ASIENTO, args=[extracto.pk]))
        assert respuesta.status_code == 302
        assert respuesta.url == reverse("punteo")
        libro = MovimientoLibro.objects.get(detalle=extracto.detalle)
        assert libro.debe == Decimal("100.00")
        assert Punteo.objects.filter(movimiento_extracto=extracto, movimiento_libro=libro).exists()
        extracto.refresh_from_db()
        assert extracto.conciliado is True

    @pytest.mark.django_db
    def test_post_de_conciliado_devuelve_400(self, client, cuenta_bancaria):
        extracto = _crear_extracto(cuenta_bancaria, importe=Decimal("100.00"), conciliado=True)
        respuesta = client.post(reverse(NOMBRE_URL_CREAR_ASIENTO, args=[extracto.pk]))
        assert respuesta.status_code == 400

