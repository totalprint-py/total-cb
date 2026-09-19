"""Modelos de datos del motor de conciliación (Fase 3).

Definición física de las entidades del dominio descrito en
``specs/001-core-reconciliation-engine/data-model.md``:

* Catálogos: ``Banco``, ``TipoCuenta``, ``Moneda``, ``TipoOperacion`` y
  ``ConceptoAjuste``.
* Operativas: ``LoteImportacion``, ``CuentaBancaria``, ``MovimientoBancario``,
  ``MovimientoInterno``, ``Conciliacion``, ``DetalleConciliacionBancaria``,
  ``DetalleConciliacionInterna`` y ``AjusteConciliacion``.

Los campos monetarios son ``DecimalField`` (nunca ``FloatField``) con
``max_digits=19`` y ``decimal_places=8``; además, ``ImporteDecimalField``
rechaza explícitamente los valores ``float`` forzando ``decimal.Decimal``.
Las restricciones de dominio se declaran con ``CheckConstraint(condition=Q(...))``
y los pares únicos con ``UniqueConstraint``. Los modelos son exclusivamente
estructuras de datos: sin lógica de negocio.
"""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.db.models.constraints import CheckConstraint, UniqueConstraint


class ConciliadoBloqueadoError(Exception):
    """Un movimiento conciliado no puede editarse ni eliminarse."""


# ---------------------------------------------------------------------------
# Campo monetario: exige ``decimal.Decimal`` y rechaza ``float``.
# ---------------------------------------------------------------------------


class ImporteDecimalField(models.DecimalField):
    """Campo monetario que rechaza ``float`` y exige ``decimal.Decimal``.

    ``DecimalField`` convertiría silenciosamente un ``float`` a ``Decimal``;
    este campo lo rechaza en ``to_python`` para garantizar precisión monetaria
    de extremo a extremo (FR-007).
    """

    def to_python(self, value):
        if isinstance(value, float):
            raise TypeError(
                "Los importes monetarios no admiten float; use decimal.Decimal."
            )
        return super().to_python(value)


# ---------------------------------------------------------------------------
# Catálogos
# ---------------------------------------------------------------------------


def _siguiente_codigo(modelo):
    """Calcula el siguiente código secuencial (en texto) para un catálogo.

    ``codigo`` se modela como ``CharField``; para respetar el orden numérico
    (evitando que ``"10"`` quede antes que ``"2"``) se convierten los valores
    existentes a entero y se devuelve ``máximo + 1``. Los valores no numéricos
    se ignoran; si no hay registros, el consecutivo arranca en ``"1"``.
    """
    numeros = []
    for codigo in modelo.objects.values_list("codigo", flat=True):
        try:
            numeros.append(int(codigo))
        except (TypeError, ValueError):
            # Los códigos alfabéticos (p. ej. "USD") no entran en el consecutivo.
            continue
    return str(max(numeros, default=0) + 1)


class Banco(models.Model):
    """Catálogo de bancos emisores de las cuentas a conciliar."""

    codigo = models.CharField(max_length=50, unique=True, blank=True)
    nombre = models.CharField(max_length=200)

    class Meta:
        verbose_name = "banco"
        verbose_name_plural = "bancos"

    def __str__(self):
        return self.nombre

    def save(self, *args, **kwargs):
        # Asigna el código consecutivo automático al crear un banco sin código.
        if not self.pk and not self.codigo:
            self.codigo = _siguiente_codigo(type(self))
        super().save(*args, **kwargs)


class TipoCuenta(models.Model):
    """Catálogo de tipos de cuenta bancaria."""

    codigo = models.CharField(max_length=50, unique=True, blank=True)
    nombre = models.CharField(max_length=200)

    class Meta:
        verbose_name = "tipo de cuenta"
        verbose_name_plural = "tipos de cuenta"

    def __str__(self):
        return self.nombre

    def save(self, *args, **kwargs):
        # Asigna el código consecutivo automático al crear un tipo de cuenta sin código.
        if not self.pk and not self.codigo:
            self.codigo = _siguiente_codigo(type(self))
        super().save(*args, **kwargs)


