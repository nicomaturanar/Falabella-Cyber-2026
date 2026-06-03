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

def clp(valor):
    """Formatea un numero al estilo chileno con puntos como separador de miles."""
    return "$" + f"{int(valor):,}".replace(",", ".")

def var_pct(actual, anterior):
    """Calcula variacion porcentual y retorna string formateado."""
    try:
        if anterior == 0 or pd.isna(anterior) or pd.isna(actual):
            return None
        pct = ((actual - anterior) / anterior) * 100
        if pd.isna(pct):
            return None
        return round(pct, 1)
    except Exception:
        return None

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
    "16": "16 Hrs",
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
        # Solo parar si no vino nada en esta pagina
        if len(orders) == 0:
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

@st.cache_data(ttl=600)
def get_multiple_order_items(order_ids_tuple):
    """Obtiene items de multiples ordenes en una sola llamada."""
    order_ids_str = ",".join(str(oid) for oid in order_ids_tuple)
    data = call_api("GetMultipleOrderItems", {"OrderIdList": order_ids_str})
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
            shipping_raw = (item.get("ShippingType", "") or "").strip()
            shipping_norm = shipping_raw.lower().replace("_", " ")
            if "own" in shipping_norm or shipping_norm == "fulfillment":
                fulfillment = "Fulfillment by Falabella"
            else:
                fulfillment = "Bodega 101"
            all_items.append({
                "order_id":    order_id,
                "created_at":  pd.to_datetime(order.get("CreatedAt")),
                "status":      item.get("Status", ""),
                "sku":         sku,
                "nombre":      nombre,
                "marca":       extraer_marca(nombre, sku),
                "linea":       linea,
                "categoria":   categoria,
                "genero":      extraer_genero(nombre),
                "fulfillment": fulfillment,
                "price":       float(item.get("PaidPrice", 0) or 0),
                "qty":         int(item.get("QtyOrdered", 1) or 1),
            })
        progress.progress((i + 1) / total, text=f"Cargando orden {i+1} de {total}...")
    progress.empty()



    return pd.DataFrame(all_items) if all_items else pd.DataFrame()

def get_comparativo_anio_anterior(created_after_actual, created_before_actual):
    """Retorna el mismo rango del anio anterior con mismo dia ISO.
    Si el rango incluye hoy, corta a la hora actual. Si no, toma el rango completo."""
    import datetime as dt_module
    chile_tz = timezone(timedelta(hours=-4))
    hoy = datetime.now(chile_tz)
    hoy_date = hoy.date()

    # Calcular offset de dias entre fechas actuales y equivalentes del anio anterior
    # Usar el mismo dia ISO (semana + dia semana) para el inicio del rango
    fecha_inicio_actual = dt_module.date.fromisoformat(created_after_actual[:10])
    iso_year_ant = fecha_inicio_actual.year - 1
    iso_week     = fecha_inicio_actual.isocalendar()[1]
    iso_day      = fecha_inicio_actual.isocalendar()[2]
    fecha_inicio_ant = dt_module.date.fromisocalendar(iso_year_ant, iso_week, iso_day)

    # Calcular offset para el fin del rango
    if created_before_actual:
        fecha_fin_actual = dt_module.date.fromisoformat(created_before_actual[:10])
        offset = fecha_fin_actual - fecha_inicio_actual
        fecha_fin_ant = fecha_inicio_ant + offset
    else:
        fecha_fin_ant = fecha_inicio_ant

    # Hora de corte: solo si el rango incluye hoy
    hora_inicio = created_after_actual[11:19] if len(created_after_actual) > 10 else "00:00:00"

    # Si created_before es None significa que el rango llega hasta ahora (Hoy o Últimas 24h)
    if created_before_actual is None:
        hora_fin = hoy.strftime("%H:%M:%S")
    else:
        fecha_fin_real = dt_module.date.fromisoformat(created_before_actual[:10])
        if fecha_fin_real >= hoy_date:
            # Rango incluye hoy -> cortar a hora actual
            hora_fin = hoy.strftime("%H:%M:%S")
        else:
            # Rango ya terminó -> tomar completo
            hora_fin = "23:59:59"

    ca_ant = f"{fecha_inicio_ant}T00:00:00"
    cb_ant = f"{fecha_fin_ant}T{hora_fin}"

    return ca_ant, cb_ant, fecha_inicio_ant

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
            "operator_raw": o.get("OperatorCode", "") or "",
            "operador":    "Sodimac" if (o.get("OperatorCode", "") or "").lower() in ["sodicl", "sodimac", "sodi"] else "Falabella",
        })
    df = pd.DataFrame(rows)
    df["hour"] = df["created_at"].dt.floor("h")
    return df

