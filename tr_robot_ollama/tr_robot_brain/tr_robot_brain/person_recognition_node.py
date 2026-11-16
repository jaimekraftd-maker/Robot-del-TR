#!/usr/bin/env python3
"""
person_recognition_node.py — TR reconoce a las personas (se ejecuta en el PORTÁTIL)
=====================================================================================
Carga fotos de referencia de ~/.tr_robot_ollama/persons/<nombre>/foto.jpg (y
descripcion.txt). Usa face_recognition (dlib) si está instalado; si no, una
comparación visual con características ORB de OpenCV.

Cada 5 s descomprime el último JPEG de /tr/camera/image/compressed y lo
compara con las personas conocidas. Si reconoce a alguien (confianza > 0.6)
publica un JSON en /tr/persons_detected. La primera vez que ve a alguien en la
sesión, avisa al cerebro por /tr/speech_in con una "percepción", para que sea
TR quien salude con su propia voz, edad y personalidad.

Registro: /tr/register_person con "nombre:descripcion" guarda la foto actual.
"""
import json
import threading
from pathlib import Path

import cv2
import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import CompressedImage
from std_msgs.msg import String

try:
    import face_recognition
except ImportError:
    face_recognition = None

PERSONS_DIR = Path.home() / ".tr_robot_ollama" / "persons"
COMPARE_INTERVAL_SEC = 5.0
CONFIDENCE_THRESHOLD = 0.6
ORB_BUENAS_PARA_CONFIANZA_TOTAL = 40