class Moneda(models.Model):
    """Catálogo de monedas y su precisión decimal."""

    codigo = models.CharField(max_length=50, unique=True, blank=True)
    nombre = models.CharField(max_length=200)
    cantidad_decimales = models.PositiveIntegerField()

    class Meta:
        constraints = [
            CheckConstraint(
                condition=Q(cantidad_decimales__gte=0),
                name="moneda_cantidad_decimales_no_negativa",
            ),
        ]
        verbose_name = "moneda"
        verbose_name_plural = "monedas"

    def __str__(self):
        return f"{self.nombre} ({self.codigo})"

    def save(self, *args, **kwargs):
        # Asigna el código consecutivo automático al crear una moneda sin código.
        if not self.pk and not self.codigo:
            self.codigo = _siguiente_codigo(type(self))
        super().save(*args, **kwargs)


class TipoOperacion(models.Model):
    """Catálogo de tipos de operación de los movimientos."""

    codigo = models.CharField(max_length=50, unique=True, blank=True)
    nombre = models.CharField(max_length=200)

    class Meta:
        verbose_name = "tipo de operación"
        verbose_name_plural = "tipos de operación"

    def __str__(self):
        return self.nombre

    def save(self, *args, **kwargs):
        # Asigna el código consecutivo automático al crear un tipo de operación sin código.
        if not self.pk and not self.codigo:
            self.codigo = _siguiente_codigo(type(self))
        super().save(*args, **kwargs)


class ConceptoAjuste(models.Model):
    """Catálogo de conceptos de ajuste para la conciliación."""

    codigo = models.CharField(max_length=50, unique=True, blank=True)
    nombre = models.CharField(max_length=200)

    class Meta:
        verbose_name = "concepto de ajuste"
        verbose_name_plural = "conceptos de ajuste"

    def __str__(self):
        return self.nombre

    def save(self, *args, **kwargs):
        # Asigna el código consecutivo automático al crear un concepto de ajuste sin código.
        if not self.pk and not self.codigo:
            self.codigo = _siguiente_codigo(type(self))
        super().save(*args, **kwargs)


# ---------------------------------------------------------------------------
# Entidades operativas
# ---------------------------------------------------------------------------


class LoteImportacion(models.Model):
    """Lote de importación que da trazabilidad a los movimientos (FR-004)."""

    fuente = models.CharField(max_length=255)
    fecha_importacion = models.DateTimeField()

    class Meta:
        constraints = [
            UniqueConstraint(
                fields=["fuente", "fecha_importacion"],
                name="lote_importacion_identidad_unica",
            ),
        ]
        verbose_name = "lote de importación"
        verbose_name_plural = "lotes de importación"

    def __str__(self):
        return f"{self.fuente} ({self.fecha_importacion})"


class CuentaBancaria(models.Model):
    """Cuenta bancaria sujeta a conciliación."""

    banco = models.ForeignKey(Banco, on_delete=models.PROTECT)
    tipo_cuenta = models.ForeignKey(TipoCuenta, on_delete=models.PROTECT)
    moneda = models.ForeignKey(Moneda, on_delete=models.PROTECT)
    numero_cuenta = models.CharField(max_length=50)
    denominacion = models.CharField(max_length=100, help_text="Ej: GNB Dólares")
    saldo_inicial = models.DecimalField(
        max_digits=18, decimal_places=2, default=Decimal("0.00")
    )

    class Meta:
        verbose_name = "cuenta bancaria"
        verbose_name_plural = "cuentas bancarias"

    def __str__(self):
        return self.denominacion


class MovimientoBancario(models.Model):
    """Movimiento financiero proveniente del extracto bancario."""

    importe = ImporteDecimalField(max_digits=19, decimal_places=8)
    fecha = models.DateField()
    notas = models.TextField(blank=True, null=True)
    en_consulta = models.BooleanField(default=False)
    cuenta_bancaria = models.ForeignKey(CuentaBancaria, on_delete=models.PROTECT)
    lote_importacion = models.ForeignKey(LoteImportacion, on_delete=models.PROTECT)
    tipo_operacion = models.ForeignKey(TipoOperacion, on_delete=models.PROTECT)
    moneda = models.ForeignKey(Moneda, on_delete=models.PROTECT)

    class Meta:
        constraints = [
            CheckConstraint(
                condition=Q(importe__gte=0),
                name="movimiento_bancario_importe_no_negativo",
            ),
        ]
        verbose_name = "movimiento bancario"
        verbose_name_plural = "movimientos bancarios"

    def clean(self):
        super().clean()
        if self.cuenta_bancaria_id and self.moneda_id:
            cuenta = self.cuenta_bancaria
            if cuenta is not None and cuenta.moneda_id != self.moneda_id:
                raise ValidationError(
                    {
                        "moneda": (
                            "La moneda del movimiento debe coincidir con la de "
                            "la cuenta bancaria."
                        ),
                    }
                )

    def __str__(self):
        return f"{self.fecha} - {self.importe}"



