from django.contrib import admin
from django.contrib.humanize.templatetags.humanize import intcomma

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
    list_editable = ["activa"]
    list_filter = ["activa"]
    search_fields = ["nombre"]
    actions = ["marcar_activa", "marcar_inactiva"]

    @admin.action(description="Marcar como activa")
    def marcar_activa(self, request, queryset):
        actualizadas = queryset.update(activa=True)
        self.message_user(request, f"{actualizadas} sucursal(es) marcada(s) como activa.")

    @admin.action(description="Marcar como inactiva")
    def marcar_inactiva(self, request, queryset):
        actualizadas = queryset.update(activa=False)
        self.message_user(request, f"{actualizadas} sucursal(es) marcada(s) como inactiva.")


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
    list_display = ["sucursal", "tipo_gasto", "semana", "monto_formateado", "creado_por"]
    list_filter = ["sucursal", "tipo_gasto", "semana"]

    @admin.display(description="Monto", ordering="monto")
    def monto_formateado(self, obj):
        return f"${intcomma(obj.monto)}"


@admin.register(GastoReal)
class GastoRealAdmin(admin.ModelAdmin):
    list_display = [
        "factura_numero",
        "proveedor_nombre",
        "sucursal",
        "tipo_gasto",
        "fecha_factura",
        "fecha_pago",
        "semana",
        "monto_formateado",
        "coincide_pago",
        "payment_state",
    ]
    list_filter = ["sucursal", "tipo_gasto", "payment_state", "semana"]
    search_fields = ["factura_numero", "proveedor_nombre"]

    @admin.display(description="Factura vs pagado", boolean=True)
    def coincide_pago(self, obj):
        if obj.monto_factura is None or obj.monto_pagado is None:
            return None
        return obj.monto_factura == obj.monto_pagado

    @admin.display(description="Monto", ordering="monto")
    def monto_formateado(self, obj):
        return f"${intcomma(obj.monto)}"


@admin.register(PerfilUsuario)
class PerfilUsuarioAdmin(admin.ModelAdmin):
    list_display = ["user", "sucursal"]
    list_filter = ["sucursal"]