class PersonRecognitionNode(Node):
    """Reconoce caras conocidas y avisa al cerebro la primera vez que ve a alguien."""

    def __init__(self):
        super().__init__("person_recognition_node")
        self.get_logger().info("🧑 Iniciando person_recognition_node...")

        self._lock = threading.Lock()
        self._ultimo_jpeg: bytes | None = None
        self._personas: list[dict] = []
        self._vistos_en_sesion: set[str] = set()

        self._usar_face_recognition = face_recognition is not None
        if not self._usar_face_recognition:
            self.get_logger().warn("🧑 'face_recognition' no está instalado; uso comparación ORB.")
            self._orb = cv2.ORB_create(nfeatures=500)
            self._matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)

        self._cargar_personas()

        self.pub_persons = self.create_publisher(String, "/tr/persons_detected", 10)
        self.pub_speech_in = self.create_publisher(String, "/tr/speech_in", 10)
        self.create_subscription(CompressedImage, "/tr/camera/image/compressed",
                                 self._on_image, qos_profile_sensor_data)
        self.create_subscription(String, "/tr/register_person", self._on_register_person, 10)
        self.create_timer(COMPARE_INTERVAL_SEC, self._comparar)

        self.get_logger().info(f"🧑 Listo ({len(self._personas)} personas conocidas).")

    def _on_image(self, msg: CompressedImage):
        with self._lock:
            self._ultimo_jpeg = bytes(msg.data)

    def _frame_actual(self):
        """Descomprime el último JPEG solo cuando hace falta (ahorra CPU)."""
        with self._lock:
            jpeg = self._ultimo_jpeg
        if jpeg is None:
            return None
        return cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)

    # ------------------------------------------------------------------ #
    # Personas conocidas
    # ------------------------------------------------------------------ #
    def _cargar_personas(self):
        self._personas = []
        if not PERSONS_DIR.exists():
            return
        for carpeta in sorted(PERSONS_DIR.iterdir()):
            foto = carpeta / "foto.jpg"
            if not carpeta.is_dir() or not foto.exists():
                continue
            nombre = carpeta.name
            desc_path = carpeta / "descripcion.txt"
            persona = {
                "nombre": nombre,
                "descripcion": desc_path.read_text(encoding="utf-8").strip() if desc_path.exists() else "",
            }
            try:
                imagen = cv2.imread(str(foto))
                if imagen is None:
                    self.get_logger().error(f"🧑 No pude leer la foto de {nombre}.")
                    continue
                if self._usar_face_recognition:
                    encodings = face_recognition.face_encodings(cv2.cvtColor(imagen, cv2.COLOR_BGR2RGB))
                    if not encodings:
                        self.get_logger().error(f"🧑 No hay ninguna cara en la foto de {nombre}.")
                        continue
                    persona["encoding"] = encodings[0]
                else:
                    _, desc = self._orb.detectAndCompute(cv2.cvtColor(imagen, cv2.COLOR_BGR2GRAY), None)
                    if desc is None:
                        self.get_logger().error(f"🧑 Sin características ORB en la foto de {nombre}.")
                        continue
                    persona["orb"] = desc
                self._personas.append(persona)
                self.get_logger().info(f"🧑 Persona cargada: {nombre}")
            except Exception as e:
                self.get_logger().error(f"🧑 Error cargando a {nombre}: {e}")

    # ------------------------------------------------------------------ #
    # Comparación periódica
    # ------------------------------------------------------------------ #
    def _comparar(self):
        if not self._personas:
            return
        frame = self._frame_actual()
        if frame is None:
            return
        try:
            if self._usar_face_recognition:
                nombre, confianza = self._reconocer_face_recognition(frame)
            else:
                nombre, confianza = self._reconocer_orb(frame)
        except Exception as e:
            self.get_logger().error(f"🧑 Error comparando caras: {e}")
            return
        if nombre is None or confianza < CONFIDENCE_THRESHOLD:
            return

        self.get_logger().info(f"🧑 Reconocido: {nombre} (confianza {confianza:.2f})")
        msg = String()
        msg.data = json.dumps({"nombre": nombre, "confianza": round(confianza, 2)}, ensure_ascii=False)
        self.pub_persons.publish(msg)

        if nombre not in self._vistos_en_sesion:
            self._vistos_en_sesion.add(nombre)
            self._avisar_al_cerebro(nombre)

    def _reconocer_face_recognition(self, frame):
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        ubicaciones = face_recognition.face_locations(rgb)
        if not ubicaciones:
            return None, 0.0
        mejor, mejor_conf = None, 0.0
        conocidos = [p["encoding"] for p in self._personas]
        for encoding in face_recognition.face_encodings(rgb, ubicaciones):
            distancias = face_recognition.face_distance(conocidos, encoding)
            i = int(np.argmin(distancias))
            confianza = max(0.0, 1.0 - float(distancias[i]))
            if confianza > mejor_conf:
                mejor, mejor_conf = self._personas[i]["nombre"], confianza
        return mejor, mejor_conf

    def _reconocer_orb(self, frame):
        _, desc_frame = self._orb.detectAndCompute(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), None)
        if desc_frame is None:
            return None, 0.0
        mejor, mejor_conf = None, 0.0
        for persona in self._personas:
            try:
                coincidencias = self._matcher.match(desc_frame, persona["orb"])
            except cv2.error:
                continue
            buenas = sum(1 for m in coincidencias if m.distance < 60)
            confianza = min(1.0, buenas / ORB_BUENAS_PARA_CONFIANZA_TOTAL)
            if confianza > mejor_conf:
                mejor, mejor_conf = persona["nombre"], confianza
        return mejor, mejor_conf

    def _avisar_al_cerebro(self, nombre: str):
        persona = next((p for p in self._personas if p["nombre"] == nombre), {})
        texto = f"[percepción] Acabas de ver a {nombre} delante de ti."
        if persona.get("descripcion"):
            texto += f" Lo que sabes de esta persona: {persona['descripcion']}."
        texto += " Salúdale por su nombre."
        msg = String()
        msg.data = texto
        self.pub_speech_in.publish(msg)
        self.get_logger().info(f"🧑 Aviso de saludo enviado al cerebro: {nombre}.")

    # ------------------------------------------------------------------ #
    # Registro de personas nuevas
    # ------------------------------------------------------------------ #
    def _on_register_person(self, msg: String):
        nombre, _, descripcion = msg.data.partition(":")
        nombre, descripcion = nombre.strip(), descripcion.strip()
        if not nombre or "/" in nombre or "\\" in nombre or nombre.startswith("."):
            self.get_logger().error(
                "🧑 Nombre inválido en /tr/register_person (formato 'nombre:descripcion')."
            )
            return
        frame = self._frame_actual()
        if frame is None:
            self.get_logger().error(f"🧑 No hay imagen de la cámara para registrar a {nombre}.")
            return
        carpeta = PERSONS_DIR / nombre
        try:
            carpeta.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(carpeta / "foto.jpg"), frame)
            (carpeta / "descripcion.txt").write_text(descripcion, encoding="utf-8")
            self.get_logger().info(f"🧑 Persona registrada: {nombre} ({carpeta})")
        except Exception as e:
            self.get_logger().error(f"🧑 Error guardando a {nombre}: {e}")
            return
        self._cargar_personas()
        self._vistos_en_sesion.discard(nombre)


def main(args=None):
    rclpy.init(args=args)
    node = PersonRecognitionNode()
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
