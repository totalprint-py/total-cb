"""Adaptadores HTTP delgados del motor de conciliación (Fase 6 — GREEN).

Cada vista delega toda la lógica de dominio en ``conciliacion.services``;
aquí solo se parsean/validan parámetros HTTP, se invoca al servicio
correspondiente y se decide el código de respuesta (200/302/400).

Convenciones (contrato con ``tests/unit/test_vistas.py``):

* Nombres de URL: ``tablero``, ``reporte_manual``, ``emparejar_movimientos``,
  ``comprometer_conciliacion`` y ``revertir_conciliacion``.
* Claves de contexto del tablero: ``movimientos_bancarios`` y
  ``movimientos_internos`` (solo movimientos sin conciliar).
* Plantillas: ``conciliacion/matcher.html`` y
  ``conciliacion/reporte_manual.html``.
* Acciones POST exitosas → redirección 302; errores de dominio tipados
  (``AmountMismatchError`` / ``ZeroSumError``) → respuesta 400.

Toda la interfaz, los mensajes y los nombres están en español.
"""
from __future__ import annotations

from decimal import Decimal

from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.views.generic import CreateView, ListView, UpdateView

from conciliacion.forms import (
    BancoForm,
    ConceptoAjusteForm,
    CuentaBancariaForm,
    MovimientoLibroForm,
    MonedaForm,
    TipoCuentaForm,
    TipoOperacionForm,
)
from conciliacion.models import (
    Banco,
    ConceptoAjuste,
    Conciliacion,
    CuentaBancaria,
    DetalleConciliacionBancaria,
    DetalleConciliacionInterna,
    Moneda,
    MovimientoBancario,
    MovimientoInterno,
    MovimientoLibro,
    TipoCuenta,
    TipoOperacion,
)
from conciliacion.services import (
    AmountMismatchError,
    ZeroSumError,
    commit_reconciliation,
    match_movimientos,
    revert_conciliacion,
)


def _movimientos_bancarios_sin_conciliar():
    """Devuelve los ``MovimientoBancario`` que no tienen detalle de conciliación."""
    return MovimientoBancario.objects.exclude(
        pk__in=DetalleConciliacionBancaria.objects.values_list(
            "movimiento_bancario_id", flat=True
        )
    )


def _movimientos_internos_sin_conciliar():
    """Devuelve los ``MovimientoInterno`` que no tienen detalle de conciliación."""
    return MovimientoInterno.objects.exclude(
        pk__in=DetalleConciliacionInterna.objects.values_list(
            "movimiento_interno_id", flat=True
        )
    )


def tablero(request):
    """Pantalla dividida: bancarios vs. internos sin conciliar (FR-016)."""
    contexto = {
        "movimientos_bancarios": _movimientos_bancarios_sin_conciliar(),
        "movimientos_internos": _movimientos_internos_sin_conciliar(),
    }
    return render(request, "conciliacion/matcher.html", contexto)


def reporte_manual(request):
    """Reporte de Verificación Manual optimizado para impresión (FR-017)."""
    contexto = {
        "movimientos_bancarios": _movimientos_bancarios_sin_conciliar(),
        "movimientos_internos": _movimientos_internos_sin_conciliar(),
    }
    return render(request, "conciliacion/reporte_manual.html", contexto)


def emparejar_movimientos(request):
    """Endpoint POST que delega en ``match_movimientos`` (FR-015)."""
    if request.method != "POST":
        return HttpResponse(status=405)

    bancario_id = request.POST.get("bancario_id")
    interno_id = request.POST.get("interno_id")
    bancario = get_object_or_404(MovimientoBancario, pk=bancario_id)
    interno = get_object_or_404(MovimientoInterno, pk=interno_id)

    try:
        match_movimientos(bancario=bancario, interno=interno)
    except AmountMismatchError:
        return HttpResponse(
            "No se puede emparejar: los importes no coinciden.",
            status=400,
        )

    return redirect("tablero")


def comprometer_conciliacion(request):
    """Endpoint POST que delega en ``commit_reconciliation`` (FR-006)."""
    if request.method != "POST":
        return HttpResponse(status=405)

    conciliacion_id = request.POST.get("conciliacion_id")
    conciliacion = get_object_or_404(Conciliacion, pk=conciliacion_id)

    try:
        commit_reconciliation(conciliacion=conciliacion)
    except ZeroSumError:
        return HttpResponse(
            "No se puede comprometer: la ecuación de suma cero no se cumple.",
            status=400,
        )

    return redirect("tablero")


