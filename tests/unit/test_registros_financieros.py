"""Pruebas unitarias de los registros financieros (TDD — Fase 2, T009).

Verifican la creación y validación de las entidades operativas de registros
financieros definidas en ``data-model.md``: ``LoteImportacion``,
``CuentaBancaria``, ``MovimientoBancario`` y ``MovimientoInterno``.

Cubren:

* el esquema de campos y su obligatoriedad;
* las relaciones obligatorias (``ForeignKey``) hacia los catálogos y el lote;
* la identidad única de importación (FR-012, deduplicación);
* el dinero como ``DecimalField`` (nunca ``FloatField``) con precisión física
  ``max_digits=19`` / ``decimal_places=8`` (FR-007, FR-009);
* la restricción ``CheckConstraint(condition=Q(...))`` que bloquea importes
  negativos (tanto a nivel de validación como a nivel de base de datos);
* el rechazo de ``float`` en los campos monetarios (forzando ``decimal.Decimal``);
* la coincidencia de moneda entre un ``MovimientoBancario`` y su
  ``CuentaBancaria``;
* el flag ``en_consulta`` (por defecto ``False``) y las ``notas`` opcionales.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pytest
from django.core.exceptions import FieldDoesNotExist, ValidationError
from django.db import IntegrityError, models
from django.db.models import Q
from django.db.models.constraints import CheckConstraint, UniqueConstraint
from django.utils import timezone

from conciliacion.models import (
    Banco,
    CuentaBancaria,
    LoteImportacion,
    Moneda,
    MovimientoBancario,
    MovimientoInterno,
    TipoCuenta,
    TipoOperacion,
)

# Valores por defecto para construir registros financieros válidos.
FECHA_IMPORTACION = timezone.make_aware(datetime(2026, 9, 5, 10, 30, 0))
FECHA_MOVIMIENTO = date(2026, 9, 5)


# ---------------------------------------------------------------------------
# Fábricas de apoyo (persisten los registros financieros).
# ---------------------------------------------------------------------------


def _crear_lote(**sobrescribir):
    """Crea y persiste un ``LoteImportacion`` válido, permitiendo sobreescribir campos."""
    valores = {"fuente": "BANCO-X.csv", "fecha_importacion": FECHA_IMPORTACION}
    valores.update(sobrescribir)
    return LoteImportacion.objects.create(**valores)


def _crear_cuenta_bancaria(banco, tipo_cuenta, moneda, **sobrescribir):
    """Crea y persiste una ``CuentaBancaria`` válida, permitiendo sobreescribir campos."""
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
    """Crea y persiste un ``MovimientoBancario`` válido, permitiendo sobreescribir campos."""
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
    """Crea y persiste un ``MovimientoInterno`` válido, permitiendo sobreescribir campos."""
    valores = {
        "importe": Decimal("100.00"),
        "fecha": FECHA_MOVIMIENTO,
        "lote_importacion": lote_importacion,
        "tipo_operacion": tipo_operacion,
        "moneda": moneda,
    }
    valores.update(sobrescribir)
    return MovimientoInterno.objects.create(**valores)


# ---------------------------------------------------------------------------
# Fixtures que construyen el grafo completo de objetos relacionados.
# ---------------------------------------------------------------------------


@pytest.fixture
def registro_bancario(banco_factory, tipo_cuenta_factory, moneda_factory, tipo_operacion_factory):
    """Devuelve el grafo persistido de un movimiento bancario válido (sin el movimiento)."""
    banco = banco_factory()
    tipo_cuenta = tipo_cuenta_factory()
    moneda = moneda_factory()
    tipo_operacion = tipo_operacion_factory()
    lote_importacion = _crear_lote()
    cuenta_bancaria = _crear_cuenta_bancaria(banco, tipo_cuenta, moneda)
    return {
        "cuenta_bancaria": cuenta_bancaria,
        "lote_importacion": lote_importacion,
        "tipo_operacion": tipo_operacion,
        "moneda": moneda,
    }


@pytest.fixture
def registro_interno(tipo_operacion_factory, moneda_factory):
    """Devuelve el grafo persistido de un movimiento interno válido (sin el movimiento)."""
    tipo_operacion = tipo_operacion_factory()
    moneda = moneda_factory()
    lote_importacion = _crear_lote()
    return {
        "lote_importacion": lote_importacion,
        "tipo_operacion": tipo_operacion,
        "moneda": moneda,
    }



# ---------------------------------------------------------------------------
# ``LoteImportacion``
# ---------------------------------------------------------------------------


class TestLoteImportacion:
    """Pruebas de ``LoteImportacion``: campos e identidad única de importación (FR-012)."""

    def test_fuente_es_charfield(self):
        """El campo ``fuente`` debe ser un ``CharField``."""
        campo = LoteImportacion._meta.get_field("fuente")
        assert isinstance(campo, models.CharField)

    def test_fuente_es_obligatorio(self):
        """El campo ``fuente`` no debe admitir nulos ni vacíos."""
        campo = LoteImportacion._meta.get_field("fuente")
        assert campo.null is False
        assert campo.blank is False

    def test_fecha_importacion_es_datetimefield(self):
        """El campo ``fecha_importacion`` debe ser un ``DateTimeField`` (marca de tiempo)."""
        campo = LoteImportacion._meta.get_field("fecha_importacion")
        assert isinstance(campo, models.DateTimeField)

    def test_fecha_importacion_es_obligatorio(self):
        """El campo ``fecha_importacion`` no debe admitir nulos ni vacíos."""
        campo = LoteImportacion._meta.get_field("fecha_importacion")
        assert campo.null is False
        assert campo.blank is False

    def test_identidad_de_importacion_tiene_restriccion_unica(self):
        """La identidad de importación debe ser una ``UniqueConstraint`` nombrada sobre ``fuente`` y ``fecha_importacion``."""
        restricciones = {c.name: c for c in LoteImportacion._meta.constraints}
        assert "lote_importacion_identidad_unica" in restricciones
        restriccion = restricciones["lote_importacion_identidad_unica"]
        assert isinstance(restriccion, UniqueConstraint)
        assert set(restriccion.fields) == {"fuente", "fecha_importacion"}

    @pytest.mark.django_db
    def test_importacion_duplicada_es_rechazada(self):
        """Importar dos veces el mismo lote debe rechazarse con ``IntegrityError`` (FR-012)."""
        _crear_lote()
        with pytest.raises(IntegrityError):
            _crear_lote()

    @pytest.mark.django_db
    def test_creacion_persiste_campos(self):
        """Crear un ``LoteImportacion`` persiste ``fuente`` y ``fecha_importacion``."""
        lote = _crear_lote(fuente="BANCO-Y.csv")
        persistido = LoteImportacion.objects.get(pk=lote.pk)
        assert persistido.fuente == "BANCO-Y.csv"
        assert persistido.fecha_importacion == FECHA_IMPORTACION


# ---------------------------------------------------------------------------
# ``CuentaBancaria``
# ---------------------------------------------------------------------------


class TestCuentaBancaria:
    """Pruebas de ``CuentaBancaria``: campos y relaciones con los catálogos."""

    def test_numero_cuenta_es_charfield(self):
        """El campo ``numero_cuenta`` debe ser un ``CharField``."""
        campo = CuentaBancaria._meta.get_field("numero_cuenta")
        assert isinstance(campo, models.CharField)

    def test_numero_cuenta_es_obligatorio(self):
        """El campo ``numero_cuenta`` no debe admitir nulos ni vacíos."""
        campo = CuentaBancaria._meta.get_field("numero_cuenta")
        assert campo.null is False
        assert campo.blank is False

    def test_denominacion_es_charfield(self):
        """El campo ``denominacion`` debe ser un ``CharField``."""
        campo = CuentaBancaria._meta.get_field("denominacion")
        assert isinstance(campo, models.CharField)

    def test_denominacion_es_obligatorio(self):
        """El campo ``denominacion`` no debe admitir nulos ni vacíos."""
        campo = CuentaBancaria._meta.get_field("denominacion")
        assert campo.null is False
        assert campo.blank is False

    @pytest.mark.parametrize(
        "nombre_campo, modelo_destino",
        [
            ("banco", Banco),
            ("tipo_cuenta", TipoCuenta),
            ("moneda", Moneda),
        ],
        ids=["banco", "tipo_cuenta", "moneda"],
    )
    def test_relaciones_obligatorias(self, nombre_campo, modelo_destino):
        """Cada relación debe ser una ``ForeignKey`` obligatoria hacia el modelo correcto."""
        campo = CuentaBancaria._meta.get_field(nombre_campo)
        assert campo.many_to_one is True
        assert campo.remote_field.model is modelo_destino
        assert campo.null is False

    def test_saldo_inicial_es_decimalfield(self):
        """El campo ``saldo_inicial`` debe ser un ``DecimalField`` con precisión 18,2."""
        campo = CuentaBancaria._meta.get_field("saldo_inicial")
        assert isinstance(campo, models.DecimalField)
        assert campo.max_digits == 18
        assert campo.decimal_places == 2

    @pytest.mark.django_db
    def test_creacion_persiste_campos(self, banco_factory, tipo_cuenta_factory, moneda_factory):
        """Crear una ``CuentaBancaria`` persiste campos y relaciones."""
        banco = banco_factory()
        tipo_cuenta = tipo_cuenta_factory()
        moneda = moneda_factory()
        cuenta = _crear_cuenta_bancaria(
            banco, tipo_cuenta, moneda,
            numero_cuenta="9876-5432-1000", denominacion="Cuenta Ahorro",
        )
        persistida = CuentaBancaria.objects.get(pk=cuenta.pk)
        assert persistida.numero_cuenta == "9876-5432-1000"
        assert persistida.denominacion == "Cuenta Ahorro"
        assert persistida.saldo_inicial == Decimal("0.00")
        assert persistida.banco_id == banco.pk
        assert persistida.tipo_cuenta_id == tipo_cuenta.pk
        assert persistida.moneda_id == moneda.pk


# ---------------------------------------------------------------------------
# ``MovimientoBancario``
# ---------------------------------------------------------------------------


class TestMovimientoBancario:
    """Pruebas de ``MovimientoBancario``: dinero decimal, ``en_consulta``, notas y FK."""

    def test_importe_es_decimal_field(self):
        """El campo ``importe`` debe ser un ``DecimalField``."""
        campo = MovimientoBancario._meta.get_field("importe")
        assert isinstance(campo, models.DecimalField)

    def test_importe_no_es_float_field(self):
        """El campo ``importe`` nunca debe ser un ``FloatField`` (FR-007)."""
        campo = MovimientoBancario._meta.get_field("importe")
        assert not isinstance(campo, models.FloatField)

    def test_importe_tiene_precision_19_digitos_8_decimales(self):
        """El campo ``importe`` debe tener ``max_digits=19`` y ``decimal_places=8``."""
        campo = MovimientoBancario._meta.get_field("importe")
        assert campo.max_digits == 19
        assert campo.decimal_places == 8

    def test_importe_es_obligatorio(self):
        """El campo ``importe`` no debe admitir nulos ni vacíos."""
        campo = MovimientoBancario._meta.get_field("importe")
        assert campo.null is False
        assert campo.blank is False

    def test_fecha_es_datefield(self):
        """El campo ``fecha`` debe ser un ``DateField``."""
        campo = MovimientoBancario._meta.get_field("fecha")
        assert isinstance(campo, models.DateField)

    def test_fecha_es_obligatorio(self):
        """El campo ``fecha`` no debe admitir nulos ni vacíos."""
        campo = MovimientoBancario._meta.get_field("fecha")
        assert campo.null is False
        assert campo.blank is False

    def test_notas_es_textfield_opcional(self):
        """El campo ``notas`` debe ser un ``TextField`` opcional (null/blank)."""
        campo = MovimientoBancario._meta.get_field("notas")
        assert isinstance(campo, models.TextField)
        assert campo.null is True
        assert campo.blank is True

    def test_en_consulta_es_booleano_con_por_defecto_false(self):
        """El campo ``en_consulta`` debe ser ``BooleanField`` con valor por defecto ``False``."""
        campo = MovimientoBancario._meta.get_field("en_consulta")
        assert isinstance(campo, models.BooleanField)
        assert campo.default is False

    def test_en_consulta_es_false_en_instancia_nueva(self):
        """Una instancia nueva de ``MovimientoBancario`` tiene ``en_consulta`` en ``False``."""
        instancia = MovimientoBancario()
        assert instancia.en_consulta is False

    @pytest.mark.parametrize(
        "nombre_campo, modelo_destino",
        [
            ("cuenta_bancaria", CuentaBancaria),
            ("lote_importacion", LoteImportacion),
            ("tipo_operacion", TipoOperacion),
            ("moneda", Moneda),
        ],
        ids=["cuenta_bancaria", "lote_importacion", "tipo_operacion", "moneda"],
    )
    def test_relaciones_obligatorias(self, nombre_campo, modelo_destino):
        """Cada relación debe ser una ``ForeignKey`` obligatoria hacia el modelo correcto."""
        campo = MovimientoBancario._meta.get_field(nombre_campo)
        assert campo.many_to_one is True
        assert campo.remote_field.model is modelo_destino
        assert campo.null is False

    def test_lote_importacion_es_obligatorio(self):
        """Todo ``MovimientoBancario`` debe trazarse a exactamente un ``LoteImportacion`` (FR-004)."""
        campo = MovimientoBancario._meta.get_field("lote_importacion")
        assert campo.null is False
        assert campo.blank is False

    def test_restriccion_importe_no_negativo(self):
        """``importe >= 0`` debe expresarse con un ``CheckConstraint(condition=Q(...))`` nombrado."""
        restricciones = {c.name: c for c in MovimientoBancario._meta.constraints}
        assert "movimiento_bancario_importe_no_negativo" in restricciones
        restriccion = restricciones["movimiento_bancario_importe_no_negativo"]
        assert isinstance(restriccion, CheckConstraint)
        assert restriccion.condition == Q(importe__gte=0)


    @pytest.mark.django_db
    def test_importe_negativo_falla_la_validacion(self, registro_bancario):
        """Un ``importe`` negativo no supera la validación del modelo."""
        movimiento = MovimientoBancario(
            importe=Decimal("-1.00"),
            fecha=FECHA_MOVIMIENTO,
            **registro_bancario,
        )
        with pytest.raises(ValidationError):
            movimiento.full_clean()

    @pytest.mark.django_db
    def test_importe_negativo_es_rechazado_por_la_base_de_datos(self, registro_bancario):
        """Un ``importe`` negativo es rechazado por la base de datos con ``IntegrityError``."""
        with pytest.raises(IntegrityError):
            _crear_movimiento_bancario(
                **registro_bancario,
                importe=Decimal("-1.00"),
            )

    @pytest.mark.django_db
    def test_asignar_float_al_importe_lanza_error_de_tipo_o_validacion(self, registro_bancario):
        """Asignar un ``float`` al ``importe`` debe lanzar un error de tipo o de validación."""
        with pytest.raises((ValidationError, TypeError)):
            movimiento = MovimientoBancario(
                importe=1500.75,
                fecha=FECHA_MOVIMIENTO,
                **registro_bancario,
            )
            movimiento.full_clean()

    @pytest.mark.django_db
    def test_importe_decimal_es_aceptado(self, registro_bancario):
        """Un ``importe`` expresado como ``decimal.Decimal`` se persiste con exactitud."""
        movimiento = _crear_movimiento_bancario(
            **registro_bancario,
            importe=Decimal("1500.75"),
        )
        persistido = MovimientoBancario.objects.get(pk=movimiento.pk)
        assert persistido.importe == Decimal("1500.75")

    @pytest.mark.django_db
    def test_en_consulta_es_false_por_defecto_al_crear(self, registro_bancario):
        """Crear un ``MovimientoBancario`` sin ``en_consulta`` lo deja en ``False``."""
        movimiento = _crear_movimiento_bancario(**registro_bancario)
        assert movimiento.en_consulta is False

    @pytest.mark.django_db
    def test_en_consulta_se_persiste(self, registro_bancario):
        """El flag ``en_consulta`` en ``True`` se persiste (FR-013)."""
        movimiento = _crear_movimiento_bancario(**registro_bancario, en_consulta=True)
        persistido = MovimientoBancario.objects.get(pk=movimiento.pk)
        assert persistido.en_consulta is True

    @pytest.mark.django_db
    def test_notas_es_opcional_y_se_persiste(self, registro_bancario):
        """Las ``notas`` opcionales se persisten como texto libre (FR-014)."""
        movimiento = _crear_movimiento_bancario(**registro_bancario, notas="Revisar comprobante")
        persistido = MovimientoBancario.objects.get(pk=movimiento.pk)
        assert persistido.notas == "Revisar comprobante"

    @pytest.mark.django_db
    def test_moneda_distinta_a_la_de_la_cuenta_falla_la_validacion(
        self, banco_factory, tipo_cuenta_factory, moneda_factory, tipo_operacion_factory
    ):
        """La moneda del movimiento debe coincidir con la de su cuenta (falla si difiere)."""
        banco = banco_factory()
        tipo_cuenta = tipo_cuenta_factory()
        moneda_cuenta = moneda_factory(codigo="USD")
        moneda_movimiento = moneda_factory(codigo="EUR")
        tipo_operacion = tipo_operacion_factory()
        lote_importacion = _crear_lote()
        cuenta_bancaria = _crear_cuenta_bancaria(banco, tipo_cuenta, moneda_cuenta)
        movimiento = MovimientoBancario(
            importe=Decimal("100.00"),
            fecha=FECHA_MOVIMIENTO,
            cuenta_bancaria=cuenta_bancaria,
            lote_importacion=lote_importacion,
            tipo_operacion=tipo_operacion,
            moneda=moneda_movimiento,
        )
        with pytest.raises(ValidationError):
            movimiento.full_clean()

    @pytest.mark.django_db
    def test_moneda_coincidente_con_la_cuenta_es_valida(self, registro_bancario):
        """La moneda del movimiento igual a la de su cuenta supera la validación."""
        movimiento = MovimientoBancario(
            importe=Decimal("100.00"),
            fecha=FECHA_MOVIMIENTO,
            **registro_bancario,
        )
        movimiento.full_clean()  # no debe lanzar ValidationError

    @pytest.mark.django_db
    def test_creacion_persiste_campos(self, registro_bancario):
        """Crear un ``MovimientoBancario`` persiste importe, fecha, notas y relaciones."""
        movimiento = _crear_movimiento_bancario(
            **registro_bancario,
            importe=Decimal("1234.56"),
            notas="Post-it",
        )
        persistido = MovimientoBancario.objects.get(pk=movimiento.pk)
        assert persistido.importe == Decimal("1234.56")
        assert persistido.fecha == FECHA_MOVIMIENTO
        assert persistido.notas == "Post-it"
        assert persistido.en_consulta is False
        assert persistido.cuenta_bancaria_id == registro_bancario["cuenta_bancaria"].pk
        assert persistido.lote_importacion_id == registro_bancario["lote_importacion"].pk
        assert persistido.tipo_operacion_id == registro_bancario["tipo_operacion"].pk
        assert persistido.moneda_id == registro_bancario["moneda"].pk



# ---------------------------------------------------------------------------
# ``MovimientoInterno``
# ---------------------------------------------------------------------------


class TestMovimientoInterno:
    """Pruebas de ``MovimientoInterno``: dinero decimal, notas y FK (sin ``en_consulta`` ni cuenta)."""

    def test_importe_es_decimal_field(self):
        """El campo ``importe`` debe ser un ``DecimalField``."""
        campo = MovimientoInterno._meta.get_field("importe")
        assert isinstance(campo, models.DecimalField)

    def test_importe_no_es_float_field(self):
        """El campo ``importe`` nunca debe ser un ``FloatField`` (FR-007)."""
        campo = MovimientoInterno._meta.get_field("importe")
        assert not isinstance(campo, models.FloatField)

    def test_importe_tiene_precision_19_digitos_8_decimales(self):
        """El campo ``importe`` debe tener ``max_digits=19`` y ``decimal_places=8``."""
        campo = MovimientoInterno._meta.get_field("importe")
        assert campo.max_digits == 19
        assert campo.decimal_places == 8

    def test_importe_es_obligatorio(self):
        """El campo ``importe`` no debe admitir nulos ni vacíos."""
        campo = MovimientoInterno._meta.get_field("importe")
        assert campo.null is False
        assert campo.blank is False

    def test_fecha_es_datefield(self):
        """El campo ``fecha`` debe ser un ``DateField``."""
        campo = MovimientoInterno._meta.get_field("fecha")
        assert isinstance(campo, models.DateField)

    def test_fecha_es_obligatorio(self):
        """El campo ``fecha`` no debe admitir nulos ni vacíos."""
        campo = MovimientoInterno._meta.get_field("fecha")
        assert campo.null is False
        assert campo.blank is False

    def test_notas_es_textfield_opcional(self):
        """El campo ``notas`` debe ser un ``TextField`` opcional (null/blank)."""
        campo = MovimientoInterno._meta.get_field("notas")
        assert isinstance(campo, models.TextField)
        assert campo.null is True
        assert campo.blank is True

    def test_no_tiene_relacion_con_cuenta_bancaria(self):
        """``MovimientoInterno`` no debe tener relación con ``CuentaBancaria``."""
        with pytest.raises(FieldDoesNotExist):
            MovimientoInterno._meta.get_field("cuenta_bancaria")

    def test_no_tiene_flag_en_consulta(self):
        """``MovimientoInterno`` no debe tener el flag ``en_consulta``."""
        with pytest.raises(FieldDoesNotExist):
            MovimientoInterno._meta.get_field("en_consulta")

    @pytest.mark.parametrize(
        "nombre_campo, modelo_destino",
        [
            ("lote_importacion", LoteImportacion),
            ("tipo_operacion", TipoOperacion),
            ("moneda", Moneda),
        ],
        ids=["lote_importacion", "tipo_operacion", "moneda"],
    )
    def test_relaciones_obligatorias(self, nombre_campo, modelo_destino):
        """Cada relación debe ser una ``ForeignKey`` obligatoria hacia el modelo correcto."""
        campo = MovimientoInterno._meta.get_field(nombre_campo)
        assert campo.many_to_one is True
        assert campo.remote_field.model is modelo_destino
        assert campo.null is False

    def test_lote_importacion_es_obligatorio(self):
        """Todo ``MovimientoInterno`` debe trazarse a exactamente un ``LoteImportacion`` (FR-004)."""
        campo = MovimientoInterno._meta.get_field("lote_importacion")
        assert campo.null is False
        assert campo.blank is False

    def test_restriccion_importe_no_negativo(self):
        """``importe >= 0`` debe expresarse con un ``CheckConstraint(condition=Q(...))`` nombrado."""
        restricciones = {c.name: c for c in MovimientoInterno._meta.constraints}
        assert "movimiento_interno_importe_no_negativo" in restricciones
        restriccion = restricciones["movimiento_interno_importe_no_negativo"]
        assert isinstance(restriccion, CheckConstraint)
        assert restriccion.condition == Q(importe__gte=0)


    @pytest.mark.django_db
    def test_importe_negativo_falla_la_validacion(self, registro_interno):
        """Un ``importe`` negativo no supera la validación del modelo."""
        movimiento = MovimientoInterno(
            importe=Decimal("-1.00"),
            fecha=FECHA_MOVIMIENTO,
            **registro_interno,
        )
        with pytest.raises(ValidationError):
            movimiento.full_clean()

    @pytest.mark.django_db
    def test_importe_negativo_es_rechazado_por_la_base_de_datos(self, registro_interno):
        """Un ``importe`` negativo es rechazado por la base de datos con ``IntegrityError``."""
        with pytest.raises(IntegrityError):
            _crear_movimiento_interno(
                **registro_interno,
                importe=Decimal("-1.00"),
            )

    @pytest.mark.django_db
    def test_asignar_float_al_importe_lanza_error_de_tipo_o_validacion(self, registro_interno):
        """Asignar un ``float`` al ``importe`` debe lanzar un error de tipo o de validación."""
        with pytest.raises((ValidationError, TypeError)):
            movimiento = MovimientoInterno(
                importe=1500.75,
                fecha=FECHA_MOVIMIENTO,
                **registro_interno,
            )
            movimiento.full_clean()

    @pytest.mark.django_db
    def test_importe_decimal_es_aceptado(self, registro_interno):
        """Un ``importe`` expresado como ``decimal.Decimal`` se persiste con exactitud."""
        movimiento = _crear_movimiento_interno(
            **registro_interno,
            importe=Decimal("1500.75"),
        )
        persistido = MovimientoInterno.objects.get(pk=movimiento.pk)
        assert persistido.importe == Decimal("1500.75")

    @pytest.mark.django_db
    def test_notas_es_opcional_y_se_persiste(self, registro_interno):
        """Las ``notas`` opcionales se persisten como texto libre (FR-014)."""
        movimiento = _crear_movimiento_interno(**registro_interno, notas="Conciliar con ventas")
        persistido = MovimientoInterno.objects.get(pk=movimiento.pk)
        assert persistido.notas == "Conciliar con ventas"

    @pytest.mark.django_db
    def test_creacion_persiste_campos(self, registro_interno):
        """Crear un ``MovimientoInterno`` persiste importe, fecha, notas y relaciones."""
        movimiento = _crear_movimiento_interno(
            **registro_interno,
            importe=Decimal("987.65"),
            notas="Post-it interno",
        )
        persistido = MovimientoInterno.objects.get(pk=movimiento.pk)
        assert persistido.importe == Decimal("987.65")
        assert persistido.fecha == FECHA_MOVIMIENTO
        assert persistido.notas == "Post-it interno"
        assert persistido.lote_importacion_id == registro_interno["lote_importacion"].pk
        assert persistido.tipo_operacion_id == registro_interno["tipo_operacion"].pk
        assert persistido.moneda_id == registro_interno["moneda"].pk

