#!/usr/bin/env python3
"""
voice_node.py — Nodo ROS 2 de VOZ (oído + habla)
=================================================
Cierra el bucle hablado del robot:
  - escucha por micrófono (Vosk, offline) y publica lo entendido en /tr/speech_in
  - se suscribe a /tr/speech_out y lo pronuncia (pyttsx3 / espeak-ng)

Mientras el robot habla, el reconocedor se silencia para NO oírse a sí mismo.

Usa las clases puras de tr_brain.voice (testeables sin ROS con demo_voz.py).
Requisito: `pip install -e ".[voice]"` (vosk, pyaudio, pyttsx3).
"""
import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from tr_brain.voice import ReconocedorVoz, SintetizadorVoz


class VoiceNode(Node):
    def __init__(self):
        super().__init__("voice_node")

        self.pub_in = self.create_publisher(String, "/tr/speech_in", 10)

        # TTS: habla lo que publique el cerebro
        self.synth = SintetizadorVoz()
        self.create_subscription(String, "/tr/speech_out", self._on_speech_out, 10)

        # STT: escucha y publica; se silencia mientras el TTS suena
        self.stt = ReconocedorVoz(
            al_reconocer=self._on_texto,
            esta_silenciado=lambda: self.synth.hablando.is_set(),
        )
        self.stt.iniciar()

        self.get_logger().info(
            f"🗣️ Voice Node listo (STT: {self.stt.modo}, TTS: {self.synth.backend})")

    def _on_texto(self, texto: str):
        msg = String()
        msg.data = texto
        self.pub_in.publish(msg)

    def _on_speech_out(self, msg: String):
        self.synth.decir(msg.data)

    def destroy_node(self):
        self.stt.detener()
        self.synth.detener()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = VoiceNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
