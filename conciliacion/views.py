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

from django.contrib import messages
from django.db.models.deletion import ProtectedError
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from conciliacion.exportadores import exportar_csv, exportar_pdf, exportar_xlsx
from conciliacion.forms import (
    BancoForm,
    ConceptoAjusteForm,
    CrearAsientoExtractoForm,
    CuentaBancariaForm,
    ExtractoImportarForm,
    MovimientoExtractoForm,
    MovimientoLibroForm,
    MonedaForm,
    ReporteLibroForm,
    TipoCuentaForm,
    TipoOperacionForm,
)
from conciliacion.importadores import ErrorImportacion
from conciliacion.models import (
    Banco,
    ConceptoAjuste,
    Conciliacion,
    ConciliadoBloqueadoError,
    CuentaBancaria,
    DetalleConciliacionBancaria,
    DetalleConciliacionInterna,
    Moneda,
    MovimientoBancario,
    MovimientoExtracto,
    MovimientoInterno,
    MovimientoLibro,
    TipoCuenta,
    TipoOperacion,
)
from conciliacion.reportes import RangoFechasInvalidoError, generar_reporte_libro
from conciliacion.punteo import (
    ImporteNoCoincideError,
    crear_asiento_desde_extracto,
    despuntear as despuntear_servicio,
    importar_extracto,
    puntear as puntear_servicio,
)
from conciliacion.services import (
    AmountMismatchError,
    ZeroSumError,
    commit_reconciliation,
    match_movimientos,
    quantize_to_moneda,
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
    """Panel de control del motor de extracto y punteo (v2.0)."""
    extractos_pendientes = MovimientoExtracto.objects.filter(
        conciliado=False
    ).count()
    libros_pendientes = MovimientoLibro.objects.filter(conciliado=False).count()
    contexto = {
        "extractos_pendientes": extractos_pendientes,
        "libros_pendientes": libros_pendientes,
        "pendientes_totales": extractos_pendientes + libros_pendientes,
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
# Eliminación segura (ProtectedError → mensaje de error).
# ---------------------------------------------------------------------------


class EliminacionProtegidaMixin:
    """Captura ``ProtectedError`` al eliminar y muestra un mensaje de error.

    Las vistas de eliminación de catálogos usan este mixin para que, cuando un
    registro tenga dependencias protegidas (``on_delete=PROTECT``), la operación
    no trace una excepción sin controlar: se redirige a la lista con un
    ``messages.error``.
    """

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        try:
            return self.delete(request, *args, **kwargs)
        except ProtectedError:
            messages.error(
                request,
                f"No se puede eliminar «{self.object}» porque tiene registros relacionados.",
            )
            return redirect(self.get_success_url())


class ConfirmarEliminacionView(EliminacionProtegidaMixin, DeleteView):
    """Base común: plantilla de confirmación y enlace de cancelación."""

    template_name = "conciliacion/confirm_delete.html"

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["cancel_url"] = self.get_success_url()
        return contexto


class BancoDeleteView(ConfirmarEliminacionView):
    model = Banco
    success_url = reverse_lazy("banco_list")


class TipoCuentaDeleteView(ConfirmarEliminacionView):
    model = TipoCuenta
    success_url = reverse_lazy("tipocuenta_list")


class MonedaDeleteView(ConfirmarEliminacionView):
    model = Moneda
    success_url = reverse_lazy("moneda_list")


class TipoOperacionDeleteView(ConfirmarEliminacionView):
    model = TipoOperacion
    success_url = reverse_lazy("tipooperacion_list")


class ConceptoAjusteDeleteView(ConfirmarEliminacionView):
    model = ConceptoAjuste
    success_url = reverse_lazy("conceptoajuste_list")


class CuentaBancariaDeleteView(ConfirmarEliminacionView):
    model = CuentaBancaria
    success_url = reverse_lazy("cuentabancaria_list")


class MovimientoLibroDeleteView(ConfirmarEliminacionView):
    model = MovimientoLibro

    def get_success_url(self):
        return f"{reverse('libro_bancario')}?cuenta={self.object.cuenta_id}"

    def post(self, request, *args, **kwargs):
        try:
            return super().post(request, *args, **kwargs)
        except ConciliadoBloqueadoError:
            return HttpResponse(
                "El movimiento conciliado no puede editarse ni eliminarse.",
                status=400,
            )


class MovimientoLibroUpdateView(UpdateView):
    """Edita un movimiento del libro y recalcula los saldos corridos (FR-008).

    Al guardar se persiste el movimiento con el formulario ``MovimientoLibroForm``
    y luego se reconstruye el saldo corrido de toda la cuenta con
    ``MovimientoLibro.recalcular_saldos``, de modo que las filas posteriores
    reflejen la corrección (igual que al crear o eliminar).
    """

    model = MovimientoLibro
    form_class = MovimientoLibroForm
    template_name = "conciliacion/movimiento_libro_form.html"

    def get_success_url(self):
        return f"{reverse('libro_bancario')}?cuenta={self.object.cuenta_id}"

    def form_valid(self, form):
        if self.object.conciliado:
            return HttpResponse(
                "El movimiento conciliado no puede editarse ni eliminarse.",
                status=400,
            )
        self.object = form.save()
        MovimientoLibro.recalcular_saldos(self.object.cuenta_id)
        return redirect(self.get_success_url())


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
        MovimientoLibro.objects.filter(cuenta=cuenta).order_by("-fecha", "-id")
        if cuenta is not None
        else MovimientoLibro.objects.none()
    )
    detalles_existentes = (
        MovimientoLibro.objects.filter(cuenta=cuenta)
        .exclude(detalle="")
        .exclude(detalle__isnull=True)
        .order_by("detalle")
        .values_list("detalle", flat=True)
        .distinct()
        if cuenta is not None
        else []
    )
    contexto = {
        "cuentas": cuentas,
        "cuenta": cuenta,
        "movimientos": movimientos,
        "detalles_existentes": detalles_existentes,
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
            "-fecha", "-id"
        ),
        "detalles_existentes": (
            MovimientoLibro.objects.filter(cuenta=cuenta)
            .exclude(detalle="")
            .exclude(detalle__isnull=True)
            .order_by("detalle")
            .values_list("detalle", flat=True)
            .distinct()
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


# ---------------------------------------------------------------------------
# Reportes del Libro Bancario (Fase 3 — GREEN)
# ---------------------------------------------------------------------------


def _resolver_cuenta_reporte(pk):
    """Resuelve la cuenta del reporte; 404 si falta, no existe o no es numérica.

    ``get_object_or_404`` ya cubre ``DoesNotExist``; se captura además ``ValueError``
    para convertir en 404 una clave no numérica (p. ej. ``cuenta=abc``), coherente
    con el contrato HTTP (``contracts/http-api.md``).
    """
    try:
        return get_object_or_404(CuentaBancaria, pk=pk)
    except ValueError:
        raise Http404("Cuenta bancaria inexistente.")


def reporte_libro(request):
    """Reporte del Libro Bancario filtrable e imprimible (US1 — Fase 3).

    * GET sin parámetros → 200 con el formulario de filtros vacío (``reporte=None``).
    * GET con parámetros → ``cuenta`` se resuelve con ``get_object_or_404``
      (404 si falta o es inválida) y ``desde``/``hasta`` se validan con
      ``ReporteLibroForm``; un rango inválido re-renderiza 200 el formulario con
      el error en línea y sin tabla.
    * Cualquier método distinto de GET → 405 (coherente con el resto de vistas).
    """
    if request.method != "GET":
        return HttpResponse(status=405)

    # Sin parámetros: solo el filtro, sin reporte.
    if not request.GET:
        contexto = {
            "form": ReporteLibroForm(),
            "reporte": None,
            "cuentas": CuentaBancaria.objects.all(),
        }
        return render(request, "conciliacion/reporte_libro.html", contexto)

    cuenta = _resolver_cuenta_reporte(request.GET.get("cuenta"))
    form = ReporteLibroForm(request.GET)
    reporte = None
    if form.is_valid():
        reporte = generar_reporte_libro(
            cuenta=cuenta,
            fecha_desde=form.cleaned_data["desde"],
            fecha_hasta=form.cleaned_data["hasta"],
        )

    contexto = {
        "form": form,
        "reporte": reporte,
        "cuentas": CuentaBancaria.objects.all(),
        "cuenta": cuenta,
    }
    return render(request, "conciliacion/reporte_libro.html", contexto)


# ---------------------------------------------------------------------------
# Reportes del Libro Bancario — Exportaciones CSV/XLSX (Fase 4 — GREEN)
# ---------------------------------------------------------------------------


def _construir_reporte_exportacion(request):
    """Resuelve ``cuenta`` (404) y valida ``desde``/``hasta`` (400) para exportar.

    Devuelve el ``ReporteLibro`` canónico producido por ``generar_reporte_libro``
    (FR-007). Un rango inválido (fechas malformadas o ``desde > hasta``) se
    traduce en ``RangoFechasInvalidoError``, que las vistas convierten en 400 sin
    cuerpo útil (``contracts/http-api.md``).
    """
    cuenta = _resolver_cuenta_reporte(request.GET.get("cuenta"))
    form = ReporteLibroForm(
        {
            "cuenta": cuenta.pk,
            "desde": request.GET.get("desde"),
            "hasta": request.GET.get("hasta"),
        }
    )
    if not form.is_valid():
        raise RangoFechasInvalidoError(
            "El rango de fechas es inválido: 'desde' y 'hasta' deben ser fechas "
            "válidas y 'desde' no puede ser posterior a 'hasta'."
        )
    return generar_reporte_libro(
        cuenta=cuenta,
        fecha_desde=form.cleaned_data["desde"],
        fecha_hasta=form.cleaned_data["hasta"],
    )


def _nombre_archivo_reporte(reporte, extension):
    """Devuelve ``reporte_libro_<cuenta>_<desde>_<hasta>.<ext>``."""
    return (
        f"reporte_libro_{reporte.cuenta.pk}_"
        f"{reporte.fecha_desde.isoformat()}_{reporte.fecha_hasta.isoformat()}"
        f".{extension}"
    )


def _respuesta_archivo(contenido, mimetype, nombre):
    """Construye una descarga con ``Content-Disposition: attachment``."""
    respuesta = HttpResponse(contenido, content_type=mimetype)
    respuesta["Content-Disposition"] = f'attachment; filename="{nombre}"'
    return respuesta


def reporte_libro_csv(request):
    """Descarga CSV (``text/csv``) del reporte filtrado (US2 — Fase 4)."""
    if request.method != "GET":
        return HttpResponse(status=405)

    try:
        reporte = _construir_reporte_exportacion(request)
    except RangoFechasInvalidoError:
        return HttpResponse(status=400)

    nombre = _nombre_archivo_reporte(reporte, "csv")
    return _respuesta_archivo(
        exportar_csv(reporte), "text/csv; charset=utf-8", nombre
    )


def reporte_libro_excel(request):
    """Descarga Excel (``.xlsx``) del reporte filtrado (US2 — Fase 4)."""
    if request.method != "GET":
        return HttpResponse(status=405)

    try:
        reporte = _construir_reporte_exportacion(request)
    except RangoFechasInvalidoError:
        return HttpResponse(status=400)

    nombre = _nombre_archivo_reporte(reporte, "xlsx")
    mimetype = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return _respuesta_archivo(exportar_xlsx(reporte), mimetype, nombre)


def reporte_libro_pdf(request):
    """Descarga PDF (``application/pdf``) del reporte filtrado (US3 — Fase 5)."""
    if request.method != "GET":
        return HttpResponse(status=405)

    try:
        reporte = _construir_reporte_exportacion(request)
    except RangoFechasInvalidoError:
        return HttpResponse(status=400)

    nombre = _nombre_archivo_reporte(reporte, "pdf")
    return _respuesta_archivo(exportar_pdf(reporte), "application/pdf", nombre)


# ---------------------------------------------------------------------------
# Extracto Bancario — CRUD e importación (US1 — Fase 3).
# ---------------------------------------------------------------------------


MENSAJE_BLOQUEO = "El movimiento conciliado no puede editarse ni eliminarse."


def _queryset_extracto(queryset):
    """Aplica el orden canónico ``fecha`` / ``id`` a un queryset de extractos."""
    return queryset.order_by("fecha", "id")


def extracto_list(request):
    """Lista los ``MovimientoExtracto``, con filtro opcional ``?cuenta=<pk>``.

    El contexto expone el total ``movimientos`` y los desgloses ``pendientes``
    (``conciliado=False``) y ``conciliados`` (``conciliado=True``), todos
    ordenados por ``fecha`` e ``id`` (FR-010 del contrato HTTP).
    """
    queryset = MovimientoExtracto.objects.all()
    cuenta_pk = request.GET.get("cuenta")
    if cuenta_pk:
        queryset = queryset.filter(cuenta_bancaria_id=cuenta_pk)
    contexto = {
        "movimientos": _queryset_extracto(queryset),
        "pendientes": _queryset_extracto(queryset.filter(conciliado=False)),
        "conciliados": _queryset_extracto(queryset.filter(conciliado=True)),
    }
    return render(request, "conciliacion/extracto_list.html", contexto)


def extracto_create(request):
    """Alta manual de un ``MovimientoExtracto`` (``origen=manual`` por defecto)."""
    if request.method == "POST":
        form = MovimientoExtractoForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("extracto_list")
    else:
        form = MovimientoExtractoForm()
    return render(request, "conciliacion/extracto_form.html", {"form": form})


def extracto_update(request, pk):
    """Edición de un ``MovimientoExtracto`` sin conciliar.

    Un extracto ya ``conciliado`` queda bloqueado (400), sin mutación, tanto en
    GET como en POST (FR-010 del contrato HTTP).
    """
    movimiento = get_object_or_404(MovimientoExtracto, pk=pk)
    if movimiento.conciliado:
        return HttpResponse(MENSAJE_BLOQUEO, status=400)
    if request.method == "POST":
        form = MovimientoExtractoForm(request.POST, instance=movimiento)
        if form.is_valid():
            form.save()
            return redirect("extracto_list")
    else:
        form = MovimientoExtractoForm(instance=movimiento)
    return render(request, "conciliacion/extracto_form.html", {"form": form})


def extracto_delete(request, pk):
    """Eliminación de un ``MovimientoExtracto`` sin conciliar (solo POST)."""
    if request.method != "POST":
        return HttpResponse(status=405)
    movimiento = get_object_or_404(MovimientoExtracto, pk=pk)
    if movimiento.conciliado:
        return HttpResponse(MENSAJE_BLOQUEO, status=400)
    try:
        movimiento.delete()
    except ConciliadoBloqueadoError:
        return HttpResponse(MENSAJE_BLOQUEO, status=400)
    return redirect("extracto_list")


def extracto_importar(request):
    """Carga todo-o-nada de un extracto (``cuenta`` + ``archivo``).

    Ante un archivo inválido o sin movimientos re-renderiza el formulario con la
    clave de contexto ``errores`` sin persistir ninguna fila; ante un lote
    válido muestra un mensaje de éxito y redirige (302) al listado (FR-010).
    """
    if request.method == "POST":
        form = ExtractoImportarForm(request.POST, request.FILES)
        if form.is_valid():
            cuenta = form.cleaned_data["cuenta"]
            archivo = request.FILES["archivo"]
            try:
                resultado = importar_extracto(cuenta, archivo)
            except ErrorImportacion as exc:
                return render(
                    request,
                    "conciliacion/extracto_importar.html",
                    {"form": form, "errores": [str(exc)]},
                )
            creados = resultado.creados
            omitidos = resultado.omitidos
            if not creados and not omitidos:
                return render(
                    request,
                    "conciliacion/extracto_importar.html",
                    {
                        "form": form,
                        "errores": ["El archivo no contiene movimientos para importar."],
                    },
                )
            if not creados:
                messages.warning(
                    request,
                    f"No se importaron movimientos nuevos: {len(omitidos)} ya existian.",
                )
                return redirect("extracto_list")
            if omitidos:
                messages.success(
                    request,
                    f"Se importaron {len(creados)} movimientos. Se omitieron {len(omitidos)} ya existentes.",
                )
            else:
                messages.success(
                    request, f"Se importaron {len(creados)} movimientos."
                )
            return redirect("extracto_list")
    else:
        form = ExtractoImportarForm()
    return render(request, "conciliacion/extracto_importar.html", {"form": form})


def crear_asiento_extracto(request, pk):
    """Convierte un extracto pendiente en asiento de libro y lo concilia (GET/POST).

    GET: formula un ``CrearAsientoExtractoForm`` precargado (fecha/detalle y el
    signo ya mapeado a ``debe``/``haber``). POST: invoca el servicio atómico
    ``crear_asiento_desde_extracto`` y redirige (302) a ``punteo``; un extracto
    ya conciliado devuelve 400 sin mutar.
    """
    extracto = get_object_or_404(MovimientoExtracto, pk=pk)
    if request.method == "POST":
        try:
            crear_asiento_desde_extracto(extracto=extracto)
        except ConciliadoBloqueadoError:
            return HttpResponse(MENSAJE_BLOQUEO, status=400)
        return redirect("punteo")

    importe = quantize_to_moneda(extracto.importe, extracto.cuenta_bancaria.moneda)
    es_debe = importe > 0
    inicial = {
        "fecha": extracto.fecha,
        "detalle": extracto.detalle,
        "debe": importe if es_debe else Decimal("0.00"),
        "haber": -importe if not es_debe else Decimal("0.00"),
    }
    form = CrearAsientoExtractoForm(initial=inicial)
    return render(request, "conciliacion/crear_asiento_form.html", {"form": form, "extracto": extracto})


# ---------------------------------------------------------------------------
# Punteo — dual-list y acciones de punteo/despunteo (US2 — Fase 4).
# ---------------------------------------------------------------------------


def punteo(request):
    """Lista dual extractos vs. libros pendientes de conciliar (GET).

    Con ``?cuenta=<pk>`` filtra ambas listas a esa ``CuentaBancaria``; sin filtro
    expone todos los pendientes. El contexto expone ``extractos`` y ``libros``
    (solo ``conciliado=False``, ordenados por ``fecha`` e ``id``), además de
    ``cuentas`` y ``cuenta`` para el selector de la plantilla.
    """
    cuenta_pk = request.GET.get("cuenta")
    cuenta = None
    if cuenta_pk:
        cuenta = get_object_or_404(CuentaBancaria, pk=cuenta_pk)

    extractos = MovimientoExtracto.objects.filter(conciliado=False)
    libros = MovimientoLibro.objects.filter(conciliado=False)
    if cuenta_pk:
        extractos = extractos.filter(cuenta_bancaria_id=cuenta_pk)
        libros = libros.filter(cuenta_id=cuenta_pk)

    contexto = {
        "extractos": extractos.order_by("fecha", "id"),
        "libros": libros.order_by("fecha", "id"),
        "cuentas": CuentaBancaria.objects.all(),
        "cuenta": cuenta,
    }
    return render(request, "conciliacion/punteo.html", contexto)


def puntear(request):
    """Vincula un extracto con un libro (POST), ``conciliado=True`` en ambos.

    Parsear los ``pk`` del cuerpo, invoca el servicio y redirige (302) al listado
    de punteo; los errores de dominio devuelven 400.
    """
    if request.method != "POST":
        return HttpResponse(status=405)
    extracto = get_object_or_404(MovimientoExtracto, pk=request.POST.get("extracto_id"))
    libro = get_object_or_404(MovimientoLibro, pk=request.POST.get("libro_id"))
    try:
        puntear_servicio(extracto=extracto, libro=libro)
    except (ImporteNoCoincideError, ValueError):
        return HttpResponse(status=400)
    return redirect("punteo")


def despuntear(request, extracto_id):
    """Elimina el vínculo de un extracto y reinicia banderas (POST)."""
    if request.method != "POST":
        return HttpResponse(status=405)
    extracto = get_object_or_404(MovimientoExtracto, pk=extracto_id)
    try:
        despuntear_servicio(extracto=extracto)
    except ValueError:
        return HttpResponse(status=400)
    return redirect("punteo")