class MovimientoInterno(models.Model):
    """Movimiento financiero proveniente del sistema interno (contable)."""

    importe = ImporteDecimalField(max_digits=19, decimal_places=8)
    fecha = models.DateField()
    notas = models.TextField(blank=True, null=True)
    lote_importacion = models.ForeignKey(LoteImportacion, on_delete=models.PROTECT)
    tipo_operacion = models.ForeignKey(TipoOperacion, on_delete=models.PROTECT)
    moneda = models.ForeignKey(Moneda, on_delete=models.PROTECT)

    class Meta:
        constraints = [
            CheckConstraint(
                condition=Q(importe__gte=0),
                name="movimiento_interno_importe_no_negativo",
            ),
        ]
        verbose_name = "movimiento interno"
        verbose_name_plural = "movimientos internos"

    def __str__(self):
        return f"{self.fecha} - {self.importe}"


class MovimientoLibro(models.Model):
    """Movimiento del libro mayor de una cuenta bancaria, con saldo corrido.

    Cada movimiento ajusta el saldo de la cuenta partiendo del saldo del
    movimiento cronológico anterior (o del ``saldo_inicial`` de la cuenta si es
    el primero). La convención es ``saldo = saldo_base + debe - haber``.
    """

    cuenta = models.ForeignKey(CuentaBancaria, on_delete=models.CASCADE)
    fecha = models.DateField()
    tipo_operacion = models.ForeignKey(TipoOperacion, on_delete=models.PROTECT)
    detalle = models.CharField(max_length=255)
    debe = models.DecimalField(
        max_digits=18, decimal_places=2, default=Decimal("0.00")
    )
    haber = models.DecimalField(
        max_digits=18, decimal_places=2, default=Decimal("0.00")
    )
    saldo = models.DecimalField(
        max_digits=18, decimal_places=2, default=Decimal("0.00"), editable=False
    )
    conciliado = models.BooleanField(default=False)

    class Meta:
        ordering = ["fecha", "id"]
        constraints = [
            CheckConstraint(
                condition=Q(debe__gte=0),
                name="movimiento_libro_debe_no_negativo",
            ),
            CheckConstraint(
                condition=Q(haber__gte=0),
                name="movimiento_libro_haber_no_negativo",
            ),
            CheckConstraint(
                condition=Q(debe__gt=0) | Q(haber__gt=0),
                name="movimiento_libro_importe_requerido",
            ),
            CheckConstraint(
                condition=Q(debe=0) | Q(haber=0),
                name="movimiento_libro_mutua_exclusion",
            ),
        ]
        verbose_name = "movimiento de libro"
        verbose_name_plural = "movimientos de libro"

    def __str__(self):
        return f"{self.fecha} - {self.detalle}"

    def clean(self):
        """Valida FR-007 en el modelo: importes no negativos, al menos uno no
        cero y exclusión mutua entre ``debe`` y ``haber``."""
        super().clean()
        errores = {}
        if self.debe is not None and self.debe < 0:
            errores["debe"] = "El debe no puede ser negativo."
        if self.haber is not None and self.haber < 0:
            errores["haber"] = "El haber no puede ser negativo."
        if (self.debe is None or self.debe == 0) and (
            self.haber is None or self.haber == 0
        ):
            raise ValidationError(
                "Debe indicar un importe en el debe o en el haber."
            )
        if (
            self.debe is not None
            and self.haber is not None
            and self.debe > 0
            and self.haber > 0
        ):
            raise ValidationError(
                "Solo puede cargar un valor en Debe o en Haber, no en ambos."
            )
        if errores:
            raise ValidationError(errores)

    def save(self, *args, **kwargs):
        if self.pk is None:
            last_mov = (
                MovimientoLibro.objects.filter(cuenta=self.cuenta)
                .order_by("fecha", "id")
                .last()
            )
            if last_mov is not None:
                saldo_base = last_mov.saldo
            else:
                saldo_base = self.cuenta.saldo_inicial
            self.saldo = saldo_base + self.debe - self.haber
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """Elimina el movimiento y recalcula los saldos corridos restantes.

        Al borrar un movimiento intermedio, los movimientos posteriores deben
        recalcular su saldo para mantener la coherencia del libro mayor.
        """
        if self.conciliado:
            raise ConciliadoBloqueadoError(
                "El movimiento conciliado no puede editarse ni eliminarse."
            )
        cuenta_id = self.cuenta_id
        resultado = super().delete(*args, **kwargs)
        type(self).recalcular_saldos(cuenta_id)
        return resultado

    @classmethod
    def recalcular_saldos(cls, cuenta_id):
        """Reconstruye el saldo corrido de todos los movimientos de una cuenta.

        Parte del ``saldo_inicial`` de la cuenta y recorre los movimientos en
        orden cronológico (``fecha``, ``id``) recalculando y persistiendo el
        saldo de cada uno. Devuelve la lista de movimientos actualizados.
        """
        cuenta = CuentaBancaria.objects.get(pk=cuenta_id)
        saldo_base = cuenta.saldo_inicial
        movimientos = list(
            cls.objects.filter(cuenta_id=cuenta_id).order_by("fecha", "id")
        )
        for movimiento in movimientos:
            movimiento.saldo = saldo_base + movimiento.debe - movimiento.haber
            movimiento.save(update_fields=["saldo"])
            saldo_base = movimiento.saldo
        return movimientos


