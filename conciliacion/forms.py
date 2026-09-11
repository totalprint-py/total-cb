"""Formularios del motor de conciliación (Fase 6 — GREEN).

``ModelForm`` delgados para los catálogos y para las operaciones de apoyo
``notas`` y ``en_consulta``. La lógica de negocio permanece en
``conciliacion/services.py``; estos formularios solo definen los campos
editables y sus etiquetas en español.
"""
from __future__ import annotations

from django import forms

from conciliacion.models import (
    Banco,
    ConceptoAjuste,
    CuentaBancaria,
    Moneda,
    MovimientoBancario,
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
            "saldo_inicial": forms.NumberInput(
                attrs={"class": CLASES_CAMPO, "step": "0.01"}
            ),
        }


class MovimientoLibroForm(forms.ModelForm):
    """Formulario para registrar un movimiento del libro mayor."""

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
                attrs={"class": CLASES_CAMPO, "type": "date", "autofocus": "autofocus"}
            ),
            "tipo_operacion": forms.Select(attrs={"class": "form-select"}),
            "detalle": forms.TextInput(attrs={"class": CLASES_CAMPO}),
            "debe": forms.NumberInput(
                attrs={"class": CLASES_CAMPO, "step": "0.01", "inputmode": "decimal"}
            ),
            "haber": forms.NumberInput(
                attrs={"class": CLASES_CAMPO, "step": "0.01", "inputmode": "decimal"}
            ),
        }

    def clean(self):
        """Valida FR-007: importes no negativos y al menos uno no cero."""
        cleaned_data = super().clean()
        debe = cleaned_data.get("debe")
        haber = cleaned_data.get("haber")

        if debe is not None and debe < 0:
            self.add_error("debe", "El debe no puede ser negativo.")
        if haber is not None and haber < 0:
            self.add_error("haber", "El haber no puede ser negativo.")

        # Solo verificar "ambos en cero" si ambos están presentes y no son negativos
        if (
            debe is not None
            and haber is not None
            and debe >= 0
            and haber >= 0
            and debe == 0
            and haber == 0
        ):
            raise forms.ValidationError(
                "Debe indicar un importe en el debe o en el haber."
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