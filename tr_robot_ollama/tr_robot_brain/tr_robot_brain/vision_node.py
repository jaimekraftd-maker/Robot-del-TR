#!/usr/bin/env python3
"""
vision_node.py — Ojos de TR (se ejecuta en el PORTÁTIL)
=========================================================
La cámara está en la Pi Zero 2 W, que publica JPEG comprimidos por Wi-Fi en
/tr/camera/image/compressed. Este nodo guarda el último JPEG y describe la
escena, por orden:

  1. Claude (tareas.vision de config/agente_tr.json): cada 60 s
     (cada_s) y cuando llega /tr/vision_request. Cada
     descripción gasta uso de tu plan de Claude, de ahí que sea menos frecuente.
  2. moondream en Ollama, cada 15 s, si no hay sesión de Claude o falla.
  3. Detección de movimiento, si moondream tampoco está disponible.

El JPEG recibido se manda tal cual en base64: no hace falta descomprimirlo
(solo se descomprime para la detección de movimiento).
"""
import base64
import threading
import time

import cv2
import numpy as np
import requests
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import CompressedImage
from std_msgs.msg import String

from tr_robot_brain import agente as agente_tr
from tr_robot_brain.llm import ErrorLLM, Peticion, crear_claude

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_VISION = "moondream"
PROMPT_VISION = "Describe brevemente qué ves en esta imagen en español."
DESCRIBE_INTERVAL_SEC = 15.0
FRAME_MAX_ANTIGUEDAD_SEC = 5.0     # no describir imágenes viejas (cámara caída)
REINTENTAR_MOONDREAM_SEC = 300.0
# La descripción acaba en el system prompt de TR ("LO QUE VES AHORA MISMO")
SYSTEM_VISION = ("Eres los ojos de TR, una cabeza robótica. Describe la imagen de su "
                 "cámara en una o dos frases (como mucho unas {max_palabras} palabras), "
                 "sin listas ni formato.")


