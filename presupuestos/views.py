import base64
import io
from datetime import date, timedelta
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string
from django.utils import timezone
from xhtml2pdf import pisa

from core.database.odoo import get_odoo_connection

from .models import GastoReal, Presupuesto, Sucursal, TipoGasto

LOGO_PATH = Path(settings.BASE_DIR) / "presupuestos" / "static" / "presupuestos" / "img" / "logo.png"

SEMANAS_POR_DEFECTO = 12
OPCIONES_SEMANAS = [4, 8, 12, 26, 52]

OPCIONES_AGRUPAR_GENERAL = [("semana", "Semana"), ("sucursal", "Sucursal")]
OPCIONES_AGRUPAR_TIPO = [("tipo_gasto", "Tipo de gasto"), ("semana", "Semana"), ("sucursal", "Sucursal")]
OPCIONES_AGRUPAR_PROVEEDOR = [("proveedor", "Proveedor"), ("semana", "Semana"), ("sucursal", "Sucursal")]
TOP_PROVEEDORES = 15


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


def _clave_grupo_proveedor(fila, campo):
    if campo == "proveedor":
        return fila["proveedor_nombre"], fila["proveedor_nombre"]
    if campo == "semana":
        sem = fila["semana"]
        return sem, f"Semana {sem.isocalendar()[1]} ({sem.strftime('%d/%m/%Y')})"
    if campo == "sucursal":
        return fila["sucursal"].id, fila["sucursal"].nombre
    return None, "Todos"


def _agrupar_proveedor(filas, campo):
    grupos = {}
    orden = []
    for fila in filas:
        clave, etiqueta = _clave_grupo_proveedor(fila, campo)
        if clave not in grupos:
            grupos[clave] = {"etiqueta": etiqueta, "filas": [], "monto": 0}
            orden.append(clave)
        g = grupos[clave]
        g["filas"].append(fila)
        g["monto"] += fila["monto"]

    if campo == "semana":
        orden.sort(reverse=True)
    else:
        orden.sort(key=lambda k: grupos[k]["monto"], reverse=True)

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


