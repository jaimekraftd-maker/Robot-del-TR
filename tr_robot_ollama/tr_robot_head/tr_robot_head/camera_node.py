#!/usr/bin/env python3
"""
camera_node.py — Cámara de la cabeza (Pi Zero 2 W)
=====================================================
Captura la cámara USB a 640x480 y publica JPEG (calidad 70) a 5 fps en
/tr/camera/image/compressed. NUNCA se publican imágenes sin comprimir: una
imagen 640x480 en crudo son 900 KB; en JPEG, unos 30 KB. Por Wi-Fi a 5 fps
eso es la diferencia entre 36 Mbit/s (imposible) y 1,2 Mbit/s.

QoS "sensor data" (best effort): si se pierde una imagen, no se reenvía;
la siguiente llega en 200 ms. Los suscriptores deben usar el mismo QoS.

Modo sin cabeza en WSL: WSL no ve la webcam de Windows, así que la lee
windows/camara_windows.py y este nodo le pide la última imagen por HTTP
(parámetro url, p. ej. http://localhost:8765/frame.jpg).
"""
import array
import threading
import time
import urllib.request

import cv2
import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import CompressedImage


class CamaraHttp:
    """Misma interfaz que cv2.VideoCapture, pero cada read() pide por HTTP el
    JPEG más reciente (camara_windows.py). Sin stream: nunca acumula retraso."""

    def __init__(self, url: str):
        self.url = url

    def isOpened(self) -> bool:
        return True

    def read(self):
        try:
            with urllib.request.urlopen(self.url, timeout=2.0) as respuesta:
                datos = np.frombuffer(respuesta.read(), dtype=np.uint8)
        except Exception:
            return False, None
        frame = cv2.imdecode(datos, cv2.IMREAD_COLOR)
        return frame is not None, frame

    def release(self):
        pass


class CameraNode(Node):
    def __init__(self):
        super().__init__("camera_node")
        self.declare_parameter("device", 0)
        self.declare_parameter("url", "")   # vacío = /dev/videoN; "http://..." = webcam de Windows
        self.declare_parameter("width", 640)
        self.declare_parameter("height", 480)
        self.declare_parameter("fps", 5.0)
        self.declare_parameter("jpeg_quality", 70)
        self.get_logger().info("📷 Iniciando camera_node...")

        self.device = self.get_parameter("device").value
        self.url = self.get_parameter("url").value
        self.width = self.get_parameter("width").value
        self.height = self.get_parameter("height").value
        self.fps = float(self.get_parameter("fps").value)
        self.encode_params = [cv2.IMWRITE_JPEG_QUALITY, int(self.get_parameter("jpeg_quality").value)]

        self.pub = self.create_publisher(CompressedImage, "/tr/camera/image/compressed",
                                         qos_profile_sensor_data)
        self.cap = None
        self._abrir_camara()
        threading.Thread(target=self._bucle_captura, daemon=True).start()

    def _abrir_camara(self) -> bool:
        if self.url:
            self.cap = CamaraHttp(self.url)
            self.get_logger().info(f"📷 Cámara por HTTP: {self.url}")
            return True
        try:
            self.cap = cv2.VideoCapture(self.device, cv2.CAP_V4L2)
            # MJPG: la cámara comprime por hardware y el USB va mucho más desahogado
            self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            self.cap.set(cv2.CAP_PROP_FPS, self.fps)
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # siempre la imagen más reciente
            if self.cap.isOpened():
                self.get_logger().info(f"📷 Cámara /dev/video{self.device} abierta.")
                return True
            self.get_logger().error(f"📷 No se pudo abrir la cámara /dev/video{self.device}.")
        except Exception as e:
            self.get_logger().error(f"📷 Error abriendo la cámara: {e}")
        return False

    def _bucle_captura(self):
        periodo = 1.0 / self.fps
        fallos = 0
        while rclpy.ok():
            inicio = time.monotonic()
            if self.cap is None or not self.cap.isOpened():
                time.sleep(2.0)
                self._abrir_camara()
                continue

            ok, frame = self.cap.read()
            if not ok:
                fallos += 1
                if fallos % 10 == 1:
                    self.get_logger().error("📷 Error leyendo de la cámara (¿desconectada?).")
                if fallos >= 30:
                    self.cap.release()  # fuerza reabrir: la cámara pudo reconectarse
                    fallos = 0
                time.sleep(0.2)
                continue
            fallos = 0

            try:
                if frame.shape[1] != self.width or frame.shape[0] != self.height:
                    frame = cv2.resize(frame, (self.width, self.height))
                ok, jpeg = cv2.imencode(".jpg", frame, self.encode_params)
                if ok:
                    msg = CompressedImage()
                    msg.header.stamp = self.get_clock().now().to_msg()
                    msg.header.frame_id = "tr_camera"
                    msg.format = "jpeg"
                    msg.data = array.array("B", jpeg.tobytes())
                    self.pub.publish(msg)
            except Exception as e:
                self.get_logger().error(f"📷 Error comprimiendo/publicando la imagen: {e}")

            time.sleep(max(0.0, periodo - (time.monotonic() - inicio)))

    def destroy_node(self):
        if self.cap is not None:
            self.cap.release()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = CameraNode()
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
