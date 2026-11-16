#!/usr/bin/env python3
"""
stt_node.py — Oídos de TR (se ejecuta en el PORTÁTIL)
========================================================
La Pi Zero 2 W solo captura el micrófono y manda bloques de 0,5 s por Wi-Fi
(/tr/audio_raw). Este nodo hace el trabajo pesado:

  1. Detecta cuándo alguien habla (VAD por energía, vad.py).
  2. Reconoce la frase con Google (online) o Vosk (offline).
  3. Publica el texto en /tr/speech_in.

Mientras TR habla (/tr/speaking = True) descarta todo el audio para no
transcribirse a sí mismo.

Parámetro stt_engine:
  "auto"   → Google si hay internet; si falla, Vosk (y no reintenta Google en 60 s)
  "vosk"   → solo Vosk (100% offline)
  "google" → solo Google
"""
import json
import queue
import threading
import time
from pathlib import Path

import numpy as np
import rclpy
from rclpy.node import Node
from std_msgs.msg import Bool, String, UInt8MultiArray

from tr_robot_brain.vad import DetectorVoz

try:
    import speech_recognition as sr
except ImportError:
    sr = None

try:
    import vosk
except ImportError:
    vosk = None

VOSK_MODEL_PATH = Path.home() / ".tr_robot_ollama" / "vosk-model-small-es"
SAMPLE_RATE = 16000
MARGEN_TRAS_HABLAR_SEC = 0.6   # eco del altavoz que aún puede llegar
GOOGLE_PAUSA_SI_FALLA_SEC = 60.0


class SttNode(Node):
    """Convierte el audio que llega de la cabeza en texto."""

    def __init__(self):
        super().__init__("stt_node")
        self.declare_parameter("stt_engine", "auto")
        self.declare_parameter("energy_threshold", 300.0)
        self.declare_parameter("pause_threshold", 0.8)
        self.get_logger().info("🎤 Iniciando stt_node...")

        self.engine = self.get_parameter("stt_engine").value
        self.detector = DetectorVoz(
            sample_rate=SAMPLE_RATE,
            energia_minima=float(self.get_parameter("energy_threshold").value),
            pausa_fin=float(self.get_parameter("pause_threshold").value),
        )
        self._robot_hablando = False
        self._fin_de_habla = 0.0
        self._google_pausado_hasta = 0.0
        self._vosk_model = None
        self._frases: "queue.Queue[bytes]" = queue.Queue(maxsize=5)

        if self.engine in ("auto", "google") and sr is None:
            self.get_logger().error("🎤 'speech_recognition' no está instalado; uso solo Vosk.")
            self.engine = "vosk"
        if self.engine in ("auto", "vosk"):
            self._vosk_model = self._cargar_vosk()

        self.pub_speech_in = self.create_publisher(String, "/tr/speech_in", 10)
        self.pub_status = self.create_publisher(String, "/tr/status", 10)
        self.create_subscription(UInt8MultiArray, "/tr/audio_raw", self._on_audio, 20)
        self.create_subscription(Bool, "/tr/speaking", self._on_speaking, 10)

        # El reconocimiento puede tardar ~1 s: se hace en otro hilo
        threading.Thread(target=self._worker_reconocimiento, daemon=True).start()
        self.get_logger().info(f"🎤 stt_node listo (motor: {self.engine}).")

    # ------------------------------------------------------------------ #
    # Audio entrante
    # ------------------------------------------------------------------ #
    def _on_speaking(self, msg: Bool):
        self._robot_hablando = bool(msg.data)
        if self._robot_hablando:
            self.detector.reiniciar()
        else:
            self._fin_de_habla = time.monotonic()

    def _on_audio(self, msg: UInt8MultiArray):
        if self._robot_hablando or time.monotonic() - self._fin_de_habla < MARGEN_TRAS_HABLAR_SEC:
            return
        try:
            muestras = np.frombuffer(bytes(msg.data), dtype=np.int16)
        except ValueError as e:
            self.get_logger().error(f"🎤 Bloque de audio con tamaño inválido: {e}")
            return

        estaba_hablando = self.detector.hablando
        frases = self.detector.procesar(muestras)
        if self.detector.hablando and not estaba_hablando:
            self._publicar(self.pub_status, "listening")
        for frase in frases:
            try:
                self._frases.put_nowait(frase)
            except queue.Full:
                self.get_logger().error("🎤 Cola de reconocimiento llena; descarto una frase.")
        if estaba_hablando and not self.detector.hablando and not frases:
            self._publicar(self.pub_status, "idle")  # era solo ruido

    # ------------------------------------------------------------------ #
    # Reconocimiento
    # ------------------------------------------------------------------ #
    def _worker_reconocimiento(self):
        while rclpy.ok():
            frase = self._frases.get()
            try:
                texto = self._reconocer(frase)
            except Exception as e:
                self.get_logger().error(f"🎤 Error inesperado reconociendo: {e}")
                texto = ""
            if texto:
                self.get_logger().info(f"🎤 Reconocido: {texto!r}")
                self._publicar(self.pub_speech_in, texto)
            else:
                self._publicar(self.pub_status, "idle")

    def _reconocer(self, audio: bytes) -> str:
        usar_google = self.engine == "google" or (
            self.engine == "auto" and time.monotonic() >= self._google_pausado_hasta
        )
        if usar_google:
            try:
                datos = sr.AudioData(audio, SAMPLE_RATE, 2)
                return sr.Recognizer().recognize_google(datos, language="es-ES").strip()
            except sr.UnknownValueError:
                return ""
            except Exception as e:
                if self.engine == "google":
                    self.get_logger().error(f"🎤 Google STT no disponible: {e}")
                    return ""
                self.get_logger().error(
                    f"🎤 Google STT no disponible ({e}); uso Vosk offline durante "
                    f"{GOOGLE_PAUSA_SI_FALLA_SEC:.0f} s."
                )
                self._google_pausado_hasta = time.monotonic() + GOOGLE_PAUSA_SI_FALLA_SEC
        return self._reconocer_vosk(audio)

    def _reconocer_vosk(self, audio: bytes) -> str:
        if self._vosk_model is None:
            return ""
        try:
            reconocedor = vosk.KaldiRecognizer(self._vosk_model, SAMPLE_RATE)
            reconocedor.AcceptWaveform(audio)
            return json.loads(reconocedor.FinalResult()).get("text", "").strip()
        except Exception as e:
            self.get_logger().error(f"🎤 Error reconociendo con Vosk: {e}")
            return ""

    def _cargar_vosk(self):
        if vosk is None:
            self.get_logger().error("🎤 La librería 'vosk' no está instalada; STT offline desactivado.")
            return None
        if not VOSK_MODEL_PATH.exists():
            self.get_logger().error(
                f"🎤 No encuentro el modelo Vosk en {VOSK_MODEL_PATH}. "
                "Ejecuta scripts/install_brain.sh o descárgalo de alphacephei.com/vosk/models."
            )
            return None
        try:
            vosk.SetLogLevel(-1)
            modelo = vosk.Model(str(VOSK_MODEL_PATH))
            self.get_logger().info("🎤 Modelo Vosk cargado.")
            return modelo
        except Exception as e:
            self.get_logger().error(f"🎤 Error cargando el modelo Vosk: {e}")
            return None

    @staticmethod
    def _publicar(publisher, texto: str):
        msg = String()
        msg.data = texto
        publisher.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = SttNode()
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
