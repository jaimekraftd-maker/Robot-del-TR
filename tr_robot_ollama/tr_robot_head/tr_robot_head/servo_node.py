#!/usr/bin/env python3
"""
servo_node.py — Cuello y mandíbula de la cabeza
==================================================
Controla 3 servos por un PCA9685 (dirección 0x40): por Wi-Fi a través de la
Pico 2 W si hay pico_host o TR_PICO_HOST (pico_link.py), y si no, directamente
por I2C con adafruit-servokit (Pi Zero 2 W):
  canal 0 → pan (girar la cabeza a izquierda/derecha)
  canal 1 → tilt (asentir arriba/abajo)
  canal 2 → mandíbula

- Mientras /tr/speaking sea True, abre y cierra la mandíbula de forma
  irregular (parece más natural que un vaivén perfecto).
- /tr/head_pose (std_msgs/Float32MultiArray [pan, tilt] en grados) mueve el
  cuello suavemente hasta esa posición (90 = centro).

IMPORTANTE: los servos se alimentan con una fuente de 5 V / 3 A SEPARADA,
con las masas unidas. Nunca desde los pines de la Pi ni de la Pico.

Si no hay PCA9685 (o no está la librería) funciona en modo simulación, solo
con logs, para poder probar el resto del robot sin la electrónica montada.
"""
import random

import rclpy
from rclpy.node import Node
from std_msgs.msg import Bool, Float32MultiArray

from tr_robot_head.pico_link import PicoLink, direccion_pico

try:
    from adafruit_servokit import ServoKit
except Exception:  # ImportError o fallo de Blinka al detectar la placa
    ServoKit = None

CANAL_PAN, CANAL_TILT, CANAL_MANDIBULA = 0, 1, 2
PERIODO_SEC = 0.1          # 10 Hz: suficiente para una mandíbula creíble
PASO_CUELLO_GRADOS = 4.0   # velocidad máxima del cuello por ciclo (suavizado)
CICLOS_REENVIO = 10        # Pico: repite la posición cada segundo (UDP puede perderse)


class ServoNode(Node):
    def __init__(self):
        super().__init__("servo_node")
        self.declare_parameter("pan_min", 30.0)
        self.declare_parameter("pan_max", 150.0)
        self.declare_parameter("tilt_min", 60.0)
        self.declare_parameter("tilt_max", 120.0)
        self.declare_parameter("jaw_closed", 90.0)
        self.declare_parameter("jaw_open", 60.0)
        self.declare_parameter("pico_host", "")
        self.get_logger().info("🦴 Iniciando servo_node...")

        p = lambda nombre: float(self.get_parameter(nombre).value)  # noqa: E731
        self.pan_lim = (p("pan_min"), p("pan_max"))
        self.tilt_lim = (p("tilt_min"), p("tilt_max"))
        self.jaw_closed, self.jaw_open = p("jaw_closed"), p("jaw_open")

        self.kit = None
        self.pico = None
        self.ultimos = {}
        self.ciclos = 0
        host = direccion_pico(str(self.get_parameter("pico_host").value))
        if host:
            self.pico = PicoLink(host, self.get_logger())
            self.get_logger().info(f"🦴 Servos por Wi-Fi: Pico en {host}.")
        elif ServoKit is None:
            self.get_logger().warn("🦴 adafruit-servokit no disponible: modo SIMULACIÓN.")
        else:
            try:
                self.kit = ServoKit(channels=16)
                self.get_logger().info("🦴 PCA9685 detectado por I2C.")
            except Exception as e:
                self.get_logger().error(f"🦴 No encuentro el PCA9685 ({e}): modo SIMULACIÓN.")

        self.pan = self.pan_objetivo = 90.0
        self.tilt = self.tilt_objetivo = 90.0
        self.hablando = False
        self.mandibula_abierta = False
        self._mover(CANAL_PAN, self.pan)
        self._mover(CANAL_TILT, self.tilt)
        self._mover(CANAL_MANDIBULA, self.jaw_closed)

        self.create_subscription(Bool, "/tr/speaking", self._on_speaking, 10)
        self.create_subscription(Float32MultiArray, "/tr/head_pose", self._on_head_pose, 10)
        self.create_timer(PERIODO_SEC, self._ciclo)
        self.get_logger().info("🦴 servo_node listo.")

    def _mover(self, canal: int, angulo: float):
        angulo = max(0.0, min(180.0, angulo))
        if self.pico is not None:
            self.ultimos[canal] = angulo
            self.pico.servo(canal, angulo)
            return
        if self.kit is None:
            self.get_logger().debug(f"🦴 [sim] canal {canal} → {angulo:.0f}°")
            return
        try:
            self.kit.servo[canal].angle = angulo
        except Exception as e:
            self.get_logger().error(f"🦴 Error moviendo el servo del canal {canal}: {e}")

    def _on_speaking(self, msg: Bool):
        self.hablando = bool(msg.data)
        if not self.hablando:
            self.mandibula_abierta = False
            self._mover(CANAL_MANDIBULA, self.jaw_closed)

    def _on_head_pose(self, msg: Float32MultiArray):
        if len(msg.data) < 2:
            self.get_logger().error("🦴 /tr/head_pose necesita [pan, tilt] en grados.")
            return
        self.pan_objetivo = max(self.pan_lim[0], min(self.pan_lim[1], float(msg.data[0])))
        self.tilt_objetivo = max(self.tilt_lim[0], min(self.tilt_lim[1], float(msg.data[1])))

    def _ciclo(self):
        if self.pico is not None:
            self.ciclos += 1
            if self.ciclos >= CICLOS_REENVIO:
                self.ciclos = 0
                for canal, angulo in self.ultimos.items():
                    self.pico.servo(canal, angulo)

        # Mandíbula: sílabas de duración irregular mientras habla
        if self.hablando:
            if self.mandibula_abierta or random.random() < 0.7:
                self.mandibula_abierta = not self.mandibula_abierta
                apertura = random.uniform(0.5, 1.0)
                angulo = (self.jaw_closed + (self.jaw_open - self.jaw_closed) * apertura
                          if self.mandibula_abierta else self.jaw_closed)
                self._mover(CANAL_MANDIBULA, angulo)

        # Cuello: se acerca al objetivo poco a poco (movimiento suave)
        for eje in ("pan", "tilt"):
            actual, objetivo = getattr(self, eje), getattr(self, f"{eje}_objetivo")
            if abs(objetivo - actual) > 0.5:
                paso = max(-PASO_CUELLO_GRADOS, min(PASO_CUELLO_GRADOS, objetivo - actual))
                setattr(self, eje, actual + paso)
                self._mover(CANAL_PAN if eje == "pan" else CANAL_TILT, actual + paso)

    def destroy_node(self):
        self._mover(CANAL_MANDIBULA, self.jaw_closed)
        if self.pico is not None:
            self.pico.close()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = ServoNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
