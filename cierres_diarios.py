"""
cierres_diarios.py
------------------
Obtiene precios de bonos en ARS desde Rava Bursátil,
volumen operado desde el Mapa del Mercado de Rava,
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

# Tickers a procesar — cartera propia + seguimiento
CARTERA = [
    {"ticker_db": "GD30", "ticker_rava": "GD30"},
    {"ticker_db": "AL30", "ticker_rava": "AL30"},
    {"ticker_db": "TX26", "ticker_rava": "TX26"},
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept":     "text/html,application/xhtml+xml",
    "Referer":    "https://www.rava.com/"
}

# ─────────────────────────────────────────────────────────────
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


def obtener_volumenes_rava() -> dict:
    """
    Scrapea el Mapa del Mercado de Rava y retorna un dict
    { ticker: volumen_operado } para todos los bonos disponibles.
    El volumen viene en ARS (pesos).
    """
    volumenes = {}
    try:
        url  = "https://www.rava.com/herramientas/mapa-del-mercado"
        resp = requests.get(url, headers=HEADERS, timeout=15, verify=False)
        if resp.status_code != 200:
            print(f"  [!] Mapa del mercado: HTTP {resp.status_code}")
            return volumenes

        # El mapa tiene formato: TICKER · +/-X.XX% VOLUMEN · PRECIO · DESCRIPCION
        # Buscamos patrones como: GD30 · +0.21% 10.738.439.305 · 91990,00
        patron = re.compile(
            r'([A-Z0-9]+)\s*·\s*[+-]?\d+[\.,]\d+%\s*([\d\.]+)\s*·',
            re.MULTILINE
        )
        texto = resp.text
        for match in patron.finditer(texto):
            ticker  = match.group(1).strip()
            volumen = match.group(2).replace(".", "").replace(",", "")
            try:
                volumenes[ticker] = float(volumen)
            except:
                pass

        print(f"  [ok] Mapa del mercado: {len(volumenes)} instrumentos con volumen")
    except Exception as e:
        print(f"  [!] Error obteniendo volúmenes: {e}")
    return volumenes


def obtener_precio_rava(ticker: str) -> float | None:
    url = f"https://www.rava.com/perfil/{ticker}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10, verify=False)
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


def procesar_cartera(dolar_venta: float, volumenes: dict) -> list:
    resultados = []
    for item in CARTERA:
        ticker_db   = item["ticker_db"]
        ticker_rava = item["ticker_rava"]

        precio_ars = obtener_precio_rava(ticker_rava)
        if not precio_ars:
            print(f"  [!] {ticker_db}: sin precio")
            continue

        precio_usd     = round(precio_ars / dolar_venta, 4)
        volumen        = volumenes.get(ticker_rava)

        print(f"  [ok] {ticker_db}: ARS={precio_ars} | USD={precio_usd} | vol={volumen}")

        resultados.append({
            "ticker":            ticker_db,
            "fecha":             str(date.today()),
            "precio_cierre":     precio_ars,
            "precio_cierre_ars": precio_ars,
            "precio_cierre_usd": precio_usd,
            "dolar_tipo":        DOLAR_TIPO,
            "dolar_venta":       dolar_venta,
            "volumen_operado":   volumen,
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
    print(f"  [ok] Dólar {DOLAR_TIPO}: ${dolar}")

    print("\nObteniendo volúmenes del Mapa del Mercado...")
    volumenes = obtener_volumenes_rava()

    print("\nObteniendo precios desde Rava...")
    precios = procesar_cartera(dolar, volumenes)

    print("\nEnviando al backend...")
    resultado = enviar_al_backend(precios)

    return {
        "ok":        resultado.get("ok", False),
        "insertados": resultado.get("insertados", 0),
        "dolar":     dolar,
        "precios":   [{"ticker": p["ticker"], "ars": p["precio_cierre_ars"],
                       "usd": p["precio_cierre_usd"], "volumen": p["volumen_operado"]} for p in precios],
        "error":     resultado.get("error")
    }


if __name__ == "__main__":
    import json
    print(f"=== Cierre diario {date.today()} ===\n")
    print("Obteniendo dólar...")
    resultado = run()
    print(f"\n=== Resultado ===")
    print(json.dumps(resultado, indent=2))
