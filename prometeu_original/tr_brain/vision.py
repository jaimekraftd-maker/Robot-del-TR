"""
tr_brain.vision — Cámara (caras locales + descripción de escena)
================================================================
Capa de visión framework-agnóstica (sin ROS), para el demo y reutilizable.

- Detección de caras LOCAL con OpenCV (gratis), en un hilo continuo → avisa
  cuando aparece/desaparece alguien.
- La descripción de la escena con Gemini Vision NO se hace en bucle (gastaría
  cuota): se pide BAJO DEMANDA con frame_jpeg() (p. ej. el comando /mira).

OpenCV se importa de forma perezosa; si no está o no hay cámara, la visión
queda desactivada (disponible=False) y el resto del robot sigue funcionando.
"""
import time
import threading
import logging
from typing import Callable, Optional

from . import config

log = logging.getLogger("tr_brain.vision")


class Vision(threading.Thread):
    def __init__(self, al_cambiar_presencia: Callable[[bool], None] = None, indice: int = None):
        super().__init__(daemon=True, name="VisionThread")
        self.al_cambiar_presencia = al_cambiar_presencia or (lambda hay: None)
        self.indice = config.INDICE_CAMARA if indice is None else indice
        self._corriendo = False
        self._cap = None
        self._cv2 = None
        self._detector = None
        self._ultimo_frame = None
        self._lock = threading.Lock()
        self.disponible = self._preparar()

    def _preparar(self) -> bool:
        if not config.USAR_CAMARA:
            return False
        try:
            import cv2
            self._cv2 = cv2
            self._cap = cv2.VideoCapture(self.indice)
            if not self._cap.isOpened():
                log.warning("No se pudo abrir la cámara.")
                return False
            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, config.VISION_ANCHO)
            self._detector = cv2.CascadeClassifier(
                cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
            return True
        except Exception as e:
            log.warning(f"Visión no disponible ({e}); instala opencv-python para usar la cámara.")
            return False

    def iniciar(self):
        if not self.disponible:
            return
        self._corriendo = True
        self.start()

    def run(self):
        cv2 = self._cv2
        habia_alguien = False
        log.info("👁️ Cámara iniciada.")
        while self._corriendo:
            ok, frame = self._cap.read()
            if not ok:
                time.sleep(0.3)
                continue
            with self._lock:
                self._ultimo_frame = frame
            gris = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            caras = self._detector.detectMultiScale(gris, 1.2, 5, minSize=(60, 60))
            hay = len(caras) > 0
            if hay != habia_alguien:
                habia_alguien = hay
                try:
                    self.al_cambiar_presencia(hay)
                except Exception:
                    pass
            time.sleep(0.15)
        if self._cap:
            self._cap.release()

    def frame_jpeg(self, ancho: int = None) -> Optional[bytes]:
        """Último frame como JPEG (para enviarlo a Gemini Vision). None si no hay."""
        if not self.disponible:
            return None
        with self._lock:
            frame = None if self._ultimo_frame is None else self._ultimo_frame.copy()
        if frame is None:
            return None
        cv2 = self._cv2
        if ancho:
            h, w = frame.shape[:2]
            frame = cv2.resize(frame, (ancho, int(h * ancho / w)))
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
        return buf.tobytes() if ok else None

    def detener(self):
        self._corriendo = False
