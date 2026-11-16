#!/usr/bin/env python3
"""
TR Robot - Vision Node (Gemini)
Captura imágenes de la cámara USB y genera descripciones con Gemini Vision.
"""

import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from sensor_msgs.msg import Image
from cv_bridge import CvBridge

import cv2
import threading
import time
import os
import google.generativeai as genai
from PIL import Image as PILImage
import io

genai.configure(api_key=os.environ.get("GEMINI_API_KEY", ""))


class VisionNode(Node):
    def __init__(self):
        super().__init__("vision_node")
        self.get_logger().info("👁️ TR Vision Node (Gemini) iniciado")

        self.bridge = CvBridge()
        self.vision_model = genai.GenerativeModel(
            model_name="gemini-1.5-flash",  # Flash soporta visión y es gratis
            generation_config={"max_output_tokens": 150, "temperature": 0.3},
        )

        # Cámara USB
        self.cap = cv2.VideoCapture(0)
        if self.cap.isOpened():
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            self.get_logger().info("✅ Cámara USB abierta")
        else:
            self.get_logger().error("❌ No se pudo abrir la cámara USB")

        # Publicadores
        self.pub_description = self.create_publisher(
            String, "/tr/vision_description", 10
        )
        self.pub_image = self.create_publisher(Image, "/tr/camera/image_raw", 10)

        # Suscriptor: descripción bajo demanda
        self.sub_request = self.create_subscription(
            String, "/tr/vision_request", self._on_vision_request, 10
        )

        self._last_describe_time = 0
        self._describe_interval = 15.0

        # Timers
        self.create_timer(0.1, self._capture_frame)       # Captura continua 10fps
        self.create_timer(self._describe_interval, self._describe_scene)

        self.get_logger().info("✅ Vision Node listo")

    def _capture_frame(self):
        if not self.cap.isOpened():
            return
        ret, frame = self.cap.read()
        if ret:
            try:
                msg = self.bridge.cv2_to_imgmsg(frame, encoding="bgr8")
                self.pub_image.publish(msg)
            except Exception:
                pass

    def _describe_scene(self):
        threading.Thread(target=self._run_description, daemon=True).start()

    def _on_vision_request(self, msg: String):
        threading.Thread(target=self._run_description, daemon=True).start()

    def _run_description(self):
        if not self.cap.isOpened():
            return

        ret, frame = self.cap.read()
        if not ret:
            return

        try:
            # Convertir frame OpenCV a PIL Image (formato que acepta Gemini)
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            pil_img = PILImage.fromarray(rgb)

            # Comprimir para ahorrar tokens
            buf = io.BytesIO()
            pil_img.save(buf, format="JPEG", quality=70)
            buf.seek(0)
            pil_img_compressed = PILImage.open(buf)

            response = self.vision_model.generate_content([
                pil_img_compressed,
                ("Describe brevemente (1-2 frases) qué ves desde la perspectiva "
                 "de un robot en una habitación. Menciona personas, objetos relevantes "
                 "y el entorno general. Responde en español.")
            ])

            description = response.text.strip()
            self.get_logger().info(f"👁️ Veo: {description}")

            msg = String()
            msg.data = description
            self.pub_description.publish(msg)

        except Exception as e:
            self.get_logger().warning(f"Error en visión Gemini: {e}")

    def destroy_node(self):
        if self.cap.isOpened():
            self.cap.release()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = VisionNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
