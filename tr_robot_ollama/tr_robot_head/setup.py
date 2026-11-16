"""
setup.py — Paquete ROS 2 ament_python 'tr_robot_head'
======================================================
Nodos ligeros de la cabeza de TR, para la Raspberry Pi Zero 2 W.
"""
import os
from glob import glob

from setuptools import find_packages, setup

package_name = "tr_robot_head"

setup(
    name=package_name,
    version="0.2.0",
    packages=find_packages(exclude=["test", "test.*"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        (os.path.join("share", package_name, "launch"), glob("launch/*.py")),
        (os.path.join("share", package_name, "systemd"), glob("systemd/*")),
        # Corre en el Python de Windows, no en ROS (modo sin cabeza en WSL)
        (os.path.join("share", package_name, "windows"), glob("windows/*.py")),
        # Corre en la Pico 2 W (MicroPython), no en ROS
        (os.path.join("share", package_name, "pico"), glob("pico/*.py")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="Jaime",
    maintainer_email="jaimekraftd@gmail.com",
    description="Cabeza de TR (Pi Zero 2 W): cámara, micrófono, voz, servos y LEDs.",
    license="MIT",
    entry_points={
        "console_scripts": [
            "head_all = tr_robot_head.head_all:main",
            "camera_node = tr_robot_head.camera_node:main",
            "audio_capture_node = tr_robot_head.audio_capture_node:main",
            "tts_node = tr_robot_head.tts_node:main",
            "servo_node = tr_robot_head.servo_node:main",
            "led_node = tr_robot_head.led_node:main",
        ],
    },
)
