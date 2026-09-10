# presupuestos/views_catalogos.py
#
# /admin/catalogos/ - Excel-based bulk load for Categoria, TipoGasto, and
# both mapping tables. Kept separate from views.py (dashboard/reports)
# since this is a distinct, admin-only concern built around
# catalogos_excel.py's export/parse/apply functions.

from django.contrib import messages
from django.contrib.admin import site as admin_site
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import ProtectedError
from django.http import HttpResponse
from django.shortcuts import redirect, render

from .catalogos_excel import ErroresPlantilla, aplicar_plantilla, plantilla_a_bytes, procesar_plantilla_excel
from .models import ConfiguracionCatalogos


@staff_member_required
def catalogos_admin(request):
    config = ConfiguracionCatalogos.obtener()
    context = {**admin_site.each_context(request), "config": config, "title": "Catalogos: importar / exportar"}
    return render(request, "presupuestos/catalogos_admin.html", context)


@staff_member_required
def catalogos_exportar(request):
    response = HttpResponse(
        plantilla_a_bytes(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = 'attachment; filename="Plantilla_Catalogos_Presupuestos_AP.xlsx"'
    return response


@staff_member_required
def catalogos_importar(request):
    if request.method != "POST" or not request.FILES.get("archivo"):
        messages.error(request, "Selecciona un archivo .xlsx para importar.")
        return redirect("catalogos_admin")

    config = ConfiguracionCatalogos.obtener()

    try:
        datos = procesar_plantilla_excel(request.FILES["archivo"])
    except ErroresPlantilla as exc:
        for error in exc.errores:
            messages.error(request, error)
        return redirect("catalogos_admin")

    borrar_todo = config.permitir_carga_inicial
    try:
        resumen = aplicar_plantilla(datos, borrar_todo)
    except ProtectedError:
        messages.error(
            request,
            "No se pudo reemplazar: ya existen Presupuestos capturados que usan uno de los tipos de "
            "gasto actuales. Borralos o reclasificalos antes de repetir una carga inicial.",
        )
        return redirect("catalogos_admin")

    resumen_texto = (
        f"{resumen['categorias']} categorias, {resumen['tipos']} tipos de gasto, "
        f"{resumen['cuentas']} cuentas contables, {resumen['categorias_producto']} categorias de producto."
    )
    if borrar_todo:
        config.permitir_carga_inicial = False
        config.save()
        messages.success(
            request,
            f"Catalogos reemplazados desde cero: {resumen_texto} Tambien se borraron "
            f"{resumen['gastos_reales_borrados']} gastos reales (desde 2026-01-01 en adelante) para que se "
            "reclasifiquen con el catalogo nuevo en la proxima corrida del scheduler. La carga inicial ya quedo "
            "desactivada.",
        )
    else:
        messages.success(request, f"Catalogos actualizados: {resumen_texto}")
    return redirect("catalogos_admin")
