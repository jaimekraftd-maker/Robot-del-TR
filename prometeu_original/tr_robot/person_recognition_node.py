#!/usr/bin/env python3
"""
TR Robot - Person Recognition Node (Gemini)
Identifica personas por nombre usando Gemini Vision + memoria persistente.
"""

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

import cv2
import json
import os
import threading
import time
from pathlib import Path
import google.generativeai as genai
from PIL import Image as PILImage
import io

genai.configure(api_key=os.environ.get("GEMINI_API_KEY", ""))

PERSONS_DIR = Path(os.path.expanduser("~/.tr_robot/persons"))


class PersonRecognitionNode(Node):
    def __init__(self):
        super().__init__("person_recognition_node")
        self.get_logger().info("🧑 TR Person Recognition Node (Gemini) iniciado")

        self.vision_model = genai.GenerativeModel(
            model_name="gemini-1.5-flash",
            generation_config={"max_output_tokens": 400, "temperature": 0.2},
        )

        self.known_persons = self._load_known_persons()
        self.get_logger().info(
            f"📷 Personas conocidas: {list(self.known_persons.keys())}"
        )

        # Cámara
        self.cap = cv2.VideoCapture(0)
        if self.cap.isOpened():
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

        # Publicadores
        self.pub_persons = self.create_publisher(String, "/tr/persons_detected", 10)
        self.pub_greeting = self.create_publisher(String, "/tr/speech_in", 10)

        # Suscriptores
        self.sub_identify = self.create_subscription(
            String, "/tr/identify_request", self._on_identify_request, 10
        )
        self.sub_register = self.create_subscription(
            String, "/tr/register_person", self._on_register_person, 10
        )

        self._greeted_this_session: set = set()
        self._last_identify_time = 0
        self._identify_cooldown = 8.0

        self.create_timer(5.0, self._periodic_identify)

        self.get_logger().info("✅ Person Recognition Node listo")

    # ── Carga de personas ────────────────────────────────────────────────────

    def _load_known_persons(self) -> dict:
        PERSONS_DIR.mkdir(parents=True, exist_ok=True)
        persons = {}
        for person_dir in PERSONS_DIR.iterdir():
            if not person_dir.is_dir():
                continue
            name = person_dir.name
            photo_path = person_dir / "foto.jpg"
            desc_path = person_dir / "descripcion.txt"
            persons[name] = {
                "pil_image": None,
                "description": "",
            }
            if photo_path.exists():
                persons[name]["pil_image"] = PILImage.open(str(photo_path)).copy()
            if desc_path.exists():
                persons[name]["description"] = desc_path.read_text(encoding="utf-8").strip()
        return persons

    # ── Identificación ───────────────────────────────────────────────────────

    def _periodic_identify(self):
        if time.time() - self._last_identify_time < self._identify_cooldown:
            return
        threading.Thread(target=self._run_identification, daemon=True).start()

    def _on_identify_request(self, msg: String):
        threading.Thread(target=self._run_identification, daemon=True).start()

    def _run_identification(self):
        if not self.cap.isOpened():
            return
        self._last_identify_time = time.time()

        ret, frame = self.cap.read()
        if not ret:
            return

        try:
            detected = self._identify_with_gemini(frame)

            if detected:
                self.get_logger().info(f"🧑 Detectados: {detected}")

                msg = String()
                msg.data = json.dumps(detected, ensure_ascii=False)
                self.pub_persons.publish(msg)

                for person in detected:
                    name = person.get("name")
                    confidence = person.get("confidence", "low")
                    if (
                        name
                        and name != "desconocido"
                        and confidence in ("high", "medium")
                        and name not in self._greeted_this_session
                    ):
                        self._greeted_this_session.add(name)
                        greeting = String()
                        greeting.data = f"He visto a {name} entrando"
                        self.pub_greeting.publish(greeting)

        except Exception as e:
            self.get_logger().warning(f"Error en identificación: {e}")

    def _identify_with_gemini(self, frame) -> list:
        """Usa Gemini Vision para identificar personas."""
        # Frame actual como PIL
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        current_pil = PILImage.fromarray(rgb)

        # Construir contenido: imagen actual + fotos de referencia
        content = [
            current_pil,
            "Esta es la imagen actual de la cámara del robot.\n"
        ]

        if self.known_persons:
            content.append("Fotos de referencia de personas conocidas:\n")
            for name, data in self.known_persons.items():
                if data["pil_image"]:
                    content.append(data["pil_image"])
                    desc = data["description"] or "sin descripción adicional"
                    content.append(f"Persona conocida: {name} — {desc}\n")

        known_names = list(self.known_persons.keys())
        content.append(
            f"""Analiza la imagen actual. Identifica todas las personas visibles.
Personas conocidas en la base de datos: {known_names}

Para cada persona visible responde con un JSON array:
[{{"name": "nombre o 'desconocido'", "confidence": "high/medium/low", "physical_description": "descripción breve", "position": "izquierda/centro/derecha/fondo"}}]

Si no hay personas, responde [].
Responde SOLO con el JSON array, sin texto adicional."""
        )

        response = self.vision_model.generate_content(content)
        raw = response.text.strip().replace("```json", "").replace("```", "").strip()
        return json.loads(raw)

    # ── Registro ─────────────────────────────────────────────────────────────

    def _on_register_person(self, msg: String):
        parts = msg.data.split(":", 1)
        name = parts[0].strip()
        description = parts[1].strip() if len(parts) > 1 else ""
        if name:
            threading.Thread(
                target=self._capture_and_save_person,
                args=(name, description),
                daemon=True,
            ).start()

    def _capture_and_save_person(self, name: str, description: str):
        if not self.cap.isOpened():
            return
        ret, frame = self.cap.read()
        if not ret:
            return

        person_dir = PERSONS_DIR / name
        person_dir.mkdir(parents=True, exist_ok=True)
        photo_path = person_dir / "foto.jpg"
        cv2.imwrite(str(photo_path), frame)

        if description:
            (person_dir / "descripcion.txt").write_text(description, encoding="utf-8")

        pil_img = PILImage.open(str(photo_path)).copy()
        self.known_persons[name] = {"pil_image": pil_img, "description": description}

        self.get_logger().info(f"✅ Registrado: {name}")

        notification = String()
        notification.data = f"He guardado la foto de {name}. Ahora te reconoceré cuando te vea."
        self.pub_greeting.publish(notification)

    def destroy_node(self):
        if self.cap.isOpened():
            self.cap.release()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = PersonRecognitionNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
