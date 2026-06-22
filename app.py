"""
app.py
------
Mini servidor Flask que expone el script de cierres
como un endpoint HTTP para Railway.

Endpoints:
  GET  /health       — verificar que el servicio está vivo
  POST /run          — ejecutar el script de cierres (requiere API_KEY)
"""

from flask import Flask, jsonify, request
from cierres_diarios import run
from dotenv import load_dotenv
import os

load_dotenv()

app = Flask(__name__)

API_KEY = os.getenv("SCRIPT_API_KEY", "")

def verificar_api_key():
    key = request.headers.get("x-api-key") or request.args.get("api_key")
    if not API_KEY:
        return True  # si no está configurada, no bloquea
    return key == API_KEY

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})

@app.route("/run", methods=["POST"])
def ejecutar_script():
    if not verificar_api_key():
        return jsonify({"ok": False, "error": "No autorizado"}), 401
    try:
        resultado = run()
        return jsonify(resultado)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