def revertir_conciliacion(request):
    """Endpoint POST que delega en ``revert_conciliacion`` (FR-010)."""
    if request.method != "POST":
        return HttpResponse(status=405)

    conciliacion_id = request.POST.get("conciliacion_id")
    conciliacion = get_object_or_404(Conciliacion, pk=conciliacion_id)

    revert_conciliacion(conciliacion=conciliacion)
    return redirect("tablero")


# ---------------------------------------------------------------------------
# Vistas CRUD de los catálogos auxiliares.
#
# Cada catálogo expone tres vistas basadas en clase: ``ListView`` (lectura),
# ``CreateView`` (alta) y ``UpdateView`` (edición). Reutilizan los
# ``ModelForm`` declarados en ``forms.py`` y resuelven sus plantillas por
# convención de Django: ``conciliacion/<modelo>_list.html`` y
# ``conciliacion/<modelo>_form.html``.
# ---------------------------------------------------------------------------


class BancoListView(ListView):
    """Lista los bancos del catálogo (modo creación maestro-detalle)."""

    model = Banco
    context_object_name = "bancos"
    ordering = ["codigo"]

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["form"] = BancoForm()
        return contexto


class BancoCreateView(CreateView):
    """Crea un banco nuevo en el catálogo."""

    model = Banco
    form_class = BancoForm
    success_url = reverse_lazy("banco_list")


class BancoUpdateView(UpdateView):
    """Edita un banco existente del catálogo (modo edición maestro-detalle)."""

    model = Banco
    form_class = BancoForm
    success_url = reverse_lazy("banco_list")

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["object_list"] = Banco.objects.all()
        return contexto


class TipoCuentaListView(ListView):
    """Lista los tipos de cuenta del catálogo (modo creación maestro-detalle)."""

    model = TipoCuenta
    context_object_name = "tipos_cuenta"
    ordering = ["codigo"]

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["form"] = TipoCuentaForm()
        return contexto


class TipoCuentaCreateView(CreateView):
    """Crea un tipo de cuenta nuevo en el catálogo."""

    model = TipoCuenta
    form_class = TipoCuentaForm
    success_url = reverse_lazy("tipocuenta_list")


class TipoCuentaUpdateView(UpdateView):
    """Edita un tipo de cuenta existente del catálogo (modo edición maestro-detalle)."""

    model = TipoCuenta
    form_class = TipoCuentaForm
    success_url = reverse_lazy("tipocuenta_list")

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["object_list"] = TipoCuenta.objects.all()
        return contexto


class MonedaListView(ListView):
    """Lista las monedas del catálogo (modo creación maestro-detalle)."""

    model = Moneda
    context_object_name = "monedas"
    ordering = ["codigo"]

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["form"] = MonedaForm()
        return contexto


class MonedaCreateView(CreateView):
    """Crea una moneda nueva en el catálogo."""

    model = Moneda
    form_class = MonedaForm
    success_url = reverse_lazy("moneda_list")


class MonedaUpdateView(UpdateView):
    """Edita una moneda existente del catálogo (modo edición maestro-detalle)."""

    model = Moneda
    form_class = MonedaForm
    success_url = reverse_lazy("moneda_list")

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["object_list"] = Moneda.objects.all()
        return contexto


class TipoOperacionListView(ListView):
    """Lista los tipos de operación del catálogo (modo creación maestro-detalle)."""

    model = TipoOperacion
    context_object_name = "tipos_operacion"
    ordering = ["codigo"]

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["form"] = TipoOperacionForm()
        return contexto


class TipoOperacionCreateView(CreateView):
    """Crea un tipo de operación nuevo en el catálogo."""

    model = TipoOperacion
    form_class = TipoOperacionForm
    success_url = reverse_lazy("tipooperacion_list")


class TipoOperacionUpdateView(UpdateView):
    """Edita un tipo de operación existente del catálogo (modo edición maestro-detalle)."""

    model = TipoOperacion
    form_class = TipoOperacionForm
    success_url = reverse_lazy("tipooperacion_list")

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["object_list"] = TipoOperacion.objects.all()
        return contexto


class ConceptoAjusteListView(ListView):
    """Lista los conceptos de ajuste del catálogo (modo creación maestro-detalle)."""

    model = ConceptoAjuste
    context_object_name = "conceptos_ajuste"
    ordering = ["codigo"]

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["form"] = ConceptoAjusteForm()
        return contexto


