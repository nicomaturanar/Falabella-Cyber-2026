import streamlit as st
import hashlib
import hmac
import urllib.parse
import requests
from datetime import datetime, timedelta, timezone
import pandas as pd
import time
import unicodedata
import json
import os

st.set_page_config(
    page_title="Falabella Marketplace — Cyber Dashboard",
    page_icon="🛒",
    layout="wide",
)

USER_ID  = st.secrets["FALABELLA_USER_ID"]
API_KEY  = st.secrets["FALABELLA_API_KEY"]
BASE_URL = "https://sellercenter-api.falabella.com/"
CACHE_FILE = "/tmp/cyber_cache.json"
CYBER_START = "2026-05-31"

# ── Helpers ──────────────────────────────────────────────────────────────────
def normalizar(texto):
    texto = texto.upper()
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")

def clp(valor):
    return "$" + f"{int(valor):,}".replace(",", ".")

def var_pct(actual, anterior):
    try:
        if anterior == 0 or pd.isna(anterior) or pd.isna(actual):
            return None
        pct = ((actual - anterior) / anterior) * 100
        return None if pd.isna(pct) else round(pct, 1)
    except:
        return None

# ── Listas extracción ────────────────────────────────────────────────────────
MARCAS = ["PANAMA JACK", "PJACK", "16 HRS", "PLUMA", "SHERPA", "BRUNO ROSSI",
          "ZAPPA", "POLLINI", "DAKOTA", "ENDURO", "IBIZAS HERITAGE", "LUZ DA LUA", "MINGO"]

SKU_PREFIJOS = {"PJ": "Panama Jack", "PO": "Pollini", "16": "16 Hrs", "BR": "Bruno Rossi"}

ROPA_TERMINOS = {
    "BERMUDA": "Bermuda", "BUZO": "Buzo", "CAMISA MC": "Camisa", "CAMISA ML": "Camisa",
    "CAMISA": "Camisa", "CHAQUETAS": "Chaqueta", "CHAQUETA": "Chaqueta",
    "CORTAVIENTO": "Cortaviento", "GORRO": "Gorro", "JEANS": "Jeans", "JOCKEY": "Jockey",
    "JOGGER": "Jogger", "PANTALONES": "Pantalon", "PANTALON": "Pantalon",
    "PARKA ML": "Parka", "PARKA": "Parka", "POLAR": "Polar",
    "POLERA MC": "Polera", "POLERA ML": "Polera", "POLERA PIQUE": "Polera",
    "POLERON": "Polera", "POLERA": "Polera", "MANGA CORTA": "Polera", "MANGA LARGA": "Polera",
    "SHORT": "Short", "TRAJE DE BANO": "Traje de Bano",
}

LINEAS_BAGS = ["BACKPACK", "BANANO", "BANDANAS", "BANDANA", "BANDOLERA", "BELTBAG",
               "BILLETERAS", "BOLSO", "BOWLING", "CALCETIN", "CARTERAS", "CHARMS",
               "CINTURONES", "CINTURON", "CLASICAS", "CLUTCH", "CROSSBODY", "ESTUCHES",
               "FIESTA", "LLAVERO", "MOCHILA", "PANUELOS", "STRAPS", "TOTE"]

LINEAS_CALZADO = ["FLIP FLOP", "BALLERINA", "PANTUFLA", "ZAPATILLA", "SANDALIA",
                  "MAFALDA", "MOCASIN", "ZAPATO", "BOTIN", "BOTA", "ALPARGATA", "SEGURIDAD"]

GENEROS = ["NINA", "NINO", "HOMBRE", "MUJER", "UNISEX"]
GENERO_DISPLAY = {"NINA": "Niña", "NINO": "Niño", "HOMBRE": "Hombre", "MUJER": "Mujer", "UNISEX": "Unisex"}

def extraer_linea_y_categoria(nombre, sku):
    n = normalizar(nombre)
    s = normalizar(sku)
    if "SEGURIDAD" in n or "SEGURIDAD" in s:
        return "Seguridad", "Calzado"
    for termino, linea_display in ROPA_TERMINOS.items():
        if normalizar(termino) in n:
            return linea_display, "Ropa"
    for linea in LINEAS_BAGS:
        if normalizar(linea) in n:
            return linea.title(), "Bags & Accesorios"
    for linea in LINEAS_CALZADO:
        if normalizar(linea) in n:
            return linea.title(), "Calzado"
    return "Sin linea", "No identificado"