class Conciliacion(models.Model):
    """Cabecera de una conciliación sobre una cuenta bancaria (FR-010)."""

    ESTADO_BORRADOR = "draft"
    ESTADO_COMPROMETIDA = "committed"
    ESTADO_REVERTIDA = "reverted"
    ESTADOS = [
        (ESTADO_BORRADOR, "Borrador"),
        (ESTADO_COMPROMETIDA, "Comprometida"),
        (ESTADO_REVERTIDA, "Revertida"),
    ]

    estado = models.CharField(
        max_length=20, choices=ESTADOS, default=ESTADO_BORRADOR
    )
    fecha_desde = models.DateField()
    fecha_hasta = models.DateField()
    cuenta_bancaria = models.ForeignKey(CuentaBancaria, on_delete=models.PROTECT)

    class Meta:
        constraints = [
            CheckConstraint(
                condition=Q(
                    estado__in=["draft", "committed", "reverted"],
                ),
                name="conciliacion_estado_valido",
            ),
        ]
        verbose_name = "conciliación"
        verbose_name_plural = "conciliaciones"

    def __str__(self):
        return f"{self.cuenta_bancaria} ({self.estado})"


class DetalleConciliacionBancaria(models.Model):
    """Vínculo único entre una conciliación y un movimiento bancario."""

    conciliacion = models.ForeignKey(Conciliacion, on_delete=models.CASCADE)
    movimiento_bancario = models.ForeignKey(
        MovimientoBancario, on_delete=models.CASCADE
    )

    class Meta:
        constraints = [
            UniqueConstraint(
                fields=["conciliacion", "movimiento_bancario"],
                name="detalle_conciliacion_bancaria_unico",
            ),
        ]
        verbose_name = "detalle de conciliación bancaria"
        verbose_name_plural = "detalles de conciliación bancaria"

    def __str__(self):
        return f"{self.conciliacion} - {self.movimiento_bancario}"


class DetalleConciliacionInterna(models.Model):
    """Vínculo único entre una conciliación y un movimiento interno."""

    conciliacion = models.ForeignKey(Conciliacion, on_delete=models.CASCADE)
    movimiento_interno = models.ForeignKey(
        MovimientoInterno, on_delete=models.CASCADE
    )

    class Meta:
        constraints = [
            UniqueConstraint(
                fields=["conciliacion", "movimiento_interno"],
                name="detalle_conciliacion_interna_unico",
            ),
        ]
        verbose_name = "detalle de conciliación interna"
        verbose_name_plural = "detalles de conciliación interna"

    def __str__(self):
        return f"{self.conciliacion} - {self.movimiento_interno}"


