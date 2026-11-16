"""
pc_launch.py — La cabeza de TR en el PC (modo sin cabeza)
============================================================
Sin la Pi Zero 2 W, TR oye, habla y ve con el micrófono, los altavoces y la
webcam del propio PC. Son los mismos nodos de head_launch.py, sin servos ni LEDs
salvo que haya una Pico 2 W en la cabeza (variable TR_PICO_HOST o pico_host):

    ros2 launch tr_robot_brain brain_launch.py sin_cabeza:=true   # TR entero en el PC
    ros2 launch tr_robot_head pc_launch.py                        # solo la cabeza

- Audio: PyAudio y espeak-ng usan el sonido por defecto. En WSL2 es el
  PulseAudio de WSLg, que lleva al micro y a los altavoces de Windows.
- Cámara: en Linux nativo, /dev/video0. En WSL2 no hay /dev/video: el Python
  de Windows lee la webcam (windows/camara_windows.py, lanzado por interop) y
  camera_node le pide la última imagen en localhost.

- Cráneo con Pico: conecta la cámara y el micro del cráneo al PC por USB y elige
  la cámara con webcam:=N. La Pico mueve los servos y los LEDs por Wi-Fi.

Los argumentos de head_launch.py también valen aquí (mic_device, alsa_device...).
"""
import os
import shutil
import subprocess

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (DeclareLaunchArgument, ExecuteProcess, IncludeLaunchDescription,
                            LogInfo, OpaqueFunction)
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import EnvironmentVariable, LaunchConfiguration

# Topes de la mandíbula del cráneo v5 (ver hardware/tr_servo_skull_v5)
JAW_CERRADA, JAW_ABIERTA = "60.0", "85.0"


def _en_wsl() -> bool:
    try:
        with open("/proc/version") as f:
            return "microsoft" in f.read().lower()
    except OSError:
        return False


def _cabeza_en_el_pc(context):
    compartido = get_package_share_directory("tr_robot_head")
    argumentos = {"servos": "false", "leds": "false"}
    pico = LaunchConfiguration("pico_host").perform(context).strip()
    if pico:
        argumentos = {"servos": "true", "leds": "true", "pico_host": pico,
                      "jaw_closed": JAW_CERRADA, "jaw_open": JAW_ABIERTA}
    argumentos["speech_end_margin"] = LaunchConfiguration("speech_end_margin").perform(context)
    acciones = []
    if _en_wsl():
        if shutil.which("py.exe") is None:
            acciones.append(LogInfo(msg="📷 No encuentro py.exe (Python de Windows): TR oirá y hablará, "
                                        "pero sin cámara. Instala Python en Windows y opencv-python."))
        else:
            puerto = LaunchConfiguration("camera_port").perform(context)
            # realpath: con --symlink-install es un enlace de Linux que Windows no sabe seguir
            script = subprocess.run(
                ["wslpath", "-w", os.path.realpath(os.path.join(compartido, "windows", "camara_windows.py"))],
                capture_output=True, text=True, check=True).stdout.strip()
            acciones.append(ExecuteProcess(
                name="camara_windows", output="screen",
                cmd=["py.exe", "-3", script, "--puerto", puerto,
                     "--camara", LaunchConfiguration("webcam").perform(context)]))
            argumentos["camera_url"] = f"http://localhost:{puerto}/frame.jpg"
    acciones.append(IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(compartido, "launch", "head_launch.py")),
        launch_arguments=argumentos.items()))
    return acciones


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument("webcam", default_value="0", description="WSL: índice de la webcam de Windows"),
        DeclareLaunchArgument("camera_port", default_value="8765", description="WSL: puerto local de camara_windows.py"),
        # WSLg da el sonido por terminado antes de tiempo, y en un PC el micro está junto al altavoz
        DeclareLaunchArgument("speech_end_margin", default_value="1.0", description="Segundos que TR sigue sin escuchar tras terminar una frase"),
        DeclareLaunchArgument("pico_host", default_value=EnvironmentVariable("TR_PICO_HOST", default_value=""),
                              description="IP de la Pico 2 W de la cabeza (vacío = sin servos ni LEDs)"),
        OpaqueFunction(function=_cabeza_en_el_pc),
    ])