# ── UI ───────────────────────────────────────────────────────────────────────
st.title("🛒 Falabella Marketplace — Cyber Dashboard")
chile_tz = timezone(timedelta(hours=-4))
ahora_chile = datetime.now(chile_tz)
st.caption(f"Última actualización: {ahora_chile.strftime('%d/%m/%Y %H:%M:%S')} | Gino S.A")

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
        chile_tz = timezone(timedelta(hours=-4))
        hoy_chile = datetime.now(chile_tz)
        created_after  = hoy_chile.strftime("%Y-%m-%dT00:00:00")
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

# ── Datos año anterior (mismo día ISO) ───────────────────────────────────────
ca_anterior, cb_anterior, fecha_equiv = get_comparativo_anio_anterior(created_after, created_before)
with st.spinner(f"Cargando comparativo año anterior ({fecha_equiv})..."):
    orders_raw_anterior = get_orders(ca_anterior, cb_anterior)
    # Filtrar manualmente por rango exacto
    if orders_raw_anterior:
        from dateutil import parser as dateparser
        ca_dt = dateparser.parse(ca_anterior)
        cb_dt = dateparser.parse(cb_anterior)
        orders_raw_anterior = [
            o for o in orders_raw_anterior
            if o.get("CreatedAt") and ca_dt <= dateparser.parse(o["CreatedAt"]).replace(tzinfo=ca_dt.tzinfo) <= cb_dt
        ]
df_orders_anterior = orders_to_df(orders_raw_anterior)
# Para año anterior solo usamos nivel orden (GetOrderItems falla con ordenes antiguas)
# Para año anterior: usar GetOrderItems pero con timeout mayor y cache
# Si falla una orden, usar datos del año actual para inferir linea/marca/categoria por SKU
if orders_raw_anterior:
    all_items_ant = []
    prog_ant = st.progress(0, text="Cargando detalle año anterior...")
    total_ant = len(orders_raw_anterior)
    
    # Crear mapa SKU -> atributos desde datos actuales
    sku_map = {}
    if not df_items.empty:
        for _, row in df_items.iterrows():
            sku15 = row["sku"][:-3] if len(row["sku"]) > 3 else row["sku"]
            if sku15 not in sku_map:
                sku_map[sku15] = {
                    "nombre":   row["nombre"],
                    "marca":    row["marca"],
                    "linea":    row["linea"],
                    "categoria":row["categoria"],
                    "genero":   row["genero"],
                }

    for i, order in enumerate(orders_raw_anterior):
        order_id = order.get("OrderId")
        items = get_order_items(order_id)
        for item in items:
            nombre = item.get("Name", "") or ""
            sku    = item.get("Sku", "") or ""
            sku15  = sku[:-3] if len(sku) > 3 else sku
            # Intentar inferir atributos desde SKU map si el nombre viene vacio
            if sku15 in sku_map and not nombre:
                attrs = sku_map[sku15]
                nombre    = attrs["nombre"]
                marca     = attrs["marca"]
                linea     = attrs["linea"]
                categoria = attrs["categoria"]
                genero    = attrs["genero"]
            else:
                linea, categoria = extraer_linea_y_categoria(nombre, sku)
                marca  = extraer_marca(nombre, sku)
                genero = extraer_genero(nombre)
            all_items_ant.append({
                "order_id":    order_id,
                "created_at":  pd.to_datetime(order.get("CreatedAt", "")),
                "sku":         sku,
                "nombre":      nombre,
                "marca":       marca,
                "linea":       linea,
                "categoria":   categoria,
                "genero":      genero,
                "fulfillment": "Año anterior",
                "price":       float(item.get("PaidPrice", 0) or 0),
                "qty":         int(item.get("QtyOrdered", 1) or 1),
            })
        prog_ant.progress((i + 1) / total_ant, text=f"Año anterior: {i+1} de {total_ant}...")
    prog_ant.empty()
    df_items_anterior = pd.DataFrame(all_items_ant) if all_items_ant else pd.DataFrame()
