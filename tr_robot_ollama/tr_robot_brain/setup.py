"""
setup.py — Paquete ROS 2 ament_python 'tr_robot_brain'
=======================================================
Cerebro de TR, para el portátil: STT, Claude (con Ollama de respaldo), visión, caras, memoria,
emociones y etapas de desarrollo.
"""
import os
from glob import glob

from setuptools import find_packages, setup

package_name = "tr_robot_brain"

setup(
    name=package_name,
    version="0.2.0",
    packages=find_packages(exclude=["test", "test.*"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        (os.path.join("share", package_name, "launch"), glob("launch/*.py")),
        (os.path.join("share", package_name, "config"), glob("config/*.json")),
    ],
    install_requires=["setuptools", "requests>=2.25", "numpy"],
    zip_safe=True,
    maintainer="Jaime",
    maintainer_email="jaimekraftd@gmail.com",
    description="Cerebro de TR (portátil): Claude/Ollama, STT, visión, caras, memoria y desarrollo.",
    license="MIT",
    entry_points={
        "console_scripts": [
            "stt_node = tr_robot_brain.stt_node:main",
            "brain_node = tr_robot_brain.brain_node:main",
            "vision_node = tr_robot_brain.vision_node:main",
            "person_recognition_node = tr_robot_brain.person_recognition_node:main",
        ],
    },
)
