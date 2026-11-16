#!/usr/bin/env python3
"""
demo_voz.py — Prueba el OÍDO y la VOZ sin ROS
=============================================
Comprueba el micrófono (Vosk), el altavoz (TTS) y que el robot NO se oye a sí
mismo. Si no hay micrófono/Vosk, cae a teclado; si no hay TTS, imprime.

    py -3 demo_voz.py        (Windows)
    python3 demo_voz.py      (Linux / Raspberry)

Di (o escribe) algo y el robot lo repetirá. Di "adiós" para salir.
"""
import sys
import time
import logging

from tr_brain.voice import ReconocedorVoz, SintetizadorVoz

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def main():
    synth = SintetizadorVoz()

    def al_reconocer(texto):
        print(f"Oído> {texto}")
        if texto.lower().strip(" .!?") in ("adiós", "adios", "salir", "para"):
            synth.decir("Hasta luego.")
            synth.esperar()
            stt.detener()
            return
        synth.decir(f"Has dicho: {texto}")

    stt = ReconocedorVoz(al_reconocer=al_reconocer,
                         esta_silenciado=lambda: synth.hablando.is_set())

    print(f"=== Demo de voz · STT: {stt.modo} · TTS: {synth.backend} ===")
    synth.decir("Hola, soy TR. Di algo y te lo repetiré. Di 'adiós' para salir.")
    stt.iniciar()
    try:
        while stt.esta_activo():
            time.sleep(0.2)
    except KeyboardInterrupt:
        pass
    finally:
        stt.detener()
        synth.detener()
    print("Fin de la demo de voz.")


if __name__ == "__main__":
    main()