else:
    df_items_anterior = pd.DataFrame()

# ── Filtros ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.divider()
    st.header("🔍 Filtros")
    filtro_cats = filtro_marcas = filtro_lineas = filtro_generos = filtro_fulfillment = filtro_operador = []
    if not df_orders.empty:
        filtro_operador = st.multiselect("🏪 Operador", sorted(df_orders["operador"].dropna().unique()))
    else:
        filtro_operador = []
    if not df_items.empty:
        filtro_fulfillment = st.multiselect("🚚 Fulfillment", sorted(df_items["fulfillment"].dropna().unique()))
        filtro_cats    = st.multiselect("🗂️ Categoría", sorted(df_items["categoria"].dropna().unique()))
        filtro_marcas  = st.multiselect("🏷️ Marca",     sorted(df_items["marca"].dropna().unique()))
        filtro_lineas  = st.multiselect("👟 Línea",     sorted(df_items["linea"].dropna().unique()))
        filtro_generos = st.multiselect("👤 Género",    sorted(df_items["genero"].dropna().unique()))

# Aplicar filtro operador a ordenes
if filtro_operador:
    df_orders_op = df_orders[df_orders["operador"].isin(filtro_operador)]
else:
    df_orders_op = df_orders

df_items_f = df_items.copy()
if "modelo" not in df_items_f.columns:
    df_items_f["modelo"] = df_items_f["sku"].str[:7]
if filtro_operador:
    df_items_f = df_items_f[df_items_f["order_id"].isin(df_orders_op["order_id"])]
if filtro_fulfillment: df_items_f = df_items_f[df_items_f["fulfillment"].isin(filtro_fulfillment)]
if filtro_cats:        df_items_f = df_items_f[df_items_f["categoria"].isin(filtro_cats)]
if filtro_marcas:      df_items_f = df_items_f[df_items_f["marca"].isin(filtro_marcas)]
if filtro_lineas:      df_items_f = df_items_f[df_items_f["linea"].isin(filtro_lineas)]
if filtro_generos:     df_items_f = df_items_f[df_items_f["genero"].isin(filtro_generos)]

hay_filtros = any([filtro_operador, filtro_cats, filtro_marcas, filtro_lineas, filtro_generos, filtro_fulfillment])
if hay_filtros and not df_items_f.empty:
    df_orders_f = df_orders[df_orders["order_id"].isin(df_items_f["order_id"].unique())]
else:
    df_orders_f = df_orders

if hay_filtros:
    partes = []
    if filtro_operador:   partes.append(f"Operador: **{', '.join(filtro_operador)}**")
    if filtro_fulfillment: partes.append(f"Fulfillment: **{', '.join(filtro_fulfillment)}**")
    if filtro_cats:        partes.append(f"Categoría: **{', '.join(filtro_cats)}**")
    if filtro_marcas:      partes.append(f"Marca: **{', '.join(filtro_marcas)}**")
    if filtro_lineas:      partes.append(f"Línea: **{', '.join(filtro_lineas)}**")
    if filtro_generos:     partes.append(f"Género: **{', '.join(filtro_generos)}**")
    st.info(f"🔍 Filtros activos → {' | '.join(partes)}")

# ── KPIs ─────────────────────────────────────────────────────────────────────
st.subheader("📊 Resumen general")
col1, col2, col3, col4 = st.columns(4)
total_ordenes = len(df_orders_f)
gmv_total     = df_orders_f["price"].sum()
total_items   = df_orders_f["items_count"].sum()
ticket_prom   = gmv_total / total_ordenes if total_ordenes else 0
# Calcular métricas año anterior (solo nivel orden)
total_ordenes_ant = len(df_orders_anterior) if not df_orders_anterior.empty else 0
gmv_ant           = df_orders_anterior["price"].sum() if not df_orders_anterior.empty else 0
total_items_ant   = df_orders_anterior["items_count"].sum() if not df_orders_anterior.empty else 0