def extraer_marca(nombre, sku=""):
    n = normalizar(nombre)
    for marca in MARCAS:
        if normalizar(marca) in n:
            return marca.title()
    sku_up = sku.upper()
    for prefijo, marca in SKU_PREFIJOS.items():
        if sku_up.startswith(prefijo):
            return marca
    return "Sin marca"

def extraer_genero(nombre):
    n = normalizar(nombre)
    if "CARTERA" in n:
        return "Mujer"
    for genero in GENEROS:
        if genero in n:
            return GENERO_DISPLAY.get(genero, genero.title())
    return "Sin género"

# ── API ──────────────────────────────────────────────────────────────────────
def sign_request(params, api_key):
    sorted_params = sorted(params.items())
    query_string = urllib.parse.urlencode(sorted_params)
    return hmac.new(api_key.encode(), query_string.encode(), hashlib.sha256).hexdigest()

def call_api(action, extra_params={}):
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    params = {"Action": action, "Format": "JSON", "Timestamp": timestamp,
              "UserID": USER_ID, "Version": "1.0", **extra_params}
    params["Signature"] = sign_request(params, API_KEY)
    try:
        resp = requests.get(BASE_URL, params=params, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        st.error(f"Error llamando a {action}: {e}")
        return None

def get_orders(created_after, created_before=None):
    params = {"CreatedAfter": created_after, "Limit": 100, "Offset": 0}
    if created_before:
        params["CreatedBefore"] = created_before
    all_orders = []
    while True:
        data = call_api("GetOrders", params)
        if not data or not isinstance(data, dict):
            break
        try:
            orders = data.get("SuccessResponse", {}).get("Body", {}).get("Orders", {}).get("Order", [])
        except AttributeError:
            break
        if not orders:
            break
        if isinstance(orders, dict):
            orders = [orders]
        all_orders.extend(orders)
        if len(orders) == 0:
            break
        params["Offset"] += 100
    return all_orders

@st.cache_data(ttl=3600)
def get_order_items(order_id):
    data = call_api("GetOrderItems", {"OrderId": order_id})
    if not data:
        return []
    items = data.get("SuccessResponse", {}).get("Body", {}).get("OrderItems", {}).get("OrderItem", [])
    if isinstance(items, dict):
        items = [items]
    return items or []

def procesar_item(item, order):
    order_id = order.get("OrderId")
    nombre = item.get("Name", "") or ""
    sku = item.get("Sku", "") or ""
    shipping_norm = (item.get("ShippingType", "") or "").strip().lower()
    fulfillment = "Fulfillment by Falabella" if ("own" in shipping_norm or shipping_norm == "fulfillment") else "Bodega 101"
    linea, categoria = extraer_linea_y_categoria(nombre, sku)
    return {
        "order_id":    str(order_id),
        "created_at":  str(order.get("CreatedAt", "")),
        "status":      item.get("Status", ""),
        "sku":         sku,
        "modelo":      sku[:7] if len(sku) >= 7 else sku,
        "nombre":      nombre,
        "marca":       extraer_marca(nombre, sku),
        "linea":       linea,
        "categoria":   categoria,
        "genero":      extraer_genero(nombre),
        "fulfillment": fulfillment,
        "price":       float(item.get("PaidPrice", 0) or 0),
        "qty":         int(item.get("QtyOrdered", 1) or 1),
    }

def get_all_items(orders, label="Cargando detalle"):
    all_items = []
    order_map = {str(o.get("OrderId")): o for o in orders}
    order_ids = list(order_map.keys())
    total = len(order_ids)
    if total == 0:
        return []
    progress = st.progress(0, text=f"{label}...")
    for i, oid in enumerate(order_ids):
        try:
            items = get_order_items(oid)
            for item in items:
                all_items.append(procesar_item(item, order_map[oid]))
        except:
            pass
        progress.progress((i + 1) / total, text=f"{label}: {i+1} de {total}...")
    progress.empty()
    return all_items

def orders_to_rows(orders):
    rows = []
    for o in orders:
        rows.append({
            "order_id":    str(o.get("OrderId")),
            "status":      o.get("Statuses", {}).get("Status", ""),
            "created_at":  str(o.get("CreatedAt", "")),
            "price":       float(o.get("Price", 0) or 0),
            "items_count": int(o.get("ItemsCount", 0) or 0),
            "operador":    "Sodimac" if (o.get("OperatorCode", "") or "").lower() in ["sodicl", "sodimac"] else "Falabella",
        })
    return rows

def get_comparativo_anio_anterior(created_after, created_before):
    import datetime as dt_module
    chile_tz = timezone(timedelta(hours=-4))
    hoy = datetime.now(chile_tz)
    hoy_date = hoy.date()
    fecha_inicio = dt_module.date.fromisoformat(created_after[:10])
    fecha_inicio_ant = dt_module.date.fromisocalendar(fecha_inicio.year - 1, fecha_inicio.isocalendar()[1], fecha_inicio.isocalendar()[2])
    if created_before:
        fecha_fin = dt_module.date.fromisoformat(created_before[:10])
        offset = fecha_fin - fecha_inicio
        fecha_fin_ant = fecha_inicio_ant + offset
    else:
        fecha_fin_ant = fecha_inicio_ant
    fecha_fin_real = dt_module.date.fromisoformat((created_before or created_after)[:10]) if created_before else hoy_date
    hora_fin = hoy.strftime("%H:%M:%S") if (created_before is None or fecha_fin_real >= hoy_date) else "23:59:59"
    return f"{fecha_inicio_ant}T00:00:00", f"{fecha_fin_ant}T{hora_fin}", fecha_inicio_ant

# ── Cache persistente ────────────────────────────────────────────────────────
def save_cache(data):
    with open(CACHE_FILE, "w") as f:
        json.dump(data, f)

def load_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r") as f:
            return json.load(f)
    return None

def run_full_update():
    """Carga todos los datos desde CYBER_START hasta ahora y los guarda en cache."""
    chile_tz = timezone(timedelta(hours=-4))
    ahora_chile = datetime.now(chile_tz)
    created_after = f"{CYBER_START}T00:00:00"

    st.info(f"Cargando datos desde {CYBER_START} hasta ahora...")

    # Órdenes actuales
    with st.spinner("Descargando órdenes..."):
        orders_raw = get_orders(created_after)

    orders_rows = orders_to_rows(orders_raw)
    st.success(f"✅ {len(orders_rows)} órdenes descargadas")

    # Items actuales
    items_rows = get_all_items(orders_raw, "Cargando items")
    st.success(f"✅ {len(items_rows)} items procesados")

    # Año anterior
    ca_ant, cb_ant, fecha_ant = get_comparativo_anio_anterior(created_after, None)
    with st.spinner(f"Descargando órdenes año anterior ({fecha_ant})..."):
        orders_ant_raw = get_orders(ca_ant, cb_ant)
        if orders_ant_raw:
            from dateutil import parser as dp
            ca_dt = dp.parse(ca_ant)
            cb_dt = dp.parse(cb_ant)
            orders_ant_raw = [o for o in orders_ant_raw if o.get("CreatedAt") and
                ca_dt <= dp.parse(o["CreatedAt"]).replace(tzinfo=ca_dt.tzinfo) <= cb_dt]

    orders_ant_rows = orders_to_rows(orders_ant_raw)
    st.success(f"✅ {len(orders_ant_rows)} órdenes año anterior")

    # Guardar cache
    cache = {
        "updated_at": ahora_chile.strftime("%d/%m/%Y %H:%M:%S"),
        "orders": orders_rows,
        "items": items_rows,
        "orders_anterior": orders_ant_rows,
    }
    save_cache(cache)
    st.success("✅ Cache guardado correctamente")
    st.rerun()

# ── UI ───────────────────────────────────────────────────────────────────────
st.title("🛒 Falabella Marketplace — Cyber Dashboard")

cache = load_cache()

# Sidebar
with st.sidebar:
    st.header("⚙️ Período")
    if cache:
        st.caption(f"Datos al: {cache.get('updated_at', 'N/A')}")

    modo = st.radio("", ["Hoy", "Cyber completo", "Rango personalizado"], label_visibility="collapsed")

    chile_tz = timezone(timedelta(hours=-4))
    ahora_chile = datetime.now(chile_tz)

    if modo == "Hoy":
        filtro_desde = ahora_chile.strftime("%Y-%m-%d")
        filtro_hasta = ahora_chile.strftime("%Y-%m-%d")
    elif modo == "Cyber completo":
        filtro_desde = CYBER_START
        filtro_hasta = ahora_chile.strftime("%Y-%m-%d")
    else:
        fecha_inicio = st.date_input("Desde", value=ahora_chile.date())
        fecha_fin    = st.date_input("Hasta", value=ahora_chile.date())
        filtro_desde = str(fecha_inicio)
        filtro_hasta = str(fecha_fin)

    st.divider()

    # Botón actualizar (admin)
    with st.expander("🔧 Admin"):
        if st.button("🔄 Actualizar datos completos", use_container_width=True):
            run_full_update()

if not cache:
    st.warning("⚠️ No hay datos cargados. Ve a Admin → Actualizar datos completos.")
    st.stop()

# Cargar datos desde cache
df_orders = pd.DataFrame(cache["orders"])
df_items  = pd.DataFrame(cache["items"])
df_orders_anterior = pd.DataFrame(cache.get("orders_anterior", []))

# Convertir fechas
df_orders["created_at"] = pd.to_datetime(df_orders["created_at"])
df_orders["hour"] = df_orders["created_at"].dt.floor("h")
if not df_items.empty:
    df_items["created_at"] = pd.to_datetime(df_items["created_at"])
    if "modelo" not in df_items.columns:
        df_items["modelo"] = df_items["sku"].str[:7]
if not df_orders_anterior.empty:
    df_orders_anterior["created_at"] = pd.to_datetime(df_orders_anterior["created_at"])

# Filtrar por período seleccionado
df_orders = df_orders[
    (df_orders["created_at"].dt.date >= pd.to_datetime(filtro_desde).date()) &
    (df_orders["created_at"].dt.date <= pd.to_datetime(filtro_hasta).date())
]
if not df_items.empty:
    df_items = df_items[
        (df_items["created_at"].dt.date >= pd.to_datetime(filtro_desde).date()) &
        (df_items["created_at"].dt.date <= pd.to_datetime(filtro_hasta).date())
    ]
if not df_orders_anterior.empty:
    # Filtrar año anterior por mismo rango ISO
    import datetime as dt_module
    desde = pd.to_datetime(filtro_desde).date()
    hasta = pd.to_datetime(filtro_hasta).date()
    desde_ant = dt_module.date.fromisocalendar(desde.year-1, desde.isocalendar()[1], desde.isocalendar()[2])
    hasta_ant = dt_module.date.fromisocalendar(hasta.year-1, hasta.isocalendar()[1], hasta.isocalendar()[2])
    df_orders_anterior = df_orders_anterior[
        (df_orders_anterior["created_at"].dt.date >= desde_ant) &
        (df_orders_anterior["created_at"].dt.date <= hasta_ant)
    ]

if df_orders.empty:
    st.warning("No hay órdenes en el período seleccionado.")
    st.stop()

# Filtros sidebar
with st.sidebar:
    st.header("🔍 Filtros")
    filtro_operador = filtro_fulfillment = filtro_cats = filtro_marcas = filtro_lineas = filtro_generos = []
    if not df_orders.empty:
        filtro_operador = st.multiselect("🏪 Operador", sorted(df_orders["operador"].dropna().unique()))
    if not df_items.empty:
        filtro_fulfillment = st.multiselect("🚚 Fulfillment", sorted(df_items["fulfillment"].dropna().unique()))
        filtro_cats    = st.multiselect("🗂️ Categoría", sorted(df_items["categoria"].dropna().unique()))
        filtro_marcas  = st.multiselect("🏷️ Marca",     sorted(df_items["marca"].dropna().unique()))
        filtro_lineas  = st.multiselect("👟 Línea",     sorted(df_items["linea"].dropna().unique()))
        filtro_generos = st.multiselect("👤 Género",    sorted(df_items["genero"].dropna().unique()))

# Aplicar filtros
if filtro_operador:
    df_orders_f = df_orders[df_orders["operador"].isin(filtro_operador)]
else:
    df_orders_f = df_orders

df_items_f = df_items.copy()
if not df_items_f.empty:
    if filtro_operador:    df_items_f = df_items_f[df_items_f["order_id"].isin(df_orders_f["order_id"])]
    if filtro_fulfillment: df_items_f = df_items_f[df_items_f["fulfillment"].isin(filtro_fulfillment)]
    if filtro_cats:        df_items_f = df_items_f[df_items_f["categoria"].isin(filtro_cats)]
    if filtro_marcas:      df_items_f = df_items_f[df_items_f["marca"].isin(filtro_marcas)]
    if filtro_lineas:      df_items_f = df_items_f[df_items_f["linea"].isin(filtro_lineas)]
    if filtro_generos:     df_items_f = df_items_f[df_items_f["genero"].isin(filtro_generos)]

hay_filtros = any([filtro_operador, filtro_fulfillment, filtro_cats, filtro_marcas, filtro_lineas, filtro_generos])
if hay_filtros and not df_items_f.empty:
    df_orders_f = df_orders_f[df_orders_f["order_id"].isin(df_items_f["order_id"].unique())]

if hay_filtros:
    partes = []
    if filtro_operador:    partes.append(f"Operador: **{', '.join(filtro_operador)}**")
    if filtro_fulfillment: partes.append(f"Fulfillment: **{', '.join(filtro_fulfillment)}**")
    if filtro_cats:        partes.append(f"Categoría: **{', '.join(filtro_cats)}**")
    if filtro_marcas:      partes.append(f"Marca: **{', '.join(filtro_marcas)}**")
    if filtro_lineas:      partes.append(f"Línea: **{', '.join(filtro_lineas)}**")
    if filtro_generos:     partes.append(f"Género: **{', '.join(filtro_generos)}**")
    st.info(f"🔍 Filtros activos → {' | '.join(partes)}")

# Caption
st.caption(f"Última actualización: {cache.get('updated_at', 'N/A')} | Gino S.A")

# ── KPIs ─────────────────────────────────────────────────────────────────────
st.subheader("📊 Resumen general")
col1, col2, col3, col4 = st.columns(4)
total_ordenes = len(df_orders_f)
gmv_total     = df_orders_f["price"].sum()
total_items   = df_orders_f["items_count"].sum()
ticket_prom   = gmv_total / total_ordenes if total_ordenes else 0

total_ordenes_ant = len(df_orders_anterior) if not df_orders_anterior.empty else 0
gmv_ant           = df_orders_anterior["price"].sum() if not df_orders_anterior.empty else 0
total_items_ant   = df_orders_anterior["items_count"].sum() if not df_orders_anterior.empty else 0
fecha_ant_label   = f"{desde_ant.strftime('%d/%m/%Y')}" if not df_orders_anterior.empty else ""

col1.metric("🛍️ Órdenes totales",  f"{total_ordenes:,}",
    delta=f"{var_pct(total_ordenes, total_ordenes_ant):+.1f}% vs {fecha_ant_label}" if total_ordenes_ant else None)
col2.metric("💰 Ventas (CLP)", clp(gmv_total),
    delta=f"{var_pct(gmv_total, gmv_ant):+.1f}% vs {fecha_ant_label}" if gmv_ant else None)
col3.metric("📦 Unidades vendidas", f"{total_items:,}",
    delta=f"{var_pct(total_items, total_items_ant):+.1f}% vs {fecha_ant_label}" if total_items_ant else None)
col4.metric("🎯 Ticket promedio", clp(ticket_prom))
st.divider()

# ── Performance General ───────────────────────────────────────────────────────
st.subheader("📊 Performance General")
if not df_items_f.empty:
    ff_resumen = (
        df_items_f.groupby("fulfillment")
        .agg(ordenes=("order_id", "nunique"), unidades=("qty", "sum"), ventas=("price", "sum"))
        .reset_index().sort_values("ventas", ascending=False)
    )
    total_v = ff_resumen["ventas"].sum()
    ff_resumen["share"] = (ff_resumen["ventas"] / total_v * 100).round(1) if total_v > 0 else 0
    total_row = pd.DataFrame([{"fulfillment": "Total", "ordenes": ff_resumen["ordenes"].sum(),
        "unidades": ff_resumen["unidades"].sum(), "ventas": ff_resumen["ventas"].sum(), "share": 100.0}])
    ff_tabla = pd.concat([ff_resumen, total_row], ignore_index=True)
    ff_tabla["ventas"] = ff_tabla["ventas"].apply(clp)
    ff_tabla["share"]  = ff_tabla["share"].apply(lambda x: f"{x:.1f}%")
    ff_tabla.columns   = ["Fulfillment", "Órdenes", "Unidades", "Ventas (CLP)", "Share %"]
    st.dataframe(ff_tabla, use_container_width=True, hide_index=True)
st.divider()

# ── Hora a hora ───────────────────────────────────────────────────────────────
st.subheader("📈 Evolución hora a hora")
hourly = (df_orders_f.groupby("hour").agg(ordenes=("order_id", "count"), gmv=("price", "sum")).reset_index())
hourly["hour_label"] = hourly["hour"].dt.strftime("%H:%M")
tab1, tab2 = st.tabs(["Órdenes", "GMV"])
with tab1:
    st.bar_chart(hourly.set_index("hour_label")["ordenes"])
with tab2:
    st.bar_chart(hourly.set_index("hour_label")["gmv"])

st.subheader("🕐 Tabla hora a hora")
horas = [f"{h:02d}:00" for h in range(ahora_chile.hour + 1)] if modo == "Hoy" else hourly["hour_label"].tolist()
hourly_table = hourly[["hour_label","ordenes","gmv"]].set_index("hour_label").reindex(horas, fill_value=0).reset_index()
hourly_table.columns = ["Hora", "Órdenes", "GMV"]
if not df_items_f.empty:
    hi = df_items_f.copy()
    hi["hour_label"] = hi["created_at"].dt.floor("h").dt.strftime("%H:%M")
    u = hi.groupby("hour_label")["qty"].sum().reset_index()
    u.columns = ["Hora", "Unidades"]
    hourly_table = hourly_table.merge(u, on="Hora", how="left").fillna(0)
    hourly_table["Unidades"] = hourly_table["Unidades"].astype(int)
else:
    hourly_table["Unidades"] = 0
hourly_table["GMV Acum."]    = hourly_table["GMV"].cumsum()
hourly_table["Órd. Acum."]   = hourly_table["Órdenes"].cumsum()
hourly_table["Ticket Prom."] = (hourly_table["GMV"] / hourly_table["Órdenes"].replace(0, pd.NA)).fillna(0)
ht = hourly_table.copy()
for col in ["GMV", "GMV Acum.", "Ticket Prom."]:
    ht[col] = ht[col].apply(clp)
ht["Órdenes"] = ht["Órdenes"].astype(int)
ht["Órd. Acum."] = ht["Órd. Acum."].astype(int)
st.dataframe(ht[["Hora","Órdenes","Órd. Acum.","Unidades","GMV","GMV Acum.","Ticket Prom."]], use_container_width=True, hide_index=True)
st.divider()

# ── Tablas de performance ─────────────────────────────────────────────────────
def tabla_performance(df, col, titulo, emoji, df_ant=None):
    st.subheader(f"{emoji} Performance por {titulo}")
    agg = (df.groupby(col).agg(ordenes=("order_id","nunique"), unidades=("qty","sum"), ventas=("price","sum"))
           .reset_index().sort_values("ventas", ascending=False))
    total_v = agg["ventas"].sum()
    agg["share"] = (agg["ventas"] / total_v * 100).round(1) if total_v > 0 else 0
    if df_ant is not None and not df_ant.empty and col in df_ant.columns:
        agg_ant = df_ant.groupby(col).agg(unidades_ant=("qty","sum"), ventas_ant=("price","sum")).reset_index()
        agg = agg.merge(agg_ant, on=col, how="left").fillna(0)
        agg["Var% Ventas"]   = agg.apply(lambda r: var_pct(r["ventas"], r["ventas_ant"]), axis=1)
        agg["Var% Unidades"] = agg.apply(lambda r: var_pct(r["unidades"], r["unidades_ant"]), axis=1)
        d = agg[[col,"ordenes","unidades","Var% Unidades","ventas","share","Var% Ventas"]].copy()
        d.columns = [titulo,"Órdenes","Unidades","Var% Unidades","Ventas (CLP)","Share %","Var% Ventas"]
        d["Ventas (CLP)"]  = d["Ventas (CLP)"].apply(clp)
        d["Share %"]       = d["Share %"].apply(lambda x: f"{x:.1f}%")
        d["Var% Ventas"]   = d["Var% Ventas"].apply(lambda x: f"{x:+.1f}%" if (x is not None and not pd.isna(x)) else "N/A")
        d["Var% Unidades"] = d["Var% Unidades"].apply(lambda x: f"{x:+.1f}%" if (x is not None and not pd.isna(x)) else "N/A")
    else:
        agg.columns = [titulo,"Órdenes","Unidades","Ventas (CLP)","Share %"]
        d = agg.copy()
        d["Ventas (CLP)"] = d["Ventas (CLP)"].apply(clp)
        d["Share %"]      = d["Share %"].apply(lambda x: f"{x:.1f}%")
    c1, c2 = st.columns([1, 2])
    with c1:
        st.dataframe(d, use_container_width=True, hide_index=True)
    with c2:
        st.bar_chart(agg.set_index(titulo)["Ventas (CLP)"] if "Ventas (CLP)" in agg.columns else agg.set_index(titulo).iloc[:,3])
    st.divider()

if not df_items_f.empty:
    tabla_performance(df_items_f, "categoria", "Categoría", "🗂️")
    tabla_performance(df_items_f, "linea",     "Línea",     "👟")
    tabla_performance(df_items_f, "marca",     "Marca",     "🏷️")
    tabla_performance(df_items_f, "genero",    "Género",    "👤")

    # ── Performance por Modelo ────────────────────────────────────────────────
    st.subheader("🔢 Performance por Modelo")
    modelo_df = (
        df_items_f.groupby("modelo")
        .agg(nombre=("nombre","first"), marca=("marca","first"), linea=("linea","first"),
             categoria=("categoria","first"), genero=("genero","first"),
             ordenes=("order_id","nunique"), unidades=("qty","sum"), ventas=("price","sum"))
        .reset_index().sort_values("ventas", ascending=False)
    )
    total_mod = modelo_df["ventas"].sum()
    modelo_df["share"] = (modelo_df["ventas"] / total_mod * 100).round(1) if total_mod > 0 else 0
    mod_display = modelo_df.copy()
    mod_display["ventas"] = mod_display["ventas"].apply(clp)
    mod_display["share"]  = mod_display["share"].apply(lambda x: f"{x:.1f}%")
    mod_display.columns   = ["Modelo","Nombre","Marca","Línea","Categoría","Género","Órdenes","Unidades","Ventas (CLP)","Share %"]
    st.dataframe(mod_display, use_container_width=True, hide_index=True)
    st.divider()

    # ── Easy Fit ──────────────────────────────────────────────────────────────
    st.subheader("👟 Performance Easy Fit")
    df_easy = df_items_f[df_items_f["modelo"].isin(["16U0362","16M0362"])].copy()
    if not df_easy.empty:
        df_easy["sku15"] = df_easy["sku"].str[:-3]
        easy_df = (df_easy.groupby(["sku15","nombre","marca","linea","genero"])
            .agg(unidades=("qty","sum"), ventas=("price","sum")).reset_index().sort_values("ventas", ascending=False))
        total_e = easy_df["ventas"].sum()
        easy_df["share"] = (easy_df["ventas"] / total_e * 100).round(1) if total_e > 0 else 0
        c1,c2,c3 = st.columns(3)
        c1.metric("Órdenes",      f"{df_easy['order_id'].nunique():,}")
        c2.metric("Unidades",     f"{df_easy['qty'].sum():,}")
        c3.metric("Ventas (CLP)", clp(df_easy["price"].sum()))
        easy_display = easy_df.copy()
        easy_display["ventas"] = easy_display["ventas"].apply(clp)
        easy_display["share"]  = easy_display["share"].apply(lambda x: f"{x:.1f}%")
        easy_display.columns   = ["SKU 15","Nombre","Marca","Línea","Género","Unidades","Ventas (CLP)","Share %"]
        st.dataframe(easy_display, use_container_width=True, hide_index=True)
    else:
        st.info("No hay ventas de Easy Fit en el período seleccionado.")
    st.divider()

# ── Performance por Fulfillment ───────────────────────────────────────────────
st.subheader("🚚 Performance por Fulfillment")
if not df_items_f.empty:
    ff_df = (df_items_f.groupby("fulfillment")
        .agg(ordenes=("order_id","nunique"), unidades=("qty","sum"), ventas=("price","sum"))
        .reset_index().sort_values("ventas", ascending=False))
    total_ff = ff_df["ventas"].sum()
    ff_df["share"] = (ff_df["ventas"] / total_ff * 100).round(1) if total_ff > 0 else 0
    ff_d = ff_df.copy()
    ff_d["ventas"] = ff_d["ventas"].apply(clp)
    ff_d["share"]  = ff_d["share"].apply(lambda x: f"{x:.1f}%")
    ff_d.columns   = ["Fulfillment","Órdenes","Unidades","Ventas (CLP)","Share %"]
    c1,c2 = st.columns([1,2])
    with c1: st.dataframe(ff_d, use_container_width=True, hide_index=True)
    with c2: st.bar_chart(ff_df.set_index("fulfillment")["ventas"])

    df_fbf = df_items_f[df_items_f["fulfillment"] == "Fulfillment by Falabella"]
    if not df_fbf.empty:
        st.markdown("#### 📦 Detalle Fulfillment by Falabella")
        c1,c2 = st.columns(2)
        with c1:
            st.markdown("**🗂️ Categorías**")
            cat_fbf = (df_fbf.groupby("categoria").agg(unidades=("qty","sum"), ventas=("price","sum"))
                .reset_index().sort_values("ventas", ascending=False))
            total_cf = cat_fbf["ventas"].sum()
            cat_fbf["share"] = (cat_fbf["ventas"] / total_cf * 100).round(1) if total_cf > 0 else 0
            cat_fbf["ventas"] = cat_fbf["ventas"].apply(clp)
            cat_fbf["share"]  = cat_fbf["share"].apply(lambda x: f"{x:.1f}%")
            cat_fbf.columns   = ["Categoría","Unidades","Ventas (CLP)","Share %"]
            st.dataframe(cat_fbf, use_container_width=True, hide_index=True)
        with c2:
            st.markdown("**👟 Líneas**")
            linea_fbf = (df_fbf.groupby("linea").agg(unidades=("qty","sum"), ventas=("price","sum"))
                .reset_index().sort_values("ventas", ascending=False))
            total_lf = linea_fbf["ventas"].sum()
            linea_fbf["share"] = (linea_fbf["ventas"] / total_lf * 100).round(1) if total_lf > 0 else 0
            linea_fbf["ventas"] = linea_fbf["ventas"].apply(clp)
            linea_fbf["share"]  = linea_fbf["share"].apply(lambda x: f"{x:.1f}%")
            linea_fbf.columns   = ["Línea","Unidades","Ventas (CLP)","Share %"]
            st.dataframe(linea_fbf, use_container_width=True, hide_index=True)
        st.markdown("**🏆 Top Productos FBF**")
        df_fbf_s = df_fbf.copy()
        df_fbf_s["sku15"] = df_fbf_s["sku"].str[:-3]
        top_fbf = (df_fbf_s.groupby(["sku15","nombre","marca","linea","genero","categoria"])
            .agg(unidades=("qty","sum"), ventas=("price","sum")).reset_index()
            .sort_values("ventas", ascending=False).head(20))
        top_fbf["ventas"] = top_fbf["ventas"].apply(clp)
        top_fbf.columns   = ["SKU 15","Nombre","Marca","Línea","Género","Categoría","Unidades","Ventas (CLP)"]
        st.dataframe(top_fbf, use_container_width=True, hide_index=True)
st.divider()

# ── Estado órdenes ────────────────────────────────────────────────────────────
st.subheader("🔖 Estado de órdenes")
status_counts = df_orders_f["status"].value_counts().reset_index()
status_counts.columns = ["Estado","Cantidad"]
c1,c2 = st.columns([1,2])
with c1: st.dataframe(status_counts, use_container_width=True, hide_index=True)
with c2: st.bar_chart(status_counts.set_index("Estado")["Cantidad"])
st.divider()

# ── Top Productos ─────────────────────────────────────────────────────────────
if not df_items_f.empty:
    st.subheader("🏆 Top Productos")
    df_sku15 = df_items_f.copy()
    df_sku15["sku15"] = df_sku15["sku"].str[:-3]
    prod_df = (df_sku15.groupby(["sku15","marca","linea","genero","categoria"])
        .agg(nombre=("nombre","first"), unidades=("qty","sum"), ventas=("price","sum"))
        .reset_index().sort_values("ventas", ascending=False).head(50))
    pd_d = prod_df[["sku15","nombre","categoria","marca","linea","genero","unidades","ventas"]].copy()
    pd_d.columns = ["SKU 15","Nombre","Categoría","Marca","Línea","Género","Unidades","Ventas (CLP)"]
    pd_d["Ventas (CLP)"] = pd_d["Ventas (CLP)"].apply(clp)
    st.dataframe(pd_d, use_container_width=True, hide_index=True)

# ── Detalle órdenes ───────────────────────────────────────────────────────────
st.subheader("📋 Detalle de órdenes")
df_det = df_orders_f[["order_id","created_at","status","price","items_count"]].copy()
df_det.columns = ["Order ID","Fecha creación","Estado","Precio","Ítems"]
df_det = df_det.sort_values("Fecha creación", ascending=False)
st.dataframe(df_det, use_container_width=True, hide_index=True)
csv = df_det.to_csv(index=False).encode("utf-8")
st.download_button("⬇️ Descargar CSV", csv, "ordenes_cyber.csv", "text/csv")
