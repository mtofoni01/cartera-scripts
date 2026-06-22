"""
cierres_diarios.py
------------------
Obtiene precios y volumen efectivo de bonos desde Rava Bursátil,
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


def obtener_datos_rava(ticker: str) -> dict:
    """
    Scrapea precio y volumen efectivo desde la página de perfil de Rava.
    Retorna dict con precio y volumen.
    """
    url = f"https://www.rava.com/perfil/{ticker}"
    resultado = {"precio": None, "volumen": None}
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10, verify=False)
        if resp.status_code != 200:
            return resultado

        soup = BeautifulSoup(resp.text, "html.parser")

        # Precio desde og:description: "$97.670,00 (+0,57%)"
        meta = soup.find("meta", {"property": "og:description"})
        if meta:
            content_meta = meta.get("content", "")
            match = re.search(r'\$([\d\.]+(?:,\d+)?)', content_meta)
            if match:
                texto = match.group(1).replace(".", "").replace(",", ".")
                resultado["precio"] = float(texto)

        # Volumen efectivo desde el HTML: "Vol. Efectivo: 5.149.463.597"
        texto_html = soup.get_text(separator=" ")
        match_vol = re.search(r'Vol\.?\s*Efectivo[:\s]+([\d\.]+)', texto_html)
        if match_vol:
            vol_texto = match_vol.group(1).replace(".", "")
            try:
                resultado["volumen"] = float(vol_texto)
            except:
                pass

        return resultado
    except Exception as e:
        print(f"  [!] {ticker}: {e}")
        return resultado


def procesar_cartera(dolar_venta: float) -> list:
    resultados = []
    for item in CARTERA:
        ticker_db   = item["ticker_db"]
        ticker_rava = item["ticker_rava"]

        datos      = obtener_datos_rava(ticker_rava)
        precio_ars = datos["precio"]
        volumen    = datos["volumen"]

        if not precio_ars:
            print(f"  [!] {ticker_db}: sin precio")
            continue

        precio_usd = round(precio_ars / dolar_venta, 4)
        print(f"  [ok] {ticker_db}: ARS={precio_ars} | USD={precio_usd} | vol_efectivo={volumen}")

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
        script_key = os.getenv("SCRIPT_API_KEY", "")
        #print(f"  [debug] API key: '{script_key}'")
        resp = requests.post(
            f"{API_URL}/api/cartera/precios",
            json=precios,
            headers={"Content-Type": "application/json", "x-api-key": script_key},
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

    print("\nObteniendo precios y volúmenes desde Rava...")
    precios = procesar_cartera(dolar)

    print("\nEnviando al backend...")
    resultado = enviar_al_backend(precios)

    return {
        "ok":         resultado.get("ok", False),
        "insertados": resultado.get("insertados", 0),
        "dolar":      dolar,
        "precios":    [{"ticker": p["ticker"], "ars": p["precio_cierre_ars"],
                        "usd": p["precio_cierre_usd"], "volumen": p["volumen_operado"]} for p in precios],
        "error":      resultado.get("error")
    }


if __name__ == "__main__":
    import json
    print(f"=== Cierre diario {date.today()} ===\n")
    print("Obteniendo dólar...")
    resultado = run()
    print(f"\n=== Resultado ===")
    print(json.dumps(resultado, indent=2))