class VisionNode(Node):
    """Describe lo que ve la cámara de la cabeza."""

    def __init__(self):
        super().__init__("vision_node")
        self.get_logger().info("👁️ Iniciando vision_node...")

        self._lock = threading.Lock()
        self._ocupado = threading.Lock()
        self._ultimo_jpeg: bytes | None = None
        self._ultimo_jpeg_t = 0.0
        self._gris_anterior = None
        self._moondream_pausado_hasta = 0.0
        # Modelo, esfuerzo, intervalo y límite de palabras: tareas.vision de agente_tr.json
        self._agente = agente_tr.cargar(log=self.get_logger().warn)
        self._vision = self._agente["tareas"]["vision"]
        self._claude = crear_claude(self._agente, log_error=self.get_logger().warn, prefijo="👁️")
        self._claude_pausado_hasta = 0.0
        self._ultima_con_claude = float("-inf")

        self.pub_description = self.create_publisher(String, "/tr/vision_description", 10)
        # QoS "sensor data" (best effort): debe coincidir con el camera_node de la cabeza
        self.create_subscription(CompressedImage, "/tr/camera/image/compressed",
                                 self._on_image, qos_profile_sensor_data)
        self.create_subscription(String, "/tr/vision_request", self._on_vision_request, 10)
        self.create_timer(DESCRIBE_INTERVAL_SEC, self._lanzar_descripcion)

        if self._claude is not None:
            modo = (f"{agente_tr.modelo_de(self._agente, 'vision')} cada {self._vision['cada_s']:g} s, "
                    f"{MODEL_VISION} de respaldo")
        else:
            modo = f"{MODEL_VISION} cada {DESCRIBE_INTERVAL_SEC:.0f} s"
        self.get_logger().info(f"👁️ vision_node listo ({modo}; esperando imágenes de la cabeza).")

    def _on_image(self, msg: CompressedImage):
        with self._lock:
            self._ultimo_jpeg = bytes(msg.data)
            self._ultimo_jpeg_t = time.monotonic()

    def _on_vision_request(self, msg: String):
        self.get_logger().info("👁️ Descripción bajo demanda solicitada.")
        self._lanzar_descripcion(bajo_demanda=True)

    def _claude_disponible(self) -> bool:
        return self._claude is not None and time.monotonic() >= self._claude_pausado_hasta

    def _lanzar_descripcion(self, bajo_demanda: bool = False):
        # Describir tarda varios segundos: en otro hilo para no bloquear ROS,
        # y nunca dos descripciones a la vez.
        if self._ocupado.locked():
            return
        # Con Claude, el temporizador de 15 s solo describe cada tareas.vision.cada_s (60 s)
        if (not bajo_demanda and self._claude_disponible()
                and time.monotonic() - self._ultima_con_claude < self._vision["cada_s"]):
            return
        threading.Thread(target=self._describir_y_publicar, daemon=True).start()

    def _describir_y_publicar(self):
        with self._ocupado:
            with self._lock:
                jpeg, t = self._ultimo_jpeg, self._ultimo_jpeg_t
            if jpeg is None:
                self.get_logger().warn("👁️ Aún no ha llegado ninguna imagen de la cabeza.")
                return
            if time.monotonic() - t > FRAME_MAX_ANTIGUEDAD_SEC:
                self.get_logger().warn("👁️ La última imagen es antigua: ¿se ha caído la cámara o el Wi-Fi?")
                return

            descripcion = self._describir_con_claude(jpeg)
            if descripcion is None:  # Claude no disponible (sin sesión, sin internet...)
                descripcion = (self._describir_con_moondream(jpeg)
                               or self._describir_por_movimiento(jpeg))
            if descripcion:
                msg = String()
                msg.data = descripcion
                self.pub_description.publish(msg)
                self.get_logger().info(f"👁️ Descripción: {descripcion}")

    def _describir_con_claude(self, jpeg: bytes) -> str | None:
        """La descripción de Claude; "" si se negó a describirla (y entonces no se
        le pregunta a moondream); None si Claude no está disponible."""
        if not self._claude_disponible():
            return None
        peticion = Peticion(
            prompt=PROMPT_VISION, tarea="vision", imagen=jpeg, timeout=self._vision["timeout_s"],
            system=[SYSTEM_VISION.format(max_palabras=self._vision["max_palabras"])],
        )
        try:
            texto = self._claude.generar(peticion)
        except ErrorLLM as e:
            if e.permanente:
                self.get_logger().error(f"👁️ {e} Dejo de usar Claude para ver; uso {MODEL_VISION}.")
                self._claude = None
            else:
                pausa = self._agente["claude"]["pausa_tras_fallo_s"]
                self._claude_pausado_hasta = time.monotonic() + pausa
                self.get_logger().error(f"👁️ {e} Uso {MODEL_VISION} durante {pausa:g} s.")
            return None
        self._ultima_con_claude = time.monotonic()
        return texto

    def _describir_con_moondream(self, jpeg: bytes) -> str:
        if time.monotonic() < self._moondream_pausado_hasta:
            return ""
        payload = {
            "model": MODEL_VISION,
            "prompt": PROMPT_VISION,
            "images": [base64.b64encode(jpeg).decode("ascii")],
            "stream": False,
            "options": {"num_predict": 100},
        }
        try:
            respuesta = requests.post(OLLAMA_URL, json=payload, timeout=30)
            respuesta.raise_for_status()
            return respuesta.json().get("response", "").strip()
        except requests.exceptions.ConnectionError:
            self.get_logger().error("👁️ No puedo conectar con Ollama; uso detección de movimiento.")
        except Exception as e:
            self.get_logger().error(
                f"👁️ moondream no disponible ({e}); uso detección de movimiento "
                f"y reintento en {REINTENTAR_MOONDREAM_SEC:.0f} s."
            )
        self._moondream_pausado_hasta = time.monotonic() + REINTENTAR_MOONDREAM_SEC
        return ""

    def _describir_por_movimiento(self, jpeg: bytes) -> str:
        """Respaldo: compara con la imagen anterior para detectar movimiento."""
        try:
            frame = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
            if frame is None:
                return ""
            gris = cv2.GaussianBlur(frame, (21, 21), 0)
            if self._gris_anterior is None or self._gris_anterior.shape != gris.shape:
                self._gris_anterior = gris
                return "Veo la escena, pero aún no sé si algo se mueve."
            diferencia = cv2.absdiff(self._gris_anterior, gris)
            self._gris_anterior = gris
            _, umbral = cv2.threshold(diferencia, 25, 255, cv2.THRESH_BINARY)
            movimiento = float(np.count_nonzero(umbral)) / umbral.size
            if movimiento > 0.05:
                return "Detecto bastante movimiento delante de mí."
            if movimiento > 0.01:
                return "Detecto un poco de movimiento delante de mí."
            return "La escena está quieta, no veo movimiento."
        except Exception as e:
            self.get_logger().error(f"👁️ Error en detección de movimiento: {e}")
            return ""


def main(args=None):
    rclpy.init(args=args)
    node = VisionNode()
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
