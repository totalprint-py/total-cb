"""Pruebas unitarias de los modelos de catálogo (TDD — Fase 2, T008).

Verifican la creación y validación de las entidades de catálogo definidas en
``data-model.md``: ``Banco``, ``TipoCuenta``, ``Moneda``, ``TipoOperacion`` y
``ConceptoAjuste``. Cubren el esquema de los campos, la unicidad y
autonumeración de ``codigo``, y la precisión decimal no negativa de
``Moneda.cantidad_decimales``.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from django.contrib.messages import get_messages
from django.core.exceptions import ValidationError
from django.db import IntegrityError, models
from django.db.models import Q
from django.db.models.constraints import CheckConstraint
from django.urls import reverse

from conciliacion.models import (
    AjusteConciliacion,
    Banco,
    ConceptoAjuste,
    Conciliacion,
    CuentaBancaria,
    Moneda,
    MovimientoLibro,
    TipoCuenta,
    TipoOperacion,
)

# Catálogos que comparten la estructura ``codigo`` (único y autoincremental) + ``nombre``.
MODELOS_DE_CATALOGO = [Banco, TipoCuenta, Moneda, TipoOperacion, ConceptoAjuste]
NOMBRES_DE_CATALOGO = ["Banco", "TipoCuenta", "Moneda", "TipoOperacion", "ConceptoAjuste"]

# Nombre del fixture-fábrica asociado a cada modelo de catálogo.
_FABRICA_POR_MODELO = {
    Banco: "banco_factory",
    TipoCuenta: "tipo_cuenta_factory",
    Moneda: "moneda_factory",
    TipoOperacion: "tipo_operacion_factory",
    ConceptoAjuste: "concepto_ajuste_factory",
}


def _datos_validos(modelo, **sobrescribir):
    """Devuelve kwargs válidos para construir una instancia del catálogo dado."""
    datos = {"codigo": "CAT-001", "nombre": "Catálogo de Prueba"}
    if modelo is Moneda:
        datos["cantidad_decimales"] = 2
    datos.update(sobrescribir)
    return datos


# ---------------------------------------------------------------------------
# Esquema común: ``codigo`` y ``nombre`` en todos los catálogos.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("modelo", MODELOS_DE_CATALOGO, ids=NOMBRES_DE_CATALOGO)
def test_codigo_es_charfield(modelo):
    """El campo ``codigo`` debe ser un ``CharField``."""
    campo = modelo._meta.get_field("codigo")
    assert isinstance(campo, models.CharField)


@pytest.mark.parametrize("modelo", MODELOS_DE_CATALOGO, ids=NOMBRES_DE_CATALOGO)
def test_codigo_es_unico(modelo):
    """El campo ``codigo`` debe declarar ``unique=True``."""
    campo = modelo._meta.get_field("codigo")
    assert campo.unique is True


@pytest.mark.parametrize("modelo", MODELOS_DE_CATALOGO, ids=NOMBRES_DE_CATALOGO)
def test_codigo_no_admite_nulos_pero_admite_vacio(modelo):
    """El campo ``codigo`` no admite ``null``, pero sí ``blank`` (autoincremental)."""
    campo = modelo._meta.get_field("codigo")
    assert campo.null is False
    assert campo.blank is True


@pytest.mark.parametrize("modelo", MODELOS_DE_CATALOGO, ids=NOMBRES_DE_CATALOGO)
def test_nombre_es_charfield(modelo):
    """El campo ``nombre`` debe ser un ``CharField``."""
    campo = modelo._meta.get_field("nombre")
    assert isinstance(campo, models.CharField)


@pytest.mark.parametrize("modelo", MODELOS_DE_CATALOGO, ids=NOMBRES_DE_CATALOGO)
def test_nombre_es_obligatorio(modelo):
    """El campo ``nombre`` no debe admitir nulos ni vacíos."""
    campo = modelo._meta.get_field("nombre")
    assert campo.null is False
    assert campo.blank is False


# ---------------------------------------------------------------------------
# Creación y validación comunes a todos los catálogos.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("modelo", MODELOS_DE_CATALOGO, ids=NOMBRES_DE_CATALOGO)
def test_creacion_persiste_los_valores(modelo, request):
    """Crear un catálogo persiste ``codigo`` y ``nombre`` con los valores dados."""
    fabrica = request.getfixturevalue(_FABRICA_POR_MODELO[modelo])
    instancia = fabrica(codigo="CAT-123", nombre="Nombre Real")
    persistida = modelo.objects.get(pk=instancia.pk)
    assert persistida.codigo == "CAT-123"
    assert persistida.nombre == "Nombre Real"


@pytest.mark.parametrize("modelo", MODELOS_DE_CATALOGO, ids=NOMBRES_DE_CATALOGO)
def test_codigo_duplicado_lanza_error_de_integridad(modelo, request):
    """Registrar dos catálogos con el mismo ``codigo`` lanza ``IntegrityError``."""
    fabrica = request.getfixturevalue(_FABRICA_POR_MODELO[modelo])
    fabrica(codigo="CAT-DUP")
    with pytest.raises(IntegrityError):
        fabrica(codigo="CAT-DUP")


@pytest.mark.parametrize("modelo", MODELOS_DE_CATALOGO, ids=NOMBRES_DE_CATALOGO)
@pytest.mark.django_db
def test_codigo_vacio_se_autocompleta(modelo):
    """Guardar un catálogo sin ``codigo`` asigna automáticamente el consecutivo."""
    instancia = modelo(**_datos_validos(modelo, codigo=""))
    instancia.full_clean()  # ya no falla: el campo admite blank=True.
    instancia.save()
    assert instancia.codigo == "1"


@pytest.mark.parametrize("modelo", MODELOS_DE_CATALOGO, ids=NOMBRES_DE_CATALOGO)
@pytest.mark.django_db
def test_codigo_se_asigna_secuencialmente(modelo):
    """Crear dos registros sin ``codigo`` asigna los consecutivos "1" y "2"."""
    def crear_sin_codigo():
        datos = {"nombre": "Catálogo de Prueba"}
        if modelo is Moneda:
            datos["cantidad_decimales"] = 2
        return modelo.objects.create(**datos)

    primero = crear_sin_codigo()
    segundo = crear_sin_codigo()
    assert primero.codigo == "1"
    assert segundo.codigo == "2"


@pytest.mark.parametrize("modelo", MODELOS_DE_CATALOGO, ids=NOMBRES_DE_CATALOGO)
@pytest.mark.django_db
def test_nombre_vacio_falla_la_validacion(modelo):
    """Un ``nombre`` vacío no supera la validación del modelo."""
    instancia = modelo(**_datos_validos(modelo, nombre=""))
    with pytest.raises(ValidationError):
        instancia.full_clean()


# ---------------------------------------------------------------------------
# ``Moneda``: precisión decimal (``cantidad_decimales``).
# ---------------------------------------------------------------------------


class TestMoneda:
    """Pruebas específicas de ``Moneda`` y su precisión decimal."""

    def test_cantidad_decimales_es_positive_integer_field(self):
        """El campo ``cantidad_decimales`` debe ser ``PositiveIntegerField``."""
        campo = Moneda._meta.get_field("cantidad_decimales")
        assert isinstance(campo, models.PositiveIntegerField)

    def test_cantidad_decimales_es_obligatorio(self):
        """El campo ``cantidad_decimales`` no debe admitir nulos ni vacíos."""
        campo = Moneda._meta.get_field("cantidad_decimales")
        assert campo.null is False
        assert campo.blank is False

    def test_cantidad_decimales_tiene_restriccion_no_negativa(self):
        """``cantidad_decimales >= 0`` se expresa con un ``CheckConstraint`` nombrado."""
        restricciones = {c.name: c for c in Moneda._meta.constraints}
        assert "moneda_cantidad_decimales_no_negativa" in restricciones
        restriccion = restricciones["moneda_cantidad_decimales_no_negativa"]
        assert isinstance(restriccion, CheckConstraint)
        assert restriccion.condition == Q(cantidad_decimales__gte=0)

    @pytest.mark.django_db
    def test_cantidad_decimales_negativa_falla_la_validacion(self):
        """Un ``cantidad_decimales`` negativo no supera la validación del modelo."""
        moneda = Moneda(codigo="USD", nombre="Dólar", cantidad_decimales=-1)
        with pytest.raises(ValidationError):
            moneda.full_clean()

    @pytest.mark.django_db
    def test_cantidad_decimales_cero_es_valida(self):
        """Un ``cantidad_decimales`` igual a cero es válido (límite no negativo)."""
        moneda = Moneda(codigo="USD", nombre="Dólar", cantidad_decimales=0)
        moneda.full_clean()  # no debe lanzar ValidationError

    @pytest.mark.django_db
    def test_cantidad_decimales_ausente_falla_la_validacion(self):
        """Omitir ``cantidad_decimales`` no supera la validación del modelo."""
        moneda = Moneda(codigo="USD", nombre="Dólar")
        with pytest.raises(ValidationError):
            moneda.full_clean()

    def test_creacion_persiste_cantidad_decimales(self, moneda_factory):
        """Crear una ``Moneda`` persiste el valor de ``cantidad_decimales``."""
        moneda = moneda_factory(codigo="EUR", nombre="Euro", cantidad_decimales=2)
        persistida = Moneda.objects.get(pk=moneda.pk)
        assert persistida.codigo == "EUR"
        assert persistida.nombre == "Euro"
        assert persistida.cantidad_decimales == 2


# ---------------------------------------------------------------------------
# Eliminación segura de catálogos (PROTECT → mensaje de error).
# ---------------------------------------------------------------------------

# (modelo, fábrica, URL de eliminación, URL de lista) de cada catálogo eliminable.
CATALOGOS_CON_ELIMINACION = [
    (Banco, "banco_factory", "banco_delete", "banco_list"),
    (TipoCuenta, "tipo_cuenta_factory", "tipocuenta_delete", "tipocuenta_list"),
    (Moneda, "moneda_factory", "moneda_delete", "moneda_list"),
    (
        TipoOperacion,
        "tipo_operacion_factory",
        "tipooperacion_delete",
        "tipooperacion_list",
    ),
    (
        ConceptoAjuste,
        "concepto_ajuste_factory",
        "conceptoajuste_delete",
        "conceptoajuste_list",
    ),
]


def _crear_cuenta_bancaria(banco, tipo_cuenta, moneda):
    """Crea y persiste una ``CuentaBancaria`` de apoyo."""
    return CuentaBancaria.objects.create(
        numero_cuenta="0001-2345-6789",
        denominacion="Cuenta de Prueba",
        banco=banco,
        tipo_cuenta=tipo_cuenta,
        moneda=moneda,
        saldo_inicial=Decimal("1000.00"),
    )


def _crear_dependiente_protegido(registro, request):
    """Crea un registro que referencia ``registro`` con ``on_delete=PROTECT``."""
    banco_factory = request.getfixturevalue("banco_factory")
    tipo_cuenta_factory = request.getfixturevalue("tipo_cuenta_factory")
    moneda_factory = request.getfixturevalue("moneda_factory")

    if isinstance(registro, (Banco, TipoCuenta, Moneda)):
        return _crear_cuenta_bancaria(
            banco=registro if isinstance(registro, Banco) else banco_factory(),
            tipo_cuenta=(
                registro
                if isinstance(registro, TipoCuenta)
                else tipo_cuenta_factory()
            ),
            moneda=registro if isinstance(registro, Moneda) else moneda_factory(),
        )

    if isinstance(registro, TipoOperacion):
        cuenta = _crear_cuenta_bancaria(
            banco_factory(), tipo_cuenta_factory(), moneda_factory()
        )
        return MovimientoLibro.objects.create(
            cuenta=cuenta,
            fecha=date(2026, 9, 5),
            tipo_operacion=registro,
            detalle="Movimiento de prueba",
            debe=Decimal("10.00"),
            haber=Decimal("0.00"),
        )

    if isinstance(registro, ConceptoAjuste):
        cuenta = _crear_cuenta_bancaria(
            banco_factory(), tipo_cuenta_factory(), moneda_factory()
        )
        conciliacion = Conciliacion.objects.create(
            cuenta_bancaria=cuenta,
            fecha_desde=date(2026, 9, 1),
            fecha_hasta=date(2026, 9, 30),
        )
        return AjusteConciliacion.objects.create(
            conciliacion=conciliacion,
            concepto_ajuste=registro,
            importe=Decimal("10.00000000"),
        )

    raise ValueError(f"Catálogo no soportado con dependencia PROTECT: {type(registro)}")


@pytest.mark.django_db
@pytest.mark.parametrize(
    "modelo, fabrica, url_eliminar, url_lista",
    CATALOGOS_CON_ELIMINACION,
    ids=[modelo.__name__ for modelo, *_ in CATALOGOS_CON_ELIMINACION],
)
def test_eliminar_catalogo_sin_dependencias(client, request, modelo, fabrica, url_eliminar, url_lista):
    """Eliminar un catálogo sin dependencias lo borra y redirige a su lista."""
    registro = request.getfixturevalue(fabrica)()
    respuesta = client.post(reverse(url_eliminar, args=[registro.pk]))

    assert respuesta.status_code == 302
    assert respuesta.url == reverse(url_lista)
    assert not modelo.objects.filter(pk=registro.pk).exists()


@pytest.mark.django_db
@pytest.mark.parametrize(
    "modelo, fabrica, url_eliminar, url_lista",
    CATALOGOS_CON_ELIMINACION,
    ids=[modelo.__name__ for modelo, *_ in CATALOGOS_CON_ELIMINACION],
)
def test_pagina_de_confirmacion_de_eliminacion(client, request, modelo, fabrica, url_eliminar, url_lista):
    """La vista de eliminación muestra la confirmación con cancelar y eliminar."""
    registro = request.getfixturevalue(fabrica)()
    respuesta = client.get(reverse(url_eliminar, args=[registro.pk]))

    assert respuesta.status_code == 200
    nombres = [plantilla.name for plantilla in respuesta.templates]
    assert "conciliacion/confirm_delete.html" in nombres
    contenido = respuesta.content.decode()
    assert "Confirmar eliminación" in contenido
    assert str(registro) in contenido
    # El enlace "Cancelar" apunta a la lista del catálogo.
    assert reverse(url_lista) in contenido


@pytest.mark.django_db
@pytest.mark.parametrize(
    "modelo, fabrica, url_eliminar, url_lista",
    CATALOGOS_CON_ELIMINACION,
    ids=[modelo.__name__ for modelo, *_ in CATALOGOS_CON_ELIMINACION],
)
def test_eliminar_catalogo_protegido_muestra_error(client, request, modelo, fabrica, url_eliminar, url_lista):
    """Eliminar un catálogo con dependencias PROTECT redirige con un error visible."""
    registro = request.getfixturevalue(fabrica)()
    _crear_dependiente_protegido(registro, request)

    respuesta = client.post(reverse(url_eliminar, args=[registro.pk]))

    assert respuesta.status_code == 302
    assert respuesta.url == reverse(url_lista)
    assert modelo.objects.filter(pk=registro.pk).exists()

    mensajes = [str(mensaje) for mensaje in get_messages(respuesta.wsgi_request)]
    assert len(mensajes) == 1
    assert "No se puede eliminar" in mensajes[0]
    assert str(registro) in mensajes[0]
