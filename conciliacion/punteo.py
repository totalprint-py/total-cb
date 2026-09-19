"""Servicio de importación de extractos bancarios (T008).

Implementa la orquestación ``importar_extracto(cuenta, archivo, *, formato,
hoja=None)`` descrita en ``specs/004-conciliacion-bancaria/plan.md``:

* determina el formato (``csv`` o ``xlsx``) a partir del archivo subido;
* invoca :func:`conciliacion.importadores.parsear_extracto`;
* envuelve la creación en bloque de filas ``MovimientoExtracto`` dentro de
  ``transaction.atomic`` (todo-o-nada);
* marca cada fila con ``origen=MovimientoExtracto.ORIGEN_IMPORTACION``.

Los importes monetarios solo admiten ``decimal.Decimal`` (Principio 5 / FR-010);
cualquier ``float`` se rechaza antes de la coerción. Los identificadores y los
mensajes están en español.
"""
from __future__ import annotations

import os
from decimal import Decimal
from io import StringIO

from django.db import transaction

from conciliacion.importadores import parsear_extracto
from conciliacion.models import (
    AuditoriaPunteo,
    ConciliadoBloqueadoError,
    MovimientoExtracto,
    MovimientoLibro,
    Punteo,
    TipoOperacion,
)
from conciliacion.services import quantize_to_moneda


def _determinar_formato(archivo) -> str:
    """Devuelve ``"csv"`` o ``"xlsx"`` según la extensión del archivo subido."""
    nombre = getattr(archivo, "name", "") or ""
    _, extension = os.path.splitext(nombre)
    extension = extension.lower()
    if extension == ".csv":
        return "csv"
    if extension in (".xlsx", ".xls"):
        return "xlsx"
    raise ValueError(f"Extensión de archivo no soportada: {extension}")


@transaction.atomic
def importar_extracto(cuenta, archivo, *, formato=None, hoja=None):
    """Parsea un extracto y persiste sus movimientos de forma todo-o-nada.

    Pre: ``cuenta`` es una ``CuentaBancaria`` válida y ``archivo`` es un archivo
    subido (``UploadedFile``) con extensión ``.csv`` o ``.xlsx``.

    Post: devuelve la lista de ``MovimientoExtracto`` creados con
    ``origen=ORIGEN_IMPORTACION``. Cualquier fila inválida del parser revierte
    la transacción propagando ``ErrorImportacion``.
    """
    if formato is None:
        formato = _determinar_formato(archivo)

    if formato == "csv":
        # ``UploadedFile.read()`` devuelve ``bytes``; se decodifica a texto.
        contenido = archivo.read()
        if isinstance(contenido, bytes):
            contenido = contenido.decode("utf-8-sig")
        flujo = StringIO(contenido)
    else:
        # ``openpyxl`` acepta cualquier objeto binario similar a archivo.
        flujo = archivo

    filas = parsear_extracto(flujo, formato=formato, hoja=hoja)

    movimientos = [
        MovimientoExtracto(
            cuenta_bancaria=cuenta,
            fecha=fila["fecha"],
            referencia=fila.get("referencia", ""),
            detalle=fila["detalle"],
            importe=fila["importe"],
            origen=MovimientoExtracto.ORIGEN_IMPORTACION,
        )
        for fila in filas
    ]

    if movimientos:
        MovimientoExtracto.objects.bulk_create(movimientos)

    return movimientos


class ImporteNoCoincideError(Exception):
    """Se eleva cuando los importes de extracto y libro no coinciden tras quantize."""


