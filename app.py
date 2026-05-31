import streamlit as st
import hashlib
import hmac
import urllib.parse
import requests
import json
from datetime import datetime, timedelta, timezone
import pandas as pd
import time

# ─── Configuración de página ───────────────────────────────────────────────
st.set_page_config(
    page_title="Gino S.A — Cyber Dashboard",
    page_icon="🛒",
    layout="wide",
)

# ─── Credenciales desde Streamlit Secrets ──────────────────────────────────
USER_ID  = st.secrets["FALABELLA_USER_ID"]
API_KEY  = st.secrets["FALABELLA_API_KEY"]
BASE_URL = "https://sellercenter-api.falabella.com/"

# ─── Firma SHA256 (requerida por Falabella) ─────────────────────────────────
def sign_request(params: dict, api_key: str) -> str:
    sorted_params = sorted(params.items())
    query_string  = urllib.parse.urlencode(sorted_params)
    signature     = hmac.new(api_key.encode(), query_string.encode(), hashlib.sha256).hexdigest()
    return signature

# ─── Llamada genérica a la API ──────────────────────────────────────────────
def call_api(action: str, extra_params: dict = {}) -> dict | None:
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    params = {
        "Action":    action,
        "Format":    "JSON",
        "Timestamp": timestamp,
        "UserID":    USER_ID,
        "Version":   "1.0",
        **extra_params,
    }
    params["Signature"] = sign_request(params, API_KEY)
    try:
        resp = requests.get(BASE_URL, params=params, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        st.error(f"Error llamando a {action}: {e}")
        return None

# ─── Obtener órdenes en un rango de fechas ──────────────────────────────────
def get_orders(created_after: str, created_before: str = None) -> list[dict]:
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

# ─── Procesar órdenes a DataFrame ───────────────────────────────────────────
def orders_to_df(orders: list[dict]) -> pd.DataFrame:
    if not orders:
        return pd.DataFrame()
    rows = []
    for o in orders:
        rows.append({
            "order_id":     o.get("OrderId"),
            "status":       o.get("Statuses", {}).get("Status", ""),
            "created_at":   pd.to_datetime(o.get("CreatedAt")),
            "price":        float(o.get("Price", 0) or 0),
            "items_count":  int(o.get("ItemsCount", 0) or 0),
        })
    df = pd.DataFrame(rows)
    df["hour"] = df["created_at"].dt.floor("h")
    return df

# ─── UI principal ────────────────────────────────────────────────────────────
st.title("🛒 Gino S.A — Cyber Dashboard")
st.caption(f"Última actualización: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")

# ─── Sidebar: controles ─────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Configuración")
    modo = st.radio("Período", ["Hoy", "Últimas 24h", "Rango personalizado"])

    if modo == "Rango personalizado":
        fecha_inicio = st.date_input("Desde", value=datetime.now().date())
        fecha_fin    = st.date_input("Hasta", value=datetime.now().date())
        created_after  = datetime.combine(fecha_inicio, datetime.min.time()).strftime("%Y-%m-%dT00:00:00+00:00")
        created_before = datetime.combine(fecha_fin,    datetime.max.time()).strftime("%Y-%m-%dT23:59:59+00:00")
    elif modo == "Últimas 24h":
        created_after  = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%S+00:00")
        created_before = None
    else:  # Hoy
        created_after  = datetime.now().strftime("%Y-%m-%dT00:00:00+00:00")
        created_before = None

    auto_refresh = st.checkbox("🔄 Auto-refresh cada 10 min", value=False)
    if st.button("🔃 Actualizar ahora", use_container_width=True):
        st.cache_data.clear()

# ─── Carga de datos ──────────────────────────────────────────────────────────
with st.spinner("Consultando API de Falabella..."):
    orders_raw = get_orders(created_after, created_before)

df = orders_to_df(orders_raw)

# ─── KPIs principales ────────────────────────────────────────────────────────
st.subheader("📊 Resumen")

if df.empty:
    st.warning("No se encontraron órdenes en el período seleccionado.")
else:
    col1, col2, col3, col4 = st.columns(4)

    total_ordenes  = len(df)
    gmv_total      = df["price"].sum()
    total_items    = df["items_count"].sum()
    ticket_prom    = gmv_total / total_ordenes if total_ordenes else 0

    col1.metric("🛍️ Órdenes totales",  f"{total_ordenes:,}")
    col2.metric("💰 GMV total",         f"${gmv_total:,.0f}")
    col3.metric("📦 Unidades vendidas", f"{total_items:,}")
    col4.metric("🎯 Ticket promedio",   f"${ticket_prom:,.0f}")

    st.divider()

    # ─── Gráfico hora a hora ───────────────────────────────────────────────
    st.subheader("📈 Órdenes hora a hora")
    hourly = (
        df.groupby("hour")
        .agg(ordenes=("order_id", "count"), gmv=("price", "sum"))
        .reset_index()
    )
    hourly["hour_label"] = hourly["hour"].dt.strftime("%H:%M")

    tab1, tab2 = st.tabs(["Órdenes", "GMV"])
    with tab1:
        st.bar_chart(hourly.set_index("hour_label")["ordenes"])
    with tab2:
        st.bar_chart(hourly.set_index("hour_label")["gmv"])

    st.divider()

    # ─── Distribución por estado ───────────────────────────────────────────
    st.subheader("🔖 Estado de órdenes")
    status_counts = df["status"].value_counts().reset_index()
    status_counts.columns = ["Estado", "Cantidad"]
    col_a, col_b = st.columns([1, 2])
    with col_a:
        st.dataframe(status_counts, use_container_width=True, hide_index=True)
    with col_b:
        st.bar_chart(status_counts.set_index("Estado")["Cantidad"])

    st.divider()

    # ─── Tabla detalle ─────────────────────────────────────────────────────
    st.subheader("📋 Detalle de órdenes")
    df_display = df[["order_id", "created_at", "status", "price", "items_count"]].copy()
    df_display.columns = ["Order ID", "Fecha creación", "Estado", "Precio", "Ítems"]
    df_display = df_display.sort_values("Fecha creación", ascending=False)
    st.dataframe(df_display, use_container_width=True, hide_index=True)

    # ─── Exportar CSV ──────────────────────────────────────────────────────
    csv = df_display.to_csv(index=False).encode("utf-8")
    st.download_button("⬇️ Descargar CSV", csv, "ordenes_cyber.csv", "text/csv")

# ─── Auto-refresh ────────────────────────────────────────────────────────────
if auto_refresh:
    time.sleep(600)
    st.rerun()
