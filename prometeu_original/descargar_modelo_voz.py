#!/usr/bin/env python3
"""
descargar_modelo_voz.py — Descarga el modelo de voz (Vosk, español) del MICRÓFONO
=================================================================================
Tras esto, el reconocedor usará el MICRÓFONO en vez del teclado.

    py -3 -m pip install vosk pyaudio
    py -3 descargar_modelo_voz.py

Descarga ~50 MB a  ~/.tr_robot/vosk-model-small-es
"""
import os
import sys
import zipfile
import tempfile
import urllib.request
from pathlib import Path

URL = "https://alphacephei.com/vosk/models/vosk-model-small-es-0.42.zip"
HOME = Path(os.environ.get("TR_HOME", Path.home() / ".tr_robot"))
DEST = HOME / "vosk-model-small-es"


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    HOME.mkdir(parents=True, exist_ok=True)
    if DEST.exists():
        print(f"✅ El modelo ya está instalado en: {DEST}")
        return

    zip_path = Path(tempfile.gettempdir()) / "vosk-es.zip"
    print(f"⬇️  Descargando modelo de voz (~50 MB)...\n   {URL}")

    def progreso(bloques, tam_bloque, total):
        if total > 0:
            pct = min(100, bloques * tam_bloque * 100 // total)
            print(f"\r   {pct}%", end="", flush=True)

    try:
        urllib.request.urlretrieve(URL, zip_path, progreso)
        print("\n📦 Descomprimiendo...")
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(HOME)
        extraida = HOME / "vosk-model-small-es-0.42"
        if extraida.exists():
            extraida.rename(DEST)
        zip_path.unlink(missing_ok=True)
        print(f"✅ Listo: {DEST}")
        print("   Ahora 'py -3 demo_robot.py' usará el micrófono automáticamente.")
    except Exception as e:
        print(f"\n❌ Error al descargar/instalar: {e}")
        print(f"   Puedes hacerlo a mano: descarga {URL}, descomprime y renombra")
        print(f"   la carpeta a: {DEST}")


if __name__ == "__main__":
    main()
