from django.contrib import admin

from .models import (
    Categoria,
    CategoriaProductoTipoGasto,
    CuentaContableTipoGasto,
    GastoReal,
    PerfilUsuario,
    Presupuesto,
    Sucursal,
    TipoGasto,
)

admin.site.site_header = "Presupuestos AP - Sucursales"
admin.site.site_title = "Presupuestos AP"
admin.site.index_title = "Administracion"


@admin.register(Sucursal)
class SucursalAdmin(admin.ModelAdmin):
    list_display = ["nombre", "odoo_company_id", "activa"]
    list_filter = ["activa"]
    search_fields = ["nombre"]


@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ["nombre"]
    search_fields = ["nombre"]


@admin.register(TipoGasto)
class TipoGastoAdmin(admin.ModelAdmin):
    list_display = ["nombre", "categoria", "descripcion"]
    list_filter = ["categoria"]
    search_fields = ["nombre"]


@admin.register(CuentaContableTipoGasto)
class CuentaContableTipoGastoAdmin(admin.ModelAdmin):
    list_display = ["odoo_account_name", "odoo_account_id", "tipo_gasto"]
    list_filter = ["tipo_gasto"]
    search_fields = ["odoo_account_name"]


@admin.register(CategoriaProductoTipoGasto)
class CategoriaProductoTipoGastoAdmin(admin.ModelAdmin):
    list_display = ["odoo_category_name", "odoo_category_id", "tipo_gasto"]
    list_filter = ["tipo_gasto"]
    search_fields = ["odoo_category_name"]


@admin.register(Presupuesto)
class PresupuestoAdmin(admin.ModelAdmin):
    list_display = ["sucursal", "tipo_gasto", "semana", "monto", "creado_por"]
    list_filter = ["sucursal", "tipo_gasto", "semana"]


@admin.register(GastoReal)
class GastoRealAdmin(admin.ModelAdmin):
    list_display = [
        "factura_numero",
        "proveedor_nombre",
        "sucursal",
        "tipo_gasto",
        "fecha_factura",
        "semana",
        "monto",
        "payment_state",
    ]
    list_filter = ["sucursal", "tipo_gasto", "payment_state", "semana"]
    search_fields = ["factura_numero", "proveedor_nombre"]


@admin.register(PerfilUsuario)
class PerfilUsuarioAdmin(admin.ModelAdmin):
    list_display = ["user", "sucursal"]
    list_filter = ["sucursal"]
