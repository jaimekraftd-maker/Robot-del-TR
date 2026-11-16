"""
vad.py — Detector de voz por energía (VAD) para el stt_node
==============================================================
Recibe bloques de audio PCM int16 mono (los de /tr/audio_raw, 0,5 s) y
devuelve las frases completas detectadas, listas para reconocer.

Cómo funciona:
  - Trocea cada bloque en ventanas de 50 ms y calcula su energía (RMS).
  - El umbral se adapta al ruido de fondo: max(energia_minima, ruido * factor).
  - La voz empieza cuando hay 2 ventanas seguidas por encima del umbral, y
    termina tras `pausa_fin` segundos de silencio (como pause_threshold).
  - Guarda 300 ms de audio previo para no cortar el inicio de la primera sílaba.

Puro numpy (sin ROS) para poder probarlo con audio sintético en cualquier PC.
"""
from collections import deque

import numpy as np


class DetectorVoz:
    def __init__(self, sample_rate: int = 16000, energia_minima: float = 300.0,
                 factor_ruido: float = 2.5, pausa_fin: float = 0.8,
                 duracion_minima: float = 0.3, duracion_maxima: float = 15.0,
                 ventana: float = 0.05, preroll: float = 0.3):
        self.sample_rate = sample_rate
        self.energia_minima = energia_minima
        self.factor_ruido = factor_ruido
        self.muestras_ventana = int(sample_rate * ventana)
        self.ventanas_pausa = int(pausa_fin / ventana)
        self.ventanas_minimas = int(duracion_minima / ventana)
        self.ventanas_maximas = int(duracion_maxima / ventana)
        self._preroll = deque(maxlen=int(preroll / ventana))
        self.ruido = energia_minima / factor_ruido
        self._resto = np.zeros(0, dtype=np.int16)
        self.reiniciar()

    def reiniciar(self):
        """Olvida la frase en curso (p.ej. cuando el robot empieza a hablar)."""
        self.hablando = False
        self._frase: list[np.ndarray] = []
        self._ventanas_con_voz = 0
        self._silencio_seguido = 0
        self._voz_seguida = 0
        self._preroll.clear()
        self._resto = np.zeros(0, dtype=np.int16)

    @property
    def umbral(self) -> float:
        return max(self.energia_minima, self.ruido * self.factor_ruido)

    def procesar(self, muestras: np.ndarray) -> list[bytes]:
        """Añade audio int16 y devuelve las frases terminadas (bytes PCM int16)."""
        muestras = np.concatenate([self._resto, muestras.astype(np.int16, copy=False)])
        n = len(muestras) // self.muestras_ventana
        self._resto = muestras[n * self.muestras_ventana:]
        frases = []
        for i in range(n):
            ventana = muestras[i * self.muestras_ventana:(i + 1) * self.muestras_ventana]
            frase = self._procesar_ventana(ventana)
            if frase is not None:
                frases.append(frase)
        return frases

    def _procesar_ventana(self, ventana: np.ndarray) -> bytes | None:
        energia = float(np.sqrt(np.mean(ventana.astype(np.float32) ** 2)))
        es_voz = energia > self.umbral

        if not self.hablando:
            if es_voz:
                self._voz_seguida += 1
            else:
                self._voz_seguida = 0
                # El ruido de fondo solo se aprende en silencio (media móvil lenta)
                self.ruido = 0.95 * self.ruido + 0.05 * energia
            self._preroll.append(ventana)
            if self._voz_seguida >= 2:
                self.hablando = True
                self._frase = list(self._preroll)
                self._preroll.clear()
                self._ventanas_con_voz = self._voz_seguida
                self._silencio_seguido = 0
            return None

        self._frase.append(ventana)
        if es_voz:
            self._ventanas_con_voz += 1
            self._silencio_seguido = 0
        else:
            self._silencio_seguido += 1

        terminada = (self._silencio_seguido >= self.ventanas_pausa
                     or len(self._frase) >= self.ventanas_maximas)
        if not terminada:
            return None

        audio = np.concatenate(self._frase)
        valida = self._ventanas_con_voz >= self.ventanas_minimas
        self.hablando = False
        self._frase = []
        self._voz_seguida = 0
        self._ventanas_con_voz = 0
        self._silencio_seguido = 0
        return audio.tobytes() if valida else None
