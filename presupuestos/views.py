from datetime import date, timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.shortcuts import render

from .models import GastoReal, Presupuesto, Sucursal, TipoGasto

SEMANAS_POR_DEFECTO = 12
OPCIONES_SEMANAS = [4, 8, 12, 26, 52]

OPCIONES_AGRUPAR_GENERAL = [("semana", "Semana"), ("sucursal", "Sucursal")]
OPCIONES_AGRUPAR_TIPO = [("tipo_gasto", "Tipo de gasto"), ("semana", "Semana"), ("sucursal", "Sucursal")]


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


def _clave_grupo(fila, campo):
    if campo == "semana":
        sem = fila["semana"]
        etiqueta = f"Semana {sem.isocalendar()[1]} ({sem.strftime('%d/%m/%Y')})"
        return sem, etiqueta
    if campo == "sucursal":
        return fila["sucursal"].id, fila["sucursal"].nombre
    if campo == "tipo_gasto":
        return fila["tipo_gasto_nombre"], fila["tipo_gasto_nombre"]
    return None, "Todos"


def _agrupar(filas, campo):
    grupos = {}
    orden = []
    for fila in filas:
        clave, etiqueta = _clave_grupo(fila, campo)
        if clave not in grupos:
            grupos[clave] = {"clave": clave, "etiqueta": etiqueta, "filas": [], "presupuesto": 0, "gasto_real": 0, "restante": 0}
            orden.append(clave)
        g = grupos[clave]
        g["filas"].append(fila)
        g["presupuesto"] += fila["presupuesto"]
        g["gasto_real"] += fila["gasto_real"]
        g["restante"] += fila["restante"]

    if campo == "semana":
        orden.sort(reverse=True)
    else:
        orden.sort(key=lambda k: grupos[k]["etiqueta"])

    return [grupos[k] for k in orden]


def _tendencia_lineal(valores):
    """Least-squares linear trend over an evenly-spaced series (x = 0..n-1)."""
    n = len(valores)
    if n < 2:
        return list(valores)
    x_mean = (n - 1) / 2
    y_mean = sum(valores) / n
    num = sum((i - x_mean) * (valores[i] - y_mean) for i in range(n))
    den = sum((i - x_mean) ** 2 for i in range(n))
    pendiente = num / den if den else 0
    intercepto = y_mean - pendiente * x_mean
    return [round(pendiente * i + intercepto, 2) for i in range(n)]


@login_required
def dashboard(request):
    sucursales_disponibles, restringido_a_una = _sucursales_para_usuario(request.user)

    if restringido_a_una:
        sucursales_seleccionadas = list(sucursales_disponibles)
    elif "filtro_aplicado" in request.GET:
        # The filter form was submitted (even if every checkbox ended up
        # unchecked) - respect exactly what was selected, empty or not.
        seleccion = request.GET.getlist("sucursal")
        sucursales_seleccionadas = list(sucursales_disponibles.filter(pk__in=seleccion))
    else:
        # First load, no filter interaction yet - default to everything.
        sucursales_seleccionadas = list(sucursales_disponibles)

    try:
        num_semanas = int(request.GET.get("semanas", SEMANAS_POR_DEFECTO))
    except ValueError:
        num_semanas = SEMANAS_POR_DEFECTO
    num_semanas = max(1, min(num_semanas, 52))

    hoy = date.today()
    semana_actual = _lunes_de_semana(hoy)
    semanas = [semana_actual - timedelta(weeks=i) for i in range(num_semanas)]

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

    sucursales_por_id = {s.id: s for s in sucursales_seleccionadas}

    filas_general = []
    for suc in sucursales_seleccionadas:
        for sem in semanas:
            clave = (suc.id, sem)
            presupuesto = pres_general.get(clave) or 0
            gasto = gasto_general.get(clave) or 0
            if presupuesto or gasto:
                filas_general.append(
                    {"sucursal": suc, "semana": sem, "presupuesto": presupuesto, "gasto_real": gasto, "restante": presupuesto - gasto}
                )

    pres_por_tipo = {
        (r["sucursal_id"], r["semana"], r["tipo_gasto_id"]): r["total"]
        for r in presupuestos.values("sucursal_id", "semana", "tipo_gasto_id").annotate(total=Sum("monto"))
    }
    gasto_por_tipo = {
        (r["sucursal_id"], r["semana"], r["tipo_gasto_id"]): r["total"]
        for r in gastos.values("sucursal_id", "semana", "tipo_gasto_id").annotate(total=Sum("monto"))
    }

    tipos_gasto = {t.id: t.nombre for t in TipoGasto.objects.all()}
    claves = set(pres_por_tipo) | set(gasto_por_tipo)

    filas_tipo = []
    for suc_id, sem, tipo_id in claves:
        suc = sucursales_por_id.get(suc_id)
        if not suc:
            continue
        presupuesto = pres_por_tipo.get((suc_id, sem, tipo_id)) or 0
        gasto = gasto_por_tipo.get((suc_id, sem, tipo_id)) or 0
        filas_tipo.append(
            {
                "sucursal": suc,
                "semana": sem,
                # None covers two different things bucketed together: a
                # deliberate lump-sum Presupuesto (no tipo_gasto chosen) and
                # a GastoReal line the Odoo mapping couldn't classify.
                "tipo_gasto_nombre": tipos_gasto.get(tipo_id, "Sin categoria (total o sin clasificar)"),
                "presupuesto": presupuesto,
                "gasto_real": gasto,
                "restante": presupuesto - gasto,
            }
        )

    semanas_asc = list(reversed(semanas))
    graficas = []
    for suc in sucursales_seleccionadas:
        gasto_valores = [float(gasto_general.get((suc.id, s)) or 0) for s in semanas_asc]
        presupuesto_valores = [float(pres_general.get((suc.id, s)) or 0) for s in semanas_asc]
        graficas.append(
            {
                "sucursal_id": suc.id,
                "sucursal_nombre": suc.nombre,
                "etiquetas": [f"Sem {s.isocalendar()[1]}" for s in semanas_asc],
                "gasto_real": gasto_valores,
                "presupuesto": presupuesto_valores,
                "tendencia": _tendencia_lineal(gasto_valores),
            }
        )

    agrupar_general = request.GET.get("g_agrupar", "semana")
    if agrupar_general not in dict(OPCIONES_AGRUPAR_GENERAL):
        agrupar_general = "semana"

    agrupar_tipo = request.GET.get("t_agrupar", "tipo_gasto")
    if agrupar_tipo not in dict(OPCIONES_AGRUPAR_TIPO):
        agrupar_tipo = "tipo_gasto"

    context = {
        "sucursales_disponibles": sucursales_disponibles,
        "sucursales_seleccionadas_ids": {s.id for s in sucursales_seleccionadas},
        "restringido_a_una": restringido_a_una,
        "num_semanas": num_semanas,
        "opciones_semanas": OPCIONES_SEMANAS,
        "grupos_general": _agrupar(filas_general, agrupar_general),
        "grupos_tipo": _agrupar(filas_tipo, agrupar_tipo),
        "agrupar_general": agrupar_general,
        "agrupar_tipo": agrupar_tipo,
        "opciones_agrupar_general": OPCIONES_AGRUPAR_GENERAL,
        "opciones_agrupar_tipo": OPCIONES_AGRUPAR_TIPO,
        "graficas": graficas,
    }
    return render(request, "presupuestos/dashboard.html", context)
