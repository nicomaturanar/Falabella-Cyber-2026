import streamlit as st
import hashlib
import hmac
import urllib.parse
import requests
from datetime import datetime, timedelta, timezone
import pandas as pd
import time
import unicodedata

st.set_page_config(
    page_title="Falabella Marketplace — Cyber Dashboard",
    page_icon="🛒",
    layout="wide",
)

USER_ID  = st.secrets["FALABELLA_USER_ID"]
API_KEY  = st.secrets["FALABELLA_API_KEY"]
BASE_URL = "https://sellercenter-api.falabella.com/"

# ── Diccionarios de extracción ───────────────────────────────────────────────
def normalizar(texto):
    texto = texto.upper()
    return "".join(
        c for c in unicodedata.normalize("NFD", texto)
        if unicodedata.category(c) != "Mn"
    )

MARCAS = [
    "PANAMA JACK", "PJACK", "16 HRS", "PLUMA", "SHERPA", "BRUNO ROSSI", "ZAPPA", "POLLINI",
    "DAKOTA", "ENDURO", "IBIZAS HERITAGE", "LUZ DA LUA", "MINGO", "SHERPAS"
]

LINEAS_CALZADO = [
    "FLIP FLOP", "BALLERINA", "PANTUFLA", "ZAPATILLA", "SANDALIA",
    "MAFALDA", "MOCASIN", "ZAPATO", "BOTIN", "BOTA", "ALPARGATA", "SEGURIDAD"
]

LINEAS_ROPA = [
    "BERMUDA", "BUZO", "CAMISA MC", "CAMISA ML", "CAMISA",
    "CHAQUETAS", "CHAQUETA", "CORTAVIENTO", "GORRO", "JEANS", "JOCKEY",
    "JOGGER", "PANTALONES", "PANTALON", "PARKA ML", "PARKA",
    "POLAR", "POLERA MC", "POLERA ML", "POLERA PIQUE", "POLERON", "POLERA", "MANGA CORTA", "MANGA LARGA",
    "SHORT", "TRAJE DE BAÑO"
]

LINEAS_BAGS = [
    "BACKPACK", "BANANO", "BANDANAS", "BANDANA", "BANDOLERA", "BELTBAG", "BILLETERAS",
    "BOLSO", "BOWLING", "CALCETIN", "CARTERAS", "CHARMS", "CINTURONES",
    "CINTURON", "CLASICAS", "CLUTCH", "CROSSBODY", "ESTUCHES", "FIESTA",
    "LLAVERO", "MOCHILA", "PANUELOS", "STRAPS", "TOTE"
]

GENEROS = ["NINA", "NINO", "HOMBRE", "MUJER", "UNISEX"]

# Mapa de terminos -> linea display para Ropa
ROPA_TERMINOS = {
    "BERMUDA":      "Bermuda",
    "BUZO":         "Buzo",
    "CAMISA MC":    "Camisa",
    "CAMISA ML":    "Camisa",
    "CAMISA":       "Camisa",
    "CHAQUETAS":    "Chaqueta",
    "CHAQUETA":     "Chaqueta",
    "CORTAVIENTO":  "Cortaviento",
    "GORRO":        "Gorro",
    "JEANS":        "Jeans",
    "JOCKEY":       "Jockey",
    "JOGGER":       "Jogger",
    "PANTALONES":   "Pantalon",
    "PANTALON":     "Pantalon",
    "PARKA ML":     "Parka",
    "PARKA":        "Parka",
    "POLAR":        "Polar",
    "POLERA MC":    "Polera",
    "POLERA ML":    "Polera",
    "POLERA PIQUE": "Polera",
    "POLERON":      "Polera",
    "POLERA":       "Polera",
    "MANGA CORTA":  "Polera",
    "MANGA LARGA":  "Polera",
    "SHORT":        "Short",
    "TRAJE DE BANO":"Traje de Bano",
}

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

SKU_PREFIJOS = {
    "PJ":  "Panama Jack",
    "PO":  "Pollini",
    "16H": "16 Hrs",
    "BR":  "Bruno Rossi",
}