class AjusteConciliacion(models.Model):
    """Ajuste monetario que alimenta la ecuación de suma cero (FR-006)."""

    importe = ImporteDecimalField(max_digits=19, decimal_places=8)
    conciliacion = models.ForeignKey(Conciliacion, on_delete=models.CASCADE)
    concepto_ajuste = models.ForeignKey(ConceptoAjuste, on_delete=models.PROTECT)

    class Meta:
        verbose_name = "ajuste de conciliación"
        verbose_name_plural = "ajustes de conciliación"

    def __str__(self):
        return f"{self.concepto_ajuste} - {self.importe}"


# ---------------------------------------------------------------------------
# Conciliación bancaria: extracto y punteo (Fase 4).
# ---------------------------------------------------------------------------


class MovimientoExtracto(models.Model):
    """Movimiento financiero proveniente del extracto bancario."""

    ORIGEN_MANUAL = "manual"
    ORIGEN_IMPORTACION = "importacion"
    ORIGENES = [
        (ORIGEN_MANUAL, "Manual"),
        (ORIGEN_IMPORTACION, "Importación"),
    ]

    cuenta_bancaria = models.ForeignKey(
        CuentaBancaria,
        on_delete=models.PROTECT,
        related_name="movimientos_extracto",
    )
    fecha = models.DateField()
    referencia = models.CharField(max_length=100, blank=True)
    detalle = models.CharField(max_length=255)
    importe = ImporteDecimalField(max_digits=18, decimal_places=2)
    origen = models.CharField(
        max_length=20, choices=ORIGENES, default=ORIGEN_MANUAL
    )
    conciliado = models.BooleanField(default=False)

    class Meta:
        ordering = ["fecha", "id"]
        constraints = [
            CheckConstraint(
                condition=Q(importe__lt=0) | Q(importe__gt=0),
                name="movimiento_extracto_importe_no_cero",
            ),
            CheckConstraint(
                condition=Q(origen__in=["manual", "importacion"]),
                name="movimiento_extracto_origen_valido",
            ),
        ]
        verbose_name = "movimiento de extracto"
        verbose_name_plural = "movimientos de extracto"

    def __str__(self):
        return f"{self.fecha} - {self.detalle}"

    def delete(self, *args, **kwargs):
        if self.conciliado:
            raise ConciliadoBloqueadoError(
                "El movimiento conciliado no puede editarse ni eliminarse."
            )
        return super().delete(*args, **kwargs)


class Punteo(models.Model):
    """Vínculo 1:1 entre un movimiento de extracto y uno del libro mayor."""

    movimiento_extracto = models.ForeignKey(
        MovimientoExtracto,
        on_delete=models.PROTECT,
        related_name="punteo",
    )
    movimiento_libro = models.ForeignKey(
        MovimientoLibro,
        on_delete=models.PROTECT,
        related_name="punteo",
    )

    class Meta:
        constraints = [
            UniqueConstraint(
                fields=["movimiento_extracto"],
                name="punteo_movimiento_extracto_unico",
            ),
            UniqueConstraint(
                fields=["movimiento_libro"],
                name="punteo_movimiento_libro_unico",
            ),
        ]
        verbose_name = "punteo"
        verbose_name_plural = "punteos"

    def __str__(self):
        return f"{self.movimiento_extracto} - {self.movimiento_libro}"


class AuditoriaPunteo(models.Model):
    """Bitácora de las transiciones de punteo y despunteo (FR-007)."""

    ACCION_PUNTEAR = "puntear"
    ACCION_DESPUNTEAR = "despuntear"
    ACCIONES = [
        (ACCION_PUNTEAR, "Puntear"),
        (ACCION_DESPUNTEAR, "Despuntear"),
    ]

    fecha_hora = models.DateTimeField(auto_now_add=True)
    accion = models.CharField(max_length=20, choices=ACCIONES)
    movimiento_extracto = models.ForeignKey(
        MovimientoExtracto, on_delete=models.SET_NULL, null=True, blank=True
    )
    movimiento_libro = models.ForeignKey(
        MovimientoLibro, on_delete=models.SET_NULL, null=True, blank=True
    )
    usuario = models.CharField(max_length=150, blank=True)

    class Meta:
        constraints = [
            CheckConstraint(
                condition=Q(accion__in=["puntear", "despuntear"]),
                name="auditoria_punteo_accion_valida",
            ),
        ]
        verbose_name = "auditoría de punteo"
        verbose_name_plural = "auditorías de punteo"

    def __str__(self):
        return f"{self.fecha_hora} - {self.accion}"