class ConceptoAjusteCreateView(CreateView):
    """Crea un concepto de ajuste nuevo en el catálogo."""

    model = ConceptoAjuste
    form_class = ConceptoAjusteForm
    success_url = reverse_lazy("conceptoajuste_list")


class ConceptoAjusteUpdateView(UpdateView):
    """Edita un concepto de ajuste existente del catálogo (modo edición maestro-detalle)."""

    model = ConceptoAjuste
    form_class = ConceptoAjusteForm
    success_url = reverse_lazy("conceptoajuste_list")

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["object_list"] = ConceptoAjuste.objects.all()
        return contexto


class CuentaBancariaListView(ListView):
    """Lista las cuentas bancarias (modo creación maestro-detalle)."""

    model = CuentaBancaria
    context_object_name = "cuentas_bancarias"
    ordering = ["denominacion"]

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["form"] = CuentaBancariaForm()
        return contexto


class CuentaBancariaCreateView(CreateView):
    """Crea una cuenta bancaria nueva."""

    model = CuentaBancaria
    form_class = CuentaBancariaForm
    success_url = reverse_lazy("cuentabancaria_list")


class CuentaBancariaUpdateView(UpdateView):
    """Edita una cuenta bancaria existente (modo edición maestro-detalle)."""

    model = CuentaBancaria
    form_class = CuentaBancariaForm
    success_url = reverse_lazy("cuentabancaria_list")

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["object_list"] = CuentaBancaria.objects.all()
        return contexto


# ---------------------------------------------------------------------------
# Libro Bancario (Fase 5 — GREEN)
# ---------------------------------------------------------------------------


def libro_bancario(request):
    """Maestro-Detalle del libro bancario: cuentas + movimientos ordenados.

    Selecciona la cuenta por el parámetro ``cuenta`` (con ``first()`` como
    respaldo). Sin cuentas, devuelve el estado vacío en lugar de fallar.
    """
    cuentas = CuentaBancaria.objects.all()
    cuenta_id = request.GET.get("cuenta")
    cuenta = None
    if cuenta_id:
        try:
            cuenta = cuentas.get(pk=cuenta_id)
        except (ValueError, CuentaBancaria.DoesNotExist):
            cuenta = None
    if cuenta is None:
        cuenta = cuentas.first()

    movimientos = (
        MovimientoLibro.objects.filter(cuenta=cuenta).order_by("fecha", "id")
        if cuenta is not None
        else MovimientoLibro.objects.none()
    )
    contexto = {
        "cuentas": cuentas,
        "cuenta": cuenta,
        "movimientos": movimientos,
        "form": MovimientoLibroForm(),
        "saldo_inicial": (
            cuenta.saldo_inicial if cuenta is not None else Decimal("0.00")
        ),
    }
    return render(request, "conciliacion/libro_bancario.html", contexto)


def libro_bancario_crear(request):
    """Registra un movimiento del libro delegando el saldo al motor del modelo.

    La cuenta se resuelve fuera del formulario (campo oculto) y se asigna a
    ``form.instance.cuenta``. Un formulario inválido re-renderiza con el
    contexto completo y los errores en línea en español.
    """
    if request.method != "POST":
        return HttpResponse(status=405)

    cuenta = get_object_or_404(CuentaBancaria, pk=request.POST.get("cuenta"))
    form = MovimientoLibroForm(request.POST)
    if form.is_valid():
        movimiento = form.save(commit=False)
        movimiento.cuenta = cuenta
        movimiento.save()
        return redirect(f"{reverse('libro_bancario')}?cuenta={cuenta.pk}")

    contexto = {
        "cuentas": CuentaBancaria.objects.all(),
        "cuenta": cuenta,
        "movimientos": MovimientoLibro.objects.filter(cuenta=cuenta).order_by(
            "fecha", "id"
        ),
        "form": form,
        "saldo_inicial": cuenta.saldo_inicial,
    }
    return render(request, "conciliacion/libro_bancario.html", contexto)


def libro_bancario_recalcular(request):
    """Reconstruye los saldos corridos de una cuenta (FR-008)."""
    if request.method != "POST":
        return HttpResponse(status=405)

    cuenta = get_object_or_404(CuentaBancaria, pk=request.POST.get("cuenta"))
    MovimientoLibro.recalcular_saldos(cuenta.pk)
    return redirect(f"{reverse('libro_bancario')}?cuenta={cuenta.pk}")
