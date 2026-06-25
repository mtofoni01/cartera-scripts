"""
cierres_diarios.py
------------------
Obtiene precios y volumen efectivo de bonos desde Rava Bursátil,
convierte a USD usando dólar blue/MEP desde dolarapi.com
y envía los resultados al backend en Railway.

Los tickers se leen dinámicamente desde la base de datos.
"""

import requests
import warnings
import re
import mysql.connector
from bs4 import BeautifulSoup
from datetime import date
from dotenv import load_dotenv
import os

warnings.filterwarnings("ignore", message="Unverified HTTPS request")
load_dotenv()

API_URL    = os.getenv("API_URL", "https://backend-login-production-6dd0.up.railway.app")
DOLAR_TIPO = os.getenv("DOLAR_TIPO", "blue")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept":     "text/html,application/xhtml+xml",
    "Referer":    "https://www.rava.com/"
}

# ─────────────────────────────────────────────────────────────
def obtener_tickers_db() -> list:
    """
    Lee desde la BD todos los tickers activos con precio en Rava.
    FCI, Plazo Fijo, Cauciones y Saldo Vista se cargan manualmente.
    """
    try:
        conn = mysql.connector.connect(
            host     = os.getenv("DB_HOST"),
            port     = int(os.getenv("DB_PORT", 3306)),
            user     = os.getenv("DB_USER"),
            password = os.getenv("DB_PASSWORD"),
            database = os.getenv("DB_NAME"),
        )
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT ticker FROM especies
            WHERE activo = TRUE
            AND tipo IN ('bono_usd', 'bono_ars', 'bono_cer', 'bono_dv', 'letra_ars', 'letra_usd', 'on', 'accion', 'cedear')
            ORDER BY ticker
        """)
        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        tickers = [{"ticker_db": r["ticker"], "ticker_rava": r["ticker"]} for r in rows]
        print(f"  [ok] BD: {len(tickers)} tickers encontrados → {[t['ticker_db'] for t in tickers]}")
        return tickers

    except Exception as e:
        print(f"  [!] Error leyendo BD: {e}")
        print("  [!] Usando lista de respaldo hardcodeada")
        return [
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


def obtener_datos_rava(ticker: str) -> dict:
    """
    Scrapea precio y volumen efectivo desde la página de perfil de Rava.
    """
    url = f"https://www.rava.com/perfil/{ticker}"
    resultado = {"precio": None, "volumen": None}
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10, verify=False)
        if resp.status_code != 200:
            print(f"  [!] {ticker}: HTTP {resp.status_code}")
            return resultado

        soup = BeautifulSoup(resp.text, "html.parser")

        # Precio desde og:description
        meta = soup.find("meta", {"property": "og:description"})
        if meta:
            content_meta = meta.get("content", "")
            match = re.search(r'\$([\d\.]+(?:,\d+)?)', content_meta)
            if match:
                texto = match.group(1).replace(".", "").replace(",", ".")
                resultado["precio"] = float(texto)

        # Volumen efectivo
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


def procesar_cartera(cartera: list, dolar_venta: float) -> list:
    resultados = []
    for item in cartera:
        ticker_db   = item["ticker_db"]
        ticker_rava = item["ticker_rava"]

        datos      = obtener_datos_rava(ticker_rava)
        precio_ars = datos["precio"]
        volumen    = datos["volumen"]

        if not precio_ars:
            print(f"  [!] {ticker_db}: sin precio en Rava")
            continue

        precio_usd = round(precio_ars / dolar_venta, 4)
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
        script_key = os.getenv("SCRIPT_API_KEY", "")
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
    print("Leyendo tickers desde la BD...")
    cartera = obtener_tickers_db()

    dolar = obtener_dolar()
    if not dolar:
        return {"ok": False, "error": "No se pudo obtener el dólar"}
    print(f"  [ok] Dólar {DOLAR_TIPO}: ${dolar}")

    print("\nObteniendo precios y volúmenes desde Rava...")
    precios = procesar_cartera(cartera, dolar)

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
    resultado = run()
    print(f"\n=== Resultado ===")
    print(json.dumps(resultado, indent=2))
