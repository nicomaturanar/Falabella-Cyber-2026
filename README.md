# 🛒 Gino S.A — Cyber Dashboard

Dashboard en tiempo real para seguimiento de ventas en Falabella Marketplace durante el Cyber.

## ¿Qué muestra?
- Total de órdenes, GMV, unidades vendidas y ticket promedio
- Gráfico de órdenes y GMV hora a hora
- Distribución por estado de órdenes
- Tabla detalle con exportación a CSV
- Auto-refresh cada 10 minutos (opcional)

## Despliegue en Streamlit Cloud

1. Sube este repo a GitHub
2. Ve a [share.streamlit.io](https://share.streamlit.io) y conecta tu cuenta GitHub
3. Selecciona este repositorio y el archivo `app.py`
4. En **Advanced settings → Secrets**, pega esto:

```toml
FALABELLA_USER_ID = "nmaturana@gino.cl"
FALABELLA_API_KEY = "afda57ec6fddd03904839aacdb9e02d48e0c6a37"
```

5. Haz click en **Deploy** — en ~2 minutos tendrás tu link público.

## Ejecución local

```bash
pip install -r requirements.txt
streamlit run app.py
```