def extraer_marca(nombre, sku=""):
    n = normalizar(nombre)
    for marca in MARCAS:
        if normalizar(marca) in n:
            return marca.title()
    # Fallback: prefijo de SKU
    sku_up = sku.upper()
    for prefijo, marca in SKU_PREFIJOS.items():
        if sku_up.startswith(prefijo):
            return marca
    return "Sin marca"

GENERO_DISPLAY = {"NINA": "Niña", "NINO": "Niño", "HOMBRE": "Hombre", "MUJER": "Mujer", "UNISEX": "Unisex"}
def extraer_genero(nombre):
    n = normalizar(nombre)
    # Cartera siempre es Mujer
    if "CARTERA" in n:
        return "Mujer"
    for genero in GENEROS:
        if genero in n:
            return GENERO_DISPLAY.get(genero, genero.title())
    return "Sin género"

# ── API ──────────────────────────────────────────────────────────────────────
def sign_request(params, api_key):
    sorted_params = sorted(params.items())
    query_string  = urllib.parse.urlencode(sorted_params)
    return hmac.new(api_key.encode(), query_string.encode(), hashlib.sha256).hexdigest()

def call_api(action, extra_params={}):
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    params = {
        "Action": action, "Format": "JSON", "Timestamp": timestamp,
        "UserID": USER_ID, "Version": "1.0", **extra_params,
    }
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
        if not data:
            break
        orders = data.get("SuccessResponse", {}).get("Body", {}).get("Orders", {}).get("Order", [])
        if isinstance(orders, dict):
            orders = [orders]
        if not orders:
            break
        all_orders.extend(orders)
        if len(orders) < 100:
            break
        params["Offset"] += 100
    return all_orders

@st.cache_data(ttl=600)
def get_order_items(order_id):
    data = call_api("GetOrderItems", {"OrderId": order_id})
    if not data:
        return []
    items = data.get("SuccessResponse", {}).get("Body", {}).get("OrderItems", {}).get("OrderItem", [])
    if isinstance(items, dict):
        items = [items]
    return items or []

def get_all_items(orders):
    all_items = []
    progress = st.progress(0, text="Cargando detalle de órdenes...")
    total = len(orders)
    for i, order in enumerate(orders):
        order_id = order.get("OrderId")
        items = get_order_items(order_id)
        for item in items:
            nombre = item.get("Name", "") or ""
            sku    = item.get("Sku", "") or ""
            linea, categoria = extraer_linea_y_categoria(nombre, sku)
            all_items.append({
                "order_id":   order_id,
                "created_at": pd.to_datetime(order.get("CreatedAt")),
                "status":     item.get("Status", ""),
                "sku":        sku,
                "nombre":     nombre,
                "marca":      extraer_marca(nombre, sku),
                "linea":      linea,
                "categoria":  categoria,
                "genero":     extraer_genero(nombre),
                "price":      float(item.get("PaidPrice", 0) or 0),
                "qty":        int(item.get("QtyOrdered", 1) or 1),
            })
        progress.progress((i + 1) / total, text=f"Cargando orden {i+1} de {total}...")
    progress.empty()
    return pd.DataFrame(all_items) if all_items else pd.DataFrame()

def orders_to_df(orders):
    if not orders:
        return pd.DataFrame()
    rows = []
    for o in orders:
        rows.append({
            "order_id":    o.get("OrderId"),
            "status":      o.get("Statuses", {}).get("Status", ""),
            "created_at":  pd.to_datetime(o.get("CreatedAt")),
            "price":       float(o.get("Price", 0) or 0),
            "items_count": int(o.get("ItemsCount", 0) or 0),
        })
    df = pd.DataFrame(rows)
    df["hour"] = df["created_at"].dt.floor("h")
    return df

# ── UI ───────────────────────────────────────────────────────────────────────
st.title("🛒 Falabella Marketplace — Cyber Dashboard")
st.caption(f"Última actualización: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')} | Gino S.A")

