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

    def __str__(self):
        return self.nombre


class Categoria(models.Model):
    """
    Top-level P&L bucket: Costo de Ventas (COGS) vs Gasto Operativo (opex).
    Fully editable from the app - not hardcoded to just these two.
    """

    nombre = models.CharField(max_length=100, unique=True)

    class Meta:
        verbose_name_plural = "categorias"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class TipoGasto(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    categoria = models.ForeignKey(Categoria, on_delete=models.PROTECT, related_name="tipos_gasto")
    descripcion = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["categoria__nombre", "nombre"]

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

    def __str__(self):
        return f"{self.odoo_category_name} -> {self.tipo_gasto}"


class Presupuesto(models.Model):
    sucursal = models.ForeignKey(Sucursal, on_delete=models.CASCADE, related_name="presupuestos")
    tipo_gasto = models.ForeignKey(TipoGasto, on_delete=models.PROTECT, related_name="presupuestos")
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

    def __str__(self):
        return f"{self.sucursal} / {self.tipo_gasto} / {self.semana} = {self.monto}"


class GastoReal(models.Model):
    """
    One row per Odoo vendor-bill line (account.move.line). Synced read-only
    from Odoo; never edited by users. tipo_gasto is resolved at sync time via
    the hybrid CuentaContableTipoGasto / CategoriaProductoTipoGasto mapping,
    and can be null if that line couldn't be classified yet.
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
    fecha_factura = models.DateField()
    semana = models.DateField(help_text="Monday of the ISO week fecha_factura falls in.")
    monto = models.DecimalField(max_digits=12, decimal_places=2)
    payment_state = models.CharField(max_length=20, choices=PAYMENT_STATE_CHOICES)
    sincronizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-fecha_factura"]
        indexes = [
            models.Index(fields=["sucursal", "semana"]),
            models.Index(fields=["sucursal", "tipo_gasto", "semana"]),
        ]

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

    def __str__(self):
        return f"Perfil de {self.user}"
