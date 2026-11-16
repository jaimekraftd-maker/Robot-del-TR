"""
tr_brain.voice — Oído (STT) y voz (TTS) del robot
=================================================
Capa de AUDIO, framework-agnóstica (sin ROS): se puede probar sola con
demo_voz.py y la importa el nodo ROS voice_node.py.

- ReconocedorVoz (STT): micrófono -> texto, en streaming y OFFLINE con Vosk
  (modelo español ya instalado por install.sh). Si falta el stack de audio,
  cae a ENTRADA POR TECLADO para poder desarrollar sin micrófono.

- SintetizadorVoz (TTS): texto -> voz. Backends autodetectados: pyttsx3
  (Windows/Linux), espeak-ng (Raspberry/Linux) o, en último caso, imprimir.
  Hablar es NO BLOQUEANTE (cola + hilo) y expone el evento 'hablando' para que
  el reconocedor se silencie y el robot NO se oiga a sí mismo.

Todas las dependencias pesadas (vosk, pyaudio, pyttsx3) se importan de forma
PEREZOSA: importar este módulo nunca falla aunque no estén instaladas.
"""
import os
import json
import time
import queue
import shutil
import logging
import threading
import subprocess
from typing import Callable, Optional

from . import config

log = logging.getLogger("tr_brain.voice")


