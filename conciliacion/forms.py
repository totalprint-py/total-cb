"""Formularios del motor de conciliación (Fase 6 — GREEN).

``ModelForm`` delgados para los catálogos y para las operaciones de apoyo
``notas`` y ``en_consulta``. La lógica de negocio permanece en
``conciliacion/services.py``; estos formularios solo definen los campos
editables y sus etiquetas en español.
"""
from __future__ import annotations

from decimal import Decimal

from django import forms

from conciliacion.models import (
    Banco,
    ConceptoAjuste,
    CuentaBancaria,
    Moneda,
    MovimientoBancario,
    MovimientoExtracto,
    MovimientoInterno,
    MovimientoLibro,
    TipoCuenta,
    TipoOperacion,
)


# Clase CSS compartida por los controles de los formularios de catálogo.
CLASES_CAMPO = "form-control"


class BancoForm(forms.ModelForm):
    """Formulario para el catálogo de bancos."""

    class Meta:
        model = Banco
        fields = ["nombre"]
        labels = {
            "nombre": "Nombre",
        }
        widgets = {
            "nombre": forms.TextInput(attrs={"class": CLASES_CAMPO}),
        }


class TipoCuentaForm(forms.ModelForm):
    """Formulario para el catálogo de tipos de cuenta."""

    class Meta:
        model = TipoCuenta
        fields = ["nombre"]
        labels = {
            "nombre": "Nombre",
        }
        widgets = {
            "nombre": forms.TextInput(attrs={"class": CLASES_CAMPO}),
        }


class MonedaForm(forms.ModelForm):
    """Formulario para el catálogo de monedas."""

    class Meta:
        model = Moneda
        fields = ["nombre", "cantidad_decimales"]
        labels = {
            "nombre": "Nombre",
            "cantidad_decimales": "Cantidad de decimales",
        }
        widgets = {
            "nombre": forms.TextInput(attrs={"class": CLASES_CAMPO}),
            "cantidad_decimales": forms.NumberInput(
                attrs={"class": CLASES_CAMPO, "min": "0"}
            ),
        }


class TipoOperacionForm(forms.ModelForm):
    """Formulario para el catálogo de tipos de operación."""

    class Meta:
        model = TipoOperacion
        fields = ["nombre"]
        labels = {
            "nombre": "Nombre",
        }
        widgets = {
            "nombre": forms.TextInput(attrs={"class": CLASES_CAMPO}),
        }


class ConceptoAjusteForm(forms.ModelForm):
    """Formulario para el catálogo de conceptos de ajuste."""

    class Meta:
        model = ConceptoAjuste
        fields = ["nombre"]
        labels = {
            "nombre": "Nombre",
        }
        widgets = {
            "nombre": forms.TextInput(attrs={"class": CLASES_CAMPO}),
        }


class CuentaBancariaForm(forms.ModelForm):
    """Formulario para las cuentas bancarias."""

    saldo_inicial = forms.DecimalField(
        max_digits=18,
        decimal_places=2,
        localize=True,
        widget=forms.TextInput(
            attrs={"class": CLASES_CAMPO, "inputmode": "decimal"}
        ),
    )

    class Meta:
        model = CuentaBancaria
        fields = [
            "banco",
            "tipo_cuenta",
            "moneda",
            "numero_cuenta",
            "denominacion",
            "saldo_inicial",
        ]
        labels = {
            "banco": "Banco",
            "tipo_cuenta": "Tipo de cuenta",
            "moneda": "Moneda",
            "numero_cuenta": "Número de cuenta",
            "denominacion": "Denominación",
            "saldo_inicial": "Saldo inicial",
        }
        widgets = {
            "banco": forms.Select(attrs={"class": "form-select"}),
            "tipo_cuenta": forms.Select(attrs={"class": "form-select"}),
            "moneda": forms.Select(attrs={"class": "form-select"}),
            "numero_cuenta": forms.TextInput(attrs={"class": CLASES_CAMPO}),
            "denominacion": forms.TextInput(attrs={"class": CLASES_CAMPO}),
        }


class MovimientoLibroForm(forms.ModelForm):
    """Formulario para registrar un movimiento del libro mayor."""

    debe = forms.DecimalField(
        max_digits=18,
        decimal_places=2,
        localize=True,
        required=False,
        widget=forms.TextInput(
            attrs={"class": CLASES_CAMPO, "inputmode": "decimal"}
        ),
    )
    haber = forms.DecimalField(
        max_digits=18,
        decimal_places=2,
        localize=True,
        required=False,
        widget=forms.TextInput(
            attrs={"class": CLASES_CAMPO, "inputmode": "decimal"}
        ),
    )

    class Meta:
        model = MovimientoLibro
        fields = ["fecha", "tipo_operacion", "detalle", "debe", "haber"]
        labels = {
            "fecha": "Fecha",
            "tipo_operacion": "Tipo de operación",
            "detalle": "Detalle",
            "debe": "Debe",
            "haber": "Haber",
        }
        widgets = {
            "fecha": forms.DateInput(
                format="%Y-%m-%d",
                attrs={"class": CLASES_CAMPO, "type": "date", "autofocus": "autofocus"},
            ),
            "tipo_operacion": forms.Select(attrs={"class": "form-select"}),
            "detalle": forms.TextInput(attrs={"class": CLASES_CAMPO}),
        }

    def clean(self):
        """Valida FR-007: importes no negativos, al menos uno no cero y
        exclusión mutua entre ``debe`` y ``haber``.

        Los importes en blanco se interpretan como ``0.00`` (campos
        ``required=False``) para permitir cargar el movimiento indicando una
        sola de las dos columnas.
        """
        cleaned_data = super().clean()
        debe = cleaned_data.get("debe")
        haber = cleaned_data.get("haber")

        # Los campos en blanco llegan como ``None`` a ``cleaned_data``; se
        # convierten a ``0.00``. Si un campo no está presente en ``cleaned_data``
        # es porque ``super().clean()`` ya registró un error de conversión.
        for nombre in ("debe", "haber"):
            if nombre in cleaned_data and cleaned_data[nombre] is None:
                cleaned_data[nombre] = Decimal("0.00")

        debe = cleaned_data.get("debe")
        haber = cleaned_data.get("haber")
        if debe is None or haber is None:
            return cleaned_data

        if debe < 0:
            self.add_error("debe", "El debe no puede ser negativo.")
        if haber < 0:
            self.add_error("haber", "El haber no puede ser negativo.")

        # Solo verificar "ambos en cero" si ambos no son negativos.
        if debe >= 0 and haber >= 0 and debe == 0 and haber == 0:
            raise forms.ValidationError(
                "Debe indicar un importe en el debe o en el haber."
            )

        # Exclusión mutua: no puede haber importe positivo en ambas columnas.
        if debe > 0 and haber > 0:
            raise forms.ValidationError(
                "Solo puede cargar un valor en Debe o en Haber, no en ambos."
            )

        return cleaned_data


