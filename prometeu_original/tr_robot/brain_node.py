#!/usr/bin/env python3
"""
brain_node.py (INTEGRADO) — Nodo ROS 2 que usa el núcleo cognitivo tr_brain
===========================================================================
Sustituye la lógica suelta del brain_node original por el cerebro reutilizable
(memoria SQLite + aprendizaje + personalidad + iniciativa). El nodo queda
"fino": solo conecta los topics de ROS con los métodos de CerebroCognitivo.

Topics (compatibles con tus nodos actuales vision_node / person_recognition):
  sub  /tr/speech_in           <- frase del usuario (del futuro nodo de voz/STT)
  sub  /tr/vision_description   <- descripción de escena (vision_node)
  sub  /tr/persons_detected     <- personas reconocidas (person_recognition_node)
  pub  /tr/speech_out           -> lo que el robot debe decir (al nodo de voz/TTS)
  pub  /tr/status               -> thinking / idle ...

Requisito: que 'tr_brain' sea importable. Instálalo con `pip install -e .`
desde la raíz del proyecto, o añade la raíz al PYTHONPATH (ver README).

Este archivo es nuevo y NO toca tu files/brain_node.py original. Cuando lo
valides, colócalo como el brain_node de tu paquete ROS.
"""
import json

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from tr_brain import CerebroCognitivo
from tr_brain import config


class BrainNode(Node):
    def __init__(self):
        super().__init__("brain_node")
        self.core = CerebroCognitivo()
        self.get_logger().info(
            f"🧠 Cerebro cognitivo listo (LLM: {'Gemini' if self.core.llm.disponible else 'OFFLINE'})")

        self.persona_actual = None
        self._reloj_inactividad = self.get_clock().now()

        # Suscriptores
        self.create_subscription(String, "/tr/speech_in", self.on_speech, 10)
        self.create_subscription(String, "/tr/vision_description", self.on_vision, 10)
        self.create_subscription(String, "/tr/persons_detected", self.on_persons, 10)

        # Publicadores
        self.pub_out = self.create_publisher(String, "/tr/speech_out", 10)
        self.pub_status = self.create_publisher(String, "/tr/status", 10)

        # Timers: iniciativa cada 10 s; mantenimiento (olvido) + guardado cada 5 min
        self.create_timer(10.0, self._tick_iniciativa)
        self.create_timer(300.0, self._mantenimiento)

        self.get_logger().info("✅ Brain Node integrado listo")

    # ── Entradas ──────────────────────────────────────────────────────────
    def on_speech(self, msg: String):
        texto = msg.data.strip()
        if not texto:
            return
        self.get_logger().info(f"🎤 {texto}")
        self._status("thinking")
        respuesta = self.core.procesar(texto, persona=self.persona_actual)
        self._decir(respuesta)
        self._status("idle")
        self._reset_inactividad()

    def on_vision(self, msg: String):
        self.core.actualizar_vision(msg.data)

    def on_persons(self, msg: String):
        try:
            personas = json.loads(msg.data)
        except Exception:
            return
        for p in personas:
            nombre = p.get("name")
            if nombre and nombre != "desconocido" and p.get("confidence") in ("high", "medium"):
                self.persona_actual = nombre
                self._decir(self.core.saludar_persona(nombre))
                self._reset_inactividad()
                break

    # ── Comportamiento autónomo ───────────────────────────────────────────
    def _tick_iniciativa(self):
        seg = (self.get_clock().now() - self._reloj_inactividad).nanoseconds / 1e9
        frase = self.core.tick_iniciativa(seg)
        if frase:
            self._decir(frase)
            self._reset_inactividad()

    def _mantenimiento(self):
        self.core.mantenimiento()
        self.get_logger().info("🧹 Mantenimiento de memoria realizado.")

    # ── Salidas / utilidades ──────────────────────────────────────────────
    def _decir(self, texto):
        if not texto:
            return
        m = String()
        m.data = texto
        self.pub_out.publish(m)
        self.get_logger().info(f"🔊 {texto}")

    def _status(self, estado):
        m = String()
        m.data = estado
        self.pub_status.publish(m)

    def _reset_inactividad(self):
        self._reloj_inactividad = self.get_clock().now()

    def destroy_node(self):
        self.core.guardar_estado()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = BrainNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
