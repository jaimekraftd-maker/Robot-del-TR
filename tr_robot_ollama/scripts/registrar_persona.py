#!/usr/bin/env python3
"""
registrar_persona.py — Utilidad CLI para registrar una nueva persona en TR
=============================================================================
Publica en /tr/register_person con el formato "nombre:descripcion". El
person_recognition_node (en el portátil) debe estar corriendo y la cámara de
la cabeza viendo a la persona en ese instante; la foto se guarda en el
portátil, en ~/.tr_robot_ollama/persons/<nombre>/.

Uso (en cualquiera de las dos máquinas, con ROS_DOMAIN_ID=42):
    python3 scripts/registrar_persona.py
"""
import sys

import rclpy
from rclpy.node import Node
from std_msgs.msg import String


class RegistrarPersonaNode(Node):
    """Nodo CLI de un solo uso: publica una orden de registro y termina."""

    def __init__(self, nombre: str, descripcion: str):
        super().__init__("registrar_persona_cli")
        self._pub = self.create_publisher(String, "/tr/register_person", 10)
        self._nombre = nombre
        self._descripcion = descripcion
        self._enviado = False
        # Pequeño margen para que el publisher se descubra con los subscribers existentes
        self.create_timer(1.0, self._enviar)

    def _enviar(self):
        if self._enviado:
            return
        msg = String()
        msg.data = f"{self._nombre}:{self._descripcion}"
        self._pub.publish(msg)
        self._enviado = True
        self.get_logger().info(f"🧑 Petición de registro enviada para '{self._nombre}'.")


def main():
    print("=== Registrar nueva persona en TR ===")
    nombre = input("Nombre: ").strip()
    if not nombre:
        print("❌ El nombre no puede estar vacío.")
        sys.exit(1)
    descripcion = input("Descripción breve (opcional): ").strip()

    print("📸 Asegúrate de que la persona esté mirando a la cámara ahora mismo...")

    rclpy.init()
    node = RegistrarPersonaNode(nombre, descripcion)
    try:
        rclpy.spin_once(node, timeout_sec=1.5)
        rclpy.spin_once(node, timeout_sec=1.5)
    finally:
        node.destroy_node()
        rclpy.shutdown()

    print(f"✅ Solicitud de registro enviada para '{nombre}'.")
    print(f"   Comprueba ~/.tr_robot_ollama/persons/{nombre}/ para confirmar que se guardó la foto.")


if __name__ == "__main__":
    main()