with st.sidebar:
    st.header("⚙️ Período")
    modo = st.radio("Período", ["Hoy", "Últimas 24h", "Rango personalizado"], label_visibility="collapsed")
    if modo == "Rango personalizado":
        fecha_inicio = st.date_input("Desde", value=datetime.now().date())
        fecha_fin    = st.date_input("Hasta", value=datetime.now().date())
        created_after  = datetime.combine(fecha_inicio, datetime.min.time()).strftime("%Y-%m-%dT00:00:00+00:00")
        created_before = datetime.combine(fecha_fin,    datetime.max.time()).strftime("%Y-%m-%dT23:59:59+00:00")
    elif modo == "Últimas 24h":
        created_after  = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%S+00:00")
        created_before = None
    else:
        created_after  = datetime.now().strftime("%Y-%m-%dT00:00:00+00:00")
        created_before = None
    auto_refresh = st.checkbox("🔄 Auto-refresh cada 10 min", value=False)
    if st.button("🔃 Actualizar ahora", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

with st.spinner("Consultando órdenes en Falabella..."):
    orders_raw = get_orders(created_after, created_before)

df_orders = orders_to_df(orders_raw)
if df_orders.empty:
    st.warning("No se encontraron órdenes en el período seleccionado.")
    st.stop()

df_items = get_all_items(orders_raw)

# ── Filtros ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.divider()
    st.header("🔍 Filtros")
    filtro_cats = filtro_marcas = filtro_lineas = filtro_generos = []
    if not df_items.empty:
        filtro_cats    = st.multiselect("🗂️ Categoría", sorted(df_items["categoria"].dropna().unique()))
        filtro_marcas  = st.multiselect("🏷️ Marca",     sorted(df_items["marca"].dropna().unique()))
        filtro_lineas  = st.multiselect("👟 Línea",     sorted(df_items["linea"].dropna().unique()))
        filtro_generos = st.multiselect("👤 Género",    sorted(df_items["genero"].dropna().unique()))

df_items_f = df_items.copy()
if filtro_cats:    df_items_f = df_items_f[df_items_f["categoria"].isin(filtro_cats)]
if filtro_marcas:  df_items_f = df_items_f[df_items_f["marca"].isin(filtro_marcas)]
if filtro_lineas:  df_items_f = df_items_f[df_items_f["linea"].isin(filtro_lineas)]
if filtro_generos: df_items_f = df_items_f[df_items_f["genero"].isin(filtro_generos)]

hay_filtros = any([filtro_cats, filtro_marcas, filtro_lineas, filtro_generos])
if hay_filtros and not df_items_f.empty:
    df_orders_f = df_orders[df_orders["order_id"].isin(df_items_f["order_id"].unique())]
else:
    df_orders_f = df_orders

if hay_filtros:
    partes = []
    if filtro_cats:    partes.append(f"Categoría: **{', '.join(filtro_cats)}**")
    if filtro_marcas:  partes.append(f"Marca: **{', '.join(filtro_marcas)}**")
    if filtro_lineas:  partes.append(f"Línea: **{', '.join(filtro_lineas)}**")
    if filtro_generos: partes.append(f"Género: **{', '.join(filtro_generos)}**")
    st.info(f"🔍 Filtros activos → {' | '.join(partes)}")

# ── KPIs ─────────────────────────────────────────────────────────────────────
st.subheader("📊 Resumen general")
col1, col2, col3, col4 = st.columns(4)
total_ordenes = len(df_orders_f)
gmv_total     = df_orders_f["price"].sum()
total_items   = df_orders_f["items_count"].sum()
ticket_prom   = gmv_total / total_ordenes if total_ordenes else 0
col1.metric("🛍️ Órdenes totales",  f"{total_ordenes:,}")
col2.metric("💰 GMV total",         f"${gmv_total:,.0f}")
col3.metric("📦 Unidades vendidas", f"{total_items:,}")
col4.metric("🎯 Ticket promedio",   f"${ticket_prom:,.0f}")
st.divider()

# ── Hora a hora ──────────────────────────────────────────────────────────────
st.subheader("📈 Evolución hora a hora")
hourly = (
    df_orders_f.groupby("hour")
    .agg(ordenes=("order_id", "count"), gmv=("price", "sum"))
    .reset_index()
)
hourly["hour_label"] = hourly["hour"].dt.strftime("%H:%M")
tab1, tab2 = st.tabs(["Órdenes", "GMV"])
with tab1:
    st.bar_chart(hourly.set_index("hour_label")["ordenes"])
with tab2:
    st.bar_chart(hourly.set_index("hour_label")["gmv"])

st.subheader("🕐 Tabla hora a hora")
horas = [f"{h:02d}:00" for h in range(datetime.now().hour + 1)]
hourly_table = hourly[["hour_label", "ordenes", "gmv"]].set_index("hour_label").reindex(horas, fill_value=0).reset_index()
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
    ht[col] = ht[col].apply(lambda x: f"${x:,.0f}")
ht["Órdenes"]    = ht["Órdenes"].astype(int)
ht["Órd. Acum."] = ht["Órd. Acum."].astype(int)
st.dataframe(ht[["Hora", "Órdenes", "Órd. Acum.", "Unidades", "GMV", "GMV Acum.", "Ticket Prom."]], use_container_width=True, hide_index=True)
st.divider()

# ── Tabla de performance genérica ────────────────────────────────────────────
def tabla_performance(df, col, titulo, emoji):
    st.subheader(f"{emoji} Performance por {titulo}")
    agg = (
        df.groupby(col)
        .agg(ordenes=("order_id", "nunique"), unidades=("qty", "sum"), gmv=("price", "sum"))
        .reset_index().sort_values("gmv", ascending=False)
    )
    agg.columns = [titulo, "Órdenes", "Unidades", "GMV"]
    c1, c2 = st.columns([1, 2])
    with c1:
        d = agg.copy()
        d["GMV"] = d["GMV"].apply(lambda x: f"${x:,.0f}")
        st.dataframe(d, use_container_width=True, hide_index=True)
    with c2:
        st.bar_chart(agg.set_index(titulo)["GMV"].sort_values(ascending=False).head(10))
    st.divider()

if not df_items_f.empty:
    tabla_performance(df_items_f, "categoria", "Categoría", "🗂️")
    tabla_performance(df_items_f, "linea",     "Línea",     "👟")
    tabla_performance(df_items_f, "marca",     "Marca",     "🏷️")
    tabla_performance(df_items_f, "genero",    "Género",    "👤")

    # ── Top Productos ────────────────────────────────────────────────────────
    st.subheader("🏆 Top Productos")
    prod_df = (
        df_items_f.groupby(["sku", "nombre", "marca", "linea", "genero", "categoria"])
        .agg(unidades=("qty", "sum"), gmv=("price", "sum"))
        .reset_index().sort_values("gmv", ascending=False).head(50)
    )
    prod_df["Producto"] = prod_df["sku"] + " — " + prod_df["nombre"]
    pd_display = prod_df[["Producto", "categoria", "marca", "linea", "genero", "unidades", "gmv"]].copy()
    pd_display.columns = ["Producto", "Categoría", "Marca", "Línea", "Género", "Unidades", "GMV"]
    pd_display["GMV"] = pd_display["GMV"].apply(lambda x: f"${x:,.0f}")
    st.dataframe(pd_display, use_container_width=True, hide_index=True)
    st.divider()

# ── Estado órdenes ───────────────────────────────────────────────────────────
st.subheader("🔖 Estado de órdenes")
status_counts = df_orders_f["status"].value_counts().reset_index()
status_counts.columns = ["Estado", "Cantidad"]
c1, c2 = st.columns([1, 2])
with c1:
    st.dataframe(status_counts, use_container_width=True, hide_index=True)
with c2:
    st.bar_chart(status_counts.set_index("Estado")["Cantidad"])
st.divider()

# ── Detalle órdenes ──────────────────────────────────────────────────────────
st.subheader("📋 Detalle de órdenes")
df_display = df_orders_f[["order_id", "created_at", "status", "price", "items_count"]].copy()
df_display.columns = ["Order ID", "Fecha creación", "Estado", "Precio", "Ítems"]
df_display = df_display.sort_values("Fecha creación", ascending=False)
st.dataframe(df_display, use_container_width=True, hide_index=True)
csv = df_display.to_csv(index=False).encode("utf-8")
st.download_button("⬇️ Descargar CSV", csv, "ordenes_cyber.csv", "text/csv")

if auto_refresh:
    time.sleep(600)
    st.rerun()
