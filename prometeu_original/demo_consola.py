#!/usr/bin/env python3
"""
demo_consola.py — Prueba el CEREBRO sin ROS, sin cámara y sin micrófono
=======================================================================
Ejecuta el núcleo cognitivo por teclado para que VEAS cómo recuerda, aprende y
evoluciona su personalidad. Ideal para desarrollar en el portátil antes de
subirlo al robot.

    python demo_consola.py
    python demo_consola.py --migrar      # importa tu memory.json antiguo a la BD

Funciona aunque NO tengas GEMINI_API_KEY (modo OFFLINE: respuestas pobres, pero
la memoria, el aprendizaje heurístico y la iniciativa siguen operando).

Comandos especiales dentro del demo:
    /personalidad     -> muestra los rasgos actuales
    /quien <nombre>   -> simula el reconocimiento facial de una persona
    /vision <texto>   -> simula lo que vería la cámara
    /que_se           -> lista lo que el robot ha aprendido
    (línea vacía)     -> espera; si llevas mucho en silencio, el robot habla solo
    /salir
"""
import sys
import time
import logging

from tr_brain import CerebroCognitivo
from tr_brain import config

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

# En Windows la consola suele usar cp1252; forzamos UTF-8 para que los acentos
# (á, é, ñ, ¿, ¡...) se vean bien.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def main():
    core = CerebroCognitivo()

    if "--migrar" in sys.argv:
        nf, nr = core.importar_legacy()
        print(f"📦 Migrados {nf} hechos y {nr} recuerdos del memory.json antiguo.\n")

    modo = "Gemini" if core.llm.disponible else "OFFLINE (configura GEMINI_API_KEY)"
    print(f"=== {config.NOMBRE_ROBOT} · demo de consola · modo LLM: {modo} ===")
    print("Escribe y pulsa Enter. Comandos: /personalidad /quien /vision /que_se /salir\n")

    persona = None
    ultima = time.time()
    print(f"{config.NOMBRE_ROBOT}> Hola, soy {config.NOMBRE_ROBOT}. ¿Con quién hablo?")

    while True:
        try:
            entrada = input("tú> ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        # Línea vacía: comprobamos si el robot quiere tomar la iniciativa
        if not entrada:
            frase = core.tick_iniciativa(time.time() - ultima)
            if frase:
                print(f"{config.NOMBRE_ROBOT}> {frase}")
                ultima = time.time()
            continue

        if entrada == "/salir":
            break
        if entrada == "/personalidad":
            print("   rasgos:", {k: round(v, 1) for k, v in core.personalidad.rasgos.items()})
            continue
        if entrada == "/que_se":
            hechos = core.aprendizaje.todo_lo_que_se(30)
            if not hechos:
                print("   (aún no he aprendido nada)")
            for h in hechos:
                print(f"   - {h['sujeto']} {h['relacion'].replace('_', ' ')} {h['objeto']} "
                      f"(confianza {h['confianza']:.2f}, x{h['refuerzos']})")
            continue
        if entrada.startswith("/quien "):
            persona = entrada.split(" ", 1)[1].strip()
            print(f"{config.NOMBRE_ROBOT}> {core.saludar_persona(persona)}")
            ultima = time.time()
            continue
        if entrada.startswith("/vision "):
            core.actualizar_vision(entrada.split(" ", 1)[1].strip())
            print("   (contexto visual actualizado)")
            continue

        respuesta = core.procesar(entrada, persona=persona)
        print(f"{config.NOMBRE_ROBOT}> {respuesta}")
        ultima = time.time()

    core.mantenimiento()
    print(f"\n{config.NOMBRE_ROBOT}> Guardado todo en {config.TR_HOME}. ¡Hasta luego!")
    print("Personalidad final:", {k: round(v, 1) for k, v in core.personalidad.rasgos.items()})


if __name__ == "__main__":
    main()
