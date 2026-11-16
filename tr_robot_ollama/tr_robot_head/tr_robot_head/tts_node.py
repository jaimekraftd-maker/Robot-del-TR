#!/usr/bin/env python3
"""
tts_node.py — Voz de la cabeza (Pi Zero 2 W)
===============================================
Recibe /tr/speech_out y lo pronuncia en local con espeak-ng (voz española,
-v es -s 150 -p 50). espeak-ng es muy ligero: ideal para la Pi Zero.

Publica /tr/speaking (Bool) al empezar y al terminar cada frase: lo usan
audio_capture_node y stt_node (para no escucharse) y servo_node (para mover
la mandíbula). También publica /tr/status "speaking"/"idle" para los LEDs.

Las frases se encolan (threading.Queue) para no bloquear el hilo de ROS.
"""
import queue
import subprocess
import threading
import time

import rclpy
from rclpy.node import Node
from std_msgs.msg import Bool, String

MARGEN_FIN_AUDIO_SEC = 0.3   # el altavoz suena un poco después de que espeak termina


class TtsNode(Node):
    def __init__(self):
        super().__init__("tts_node")
        self.declare_parameter("voice", "es")
        self.declare_parameter("speed", 150)
        self.declare_parameter("pitch", 50)
        # Vacío = salida por defecto de ALSA. Ej. "plughw:1,0" para un altavoz USB concreto.
        self.declare_parameter("alsa_device", "")
        self.declare_parameter("end_margin", MARGEN_FIN_AUDIO_SEC)
        self.get_logger().info("🔊 Iniciando tts_node...")

        self._cola: "queue.Queue[str]" = queue.Queue()
        self.pub_speaking = self.create_publisher(Bool, "/tr/speaking", 10)
        self.pub_status = self.create_publisher(String, "/tr/status", 10)
        self.create_subscription(String, "/tr/speech_out", self._on_speech_out, 10)

        threading.Thread(target=self._worker, daemon=True).start()
        self._publicar_speaking(False)
        self._publicar_status("idle")
        self.get_logger().info("🔊 tts_node listo.")

    def _on_speech_out(self, msg: String):
        texto = msg.data.strip()
        if texto:
            self._cola.put(texto)

    def _worker(self):
        while rclpy.ok():
            texto = self._cola.get()
            self._publicar_speaking(True)
            self._publicar_status("speaking")
            try:
                self.get_logger().info(f"🔊 Hablando: {texto!r}")
                self._hablar(texto)
            except Exception as e:
                self.get_logger().error(f"🔊 Error inesperado hablando: {e}")
            finally:
                time.sleep(self.get_parameter("end_margin").value)
                if self._cola.empty():
                    self._publicar_speaking(False)
                    self._publicar_status("idle")

    def _hablar(self, texto: str):
        voz = ["-v", self.get_parameter("voice").value,
               "-s", str(self.get_parameter("speed").value),
               "-p", str(self.get_parameter("pitch").value)]
        dispositivo = self.get_parameter("alsa_device").value
        try:
            if dispositivo:
                # espeak-ng genera el WAV y aplay lo manda al dispositivo elegido
                espeak = subprocess.Popen(["espeak-ng", *voz, "--stdout", texto],
                                          stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
                subprocess.run(["aplay", "-q", "-D", dispositivo], stdin=espeak.stdout,
                               timeout=60, check=False)
                espeak.wait(timeout=5)
            else:
                subprocess.run(["espeak-ng", *voz, texto], timeout=60, check=True,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except FileNotFoundError:
            self.get_logger().error("🔊 espeak-ng no está instalado (sudo apt install espeak-ng).")
        except subprocess.TimeoutExpired:
            self.get_logger().error("🔊 espeak-ng tardó demasiado; frase abortada.")
        except subprocess.CalledProcessError as e:
            self.get_logger().error(f"🔊 espeak-ng falló (código {e.returncode}): ¿altavoz configurado?")

    def _publicar_speaking(self, valor: bool):
        msg = Bool()
        msg.data = valor
        self.pub_speaking.publish(msg)

    def _publicar_status(self, estado: str):
        msg = String()
        msg.data = estado
        self.pub_status.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = TtsNode()
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