# ===========================================================================
#  SÍNTESIS DE VOZ (TTS)
# ===========================================================================
class SintetizadorVoz:
    """Convierte texto en voz. decir() no bloquea: encola y un hilo habla."""

    def __init__(self, backend: str = None, voz: str = config.TTS_VOZ,
                 velocidad: int = config.TTS_VELOCIDAD):
        self.voz = voz
        self.velocidad = velocidad
        self.hablando = threading.Event()      # activo desde que se pide hablar hasta que calla
        self._cola: "queue.Queue[Optional[str]]" = queue.Queue()
        self._corriendo = True
        self._engine = None                     # motor pyttsx3 (se crea en SU hilo)
        self.backend = self._elegir_backend(backend or config.TTS_BACKEND)
        log.info(f"TTS backend: {self.backend}")
        self._hilo = threading.Thread(target=self._bucle, name="TTSThread", daemon=True)
        self._hilo.start()

    def _elegir_backend(self, preferido):
        if preferido in ("pyttsx3", "espeak", "print"):
            return preferido
        try:
            import pyttsx3  # noqa: F401
            return "pyttsx3"
        except Exception:
            pass
        if shutil.which("espeak-ng") or shutil.which("espeak"):
            return "espeak"
        return "print"

    def decir(self, texto: str):
        """Encola texto para hablar (no bloquea al que llama)."""
        if texto and texto.strip():
            self.hablando.set()        # se marca YA, para silenciar el micro al instante
            self._cola.put(texto.strip())

    def _bucle(self):
        while self._corriendo:
            texto = self._cola.get()
            if texto is None:          # centinela de apagado
                break
            try:
                self._hablar(texto)
            except Exception as e:
                log.warning(f"Error de TTS: {e}")
            finally:
                # seguimos "hablando" si quedan frases encoladas
                if self._cola.empty():
                    self.hablando.clear()

    def _hablar(self, texto):
        if self.backend == "pyttsx3":
            self._hablar_pyttsx3(texto)
        elif self.backend == "espeak":
            self._hablar_espeak(texto)
        else:
            print(f"[VOZ] {texto}")

    def _hablar_pyttsx3(self, texto):
        if self._engine is None:
            import pyttsx3
            self._engine = pyttsx3.init()
            self._engine.setProperty("rate", self.velocidad)
            self._elegir_voz_es(self._engine)
        # Voz robótica: generamos el audio a un WAV, le aplicamos el efecto y lo
        # reproducimos nosotros. Si algo falla, hablamos con voz normal.
        if config.VOZ_ROBOTICA:
            import os
            import tempfile
            wav = os.path.join(tempfile.gettempdir(), "tr_voz.wav")
            try:
                self._engine.save_to_file(texto, wav)
                self._engine.runAndWait()
                if self._robotizar(wav):
                    self._reproducir(wav)
                    return
            except Exception as e:
                log.debug(f"Efecto robótico no disponible ({e}); uso voz normal.")
        self._engine.say(texto)
        self._engine.runAndWait()

    def _hablar_espeak(self, texto):
        exe = shutil.which("espeak-ng") or shutil.which("espeak")
        if config.VOZ_ROBOTICA:
            args = [exe, "-v", config.VOZ_VARIANTE_ESPEAK, "-s", str(self.velocidad),
                    "-p", str(config.VOZ_ROBOT_PITCH), texto]
        else:
            args = [exe, "-v", self.voz, "-s", str(self.velocidad), texto]
        try:
            subprocess.run(args, check=False)
        except Exception as e:
            log.warning(f"espeak falló ({e}).")

    @staticmethod
    def _robotizar(path) -> bool:
        """Efecto robótico in situ sobre el WAV: modulación en anillo (timbre
        robótico) + vibrato del portador ('desafinada') + saturación ('rota').
        Necesita numpy; si no está, devuelve False (se habla con voz normal)."""
        try:
            import wave
            import numpy as np
        except Exception:
            return False
        try:
            with wave.open(path, "rb") as w:
                sr, ch, sw, n = w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()
                raw = w.readframes(n)
            if sw != 2 or n == 0:
                return False
            x = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
            if ch == 2:
                x = x.reshape(-1, 2).mean(axis=1)
            x /= 32768.0
            t = np.arange(len(x)) / sr
            vib = config.VOZ_ROBOT_DETUNE * np.sin(2 * np.pi * 5.0 * t)      # desafine
            carrier = np.sin(2 * np.pi * (config.VOZ_ROBOT_CARRIER + vib) * t)
            y = x * (0.55 + 0.45 * carrier)                                 # ring mod parcial
            y *= (0.85 + 0.15 * np.sin(2 * np.pi * 7.0 * t))                # tremolo leve
            d = max(0.1, config.VOZ_ROBOT_DISTORSION)
            y = np.tanh(d * y) / np.tanh(d)                                  # saturación -> "rota"
            y = np.clip(y, -1.0, 1.0)
            out = (y * 32767).astype(np.int16).tobytes()
            with wave.open(path, "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(sr)
                w.writeframes(out)
            return True
        except Exception as e:
            log.debug(f"robotizar falló: {e}")
            return False

    @staticmethod
    def _reproducir(path):
        """Reproduce un WAV (bloqueante). Windows: winsound; Linux: aplay/paplay/ffplay."""
        try:
            import winsound
            winsound.PlaySound(path, winsound.SND_FILENAME)
            return
        except Exception:
            pass
        for rep in ("aplay", "paplay", "ffplay"):
            exe = shutil.which(rep)
            if exe:
                args = [exe, "-nodisp", "-autoexit", path] if rep == "ffplay" else [exe, path]
                subprocess.run(args, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return
        log.warning("No encuentro reproductor de audio para el WAV robotizado.")

    @staticmethod
    def _elegir_voz_es(engine):
        try:
            for v in engine.getProperty("voices"):
                if "spanish" in v.name.lower() or "es" in (v.id or "").lower():
                    engine.setProperty("voice", v.id)
                    return
        except Exception:
            pass

    def esperar(self, timeout=15):
        """Bloquea hasta que termina de hablar (útil en scripts/demos)."""
        t0 = time.time()
        while (not self._cola.empty() or self.hablando.is_set()) and time.time() - t0 < timeout:
            time.sleep(0.05)

    def detener(self):
        self._corriendo = False
        self._cola.put(None)


# ===========================================================================
#  RECONOCIMIENTO DE VOZ (STT)
# ===========================================================================
class ReconocedorVoz:
    """Escucha el micrófono y llama a al_reconocer(texto) por cada frase.

    al_reconocer    : callback que recibe el texto entendido.
    esta_silenciado : función que devuelve True cuando hay que ignorar el audio
                      (p. ej. mientras el robot habla, para no oírse a sí mismo).
    """

    def __init__(self, al_reconocer: Callable[[str], None],
                 esta_silenciado: Callable[[], bool] = None,
                 modelo_path: str = config.VOSK_MODEL_PATH):
        self.al_reconocer = al_reconocer
        self.esta_silenciado = esta_silenciado or (lambda: False)
        self.modelo_path = modelo_path
        self._corriendo = False
        self._hilo = None
        self.modo = self._detectar_modo()

    def _detectar_modo(self):
        try:
            import vosk, pyaudio  # noqa: F401
            if os.path.isdir(self.modelo_path):
                return "vosk"
            log.warning(f"No encuentro el modelo Vosk en {self.modelo_path}; uso teclado.")
        except Exception as e:
            log.warning(f"Stack de audio no disponible ({e}); uso teclado.")
        return "teclado"

    def esta_activo(self):
        return self._corriendo

    def iniciar(self):
        self._corriendo = True
        destino = self._bucle_vosk if self.modo == "vosk" else self._bucle_teclado
        self._hilo = threading.Thread(target=destino, name="STTThread", daemon=True)
        self._hilo.start()

    def _bucle_vosk(self):
        import vosk
        import pyaudio
        vosk.SetLogLevel(-1)
        modelo = vosk.Model(self.modelo_path)
        rec = vosk.KaldiRecognizer(modelo, config.STT_SAMPLE_RATE)
        pa = pyaudio.PyAudio()
        stream = pa.open(format=pyaudio.paInt16, channels=1, rate=config.STT_SAMPLE_RATE,
                         input=True, frames_per_buffer=config.STT_BLOQUE * 2)
        stream.start_stream()
        log.info("🎤 Escucha iniciada (Vosk).")
        silenciado_antes = False
        try:
            while self._corriendo:
                data = stream.read(config.STT_BLOQUE, exception_on_overflow=False)
                if self.esta_silenciado():
                    silenciado_antes = True
                    continue                      # descartamos el audio mientras el robot habla
                if silenciado_antes:
                    rec.Reset()                   # no arrastrar la propia voz del robot
                    silenciado_antes = False
                if rec.AcceptWaveform(data):
                    texto = json.loads(rec.Result()).get("text", "").strip()
                    if texto:
                        log.info(f"🎤 Oído: {texto}")
                        self.al_reconocer(texto)
        finally:
            stream.stop_stream()
            stream.close()
            pa.terminate()

    def _bucle_teclado(self):
        log.info("⌨️  Escucha en MODO TECLADO (sin micrófono/Vosk). Escribe y pulsa Enter.")
        while self._corriendo:
            try:
                texto = input("» ")
            except (EOFError, KeyboardInterrupt):
                break
            if texto.strip():
                self.al_reconocer(texto.strip())

    def detener(self):
        self._corriendo = False
