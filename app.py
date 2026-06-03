import streamlit as st
import hashlib
import hmac
import urllib.parse
import requests
from datetime import datetime, timezone

st.title("🔧 Debug campos API Falabella")

USER_ID = st.secrets["FALABELLA_USER_ID"]
API_KEY = st.secrets["FALABELLA_API_KEY"]
BASE_URL = "https://sellercenter-api.falabella.com/"

def sign_request(params, api_key):
    sorted_params = sorted(params.items())
    query_string = urllib.parse.urlencode(sorted_params)
    return hmac.new(api_key.encode(), query_string.encode(), hashlib.sha256).hexdigest()

def call_api(action, extra_params={}):
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    params = {"Action": action, "Format": "JSON", "Timestamp": timestamp, "UserID": USER_ID, "Version": "1.0", **extra_params}
    params["Signature"] = sign_request(params, API_KEY)
    resp = requests.get(BASE_URL, params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()

if st.button("🔍 Traer campos del primer item"):
    with st.spinner("Consultando..."):
        # Traer una orden
        data = call_api("GetOrders", {"CreatedAfter": "2026-06-02T00:00:00", "Limit": 1})
        orders = data.get("SuccessResponse", {}).get("Body", {}).get("Orders", {}).get("Order", [])
        if isinstance(orders, dict):
            orders = [orders]

        if orders:
            order_id = orders[0].get("OrderId")
            st.success(f"Order ID: {order_id}")

            # Traer items
            data2 = call_api("GetOrderItems", {"OrderId": order_id})
            items = data2.get("SuccessResponse", {}).get("Body", {}).get("OrderItems", {}).get("OrderItem", [])
            if isinstance(items, dict):
                items = [items]

            if items:
                st.subheader(f"Campos encontrados: {len(items[0].keys())}")
                for key, val in items[0].items():
                    st.write(f"**{key}**: {val}")
            else:
                st.warning("No se encontraron items")
        else:
            st.warning("No se encontraron órdenes")