def _grafica_png_base64(grafica):
    """Same series/colors as the dashboard's Chart.js version, rendered as a
    static image since the PDF engine doesn't run JavaScript."""
    fig, ax = plt.subplots(figsize=(7, 2.6), dpi=150)
    x = range(len(grafica["etiquetas"]))
    ax.plot(x, grafica["gasto_real"], color="#035953", linewidth=2, marker="o", markersize=3, label="Gasto real")
    ax.plot(x, grafica["presupuesto"], color="#eb6834", linewidth=2, marker="o", markersize=3, label="Presupuesto")
    ax.plot(x, grafica["tendencia"], color="#898781", linewidth=1.5, linestyle="--", label="Tendencia (gasto real)")
    ax.set_xticks(list(x))
    ax.set_xticklabels(grafica["etiquetas"], fontsize=6, rotation=45, ha="right")
    ax.tick_params(axis="y", labelsize=7)
    ax.yaxis.set_major_formatter(lambda v, _: f"${v:,.0f}")
    ax.set_title(grafica["sucursal_nombre"], fontsize=9, color="#023f3b", fontweight="bold", loc="left")
    ax.legend(fontsize=6, loc="upper right", frameon=False)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="y", color="#e1e0d9", linewidth=0.5)
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def _calcular_contexto_dashboard(request):
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

    pres_por_tipo_raw = {
        (r["sucursal_id"], r["semana"], r["tipo_gasto_id"]): r["total"]
        for r in presupuestos.values("sucursal_id", "semana", "tipo_gasto_id").annotate(total=Sum("monto"))
    }
    gasto_por_tipo = {
        (r["sucursal_id"], r["semana"], r["tipo_gasto_id"]): r["total"]
        for r in gastos.values("sucursal_id", "semana", "tipo_gasto_id").annotate(total=Sum("monto"))
    }

    tipos_gasto_objs = list(TipoGasto.objects.all())
    tipos_gasto = {t.id: t.nombre for t in tipos_gasto_objs}
    todos_los_tipo_ids = [t.id for t in tipos_gasto_objs]

    # Group presupuesto by (sucursal, semana) so a blank-tipo_gasto row (the
    # "everything else" amount) can be spread evenly across whichever
    # tipos_gasto did NOT get an explicit amount that same sucursal/semana.
    pres_agrupado = {}
    for (suc_id, sem, tipo_id), monto in pres_por_tipo_raw.items():
        pres_agrupado.setdefault((suc_id, sem), {})[tipo_id] = monto

    pres_resuelto = {}
    for (suc_id, sem), por_tipo in pres_agrupado.items():
        especificados = {tid: monto for tid, monto in por_tipo.items() if tid is not None}
        for tid, monto in especificados.items():
            pres_resuelto[(suc_id, sem, tid)] = monto

        remanente = por_tipo.get(None)
        if remanente:
            no_especificados = [tid for tid in todos_los_tipo_ids if tid not in especificados]
            # The "sin clasificar" bucket is also part of "everything else" -
            # give it a slice too, but only if this sucursal/semana actually
            # has unclassified gasto real (no phantom row otherwise).
            if (suc_id, sem, None) in gasto_por_tipo:
                no_especificados.append(None)
            if no_especificados:
                parte = round(remanente / len(no_especificados), 2)
                for tid in no_especificados:
                    pres_resuelto[(suc_id, sem, tid)] = pres_resuelto.get((suc_id, sem, tid), 0) + parte

    claves = set(pres_resuelto) | set(gasto_por_tipo)

    filas_tipo = []
    for suc_id, sem, tipo_id in claves:
        suc = sucursales_por_id.get(suc_id)
        if not suc:
            continue
        presupuesto = pres_resuelto.get((suc_id, sem, tipo_id)) or 0
        gasto = gasto_por_tipo.get((suc_id, sem, tipo_id)) or 0
        filas_tipo.append(
            {
                "sucursal": suc,
                "semana": sem,
                # tipo_id None means "sin clasificar" - unclassified GastoReal
                # lines, which also get a slice of the blank-tipo_gasto
                # presupuesto (see the remanente split above) when that
                # sucursal/semana actually has any unclassified gasto.
                "tipo_gasto_nombre": tipos_gasto.get(tipo_id, "Sin categoria (sin clasificar)"),
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

    return {
        "sucursales_disponibles": sucursales_disponibles,
        "sucursales_seleccionadas": sucursales_seleccionadas,
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
        "filas_general": filas_general,
    }


@login_required
def dashboard(request):
    context = _calcular_contexto_dashboard(request)
    return render(request, "presupuestos/dashboard.html", context)


@login_required
def detalle_semana(request, sucursal_id, semana):
    sucursales_permitidas, _ = _sucursales_para_usuario(request.user)
    suc = get_object_or_404(sucursales_permitidas, pk=sucursal_id)

    try:
        semana_fecha = date.fromisoformat(semana)
    except ValueError:
        raise Http404("Semana invalida")

    presupuestos = Presupuesto.objects.filter(sucursal=suc, semana=semana_fecha)
    gastos = GastoReal.objects.filter(sucursal=suc, semana=semana_fecha)

    tipos_gasto_objs = list(TipoGasto.objects.all())
    tipos_gasto = {t.id: t.nombre for t in tipos_gasto_objs}
    todos_los_tipo_ids = [t.id for t in tipos_gasto_objs]

    gasto_por_tipo = {
        r["tipo_gasto_id"]: r["total"] for r in gastos.values("tipo_gasto_id").annotate(total=Sum("monto"))
    }

    especificados = {}
    remanente = None
    for r in presupuestos.values("tipo_gasto_id").annotate(total=Sum("monto")):
        if r["tipo_gasto_id"] is None:
            remanente = r["total"]
        else:
            especificados[r["tipo_gasto_id"]] = r["total"]

    pres_resuelto = dict(especificados)
    if remanente:
        no_especificados = [tid for tid in todos_los_tipo_ids if tid not in especificados]
        if None in gasto_por_tipo:
            no_especificados.append(None)
        if no_especificados:
            parte = round(remanente / len(no_especificados), 2)
            for tid in no_especificados:
                pres_resuelto[tid] = pres_resuelto.get(tid, 0) + parte

    claves_tipo = set(pres_resuelto) | set(gasto_por_tipo)
    por_tipo = []
    for tid in claves_tipo:
        presupuesto = pres_resuelto.get(tid) or 0
        gasto = gasto_por_tipo.get(tid) or 0
        por_tipo.append(
            {
                "tipo_gasto_nombre": tipos_gasto.get(tid, "Sin categoria (sin clasificar)"),
                "presupuesto": presupuesto,
                "gasto_real": gasto,
                "restante": presupuesto - gasto,
            }
        )
    por_tipo.sort(key=lambda f: f["gasto_real"], reverse=True)

    por_proveedor = list(
        gastos.values("proveedor_nombre").annotate(total=Sum("monto")).order_by("-total")[:10]
    )

    estados_pago = dict(GastoReal.PAYMENT_STATE_CHOICES)
    facturas_resumen = [
        {**f, "estado_display": estados_pago.get(f["payment_state"], f["payment_state"])}
        for f in gastos.values("factura_numero", "proveedor_nombre", "fecha_factura", "payment_state")
        .annotate(total=Sum("monto"))
        .order_by("-total")
    ]

    facturas = list(
        gastos.select_related("tipo_gasto").order_by("-monto")[:200]
    )

    total_presupuesto = sum(f["presupuesto"] for f in por_tipo)
    total_gasto_real = sum(f["gasto_real"] for f in por_tipo)

    context = {
        "sucursal": suc,
        "semana": semana_fecha,
        "por_tipo": por_tipo,
        "por_proveedor": por_proveedor,
        "facturas": facturas,
        "facturas_resumen": facturas_resumen,
        "total_presupuesto": total_presupuesto,
        "total_gasto_real": total_gasto_real,
        "total_restante": total_presupuesto - total_gasto_real,
    }
    return render(request, "presupuestos/detalle_semana.html", context)


@login_required
def reporte_proveedores(request):
    """
    Same sucursal/semana filter as the dashboard, but never restricted to a
    single branch's drill-down - this combines every selected+active
    sucursal, which is the whole point (compare a provider's spend across
    branches, not just within one).
    """
    sucursales_disponibles, restringido_a_una = _sucursales_para_usuario(request.user)

    if restringido_a_una:
        sucursales_seleccionadas = list(sucursales_disponibles)
    elif "filtro_aplicado" in request.GET:
        seleccion = request.GET.getlist("sucursal")
        sucursales_seleccionadas = list(sucursales_disponibles.filter(pk__in=seleccion))
    else:
        sucursales_seleccionadas = list(sucursales_disponibles)

    try:
        num_semanas = int(request.GET.get("semanas", SEMANAS_POR_DEFECTO))
    except ValueError:
        num_semanas = SEMANAS_POR_DEFECTO
    num_semanas = max(1, min(num_semanas, 52))

    hoy = date.today()
    semana_actual = _lunes_de_semana(hoy)
    semanas = [semana_actual - timedelta(weeks=i) for i in range(num_semanas)]

    gastos = GastoReal.objects.filter(sucursal__in=sucursales_seleccionadas, semana__in=semanas)
    sucursales_por_id = {s.id: s for s in sucursales_seleccionadas}

    filas_proveedor = []
    for r in gastos.values("proveedor_nombre", "sucursal_id", "semana").annotate(total=Sum("monto")):
        suc = sucursales_por_id.get(r["sucursal_id"])
        if not suc:
            continue
        filas_proveedor.append(
            {"proveedor_nombre": r["proveedor_nombre"], "sucursal": suc, "semana": r["semana"], "monto": r["total"]}
        )

    agrupar = request.GET.get("agrupar", "proveedor")
    if agrupar not in dict(OPCIONES_AGRUPAR_PROVEEDOR):
        agrupar = "proveedor"

    top_proveedores = list(
        gastos.values("proveedor_nombre").annotate(total=Sum("monto")).order_by("-total")[:TOP_PROVEEDORES]
    )

    context = {
        "sucursales_disponibles": sucursales_disponibles,
        "sucursales_seleccionadas": sucursales_seleccionadas,
        "sucursales_seleccionadas_ids": {s.id for s in sucursales_seleccionadas},
        "restringido_a_una": restringido_a_una,
        "num_semanas": num_semanas,
        "opciones_semanas": OPCIONES_SEMANAS,
        "grupos_proveedor": _agrupar_proveedor(filas_proveedor, agrupar),
        "agrupar": agrupar,
        "opciones_agrupar": OPCIONES_AGRUPAR_PROVEEDOR,
        "top_proveedores": top_proveedores,
    }
    return render(request, "presupuestos/reporte_proveedores.html", context)


@login_required
def facturas_pendientes(request):
    """
    Live Odoo query (not from the daily-synced GastoReal, which only
    covers paid/in_payment bills) - not_paid and partial vendor bills as of
    a cutoff date, grouped by purchase order (invoice_origin) where present.
    amount_residual is Odoo's own outstanding-balance field, computed per
    invoice - unlike account.payment.amount (see GastoReal's docstring),
    it's NOT affected by one payment covering multiple invoices, so it's
    the reliable field for "how much is still owed" here.
    """
    sucursales_disponibles, restringido_a_una = _sucursales_para_usuario(request.user)

    if restringido_a_una:
        sucursales_seleccionadas = list(sucursales_disponibles)
    elif "filtro_aplicado" in request.GET:
        seleccion = request.GET.getlist("sucursal")
        sucursales_seleccionadas = list(sucursales_disponibles.filter(pk__in=seleccion))
    else:
        sucursales_seleccionadas = list(sucursales_disponibles)

    hasta_str = request.GET.get("hasta") or date.today().isoformat()
    try:
        hasta = date.fromisoformat(hasta_str)
    except ValueError:
        hasta = date.today()
        hasta_str = hasta.isoformat()

    sucursal_by_company = {s.odoo_company_id: s for s in sucursales_seleccionadas}
    company_ids = list(sucursal_by_company.keys())

    estados_pago = dict(GastoReal.PAYMENT_STATE_CHOICES)
    facturas = []
    if company_ids:
        uid, models, db, password = get_odoo_connection()
        bills = models.execute_kw(
            db, uid, password, "account.move", "search_read",
            [[
                ["move_type", "=", "in_invoice"],
                ["state", "=", "posted"],
                ["payment_state", "in", ["not_paid", "partial"]],
                ["company_id", "in", company_ids],
                ["invoice_date", "<=", hasta_str],
            ]],
            {
                "fields": [
                    "id", "name", "invoice_origin", "partner_id", "company_id",
                    "invoice_date", "invoice_date_due", "amount_total", "amount_residual", "payment_state",
                ],
                "limit": 5000,
            },
        )
        for b in bills:
            suc = sucursal_by_company.get(b["company_id"][0]) if b["company_id"] else None
            if not suc:
                continue
            facturas.append(
                {
                    "sucursal": suc,
                    "orden_compra": b["invoice_origin"] or None,
                    "factura_numero": b["name"],
                    "proveedor_nombre": b["partner_id"][1] if b["partner_id"] else "",
                    "fecha_factura": date.fromisoformat(b["invoice_date"]) if b["invoice_date"] else None,
                    "fecha_vencimiento": date.fromisoformat(b["invoice_date_due"]) if b["invoice_date_due"] else None,
                    "monto_total": b["amount_total"],
                    "monto_pendiente": b["amount_residual"],
                    "estado_display": estados_pago.get(b["payment_state"], b["payment_state"]),
                }
            )

    grupos_dict = {}
    orden_claves = []
    for f in facturas:
        clave = f["orden_compra"] or "(Sin orden de compra)"
        if clave not in grupos_dict:
            grupos_dict[clave] = {"etiqueta": clave, "facturas": [], "pendiente": 0}
            orden_claves.append(clave)
        grupos_dict[clave]["facturas"].append(f)
        grupos_dict[clave]["pendiente"] += f["monto_pendiente"]

    orden_claves.sort(key=lambda k: grupos_dict[k]["pendiente"], reverse=True)
    grupos = [grupos_dict[k] for k in orden_claves]

    context = {
        "sucursales_disponibles": sucursales_disponibles,
        "sucursales_seleccionadas": sucursales_seleccionadas,
        "sucursales_seleccionadas_ids": {s.id for s in sucursales_seleccionadas},
        "restringido_a_una": restringido_a_una,
        "hasta": hasta,
        "grupos": grupos,
        "total_pendiente": sum(f["monto_pendiente"] for f in facturas),
        "total_facturas": len(facturas),
    }
    return render(request, "presupuestos/facturas_pendientes.html", context)


@login_required
def reporte_pdf(request):
    context = _calcular_contexto_dashboard(request)
    context["generado_en"] = timezone.now()
    context["generado_por"] = request.user.get_username()
    context["logo_path"] = str(LOGO_PATH)

    total_presupuesto = sum(g["presupuesto"] for g in context["grupos_general"])
    total_gasto_real = sum(g["gasto_real"] for g in context["grupos_general"])
    total_restante = total_presupuesto - total_gasto_real
    context["total_presupuesto"] = total_presupuesto
    context["total_gasto_real"] = total_gasto_real
    context["total_restante"] = total_restante
    context["pct_variacion"] = (
        round((total_gasto_real / total_presupuesto - 1) * 100, 1) if total_presupuesto else None
    )

    # Only rows with a captured presupuesto can have a meaningful variance -
    # a row with $0 presupuesto isn't "over budget", it's just uncaptured.
    con_presupuesto = [f for f in context["filas_general"] if f["presupuesto"]]
    context["mayores_desviaciones"] = sorted(con_presupuesto, key=lambda f: f["restante"])[:8]

    context["graficas_imagenes"] = [
        {"sucursal_nombre": g["sucursal_nombre"], "imagen": _grafica_png_base64(g)} for g in context["graficas"]
    ]

    html = render_to_string("presupuestos/reporte_pdf.html", context)
    buffer = io.BytesIO()
    pisa.CreatePDF(src=html, dest=buffer, encoding="utf-8")

    response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    nombre_archivo = f"reporte_presupuesto_{context['generado_en'].strftime('%Y%m%d_%H%M')}.pdf"
    response["Content-Disposition"] = f'inline; filename="{nombre_archivo}"'
    return response
