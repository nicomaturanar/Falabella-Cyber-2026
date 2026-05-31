import streamlit as st
import hashlib
import hmac
import urllib.parse
import requests
from datetime import datetime, timedelta, timezone
import pandas as pd
import time
import re

st.set_page_config(
    page_title="Falabella Marketplace — Cyber Dashboard",
    page_icon="🛒",
    layout="wide",
)

USER_ID  = st.secrets["FALABELLA_USER_ID"]
API_KEY  = st.secrets["FALABELLA_API_KEY"]
BASE_URL = "https://sellercenter-api.falabella.com/"

# ── Listas de extracción ─────────────────────────────────────────────────────
MARCAS = [
    "PANAMA JACK", "16 HRS", "BRUNO ROSSI", "ZAPPA", "POLLINI",
    "DAKOTA", "ENDURO", "IBIZAS HERITAGE", "LUZ DA LUA", "MINGO", "SHERPAS"
]

LINEAS = [
    "FLIP FLOP", "BALLERINA", "PANTUFLA", "ZAPATILLA", "SANDALIA",
    "MAFALDA", "MOCASIN", "ZAPATO", "BOTIN", "BOTA", "ALPARGATA"
]

GENEROS = ["NIÑA", "NIÑO", "HOMBRE", "MUJER", "UNISEX"]

CATEGORIAS = ["CALZADO", "ACCESORIOS", "BAGS", "ROPA"]

def extraer_marca(nombre):
    nombre_up = nombre.upper()
    for marca in MARCAS:
        if marca in nombre_up:
            return marca.title()
    return "Sin marca"

def extraer_linea(nombre, sku):
    nombre_up = nombre.upper()
    sku_up    = sku.upper()
    if "SEGURIDAD" in nombre_up or "SEGURIDAD" in sku_up:
        return "Seguridad"
    for linea in LINEAS:
        if linea in nombre_up:
            return linea.title()
    return "Sin línea"

def extraer_genero(nombre):
    nombre_up = nombre.upper()
    for genero in GENEROS:
        if genero in nombre_up:
            return genero.title()
    return "Sin género"

