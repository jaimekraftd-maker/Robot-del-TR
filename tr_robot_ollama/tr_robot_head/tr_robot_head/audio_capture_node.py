#!/usr/bin/env python3
"""
audio_capture_node.py — Micrófono de la cabeza (Pi Zero 2 W)
===============================================================
Captura el micrófono USB a 16 kHz mono (PCM int16) y publica bloques de
0,5 s (16.000 bytes) en /tr/audio_raw (std_msgs/UInt8MultiArray). La
detección de voz y el reconocimiento se hacen en el portátil (stt_node).

Mientras el robot habla (/tr/speaking = True) sigue leyendo el micrófono
(para que no se desborde el buffer) pero NO publica nada.

Si el micrófono no admite 16 kHz, se abre a su frecuencia nativa y se
remuestrea con numpy (barato incluso en la Pi Zero).
"""
import array
import threading

import numpy as np
import rclpy
from rclpy.node import Node
from std_msgs.msg import Bool, UInt8MultiArray

try:
    import pyaudio
except ImportError:
    pyaudio = None

RATE_OBJETIVO = 16000
DURACION_BLOQUE = 0.5


class AudioCaptureNode(Node):
    def __init__(self):
        super().__init__("audio_capture_node")
        self.declare_parameter("device_index", -1)   # -1 = dispositivo por defecto de ALSA
        self.get_logger().info("🎙️ Iniciando audio_capture_node...")

        self._robot_hablando = threading.Event()
        self.pub = self.create_publisher(UInt8MultiArray, "/tr/audio_raw", 20)
        self.create_subscription(Bool, "/tr/speaking", self._on_speaking, 10)

        if pyaudio is None:
            self.get_logger().error("🎙️ PyAudio no está instalado (apt install python3-pyaudio).")
            return
        threading.Thread(target=self._bucle_captura, daemon=True).start()

    def _on_speaking(self, msg: Bool):
        if msg.data:
            self._robot_hablando.set()
        else:
            self._robot_hablando.clear()

    def _abrir_stream(self, pa):
        """Intenta 16 kHz; si el micro no lo admite, usa su frecuencia nativa."""
        indice = self.get_parameter("device_index").value
        indice = None if indice < 0 else indice
        info = pa.get_device_info_by_index(indice) if indice is not None else pa.get_default_input_device_info()
        self.get_logger().info(f"🎙️ Micrófono: {info.get('name')}")
        for rate in (RATE_OBJETIVO, int(info.get("defaultSampleRate", 48000))):
            try:
                stream = pa.open(format=pyaudio.paInt16, channels=1, rate=rate, input=True,
                                 input_device_index=indice,
                                 frames_per_buffer=int(rate * DURACION_BLOQUE))
                return stream, rate
            except Exception as e:
                self.get_logger().warn(f"🎙️ El micrófono no acepta {rate} Hz ({e}).")
        raise RuntimeError("no se pudo abrir el micrófono a ninguna frecuencia")

    def _bucle_captura(self):
        pa = pyaudio.PyAudio()
        try:
            stream, rate = self._abrir_stream(pa)
        except Exception as e:
            self.get_logger().error(f"🎙️ No se pudo abrir el micrófono: {e}")
            pa.terminate()
            return

        muestras_bloque = int(rate * DURACION_BLOQUE)
        muestras_objetivo = int(RATE_OBJETIVO * DURACION_BLOQUE)
        if rate != RATE_OBJETIVO:
            self.get_logger().info(f"🎙️ Capturando a {rate} Hz y remuestreando a {RATE_OBJETIVO} Hz.")
            x_orig = np.linspace(0.0, 1.0, muestras_bloque, endpoint=False)
            x_obj = np.linspace(0.0, 1.0, muestras_objetivo, endpoint=False)
        self.get_logger().info("🎙️ Capturando audio.")

        try:
            while rclpy.ok():
                try:
                    datos = stream.read(muestras_bloque, exception_on_overflow=False)
                except Exception as e:
                    self.get_logger().error(f"🎙️ Error leyendo el micrófono: {e}")
                    continue
                if self._robot_hablando.is_set():
                    continue  # no escucharse a sí mismo
                if rate != RATE_OBJETIVO:
                    muestras = np.frombuffer(datos, dtype=np.int16).astype(np.float32)
                    datos = np.interp(x_obj, x_orig, muestras).astype(np.int16).tobytes()
                msg = UInt8MultiArray()
                msg.data = array.array("B", datos)
                self.pub.publish(msg)
        finally:
            stream.stop_stream()
            stream.close()
            pa.terminate()


def main(args=None):
    rclpy.init(args=args)
    node = AudioCaptureNode()
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
