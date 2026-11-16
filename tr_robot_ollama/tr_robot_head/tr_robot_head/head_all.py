#!/usr/bin/env python3
"""
head_all.py — Todos los nodos de la cabeza en UN solo proceso
================================================================
En la Pi Zero 2 W (512 MB) cada proceso Python con rclpy ocupa ~35-60 MB:
cinco procesos separados rondan 250 MB. Juntos en un proceso comparten el
intérprete, rclpy, numpy y OpenCV, y se quedan en unos 80-100 MB.

Los nodos siguen siendo nodos ROS independientes (mismos nombres, topics y
parámetros); solo comparten proceso. Las partes pesadas (captura de cámara,
micrófono, voz) ya corren en sus propios hilos, así que basta un executor
de un solo hilo para los callbacks.

Parámetros propios (nodo "tr_head"): enable_camera, enable_servos, enable_leds.
"""
import rclpy
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node

from tr_robot_head.audio_capture_node import AudioCaptureNode
from tr_robot_head.camera_node import CameraNode
from tr_robot_head.led_node import LedNode
from tr_robot_head.servo_node import ServoNode
from tr_robot_head.tts_node import TtsNode


def main(args=None):
    rclpy.init(args=args)
    gestor = Node("tr_head")
    for nombre in ("enable_camera", "enable_servos", "enable_leds"):
        gestor.declare_parameter(nombre, True)
    activado = lambda nombre: bool(gestor.get_parameter(nombre).value)  # noqa: E731

    clases = [AudioCaptureNode, TtsNode]
    if activado("enable_camera"):
        clases.append(CameraNode)
    if activado("enable_servos"):
        clases.append(ServoNode)
    if activado("enable_leds"):
        clases.append(LedNode)

    executor = SingleThreadedExecutor()
    nodos = [gestor]
    for clase in clases:
        try:
            nodos.append(clase())
        except Exception as e:
            # Un fallo de hardware en un nodo no debe tumbar al resto de la cabeza
            gestor.get_logger().error(f"🤖 No se pudo iniciar {clase.__name__}: {e}")
    for nodo in nodos:
        executor.add_node(nodo)
    gestor.get_logger().info(
        f"🤖 Cabeza en un solo proceso: {', '.join(n.get_name() for n in nodos[1:])}"
    )

    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        for nodo in nodos:
            nodo.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