col1.metric("🛍️ Órdenes totales",  f"{total_ordenes:,}",
    delta=f"{var_pct(total_ordenes, total_ordenes_ant)}% vs {fecha_equiv.strftime('%d/%m/%Y')}" if total_ordenes_ant else None)
col2.metric("💰 Ventas (CLP)",      clp(gmv_total),
    delta=f"{var_pct(gmv_total, gmv_ant)}% vs {fecha_equiv.strftime('%d/%m/%Y')}" if gmv_ant else None)
col3.metric("📦 Unidades vendidas", f"{total_items:,}",
    delta=f"{var_pct(total_items, total_items_ant)}% vs {fecha_equiv.strftime('%d/%m/%Y')}" if total_items_ant else None)
col4.metric("🎯 Ticket promedio",   clp(ticket_prom))

# ── Desglose por Fulfillment ──────────────────────────────────────────────────
st.subheader("📊 Performance General")
if not df_items_f.empty:
    ff_resumen = (
        df_items_f.groupby("fulfillment")
        .agg(ordenes=("order_id", "nunique"), unidades=("qty", "sum"), ventas=("price", "sum"))
        .reset_index().sort_values("ventas", ascending=False)
    )
    total_ventas_res = ff_resumen["ventas"].sum()
    ff_resumen["share"] = (ff_resumen["ventas"] / total_ventas_res * 100).round(1) if total_ventas_res > 0 else 0
    total_row = pd.DataFrame([{
        "fulfillment": "Total",
        "ordenes":     ff_resumen["ordenes"].sum(),
        "unidades":    ff_resumen["unidades"].sum(),
        "ventas":      ff_resumen["ventas"].sum(),
        "share":       100.0,
    }])
    ff_tabla = pd.concat([ff_resumen, total_row], ignore_index=True)
    ff_tabla["ventas"] = ff_tabla["ventas"].apply(clp)
    ff_tabla["share"]  = ff_tabla["share"].apply(lambda x: f"{x:.1f}%")
    ff_tabla.columns = ["Fulfillment", "Órdenes", "Unidades", "Ventas (CLP)", "Share %"]
    st.dataframe(ff_tabla, use_container_width=True, hide_index=True)
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
    ht[col] = ht[col].apply(lambda x: clp(x))
ht["Órdenes"]    = ht["Órdenes"].astype(int)
ht["Órd. Acum."] = ht["Órd. Acum."].astype(int)
st.dataframe(ht[["Hora", "Órdenes", "Órd. Acum.", "Unidades", "GMV", "GMV Acum.", "Ticket Prom."]], use_container_width=True, hide_index=True)
st.divider()

