#!/usr/bin/env python3
"""
tr_launch.py — Arranca TODO el robot TR con un solo comando
===========================================================
    ros2 launch tr_robot tr_launch.py                 # robot completo
    ros2 launch tr_robot tr_launch.py vision:=false   # sin cámara (solo voz)

Nodos:
  - brain_node                : cerebro cognitivo (memoria, aprendizaje, ...)
  - voice_node                : oído (Vosk STT) + voz (TTS)
  - vision_node               : describe la escena con Gemini Vision   (opcional)
  - person_recognition_node   : identifica personas con Gemini Vision  (opcional)
"""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    usar_vision = LaunchConfiguration("vision")

    return LaunchDescription([
        DeclareLaunchArgument(
            "vision", default_value="true",
            description="Arrancar visión y reconocimiento de personas (requiere cámara).",
        ),

        # --- Núcleo: siempre ---
        Node(package="tr_robot", executable="brain_node",
             name="brain_node", output="screen", emulate_tty=True),
        Node(package="tr_robot", executable="voice_node",
             name="voice_node", output="screen", emulate_tty=True),

        # --- Visión: opcional (vision:=false para desactivar) ---
        Node(package="tr_robot", executable="vision_node",
             name="vision_node", output="screen", emulate_tty=True,
             condition=IfCondition(usar_vision)),
        Node(package="tr_robot", executable="person_recognition_node",
             name="person_recognition_node", output="screen", emulate_tty=True,
             condition=IfCondition(usar_vision)),
    ])
