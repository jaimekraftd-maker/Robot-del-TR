"""
tr_brain.initiative — Motor de iniciativa (comportamiento autónomo)
==================================================================
El robot no solo reacciona: cuando lleva un rato en silencio, toma la palabra
usando recuerdos y conocimiento REALES como semilla (no frases fijas).

Lógica PURA, sin hilos: decide CUÁNDO debería intervenir y elige QUÉ semilla.
Quien llama (un timer de ROS o el bucle del demo) marca la cadencia. Esto lo
hace trivial de testear y encaja igual en ROS que en Python plano.

La frecuencia se modula con la personalidad: más curiosidad/sociabilidad =>
umbral de silencio más bajo => más iniciativa.
"""
import random
import logging
from typing import Optional
from . import config

log = logging.getLogger("tr_brain.initiative")


class MotorIniciativa:
    def __init__(self, memoria, aprendizaje, personalidad):
        self.memoria = memoria
        self.aprendizaje = aprendizaje
        self.personalidad = personalidad

    def umbral_segundos(self) -> float:
        p = self.personalidad.rasgos
        # factor entre ~0.5 y 1.0: cuanta más curiosidad+sociabilidad, menor umbral
        factor = 1.0 - (p["curiosidad"] + p["sociabilidad"]) / 400.0
        return config.SEG_INACTIVIDAD_INICIATIVA * max(0.4, factor)

    def deberia_intervenir(self, segundos_inactivo: float) -> bool:
        return segundos_inactivo >= self.umbral_segundos()

    def generar_semilla(self) -> Optional[str]:
        """Elige un dato real del que hablar: 50% un hecho aprendido, 50% un
        recuerdo de conversación reciente."""
        if random.random() < 0.5:
            h = self.aprendizaje.hecho_curioso()
            if h:
                return f"{h['sujeto']} {h['relacion'].replace('_', ' ')} {h['objeto']}"
        for r in self.memoria.resumen_reciente(12):
            if r["tipo"] == "conversacion":
                return r["contenido"]
        return None