@transaction.atomic
def puntear(*, extracto, libro):
    """Vincula ``extracto`` con ``libro`` si importes y cuentas coinciden.

    Pre: ``extracto`` es un ``MovimientoExtracto`` y ``libro`` un
    ``MovimientoLibro`` de la misma ``CuentaBancaria`` y con importes iguales
    (``extracto.importe == libro.debe - libro.haber`` tras ``quantize_to_moneda``).

    Post: crea el ``Punteo`` 1:1, marca ``conciliado=True`` en ambos y registra
    la ``AuditoriaPunteo`` (``accion=puntear``). Devuelve el ``Punteo`` creado.

    Error: ``ValueError`` si las cuentas difieren; ``ImporteNoCoincideError`` si
    los importes no coinciden.
    """
    if extracto.cuenta_bancaria_id != libro.cuenta_id:
        raise ValueError("No se puede puntear: las cuentas bancarias difieren.")

    moneda = extracto.cuenta_bancaria.moneda
    importe_extracto = quantize_to_moneda(extracto.importe, moneda)
    importe_libro = quantize_to_moneda(libro.debe - libro.haber, moneda)
    if importe_extracto != importe_libro:
        raise ImporteNoCoincideError(
            f"No se puede puntear: los importes no coinciden ({importe_extracto} vs {importe_libro})."
        )

    punteo = Punteo.objects.create(movimiento_extracto=extracto, movimiento_libro=libro)

    extracto.conciliado = True
    libro.conciliado = True
    extracto.save(update_fields=["conciliado"])
    libro.save(update_fields=["conciliado"])

    AuditoriaPunteo.objects.create(
        movimiento_extracto=extracto,
        movimiento_libro=libro,
        accion=AuditoriaPunteo.ACCION_PUNTEAR,
    )

    return punteo


@transaction.atomic
def despuntear(*, extracto):
    """Elimina el vínculo de ``extracto`` y reinicia las banderas de conciliación.

    Pre: existe un ``Punteo`` para ``extracto``.

    Post: marca ``conciliado=False`` en ambos movimientos, registra la
    ``AuditoriaPunteo`` (``accion=despuntear``) y elimina el ``Punteo``.
    Devuelve ``None``.

    Error: ``ValueError`` si no existe un punteo para ``extracto``.
    """
    punteo = Punteo.objects.filter(movimiento_extracto=extracto).first()
    if punteo is None:
        raise ValueError("No existe un punteo para este extracto.")

    libro = punteo.movimiento_libro

    extracto.conciliado = False
    libro.conciliado = False
    extracto.save(update_fields=["conciliado"])
    libro.save(update_fields=["conciliado"])

    AuditoriaPunteo.objects.create(
        movimiento_extracto=extracto,
        movimiento_libro=libro,
        accion=AuditoriaPunteo.ACCION_DESPUNTEAR,
    )

    punteo.delete()

    return None


@transaction.atomic
def crear_asiento_desde_extracto(*, extracto):
    """Crea el asiento de libro espejo de ``extracto`` y lo concilia al instante.

    Sign convention (sin inversión): ``extracto.importe > 0`` → ``debe`` (dinero
    entrante); ``extracto.importe < 0`` → ``haber = abs(importe)`` (dinero saliente).
    Post: crea ``MovimientoLibro`` (cuenta/fecha/detalle del extracto, tipo del
    fallback ``AJUSTE-BANCARIO``), recalcula el saldo corrido, crea el ``Punteo``,
    marca ambos ``conciliado`` y escribe ``AuditoriaPunteo`` (accion=puntear).
    Error: ``ConciliadoBloqueadoError`` si ``extracto.conciliado``.
    """
    if extracto.conciliado:
        raise ConciliadoBloqueadoError(
            "El movimiento conciliado no puede editarse ni eliminarse."
        )
    tipo_operacion, _ = TipoOperacion.objects.get_or_create(
        codigo="AJUSTE-BANCARIO",
        defaults={"nombre": "Ajuste Bancario"},
    )
    importe = quantize_to_moneda(extracto.importe, extracto.cuenta_bancaria.moneda)
    if importe > 0:
        debe, haber = importe, Decimal("0.00")
    else:
        debe, haber = Decimal("0.00"), -importe
    libro = MovimientoLibro.objects.create(
        cuenta=extracto.cuenta_bancaria,
        fecha=extracto.fecha,
        tipo_operacion=tipo_operacion,
        detalle=extracto.detalle,
        debe=debe,
        haber=haber,
    )
    MovimientoLibro.recalcular_saldos(extracto.cuenta_bancaria_id)
    libro.refresh_from_db()
    puntear(extracto=extracto, libro=libro)
    return libro
