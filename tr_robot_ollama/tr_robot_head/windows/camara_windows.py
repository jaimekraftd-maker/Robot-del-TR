#!/usr/bin/env python3
"""
camara_windows.py — La webcam de Windows para TR en WSL (modo sin cabeza)
===========================================================================
WSL2 no ve las webcams de Windows (no hay /dev/video). Este script corre en el
Python de WINDOWS (py -3, solo necesita opencv-python): lee la webcam y sirve
siempre la imagen más reciente en http://127.0.0.1:8765/frame.jpg. Con la red
"mirrored" de WSL, el camera_node de Ubuntu la pide en localhost (parámetro url).

Lo arranca solo:   ros2 launch tr_robot_brain brain_launch.py sin_cabeza:=true
A mano, para probar la cámara (y abre la URL en el navegador):
    py -3 tr_robot_head\\windows\\camara_windows.py

Solo escucha en 127.0.0.1: nadie de fuera del PC puede ver la cámara. Si en
60 s nadie pide una imagen (ROS se cerró), suelta la webcam y termina.
"""
import argparse
import http.server
import sys
import threading
import time

import cv2

CALIDAD_JPEG = 90   # camera_node la recomprime a 70 antes de publicarla


class Webcam:
    """Lee la webcam en un hilo y guarda la imagen más reciente."""

    def __init__(self, indice: int, ancho: int, alto: int):
        self.indice, self.ancho, self.alto = indice, ancho, alto
        self._frame = None
        self._lock = threading.Lock()
        threading.Thread(target=self._bucle, daemon=True).start()

    def _abrir(self):
        cap = cv2.VideoCapture(self.indice, cv2.CAP_MSMF)
        if not cap.isOpened():
            cap.release()
            return None
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.ancho)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.alto)
        return cap

    def _bucle(self):
        cap, fallos = None, 0
        while True:
            if cap is None:
                cap = self._abrir()
                if cap is None:
                    print(f"📷 No se pudo abrir la webcam {self.indice} (¿la usa otra app? "
                          "¿permiso de cámara para apps de escritorio?). Reintento en 5 s.", flush=True)
                    time.sleep(5.0)
                    continue
                print(f"📷 Webcam {self.indice} abierta.", flush=True)
            ok, frame = cap.read()
            if ok:
                fallos = 0
                with self._lock:
                    self._frame = frame
                continue
            fallos += 1
            if fallos >= 30:   # se desconectó o la cogió otra app: reabrir
                cap.release()
                cap, fallos = None, 0
            time.sleep(0.1)

    def jpeg(self):
        with self._lock:
            frame = self._frame
        if frame is None:
            return None
        ok, datos = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, CALIDAD_JPEG])
        return datos.tobytes() if ok else None


def main():
    # La salida va a ros2 launch por una tubería: sin esto, Windows usa cp1252 y fallan los acentos
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--camara", type=int, default=0, help="Índice de la webcam (0 = la primera)")
    parser.add_argument("--puerto", type=int, default=8765)
    parser.add_argument("--ancho", type=int, default=640)
    parser.add_argument("--alto", type=int, default=480)
    parser.add_argument("--max-inactivo", type=float, default=60.0,
                        help="Segundos sin peticiones antes de cerrarse (0 = nunca)")
    args = parser.parse_args()

    webcam = Webcam(args.camara, args.ancho, args.alto)
    ultimo_pedido = [time.monotonic()]

    class Manejador(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.split("?")[0] != "/frame.jpg":
                self.send_error(404)
                return
            ultimo_pedido[0] = time.monotonic()
            datos = webcam.jpeg()
            if datos is None:
                self.send_error(503, "La webcam aún no tiene imagen")
                return
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(datos)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(datos)

        def log_message(self, *_):
            pass   # 5 peticiones por segundo: el log sería solo ruido

    try:
        servidor = http.server.ThreadingHTTPServer(("127.0.0.1", args.puerto), Manejador)
    except OSError as e:
        print(f"📷 El puerto {args.puerto} está ocupado (¿ya hay otro camara_windows.py?): {e}", flush=True)
        sys.exit(1)
    servidor.daemon_threads = True
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    print(f"📷 Sirviendo la webcam en http://127.0.0.1:{args.puerto}/frame.jpg", flush=True)

    try:
        while True:
            time.sleep(1.0)
            if args.max_inactivo > 0 and time.monotonic() - ultimo_pedido[0] > args.max_inactivo:
                print(f"📷 {args.max_inactivo:.0f} s sin peticiones: suelto la webcam y termino.", flush=True)
                break
    except KeyboardInterrupt:
        pass
    servidor.shutdown()


if __name__ == "__main__":
    main()
