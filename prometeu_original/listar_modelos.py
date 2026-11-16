#!/usr/bin/env python3
"""
listar_modelos.py — Muestra los modelos Gemini disponibles para TU clave
========================================================================
Útil cuando un modelo da error 404 (los nombres cambian con el tiempo).

    setx GEMINI_API_KEY "tu_clave"   (o $env:GEMINI_API_KEY = "...")
    py -3 listar_modelos.py

Copia uno de los nombres "flash" que salgan y fíjalo:
    setx TR_MODELO_CHAT "gemini-2.0-flash"
"""
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

key = os.environ.get("GEMINI_API_KEY", "")
if not key:
    print("❌ Falta GEMINI_API_KEY en el entorno. Ponla con setx o $env: y reabre la terminal.")
    sys.exit(1)

try:
    import google.generativeai as genai
except Exception:
    print("❌ Falta la librería. Instálala con:  py -3 -m pip install google-generativeai")
    sys.exit(1)

genai.configure(api_key=key)

print("Modelos que soportan generateContent (úsalos en TR_MODELO_CHAT):\n")
encontrados = 0
for m in genai.list_models():
    if "generateContent" in getattr(m, "supported_generation_methods", []):
        nombre = m.name.replace("models/", "")
        marca = "  ⭐" if "flash" in nombre.lower() else ""
        print(f"   {nombre}{marca}")
        encontrados += 1

if not encontrados:
    print("   (ninguno: revisa que la clave sea válida y esté activa)")
else:
    print(f"\n✅ {encontrados} modelos disponibles. Los ⭐ 'flash' son rápidos y suelen ser gratis.")
