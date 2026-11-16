"""
setup.py — Paquete ROS 2 ament_python 'tr_robot'
================================================
Sirve a la vez para:
  - colcon build  (en el robot, dentro de ~/ros2_ws/src/tr_robot)
  - pip install -e .   (en el portátil, para importar tr_brain en los demos)

Incluye dos subpaquetes: 'tr_brain' (la librería del cerebro, sin ROS) y
'tr_robot' (los nodos ROS finos que la usan).
"""
import os
from glob import glob
from setuptools import setup, find_packages

package_name = "tr_robot"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test", "test.*"]),
    data_files=[
        # Marcadores que ROS necesita para descubrir el paquete:
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        # Archivos de lanzamiento:
        (os.path.join("share", package_name, "launch"), glob("launch/*.py")),
    ],
    install_requires=[
        "setuptools",
        "google-generativeai>=0.5",
        "python-dotenv>=1.0",
    ],
    extras_require={
        # Nodo de voz (micrófono/altavoz). En el robot:  pip install -e ".[voice]"
        "voice": ["vosk>=0.3.45", "pyaudio>=0.2.13", "pyttsx3>=2.90", "numpy>=1.24"],
        # Cámara (visión): pip install -e ".[vision]"
        "vision": ["opencv-python>=4.8"],
    },
    zip_safe=True,
    maintainer="Jaime",
    maintainer_email="jaimekraftd@gmail.com",
    description="Cabeza robótica TR: cerebro cognitivo tr_brain + nodos ROS 2 con Gemini.",
    license="MIT",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "brain_node = tr_robot.brain_node:main",
            "voice_node = tr_robot.voice_node:main",
            "vision_node = tr_robot.vision_node:main",
            "person_recognition_node = tr_robot.person_recognition_node:main",
        ],
    },
)
