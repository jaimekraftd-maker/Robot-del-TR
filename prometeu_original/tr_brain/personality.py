"""
tr_brain.personality — Personalidad evolutiva
=============================================
La personalidad NO es fija: evoluciona con la experiencia y condiciona CÓMO
responde el robot, porque descripcion_para_prompt() se inyecta en la
instrucción de sistema del LLM en cada turno.

Rasgos (0-100): curiosidad, sociabilidad, humor, confianza, energia.
Se persiste en ~/.tr_robot/personality.json.
"""
import json
import logging
from . import config

log = logging.getLogger("tr_brain.personality")


def etapa_madurez(n_aprendido: int):
    """Devuelve (nombre, estilo_de_habla) de la etapa de madurez actual, según
    cuántos hechos ha aprendido el robot. Empieza siendo un bebé y madura."""
    nombre, estilo = config.ETAPAS_MADUREZ[0][1], config.ETAPAS_MADUREZ[0][2]
    for umbral, nom, est in config.ETAPAS_MADUREZ:
        if n_aprendido >= umbral:
            nombre, estilo = nom, est
    return nombre, estilo


class Personalidad:
    def __init__(self, ruta=None):
        self.ruta = ruta or config.RUTA_PERSONALIDAD
        self.base = dict(config.PERSONALIDAD_INICIAL)      # línea base (para el decaimiento)
        self.rasgos = dict(config.PERSONALIDAD_INICIAL)
        self._cargar()

    def _cargar(self):
        try:
            if self.ruta.exists():
                self.rasgos.update(json.loads(self.ruta.read_text(encoding="utf-8")))
                log.info(f"Personalidad cargada: {self.rasgos}")
        except Exception as e:
            log.warning(f"No se pudo cargar personalidad: {e}")

    def guardar(self):
        try:
            self.ruta.write_text(json.dumps(self.rasgos, indent=2, ensure_ascii=False),
                                 encoding="utf-8")
        except Exception as e:
            log.warning(f"No se pudo guardar personalidad: {e}")

    def ajustar(self, rasgo, delta):
        if rasgo in self.rasgos:
            self.rasgos[rasgo] = max(0, min(100, self.rasgos[rasgo] + delta))

    def evolucionar(self, evento):
        """Mapea eventos de alto nivel a cambios de rasgos."""
        reglas = {
            "conversacion":   {"sociabilidad": +1.0, "energia": +0.5},
            "aprendio_algo":  {"curiosidad": +1.5, "confianza": +0.3},
            "broma":          {"humor": +1.0},
            "elogio":         {"confianza": +2.0, "sociabilidad": +1.0},
            "silencio_largo": {"energia": -1.0, "sociabilidad": -0.5},
            "persona_nueva":  {"curiosidad": +1.0, "sociabilidad": +0.5},
            "reencuentro":    {"sociabilidad": +1.5, "confianza": +0.5},
        }
        for rasgo, delta in reglas.get(evento, {}).items():
            self.ajustar(rasgo, delta)

    def decaer(self):
        """Regresión lenta hacia la línea base (evita rasgos extremos permanentes)."""
        for r in self.rasgos:
            self.rasgos[r] = self.base[r] + (self.rasgos[r] - self.base[r]) * config.DECAIMIENTO_PERSONALIDAD

    def descripcion_para_prompt(self):
        """Convierte los números en una guía de estilo para el LLM."""
        r = self.rasgos
        return " ".join([
            "Eres muy curiosa: haces preguntas propias y exploras temas nuevos." if r["curiosidad"] > 60
            else "Tu curiosidad es moderada.",
            "Eres cálida y muy conversadora." if r["sociabilidad"] > 60 else "Eres algo reservada.",
            "Usas humor y comentarios ingeniosos." if r["humor"] > 55 else "Tu tono es más bien serio.",
            "Hablas con seguridad y das tu opinión." if r["confianza"] > 55 else "Eres prudente y matizas.",
            "Respondes con entusiasmo y energía." if r["energia"] > 60 else "Tu tono es tranquilo.",
        ])
