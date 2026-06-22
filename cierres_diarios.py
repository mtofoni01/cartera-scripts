"""
cierres_diarios.py
------------------
Obtiene precios de bonos en ARS desde Rava Bursátil,
convierte a USD usando dólar blue/MEP desde dolarapi.com
y envía los resultados al backend en Railway.
"""

import requests
import warnings
import re
from bs4 import BeautifulSoup
from datetime import date
from dotenv import load_dotenv
import os

warnings.filterwarnings("ignore", message="Unverified HTTPS request")
load_dotenv()

API_URL    = os.getenv("API_URL", "https://backend-login-production-6dd0.up.railway.app")
DOLAR_TIPO = os.getenv("DOLAR_TIPO", "blue")

CARTERA = [
    {"ticker_db": "GD30", "ticker_rava": "GD30"},
    {"ticker_db": "AL30", "ticker_rava": "AL30"},
    {"ticker_db": "TX26", "ticker_rava": "TX26"},
]

def obtener_dolar() -> float | None:
    try:
        resp = requests.get("https://dolarapi.com/v1/dolares", timeout=10, verify=False)
        dolares = resp.json()
        dolar = next((d for d in dolares if d.get("casa") == DOLAR_TIPO), None)
        if not dolar:
            return None
        return float(dolar.get("venta"))
    except:
        return None

def obtener_precio_rava(ticker: str) -> float | None:
    url = f"https://www.rava.com/perfil/{ticker}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept":     "text/html,application/xhtml+xml",
        "Referer":    "https://www.rava.com/"
    }
    try:
        resp = requests.get(url, headers=headers, timeout=10, verify=False)
        if resp.status_code != 200:
            return None
        soup = BeautifulSoup(resp.text, "html.parser")
        meta = soup.find("meta", {"property": "og:description"})
        if meta:
            content = meta.get("content", "")
            match = re.search(r'\$([\d\.]+(?:,\d+)?)', content)
            if match:
                texto = match.group(1).replace(".", "").replace(",", ".")
                return float(texto)
        return None
    except:
        return None

def procesar_cartera(dolar_venta: float) -> list:
    resultados = []
    for item in CARTERA:
        precio_ars = obtener_precio_rava(item["ticker_rava"])
        if not precio_ars:
            continue
        precio_usd = round(precio_ars / dolar_venta, 4)
        resultados.append({
            "ticker":            item["ticker_db"],
            "fecha":             str(date.today()),
            "precio_cierre":     precio_ars,
            "precio_cierre_ars": precio_ars,
            "precio_cierre_usd": precio_usd,
            "dolar_tipo":        DOLAR_TIPO,
            "dolar_venta":       dolar_venta,
            "tir":               None,
            "duration":          None,
            "fuente":            f"rava/{DOLAR_TIPO}"
        })
    return resultados

def enviar_al_backend(precios: list) -> dict:
    if not precios:
        return {"ok": False, "error": "Sin precios para enviar"}
    try:
        resp = requests.post(
            f"{API_URL}/api/cartera/precios",
            json=precios,
            headers={"Content-Type": "application/json"},
            timeout=15,
            verify=False
        )
        return resp.json()
    except Exception as e:
        return {"ok": False, "error": str(e)}

def run() -> dict:
    dolar = obtener_dolar()
    if not dolar:
        return {"ok": False, "error": "No se pudo obtener el dólar"}
    precios = procesar_cartera(dolar)
    resultado = enviar_al_backend(precios)
    return {
        "ok":        resultado.get("ok", False),
        "insertados": resultado.get("insertados", 0),
        "dolar":     dolar,
        "precios":   [{"ticker": p["ticker"], "ars": p["precio_cierre_ars"], "usd": p["precio_cierre_usd"]} for p in precios],
        "error":     resultado.get("error")
    }

if __name__ == "__main__":
    import json
    print(json.dumps(run(), indent=2))
