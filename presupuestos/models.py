from django.conf import settings
from django.db import models


class Sucursal(models.Model):
    odoo_company_id = models.IntegerField(unique=True)
    nombre = models.CharField(max_length=255)
    activa = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["nombre"]
        verbose_name = "sucursal"
        verbose_name_plural = "sucursales"

    def __str__(self):
        return self.nombre


class Categoria(models.Model):
    """
    Top-level P&L bucket: Costo de Ventas (COGS) vs Gasto Operativo (opex).
    Fully editable from the app - not hardcoded to just these two.
    """

    nombre = models.CharField(max_length=100, unique=True)

    class Meta:
        ordering = ["nombre"]
        verbose_name = "categoria"
        verbose_name_plural = "categorias"

    def __str__(self):
        return self.nombre


class TipoGasto(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    categoria = models.ForeignKey(Categoria, on_delete=models.PROTECT, related_name="tipos_gasto")
    descripcion = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["categoria__nombre", "nombre"]
        verbose_name = "tipo de gasto"
        verbose_name_plural = "tipos de gasto"

    def __str__(self):
        return self.nombre


class CuentaContableTipoGasto(models.Model):
    """
    Maps a direct-expense Odoo account (rent, utilities, maintenance, etc.)
    to a TipoGasto. Used for invoice lines that are NOT routed through the
    generic goods-received clearing account.
    """

    odoo_account_id = models.IntegerField(unique=True)
    odoo_account_name = models.CharField(max_length=255)
    tipo_gasto = models.ForeignKey(TipoGasto, on_delete=models.PROTECT, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["odoo_account_name"]
        verbose_name = "cuenta contable -> tipo de gasto"
        verbose_name_plural = "cuentas contables -> tipo de gasto"

    def __str__(self):
        return f"{self.odoo_account_name} -> {self.tipo_gasto}"


class CategoriaProductoTipoGasto(models.Model):
    """
    Maps an Odoo product.category to a TipoGasto. Used for invoice lines
    routed through the generic goods-received clearing account (purchases
    matched to a purchase order/receipt), where the account itself carries
    no expense-type signal but the product's category does.
    """

    odoo_category_id = models.IntegerField(unique=True)
    odoo_category_name = models.CharField(max_length=255)
    tipo_gasto = models.ForeignKey(TipoGasto, on_delete=models.PROTECT, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["odoo_category_name"]
        verbose_name = "categoria de producto -> tipo de gasto"
        verbose_name_plural = "categorias de producto -> tipo de gasto"

    def __str__(self):
        return f"{self.odoo_category_name} -> {self.tipo_gasto}"


class Presupuesto(models.Model):
    """
    tipo_gasto is optional. Leave it blank to capture "everything else" for
    a sucursal/semana: the dashboard's by-tipo breakdown (see
    _calcular_contexto_dashboard in views.py) spreads that amount evenly
    across whichever TipoGasto records do NOT have their own explicit
    Presupuesto row for that same sucursal/semana. E.g. Carne=$120,000 and
    Oficina=$45,000 as explicit rows, plus one blank-tipo_gasto row for the
    remaining 10 tipos - each of those 10 gets 1/10th of that row's amount.
    The overall dashboard table just sums every Presupuesto row for a
    sucursal/semana regardless of tipo_gasto, so it's correct either way
    without needing to know about this split.
    """

    sucursal = models.ForeignKey(Sucursal, on_delete=models.CASCADE, related_name="presupuestos")
    tipo_gasto = models.ForeignKey(
        TipoGasto,
        on_delete=models.PROTECT,
        related_name="presupuestos",
        null=True,
        blank=True,
        help_text=(
            "Deja en blanco para capturar 'todo lo demas': ese monto se reparte en partes "
            "iguales entre los tipos de gasto que NO tengan su propio presupuesto capturado "
            "para esta misma sucursal y semana."
        ),
    )
    semana = models.DateField(help_text="Monday of the ISO week this budget applies to.")
    monto = models.DecimalField(max_digits=12, decimal_places=2)
    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["sucursal", "tipo_gasto", "semana"], name="unique_presupuesto_sucursal_tipo_semana"
            )
        ]
        ordering = ["-semana", "sucursal", "tipo_gasto"]
        verbose_name = "presupuesto"
        verbose_name_plural = "presupuestos"

    def __str__(self):
        tipo = self.tipo_gasto or "Total"
        return f"{self.sucursal} / {tipo} / {self.semana} = {self.monto}"


class GastoReal(models.Model):
    """
    One row per Odoo vendor-bill line (account.move.line). Synced read-only
    from Odoo; never edited by users. tipo_gasto is resolved at sync time via
    the hybrid CuentaContableTipoGasto / CategoriaProductoTipoGasto mapping,
    and can be null if that line couldn't be classified yet.

    semana (the week this line counts toward) is based on fecha_pago, not
    fecha_factura - the point of this whole app is tracking cash actually
    paid out per week, and 87% of sampled bills are paid on a different date
    than they're invoiced, sometimes in a different week entirely.

    When a bill has more than one reconciled payment (~4% of bills - real
    installments, e.g. $20,000 + $18,048 on different dates), fecha_pago
    uses the LATEST payment date and the full line amount counts toward
    that week, rather than splitting the line across payment dates - a
    deliberate simplification. monto_factura (the invoice's own total) and
    monto_pagado (sum of its reconciled payments' own amounts) are stored
    so a human can spot when they don't match - that mismatch is the signal
    that a payment was split across invoices or otherwise isn't a clean
    1:1 match, worth checking by hand rather than trusting the simplification.
    """

    PAYMENT_STATE_CHOICES = [
        ("not_paid", "Not paid"),
        ("in_payment", "In payment"),
        ("paid", "Paid"),
        ("partial", "Partial"),
        ("reversed", "Reversed"),
    ]

    sucursal = models.ForeignKey(Sucursal, on_delete=models.CASCADE, related_name="gastos")
    tipo_gasto = models.ForeignKey(
        TipoGasto, on_delete=models.SET_NULL, null=True, blank=True, related_name="gastos"
    )
    odoo_move_id = models.IntegerField()
    odoo_move_line_id = models.IntegerField(unique=True)
    factura_numero = models.CharField(max_length=100)
    proveedor_odoo_id = models.IntegerField(null=True, blank=True)
    proveedor_nombre = models.CharField(max_length=255)
    fecha_factura = models.DateField(help_text="Fecha de la factura en Odoo (invoice_date). Solo referencia.")
    fecha_pago = models.DateField(
        null=True, blank=True, help_text="Fecha real de pago (la mas reciente si hubo varios pagos). Define semana."
    )
    semana = models.DateField(help_text="Monday of the ISO week fecha_pago falls in.")
    monto = models.DecimalField(
        max_digits=12, decimal_places=2,
        help_text="Linea con IVA incluido (Odoo price_total, no price_subtotal) - es el efectivo real pagado.",
    )
    monto_factura = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text="Total de la factura completa (account.move.amount_total), igual en todas sus lineas.",
    )
    monto_pagado = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text=(
            "Suma de los pagos reconciliados con esta factura. Si no coincide con monto_factura, "
            "revisar a mano: puede ser un pago compartido con otras facturas."
        ),
    )
    payment_state = models.CharField(max_length=20, choices=PAYMENT_STATE_CHOICES)
    sincronizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-fecha_pago"]
        indexes = [
            models.Index(fields=["sucursal", "semana"]),
            models.Index(fields=["sucursal", "tipo_gasto", "semana"]),
        ]
        verbose_name = "gasto real"
        verbose_name_plural = "gastos reales"

    def __str__(self):
        return f"{self.factura_numero} / {self.proveedor_nombre} / {self.monto}"


class PerfilUsuario(models.Model):
    """
    Extends auth.User with the app's role/branch restriction. Role itself
    comes from Django Groups (Administrador, Usuario, Sucursal); sucursal is
    only set (and only enforced) for users in the Sucursal group.
    """

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="perfil")
    sucursal = models.ForeignKey(
        Sucursal, on_delete=models.SET_NULL, null=True, blank=True, related_name="usuarios"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "perfil de usuario"
        verbose_name_plural = "perfiles de usuario"

    def __str__(self):
        return f"Perfil de {self.user}"
