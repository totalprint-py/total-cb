"""Enrutamiento del motor de conciliación (Fase 6 — GREEN).

Define los cinco nombres de URL que el contrato de ``test_vistas.py`` exige:
``tablero``, ``reporte_manual``, ``emparejar_movimientos``,
``comprometer_conciliacion`` y ``revertir_conciliacion``. Además registra las
rutas CRUD de los catálogos auxiliares: ``banco_list``, ``tipocuenta_list``,
``moneda_list``, ``tipooperacion_list`` y ``conceptoajuste_list``, cada una con
sus variantes ``*_create`` y ``*_update``.

Sin ``app_name`` a propósito: las pruebas resuelven ``reverse("tablero")`` sin
namespace.
"""
from django.urls import path

from conciliacion import views

urlpatterns = [
    path("", views.tablero, name="tablero"),
    path("reporte-manual/", views.reporte_manual, name="reporte_manual"),
    path("emparejar/", views.emparejar_movimientos, name="emparejar_movimientos"),
    path("comprometer/", views.comprometer_conciliacion, name="comprometer_conciliacion"),
    path("revertir/", views.revertir_conciliacion, name="revertir_conciliacion"),

    # Libro Bancario (Fase 5 — GREEN).
    path("libro-bancario/", views.libro_bancario, name="libro_bancario"),
    path("libro-bancario/movimientos/nuevo/", views.libro_bancario_crear, name="libro_bancario_crear"),
    path("libro-bancario/recalcular/", views.libro_bancario_recalcular, name="libro_bancario_recalcular"),
    path("libro-bancario/movimientos/<int:pk>/eliminar/", views.MovimientoLibroDeleteView.as_view(), name="movimientolibro_delete"),
    path("libro-bancario/movimientos/<int:pk>/editar/", views.MovimientoLibroUpdateView.as_view(), name="movimientolibro_update"),

    # Reportes del Libro Bancario (Fase 3 — GREEN).
    path("libro-bancario/reportes/", views.reporte_libro, name="reporte_libro"),
    # Reportes del Libro Bancario — Exportaciones (Fases 4-5 — GREEN).
    path("libro-bancario/reportes/csv/", views.reporte_libro_csv, name="reporte_libro_csv"),
    path("libro-bancario/reportes/excel/", views.reporte_libro_excel, name="reporte_libro_excel"),
    path("libro-bancario/reportes/pdf/", views.reporte_libro_pdf, name="reporte_libro_pdf"),

    # Catálogos auxiliares (CRUD).
    path("catalogos/bancos/", views.BancoListView.as_view(), name="banco_list"),
    path("catalogos/bancos/nuevo/", views.BancoCreateView.as_view(), name="banco_create"),
    path("catalogos/bancos/<int:pk>/editar/", views.BancoUpdateView.as_view(), name="banco_update"),
    path("catalogos/bancos/<int:pk>/eliminar/", views.BancoDeleteView.as_view(), name="banco_delete"),

    path("catalogos/tipos-cuenta/", views.TipoCuentaListView.as_view(), name="tipocuenta_list"),
    path("catalogos/tipos-cuenta/nuevo/", views.TipoCuentaCreateView.as_view(), name="tipocuenta_create"),
    path("catalogos/tipos-cuenta/<int:pk>/editar/", views.TipoCuentaUpdateView.as_view(), name="tipocuenta_update"),
    path("catalogos/tipos-cuenta/<int:pk>/eliminar/", views.TipoCuentaDeleteView.as_view(), name="tipocuenta_delete"),

    path("catalogos/monedas/", views.MonedaListView.as_view(), name="moneda_list"),
    path("catalogos/monedas/nuevo/", views.MonedaCreateView.as_view(), name="moneda_create"),
    path("catalogos/monedas/<int:pk>/editar/", views.MonedaUpdateView.as_view(), name="moneda_update"),
    path("catalogos/monedas/<int:pk>/eliminar/", views.MonedaDeleteView.as_view(), name="moneda_delete"),

    path("catalogos/tipos-operacion/", views.TipoOperacionListView.as_view(), name="tipooperacion_list"),
    path("catalogos/tipos-operacion/nuevo/", views.TipoOperacionCreateView.as_view(), name="tipooperacion_create"),
    path("catalogos/tipos-operacion/<int:pk>/editar/", views.TipoOperacionUpdateView.as_view(), name="tipooperacion_update"),
    path("catalogos/tipos-operacion/<int:pk>/eliminar/", views.TipoOperacionDeleteView.as_view(), name="tipooperacion_delete"),

    path("catalogos/conceptos-ajuste/", views.ConceptoAjusteListView.as_view(), name="conceptoajuste_list"),
    path("catalogos/conceptos-ajuste/nuevo/", views.ConceptoAjusteCreateView.as_view(), name="conceptoajuste_create"),
    path("catalogos/conceptos-ajuste/<int:pk>/editar/", views.ConceptoAjusteUpdateView.as_view(), name="conceptoajuste_update"),
    path("catalogos/conceptos-ajuste/<int:pk>/eliminar/", views.ConceptoAjusteDeleteView.as_view(), name="conceptoajuste_delete"),

    path("catalogos/cuentas-bancarias/", views.CuentaBancariaListView.as_view(), name="cuentabancaria_list"),
    path("catalogos/cuentas-bancarias/nuevo/", views.CuentaBancariaCreateView.as_view(), name="cuentabancaria_create"),
    path("catalogos/cuentas-bancarias/<int:pk>/editar/", views.CuentaBancariaUpdateView.as_view(), name="cuentabancaria_update"),
    path("catalogos/cuentas-bancarias/<int:pk>/eliminar/", views.CuentaBancariaDeleteView.as_view(), name="cuentabancaria_delete"),

    # Extracto Bancario (US1 — Fase 3).
    path("extracto/", views.extracto_list, name="extracto_list"),
    path("extracto/nuevo/", views.extracto_create, name="extracto_create"),
    path("extracto/<int:pk>/editar/", views.extracto_update, name="extracto_update"),
    path("extracto/<int:pk>/eliminar/", views.extracto_delete, name="extracto_delete"),
    path("extracto/importar/", views.extracto_importar, name="extracto_importar"),
    path("extracto/<int:pk>/crear-asiento/", views.crear_asiento_extracto, name="crear_asiento_extracto"),

    # Punteo (US2 — Fase 4).
    path("punteo/", views.punteo, name="punteo"),
    path("punteo/puntear/", views.puntear, name="puntear"),
    path("punteo/despuntear/<int:extracto_id>/", views.despuntear, name="despuntear"),
]