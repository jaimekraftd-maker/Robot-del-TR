#!/usr/bin/env python3
"""
brain_node.py — Cerebro de TR (se ejecuta en el PORTÁTIL)
===========================================================
Envoltorio ROS 2 de CerebroTR (cerebro.py), donde vive toda la lógica:
Claude (u Ollama de respaldo, ver llm.py) + memoria + etapas de desarrollo +
emociones + métricas. El agente (modelo y esfuerzo de cada tarea, identidad...)
se configura en config/agente_tr.json o con variables TR_*, no con parámetros ROS.

Topics:
  Suscribe:  /tr/speech_in (String)           texto reconocido o percepciones
             /tr/vision_description (String)  contexto visual
             /tr/status (String)              órdenes, p.ej. "reset_personality"
             /tr/set_age (Int32)              fija la edad mental (pruebas/demos)
  Publica:   /tr/speech_out (String)          lo que TR va a decir
             /tr/status (String)              "thinking" mientras piensa
"""
import rclpy
from rclpy.node import Node
from std_msgs.msg import Int32, String

from tr_robot_brain.cerebro import CerebroTR

SAVE_INTERVAL_SEC = 60.0   # guardado periódico de memoria
EMOTION_TICK_SEC = 60.0    # evolución de la soledad si nadie habla
WAKE_DELAY_SEC = 8.0       # margen para que la cabeza esté lista antes de hablar


class BrainNode(Node):
    """Nodo ROS 2 que piensa las respuestas de TR."""

    def __init__(self):
        super().__init__("brain_node")
        self.declare_parameter("chat_timeout", 30.0)
        self.get_logger().info("🧠 Iniciando brain_node...")

        self.cerebro = CerebroTR(
            log_info=self.get_logger().info,
            log_error=self.get_logger().error,
            timeout_chat=self.get_parameter("chat_timeout").value,
        )

        self.pub_speech_out = self.create_publisher(String, "/tr/speech_out", 10)
        self.pub_status = self.create_publisher(String, "/tr/status", 10)

        self.create_subscription(String, "/tr/speech_in", self._on_speech_in, 10)
        self.create_subscription(String, "/tr/vision_description", self._on_vision, 10)
        self.create_subscription(String, "/tr/status", self._on_status_cmd, 10)
        self.create_subscription(Int32, "/tr/set_age", self._on_set_age, 10)

        self.create_timer(SAVE_INTERVAL_SEC, self._guardar_memoria)
        self.create_timer(EMOTION_TICK_SEC, self._tick_emocional)
        if self.cerebro.despertar_inquieto:
            self._wake_timer = self.create_timer(WAKE_DELAY_SEC, self._comentar_despertar)

        estado = self.cerebro.resumen_estado()
        self.get_logger().info(
            f"🧠 brain_node listo: {estado['edad']} años ({estado['etapa']}), "
            f"{estado['hechos']} hechos, {estado['interacciones']} interacciones. "
            f"Pienso con {self.cerebro.llm.descripcion}."
        )

    # ------------------------------------------------------------------ #
    # Callbacks
    # ------------------------------------------------------------------ #
    def _on_speech_in(self, msg: String):
        texto = msg.data.strip()
        if not texto:
            return
        self.get_logger().info(f"🧠 Entrada: {texto!r}")
        self._publicar(self.pub_status, "thinking")
        try:
            respuesta = self.cerebro.responder(texto)
        except Exception as e:
            self.get_logger().error(f"🧠 Error generando respuesta: {e}")
            respuesta = "Perdona, no he podido procesar eso ahora mismo."
        self.get_logger().info(f"🧠 Respuesta: {respuesta!r}")
        self._publicar(self.pub_speech_out, respuesta)

    def _on_vision(self, msg: String):
        self.cerebro.set_vision(msg.data)
        self.get_logger().info(f"🧠 Contexto visual: {msg.data[:80]}")

    def _on_status_cmd(self, msg: String):
        if msg.data.strip() == "reset_personality":
            self.cerebro.reset_personality()
            self._guardar_memoria()

    def _on_set_age(self, msg: Int32):
        anterior, nueva = self.cerebro.set_edad(msg.data)
        self.get_logger().info(f"🧠 /tr/set_age: {anterior} → {nueva} años.")
        self._guardar_memoria()

    # ------------------------------------------------------------------ #
    # Timers
    # ------------------------------------------------------------------ #
    def _comentar_despertar(self):
        self._wake_timer.cancel()
        try:
            comentario = self.cerebro.comentario_despertar()
            if comentario:
                self.get_logger().info(f"🧠 Comentario al despertar: {comentario!r}")
                self._publicar(self.pub_speech_out, comentario)
        except Exception as e:
            self.get_logger().error(f"🧠 Error generando comentario de despertar: {e}")

    def _tick_emocional(self):
        try:
            comentario = self.cerebro.tick_emocional()
            if comentario:
                self.get_logger().info(f"🧠 TR habla solo por soledad: {comentario!r}")
                self._publicar(self.pub_speech_out, comentario)
        except Exception as e:
            self.get_logger().error(f"🧠 Error en el tick emocional: {e}")

    def _guardar_memoria(self):
        if self.cerebro.guardar_memoria():
            self.get_logger().debug("🧠 Memoria guardada.")

    # ------------------------------------------------------------------ #
    @staticmethod
    def _publicar(publisher, texto: str):
        msg = String()
        msg.data = texto
        publisher.publish(msg)

    def destroy_node(self):
        self.get_logger().info("🧠 Cerrando brain_node, guardando memoria...")
        self.cerebro.guardar_memoria()
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
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