# ── Tabla de performance genérica ────────────────────────────────────────────
def tabla_performance(df, col, titulo, emoji, df_ant=None):
    st.subheader(f"{emoji} Performance por {titulo}")
    agg = (
        df.groupby(col)
        .agg(ordenes=("order_id", "nunique"), unidades=("qty", "sum"), ventas=("price", "sum"))
        .reset_index().sort_values("ventas", ascending=False)
    )
    total_ventas = agg["ventas"].sum()
    agg["share"] = (agg["ventas"] / total_ventas * 100).round(1) if total_ventas > 0 else 0

    # Año anterior
    if df_ant is not None and not df_ant.empty and col in df_ant.columns:
        agg_ant = (
            df_ant.groupby(col)
            .agg(unidades_ant=("qty", "sum"), ventas_ant=("price", "sum"))
            .reset_index()
        )
        agg = agg.merge(agg_ant, on=col, how="left").fillna(0)
        agg["Var% Ventas"]    = agg.apply(lambda r: var_pct(r["ventas"], r["ventas_ant"]), axis=1)
        agg["Var% Unidades"]  = agg.apply(lambda r: var_pct(r["unidades"], r["unidades_ant"]), axis=1)
        cols_show = [col, "Órdenes", "Unidades", "Var% Unidades", "ventas", "share", "Var% Ventas"]
        agg.columns = [titulo, "Órdenes", "Unidades", "Ventas (CLP)", "Share %", "unidades_ant", "ventas_ant", "Var% Ventas", "Var% Unidades"]
        d = agg[[titulo, "Órdenes", "Unidades", "Var% Unidades", "Ventas (CLP)", "Share %", "Var% Ventas"]].copy()
        d["Ventas (CLP)"] = d["Ventas (CLP)"].apply(clp)
        d["Share %"]      = d["Share %"].apply(lambda x: f"{x:.1f}%")
        d["Var% Ventas"]  = d["Var% Ventas"].apply(lambda x: f"{x:+.1f}%" if (x is not None and not pd.isna(x)) else "N/A")
        d["Var% Unidades"]= d["Var% Unidades"].apply(lambda x: f"{x:+.1f}%" if (x is not None and not pd.isna(x)) else "N/A")
    else:
        agg.columns = [titulo, "Órdenes", "Unidades", "Ventas (CLP)", "Share %"]
        d = agg.copy()
        d["Ventas (CLP)"] = d["Ventas (CLP)"].apply(clp)
        d["Share %"]      = d["Share %"].apply(lambda x: f"{x:.1f}%")

    c1, c2 = st.columns([1, 2])
    with c1:
        st.dataframe(d, use_container_width=True, hide_index=True)
    with c2:
        chart_col = "Ventas (CLP)" if "Ventas (CLP)" in agg.columns else agg.columns[4]
        st.bar_chart(agg.set_index(titulo)["Ventas (CLP)"].sort_values(ascending=False).head(10))
    st.divider()

if not df_items_f.empty:
    tabla_performance(df_items_f, "categoria", "Categoría", "🗂️", df_items_anterior)
    tabla_performance(df_items_f, "linea",     "Línea",     "👟", df_items_anterior)
    tabla_performance(df_items_f, "marca",     "Marca",     "🏷️", df_items_anterior)
    tabla_performance(df_items_f, "genero",    "Género",    "👤", df_items_anterior)

    # ── Performance por Modelo ────────────────────────────────────────────────
    st.subheader("🔢 Performance por Modelo")
    modelo_df = (
        df_items_f.groupby("modelo")
        .agg(
            nombre=("nombre", "first"),
            marca=("marca", "first"),
            linea=("linea", "first"),
            categoria=("categoria", "first"),
            genero=("genero", "first"),
            ordenes=("order_id", "nunique"),
            unidades=("qty", "sum"),
            ventas=("price", "sum")
        )
        .reset_index().sort_values("ventas", ascending=False)
    )
    total_mod = modelo_df["ventas"].sum()
    modelo_df["share"] = (modelo_df["ventas"] / total_mod * 100).round(1) if total_mod > 0 else 0
    mod_display = modelo_df.copy()
    mod_display["ventas"] = mod_display["ventas"].apply(clp)
    mod_display["share"]  = mod_display["share"].apply(lambda x: f"{x:.1f}%")
    mod_display.columns = ["Modelo", "Nombre", "Marca", "Línea", "Categoría", "Género", "Órdenes", "Unidades", "Ventas (CLP)", "Share %"]
    st.dataframe(mod_display, use_container_width=True, hide_index=True)
    st.divider()

    # ── Top Productos ────────────────────────────────────────────────────────
    st.subheader("🏆 Top Productos")
    df_items_sku15 = df_items_f.copy()
    df_items_sku15["sku15"] = df_items_sku15["sku"].str[:-3]
    prod_df = (
        df_items_sku15.groupby(["sku15", "marca", "linea", "genero", "categoria"])
        .agg(nombre=("nombre", "first"), unidades=("qty", "sum"), gmv=("price", "sum"))
        .reset_index().sort_values("gmv", ascending=False).head(50)
    )
    pd_display = prod_df[["sku15", "nombre", "categoria", "marca", "linea", "genero", "unidades", "gmv"]].copy()
    pd_display.columns = ["SKU 15", "Nombre", "Categoría", "Marca", "Línea", "Género", "Unidades", "Ventas (CLP)"]
    pd_display["Ventas (CLP)"] = pd_display["Ventas (CLP)"].apply(clp)
    st.dataframe(pd_display, use_container_width=True, hide_index=True)
    st.divider()

