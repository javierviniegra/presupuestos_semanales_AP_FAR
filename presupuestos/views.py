from datetime import date, timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.shortcuts import render

from .models import GastoReal, Presupuesto, Sucursal, TipoGasto

SEMANAS_A_MOSTRAR = 12


def home(request):
    return render(request, "presupuestos/home.html")


def _lunes_de_semana(d):
    return d - timedelta(days=d.weekday())


def _sucursales_para_usuario(user):
    """
    Users in the "Sucursal" group are locked to their own branch. Everyone
    else (Administrador, Usuario, superusers) can see all active branches.
    """
    if user.is_superuser:
        return Sucursal.objects.filter(activa=True).order_by("nombre"), False

    if user.groups.filter(name="Sucursal").exists():
        perfil = getattr(user, "perfil", None)
        if perfil and perfil.sucursal_id:
            return Sucursal.objects.filter(pk=perfil.sucursal_id), True
        return Sucursal.objects.none(), True

    return Sucursal.objects.filter(activa=True).order_by("nombre"), False


@login_required
def dashboard(request):
    sucursales_disponibles, restringido_a_una = _sucursales_para_usuario(request.user)

    if restringido_a_una:
        sucursales_seleccionadas = list(sucursales_disponibles)
    else:
        seleccion = request.GET.getlist("sucursal")
        if seleccion:
            sucursales_seleccionadas = list(sucursales_disponibles.filter(pk__in=seleccion))
        else:
            sucursales_seleccionadas = list(sucursales_disponibles)

    hoy = date.today()
    semana_actual = _lunes_de_semana(hoy)
    semanas = [semana_actual - timedelta(weeks=i) for i in range(SEMANAS_A_MOSTRAR)]

    presupuestos = Presupuesto.objects.filter(sucursal__in=sucursales_seleccionadas, semana__in=semanas)
    gastos = GastoReal.objects.filter(sucursal__in=sucursales_seleccionadas, semana__in=semanas)

    pres_general = {
        (r["sucursal_id"], r["semana"]): r["total"]
        for r in presupuestos.values("sucursal_id", "semana").annotate(total=Sum("monto"))
    }
    gasto_general = {
        (r["sucursal_id"], r["semana"]): r["total"]
        for r in gastos.values("sucursal_id", "semana").annotate(total=Sum("monto"))
    }

    tabla_general = []
    for suc in sucursales_seleccionadas:
        for sem in semanas:
            clave = (suc.id, sem)
            presupuesto = pres_general.get(clave) or 0
            gasto = gasto_general.get(clave) or 0
            if presupuesto or gasto:
                tabla_general.append(
                    {
                        "sucursal": suc,
                        "semana": sem,
                        "presupuesto": presupuesto,
                        "gasto_real": gasto,
                        "restante": presupuesto - gasto,
                    }
                )
    tabla_general.sort(key=lambda r: (r["semana"], r["sucursal"].nombre), reverse=True)

    pres_por_tipo = {
        (r["sucursal_id"], r["semana"], r["tipo_gasto_id"]): r["total"]
        for r in presupuestos.values("sucursal_id", "semana", "tipo_gasto_id").annotate(total=Sum("monto"))
    }
    gasto_por_tipo = {
        (r["sucursal_id"], r["semana"], r["tipo_gasto_id"]): r["total"]
        for r in gastos.values("sucursal_id", "semana", "tipo_gasto_id").annotate(total=Sum("monto"))
    }

    tipos_gasto = {t.id: t.nombre for t in TipoGasto.objects.all()}
    sucursales_por_id = {s.id: s for s in sucursales_seleccionadas}
    claves = set(pres_por_tipo) | set(gasto_por_tipo)

    tabla_tipo = []
    for suc_id, sem, tipo_id in claves:
        suc = sucursales_por_id.get(suc_id)
        if not suc:
            continue
        presupuesto = pres_por_tipo.get((suc_id, sem, tipo_id)) or 0
        gasto = gasto_por_tipo.get((suc_id, sem, tipo_id)) or 0
        tabla_tipo.append(
            {
                "sucursal": suc,
                "semana": sem,
                "tipo_gasto_nombre": tipos_gasto.get(tipo_id, "(sin resolver: revisar mapeo Odoo)"),
                "presupuesto": presupuesto,
                "gasto_real": gasto,
                "restante": presupuesto - gasto,
            }
        )
    tabla_tipo.sort(key=lambda r: (r["semana"], r["sucursal"].nombre, r["tipo_gasto_nombre"]), reverse=True)

    context = {
        "sucursales_disponibles": sucursales_disponibles,
        "sucursales_seleccionadas_ids": {s.id for s in sucursales_seleccionadas},
        "restringido_a_una": restringido_a_una,
        "tabla_general": tabla_general,
        "tabla_tipo": tabla_tipo,
        "semanas_a_mostrar": SEMANAS_A_MOSTRAR,
    }
    return render(request, "presupuestos/dashboard.html", context)
