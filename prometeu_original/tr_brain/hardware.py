"""
tr_brain.hardware — Capa de abstracción de hardware (HAL)
=========================================================
El cerebro habla con la interfaz abstracta InterfazFisica y NO sabe si detrás
hay servos reales, una Raspberry Pi o solo un simulador.

Hoy:     SimuladorHardware (registra en el log lo que haría).
Mañana:  RaspberryPiHardware (servos de cuello, ojos OLED, parpadeo...).
         En un proyecto ROS lo habitual es envolver esto en un NODO que escuche
         topics (p. ej. /tr/head_cmd) y mueva los servos; el HAL te sirve igual
         dentro de ese nodo.
"""
import logging
from abc import ABC, abstractmethod

log = logging.getLogger("tr_brain.hardware")


class InterfazFisica(ABC):
    @abstractmethod
    def mover_cabeza(self, yaw: float, pitch: float): ...
    @abstractmethod
    def mirar_a(self, x: float, y: float): ...
    @abstractmethod
    def expresion(self, emocion: str): ...
    @abstractmethod
    def parpadear(self): ...
    @abstractmethod
    def apagar(self): ...


class SimuladorHardware(InterfazFisica):
    """Implementación de pruebas: registra las acciones en el log."""
    def mover_cabeza(self, yaw, pitch):
        log.info(f"[SIM] cabeza -> yaw={yaw:.0f} pitch={pitch:.0f}")

    def mirar_a(self, x, y):
        log.debug(f"[SIM] mirar a ({x:.2f}, {y:.2f})")

    def expresion(self, emocion):
        log.info(f"[SIM] expresión -> {emocion}")

    def parpadear(self):
        log.debug("[SIM] parpadeo")

    def apagar(self):
        log.info("[SIM] hardware en reposo")


# ---------------------------------------------------------------------------
# Plantilla para hardware real (Raspberry Pi + servos). Descomentar y completar
# cuando exista la electrónica. Requiere, p. ej., 'adafruit-servokit'.
# ---------------------------------------------------------------------------
# class RaspberryPiHardware(InterfazFisica):
#     def __init__(self):
#         from adafruit_servokit import ServoKit
#         self.kit = ServoKit(channels=16)
#         self.CANAL_YAW, self.CANAL_PITCH = 0, 1
#
#     def mover_cabeza(self, yaw, pitch):
#         self.kit.servo[self.CANAL_YAW].angle = max(0, min(180, 90 + yaw))
#         self.kit.servo[self.CANAL_PITCH].angle = max(0, min(180, 90 + pitch))
#     # ... mirar_a / expresion / parpadear / apagar


def crear_hardware(tipo: str = "simulador") -> InterfazFisica:
    if tipo == "raspberry":
        # return RaspberryPiHardware()
        log.warning("RaspberryPiHardware aún no implementado; uso el simulador.")
    return SimuladorHardware()