# ── Performance por Fulfillment ─────────────────────────────────────────────
st.subheader("🚚 Performance por Fulfillment")
if not df_items_f.empty:
    ff_df = (
        df_items_f.groupby("fulfillment")
        .agg(ordenes=("order_id", "nunique"), unidades=("qty", "sum"), ventas=("price", "sum"))
        .reset_index().sort_values("ventas", ascending=False)
    )
    total_ventas_ff = ff_df["ventas"].sum()
    ff_df["share"] = (ff_df["ventas"] / total_ventas_ff * 100).round(1) if total_ventas_ff > 0 else 0
    ff_display = ff_df.copy()
    ff_display["ventas"] = ff_display["ventas"].apply(clp)
    ff_display["share"]  = ff_display["share"].apply(lambda x: f"{x:.1f}%")
    ff_display.columns = ["Fulfillment", "Órdenes", "Unidades", "Ventas (CLP)", "Share %"]
    st.dataframe(ff_display, use_container_width=True, hide_index=True)

    # Detalle FBF
    df_fbf = df_items_f[df_items_f["fulfillment"] == "Fulfillment by Falabella"]
    if not df_fbf.empty:
        st.markdown("#### 📦 Detalle Fulfillment by Falabella")

        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**🗂️ Categorías**")
            cat_fbf = (
                df_fbf.groupby("categoria")
                .agg(unidades=("qty", "sum"), ventas=("price", "sum"))
                .reset_index().sort_values("ventas", ascending=False)
            )
            total_cat = cat_fbf["ventas"].sum()
            cat_fbf["share"] = (cat_fbf["ventas"] / total_cat * 100).round(1) if total_cat > 0 else 0
            cat_fbf["ventas"] = cat_fbf["ventas"].apply(clp)
            cat_fbf["share"]  = cat_fbf["share"].apply(lambda x: f"{x:.1f}%")
            cat_fbf.columns = ["Categoría", "Unidades", "Ventas (CLP)", "Share %"]
            st.dataframe(cat_fbf, use_container_width=True, hide_index=True)

        with col2:
            st.markdown("**👟 Líneas**")
            linea_fbf = (
                df_fbf.groupby("linea")
                .agg(unidades=("qty", "sum"), ventas=("price", "sum"))
                .reset_index().sort_values("ventas", ascending=False)
            )
            total_linea = linea_fbf["ventas"].sum()
            linea_fbf["share"] = (linea_fbf["ventas"] / total_linea * 100).round(1) if total_linea > 0 else 0
            linea_fbf["ventas"] = linea_fbf["ventas"].apply(clp)
            linea_fbf["share"]  = linea_fbf["share"].apply(lambda x: f"{x:.1f}%")
            linea_fbf.columns = ["Línea", "Unidades", "Ventas (CLP)", "Share %"]
            st.dataframe(linea_fbf, use_container_width=True, hide_index=True)

        st.markdown("**🏆 Top Productos FBF**")
        df_fbf_sku15 = df_fbf.copy()
        df_fbf_sku15["sku15"] = df_fbf_sku15["sku"].str[:-3]
        top_fbf = (
            df_fbf_sku15.groupby(["sku15", "marca", "linea", "genero", "categoria"])
            .agg(nombre=("nombre", "first"), unidades=("qty", "sum"), ventas=("price", "sum"))
            .reset_index().sort_values("ventas", ascending=False).head(20)
        )
        top_fbf_display = top_fbf[["sku15", "nombre", "categoria", "marca", "linea", "genero", "unidades", "ventas"]].copy()
        top_fbf_display.columns = ["SKU 15", "Nombre", "Categoría", "Marca", "Línea", "Género", "Unidades", "Ventas (CLP)"]
        top_fbf_display["Ventas (CLP)"] = top_fbf_display["Ventas (CLP)"].apply(clp)
        st.dataframe(top_fbf_display, use_container_width=True, hide_index=True)

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