class CrearAsientoExtractoForm(forms.ModelForm):
    """Formulario de solo lectura para convertir un extracto en asiento.

    ``debe``/``haber`` vienen precargados con el signo ya mapeado desde la
    vista; el usuario confirma y el POST invoca ``crear_asiento_desde_extracto``.
    """

    class Meta:
        model = MovimientoLibro
        fields = ["fecha", "detalle", "debe", "haber"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            campo.disabled = True


class ExtractoImportarForm(forms.Form):
    """Formulario de carga de extractos bancarios (``cuenta`` + ``archivo``)."""

    cuenta = forms.ModelChoiceField(
        queryset=CuentaBancaria.objects.all(),
        label="Cuenta bancaria",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    archivo = forms.FileField(
        label="Archivo",
        widget=forms.ClearableFileInput(attrs={"class": CLASES_CAMPO}),
    )


class MovimientoExtractoForm(forms.ModelForm):
    """Formulario de alta/edición manual de movimientos del extracto bancario."""

    class Meta:
        model = MovimientoExtracto
        fields = ["cuenta_bancaria", "fecha", "referencia", "detalle", "importe"]
        labels = {
            "cuenta_bancaria": "Cuenta bancaria",
            "fecha": "Fecha",
            "referencia": "Referencia",
            "detalle": "Detalle",
            "importe": "Importe",
        }
        widgets = {
            "cuenta_bancaria": forms.Select(attrs={"class": "form-select"}),
            "fecha": forms.DateInput(
                format="%Y-%m-%d",
                attrs={"class": CLASES_CAMPO, "type": "date"},
            ),
            "referencia": forms.TextInput(attrs={"class": CLASES_CAMPO}),
            "detalle": forms.TextInput(attrs={"class": CLASES_CAMPO}),
            "importe": forms.TextInput(
                attrs={"class": CLASES_CAMPO, "inputmode": "decimal"}
            ),
        }

    def clean(self):
        """Valida que el ``importe`` sea ``Decimal`` (nunca ``float``) y no cero."""
        cleaned_data = super().clean()
        importe = cleaned_data.get("importe")
        if isinstance(importe, float):
            raise forms.ValidationError(
                "Los importes monetarios no admiten float; use decimal.Decimal."
            )
        if importe is not None and importe == 0:
            raise forms.ValidationError("El importe no puede ser cero.")
        return cleaned_data


class ReporteLibroForm(forms.Form):
    """Formulario de filtros del Reporte del Libro Bancario (Fase 3 — GREEN).

    Expone los tres filtros del contrato HTTP (``contracts/http-api.md``):
    ``cuenta`` (selector de cuentas), ``desde`` y ``hasta`` (rango inclusivo de
    fechas). La validación de ``desde > hasta`` (FR-008) se registra como error
    no asociado a campo para mostrarse en línea en español.
    """

    cuenta = forms.ModelChoiceField(
        queryset=CuentaBancaria.objects.all(),
        label="Cuenta",
        empty_label="— Seleccione una cuenta —",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    desde = forms.DateField(
        label="Desde",
        widget=forms.DateInput(
            format="%Y-%m-%d",
            attrs={"class": CLASES_CAMPO, "type": "date"},
        ),
    )
    hasta = forms.DateField(
        label="Hasta",
        widget=forms.DateInput(
            format="%Y-%m-%d",
            attrs={"class": CLASES_CAMPO, "type": "date"},
        ),
    )

    def clean(self):
        """Valida que ``desde`` no sea posterior a ``hasta`` (FR-008)."""
        cleaned_data = super().clean()
        desde = cleaned_data.get("desde")
        hasta = cleaned_data.get("hasta")
        if desde and hasta and desde > hasta:
            raise forms.ValidationError(
                "La fecha 'desde' no puede ser posterior a la fecha 'hasta'."
            )
        return cleaned_data


class NotaMovimientoBancarioForm(forms.ModelForm):
    """Formulario de nota de texto libre para un movimiento bancario."""

    class Meta:
        model = MovimientoBancario
        fields = ["notas"]


class NotaMovimientoInternoForm(forms.ModelForm):
    """Formulario de nota de texto libre para un movimiento interno."""

    class Meta:
        model = MovimientoInterno
        fields = ["notas"]


class EnConsultaMovimientoForm(forms.ModelForm):
    """Formulario para activar/desactivar la bandera "En Consulta"."""

    class Meta:
        model = MovimientoBancario
        fields = ["en_consulta"]