def extraer_categoria(categoria_api):
    if not categoria_api:
        return "Sin categoría"
    cat_up = categoria_api.upper()
    for cat in CATEGORIAS:
        if cat in cat_up:
            return cat.title()
    return categoria_api

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
            cat_raw = item.get("PrimaryCategory", "") or ""
            all_items.append({
                "order_id":   order_id,
                "created_at": pd.to_datetime(order.get("CreatedAt")),
                "status":     item.get("Status", ""),
                "sku":        sku,
                "producto":   f"{sku} — {nombre}",
                "nombre":     nombre,
                "marca":      extraer_marca(nombre),
                "linea":      extraer_linea(nombre, sku),
                "genero":     extraer_genero(nombre),
                "categoria":  extraer_categoria(cat_raw),
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

# ── Sidebar ──────────────────────────────────────────────────────────────────
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

# ── Carga de datos ───────────────────────────────────────────────────────────
with st.spinner("Consultando órdenes en Falabella..."):
    orders_raw = get_orders(created_after, created_before)

df_orders = orders_to_df(orders_raw)

if df_orders.empty:
    st.warning("No se encontraron órdenes en el período seleccionado.")
    st.stop()

df_items = get_all_items(orders_raw)

# ── Filtros sidebar ──────────────────────────────────────────────────────────
with st.sidebar:
    st.divider()
    st.header("🔍 Filtros")
    filtro_marcas  = []
    filtro_cats    = []
    filtro_lineas  = []
    filtro_generos = []

    if not df_items.empty:
        filtro_cats    = st.multiselect("🗂️ Categoría", sorted(df_items["categoria"].dropna().unique()))
        filtro_marcas  = st.multiselect("🏷️ Marca",     sorted(df_items["marca"].dropna().unique()))
        filtro_lineas  = st.multiselect("👟 Línea",     sorted(df_items["linea"].dropna().unique()))
        filtro_generos = st.multiselect("👤 Género",    sorted(df_items["genero"].dropna().unique()))
    else:
        st.info("Los filtros estarán disponibles una vez cargados los datos.")

# ── Aplicar filtros ──────────────────────────────────────────────────────────
df_items_f = df_items.copy()
if filtro_cats:
    df_items_f = df_items_f[df_items_f["categoria"].isin(filtro_cats)]
if filtro_marcas:
    df_items_f = df_items_f[df_items_f["marca"].isin(filtro_marcas)]
if filtro_lineas:
    df_items_f = df_items_f[df_items_f["linea"].isin(filtro_lineas)]
if filtro_generos:
    df_items_f = df_items_f[df_items_f["genero"].isin(filtro_generos)]

hay_filtros = any([filtro_cats, filtro_marcas, filtro_lineas, filtro_generos])
if hay_filtros and not df_items_f.empty:
    order_ids_f = df_items_f["order_id"].unique()
    df_orders_f = df_orders[df_orders["order_id"].isin(order_ids_f)]
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

# ── Evolución hora a hora ────────────────────────────────────────────────────
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

# ── Tabla hora a hora ────────────────────────────────────────────────────────
st.subheader("🕐 Tabla hora a hora")
hora_actual = datetime.now().hour
horas = [f"{h:02d}:00" for h in range(hora_actual + 1)]
hourly_table = hourly[["hour_label", "ordenes", "gmv"]].set_index("hour_label").reindex(horas, fill_value=0).reset_index()
hourly_table.columns = ["Hora", "Órdenes", "GMV"]

if not df_items_f.empty:
    hi = df_items_f.copy()
    hi["hour_label"] = hi["created_at"].dt.floor("h").dt.strftime("%H:%M")
    unidades_hora = hi.groupby("hour_label")["qty"].sum().reset_index()
    unidades_hora.columns = ["Hora", "Unidades"]
    hourly_table = hourly_table.merge(unidades_hora, on="Hora", how="left").fillna(0)
    hourly_table["Unidades"] = hourly_table["Unidades"].astype(int)
else:
    hourly_table["Unidades"] = 0

hourly_table["GMV Acum."]    = hourly_table["GMV"].cumsum()
hourly_table["Órd. Acum."]   = hourly_table["Órdenes"].cumsum()
hourly_table["Ticket Prom."] = (hourly_table["GMV"] / hourly_table["Órdenes"].replace(0, pd.NA)).fillna(0)

ht = hourly_table.copy()
ht["GMV"]          = ht["GMV"].apply(lambda x: f"${x:,.0f}")
ht["GMV Acum."]    = ht["GMV Acum."].apply(lambda x: f"${x:,.0f}")
ht["Ticket Prom."] = ht["Ticket Prom."].apply(lambda x: f"${x:,.0f}")
ht["Órdenes"]      = ht["Órdenes"].astype(int)
ht["Órd. Acum."]   = ht["Órd. Acum."].astype(int)
st.dataframe(ht[["Hora", "Órdenes", "Órd. Acum.", "Unidades", "GMV", "GMV Acum.", "Ticket Prom."]], use_container_width=True, hide_index=True)

st.divider()

# ── Performance por Categoría ────────────────────────────────────────────────
if not df_items_f.empty:
    st.subheader("🗂️ Performance por Categoría")
    cat_df = (
        df_items_f.groupby("categoria")
        .agg(ordenes=("order_id", "nunique"), unidades=("qty", "sum"), gmv=("price", "sum"))
        .reset_index().sort_values("gmv", ascending=False)
    )
    cat_df.columns = ["Categoría", "Órdenes", "Unidades", "GMV"]
    col_a, col_b = st.columns([1, 2])
    with col_a:
        cd = cat_df.copy()
        cd["GMV"] = cd["GMV"].apply(lambda x: f"${x:,.0f}")
        st.dataframe(cd, use_container_width=True, hide_index=True)
    with col_b:
        st.bar_chart(cat_df.set_index("Categoría")["GMV"].sort_values(ascending=False))

    st.divider()

    # ── Performance por Marca ────────────────────────────────────────────────
    st.subheader("🏷️ Performance por Marca")
    brand_df = (
        df_items_f.groupby("marca")
        .agg(ordenes=("order_id", "nunique"), unidades=("qty", "sum"), gmv=("price", "sum"))
        .reset_index().sort_values("gmv", ascending=False)
    )
    brand_df.columns = ["Marca", "Órdenes", "Unidades", "GMV"]
    col_c, col_d = st.columns([1, 2])
    with col_c:
        bd = brand_df.copy()
        bd["GMV"] = bd["GMV"].apply(lambda x: f"${x:,.0f}")
        st.dataframe(bd, use_container_width=True, hide_index=True)
    with col_d:
        st.bar_chart(brand_df.set_index("Marca")["GMV"].sort_values(ascending=False).head(10))

    st.divider()

    # ── Performance por Línea ────────────────────────────────────────────────
    st.subheader("👟 Performance por Línea")
    linea_df = (
        df_items_f.groupby("linea")
        .agg(ordenes=("order_id", "nunique"), unidades=("qty", "sum"), gmv=("price", "sum"))
        .reset_index().sort_values("gmv", ascending=False)
    )
    linea_df.columns = ["Línea", "Órdenes", "Unidades", "GMV"]
    col_e, col_f = st.columns([1, 2])
    with col_e:
        ld = linea_df.copy()
        ld["GMV"] = ld["GMV"].apply(lambda x: f"${x:,.0f}")
        st.dataframe(ld, use_container_width=True, hide_index=True)
    with col_f:
        st.bar_chart(linea_df.set_index("Línea")["GMV"].sort_values(ascending=False))

    st.divider()

    # ── Performance por Género ───────────────────────────────────────────────
    st.subheader("👤 Performance por Género")
    genero_df = (
        df_items_f.groupby("genero")
        .agg(ordenes=("order_id", "nunique"), unidades=("qty", "sum"), gmv=("price", "sum"))
        .reset_index().sort_values("gmv", ascending=False)
    )
    genero_df.columns = ["Género", "Órdenes", "Unidades", "GMV"]
    col_g, col_h = st.columns([1, 2])
    with col_g:
        gd = genero_df.copy()
        gd["GMV"] = gd["GMV"].apply(lambda x: f"${x:,.0f}")
        st.dataframe(gd, use_container_width=True, hide_index=True)
    with col_h:
        st.bar_chart(genero_df.set_index("Género")["GMV"].sort_values(ascending=False))

    st.divider()

    # ── Top Productos ────────────────────────────────────────────────────────
    st.subheader("🏆 Top Productos")
    prod_df = (
        df_items_f.groupby(["sku", "nombre", "marca", "linea", "genero"])
        .agg(unidades=("qty", "sum"), gmv=("price", "sum"))
        .reset_index().sort_values("gmv", ascending=False)
        .head(50)
    )
    prod_df["Producto"] = prod_df["sku"] + " — " + prod_df["nombre"]
    prod_display = prod_df[["Producto", "marca", "linea", "genero", "unidades", "gmv"]].copy()
    prod_display.columns = ["Producto", "Marca", "Línea", "Género", "Unidades", "GMV"]
    prod_display["GMV"] = prod_display["GMV"].apply(lambda x: f"${x:,.0f}")
    st.dataframe(prod_display, use_container_width=True, hide_index=True)

    st.divider()

# ── Estado de órdenes ────────────────────────────────────────────────────────
st.subheader("🔖 Estado de órdenes")
status_counts = df_orders_f["status"].value_counts().reset_index()
status_counts.columns = ["Estado", "Cantidad"]
col_i, col_j = st.columns([1, 2])
with col_i:
    st.dataframe(status_counts, use_container_width=True, hide_index=True)
with col_j:
    st.bar_chart(status_counts.set_index("Estado")["Cantidad"])

st.divider()

# ── Tabla detalle órdenes ────────────────────────────────────────────────────
st.subheader("📋 Detalle de órdenes")
df_display = df_orders_f[["order_id", "created_at", "status", "price", "items_count"]].copy()
df_display.columns = ["Order ID", "Fecha creación", "Estado", "Precio", "Ítems"]
df_display = df_display.sort_values("Fecha creación", ascending=False)
st.dataframe(df_display, use_container_width=True, hide_index=True)
csv = df_display.to_csv(index=False).encode("utf-8")
st.download_button("⬇️ Descargar CSV", csv, "ordenes_cyber.csv", "text/csv")

# ── Auto-refresh ─────────────────────────────────────────────────────────────
if auto_refresh:
    time.sleep(600)
    st.rerun()
