#!/usr/bin/env python3
"""
demo_robot.py — El robot TR COMPLETO en la consola (sin ROS, sin Raspberry)
===========================================================================
Une CEREBRO + OÍDO + VOZ en un solo proceso para probar el robot entero en
Windows. Escribes (o hablas, si instalas micrófono) y te responde con su
cerebro real: recuerda, aprende y toma la iniciativa cuando te quedas callado.
La cámara se simula con comandos (/quien, /vision).

──────────────────────────────────────────────────────────────────────────
PARA RESPUESTAS REALES CON GEMINI (si no, va en modo OFFLINE):
  1) Instala las librerías:
        py -3 -m pip install google-generativeai python-dotenv
  2) Pon tu clave de Gemini (elige UNA opción):
        setx GEMINI_API_KEY "tu_clave_nueva"      (permanente; reabre la terminal)
        $env:GEMINI_API_KEY = "tu_clave_nueva"     (solo esta sesión de PowerShell)
        ...o crea un archivo .env (copia .env.example) con GEMINI_API_KEY=...
──────────────────────────────────────────────────────────────────────────

EJECUTAR:
    py -3 demo_robot.py

COMANDOS:
    /quien <nombre>   simula reconocer a una persona (la saluda)
    /vision <texto>   simula lo que ve la cámara
    /personalidad     muestra los rasgos actuales
    /que_se           muestra lo que ha aprendido
    /salir
"""
import sys
import time
import threading
import logging

import tr_brain.config as cfg
from tr_brain import CerebroCognitivo
from tr_brain.voice import ReconocedorVoz, SintetizadorVoz
from tr_brain.vision import Vision

# Solo avisos/errores en pantalla (menos ruido durante la charla)
logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# Para el demo: que tome la iniciativa antes (30 s de silencio en vez de 45)
cfg.SEG_INACTIVIDAD_INICIATIVA = 30


class RobotConsola:
    def __init__(self):
        self.core = CerebroCognitivo()
        self.synth = SintetizadorVoz()
        self.stt = ReconocedorVoz(
            al_reconocer=self._oir,
            esta_silenciado=lambda: self.synth.hablando.is_set(),
        )
        self.vision = Vision(al_cambiar_presencia=self._presencia)
        self.persona = None
        self.ultima = time.time()
        self.activo = True

    # --- el robot habla: lo imprime Y lo pronuncia ---
    def hablar(self, texto):
        if not texto:
            return
        print(f"{cfg.NOMBRE_ROBOT}> {texto}")
        self.synth.decir(texto)
        self.ultima = time.time()

    # --- la cámara avisa cuando aparece/desaparece alguien ---
    def _presencia(self, hay_alguien):
        self.core.actualizar_vision("Tienes a una persona delante de ti." if hay_alguien else "")
        if hay_alguien:
            print("   👁️ (veo a alguien)")

    # --- llega texto (del teclado o del micrófono) ---
    def _oir(self, texto):
        t = texto.strip()
        if not t:
            return
        if t == "/salir":
            self.activo = False
            self.stt.detener()
            return
        if t == "/personalidad":
            print("   ", {k: round(v, 1) for k, v in self.core.personalidad.rasgos.items()})
            return
        if t == "/que_se":
            hechos = self.core.aprendizaje.todo_lo_que_se(30)
            if not hechos:
                print("   (todavía no he aprendido nada)")
            for h in hechos:
                print(f"   - {h['sujeto']} {h['relacion'].replace('_', ' ')} {h['objeto']} "
                      f"(confianza {h['confianza']:.2f})")
            return
        if t.startswith("/quien "):
            self.persona = t.split(" ", 1)[1].strip()
            self.hablar(self.core.saludar_persona(self.persona))
            return
        if t.startswith("/vision "):
            self.core.actualizar_vision(t.split(" ", 1)[1].strip())
            print("   (contexto visual actualizado)")
            return
        if t == "/mira":
            jpeg = self.vision.frame_jpeg(ancho=cfg.VISION_ANCHO)
            if not jpeg:
                print("   (no hay cámara disponible)")
            else:
                frase = self.core.mirar_y_comentar(jpeg)
                self.hablar(frase or "(no consigo describir lo que veo)")
            return
        # Turno normal de conversación
        self.hablar(self.core.procesar(t, persona=self.persona))

    # --- comprueba cada pocos segundos si el robot quiere hablar solo ---
    def _bucle_iniciativa(self):
        while self.activo:
            time.sleep(5)
            if not self.activo or self.synth.hablando.is_set():
                continue
            frase = self.core.tick_iniciativa(time.time() - self.ultima)
            if frase:
                self.hablar(frase)

    def run(self):
        print(f"=== {cfg.NOMBRE_ROBOT}: robot completo en consola ===")
        print("  LLM:", "Gemini ✅" if self.core.llm.disponible
              else "OFFLINE (instala google-generativeai y pon GEMINI_API_KEY)")
        oido = self.stt.modo if self.stt.modo != "teclado" else "teclado  (instala vosk+pyaudio+modelo para micrófono)"
        print("  Voz:", self.synth.backend, "| Oído:", oido)
        print("  Cámara:", "ON 👁️" if self.vision.disponible else "OFF (instala opencv-python)")
        print("  Comandos: /mira  /quien <nombre>  /vision <texto>  /personalidad  /que_se  /salir\n")

        threading.Thread(target=self._bucle_iniciativa, daemon=True).start()
        self.vision.iniciar()
        self.hablar(f"Hola, soy {cfg.NOMBRE_ROBOT}. ¿Con quién hablo?")
        self.stt.iniciar()
        try:
            while self.activo and self.stt.esta_activo():
                time.sleep(0.2)
        except KeyboardInterrupt:
            pass
        self.vision.detener()
        self.core.mantenimiento()
        self.synth.detener()
        print(f"\n{cfg.NOMBRE_ROBOT}> Estado guardado en {cfg.TR_HOME}. ¡Hasta luego!")


if __name__ == "__main__":
    RobotConsola().run()
