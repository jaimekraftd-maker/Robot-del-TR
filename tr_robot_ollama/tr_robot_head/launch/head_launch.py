"""
head_launch.py — Arranca la cabeza de TR (se ejecuta en la Pi Zero 2 W)
==========================================================================
    ros2 launch tr_robot_head head_launch.py
    ros2 launch tr_robot_head head_launch.py servos:=false leds:=false   # sin electrónica
    ros2 launch tr_robot_head head_launch.py alsa_device:=plughw:1,0     # altavoz USB concreto
    ros2 launch tr_robot_head head_launch.py single_process:=false       # un proceso por nodo (depurar)
    ros2 launch tr_robot_head head_launch.py camera_url:=http://localhost:8765/frame.jpg   # cámara por HTTP
    ros2 launch tr_robot_head head_launch.py pico_host:=192.168.1.50     # servos y LEDs en la Pico 2 W

Por defecto los 5 nodos van en UN solo proceso (head_all) para ahorrar RAM
en la Pi Zero 2 W. Normalmente lo lanza el servicio systemd tr-robot-head.
Para usar el micro, los altavoces y la webcam del PC en vez de la Pi: pc_launch.py.
"""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition, UnlessCondition
from launch.substitutions import LaunchConfiguration, PythonExpression
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    single = LaunchConfiguration("single_process")
    camera = LaunchConfiguration("camera")
    servos = LaunchConfiguration("servos")
    leds = LaunchConfiguration("leds")

    def por_separado(activado):
        """Condición: modo multiproceso Y el componente activado."""
        return IfCondition(PythonExpression([
            "'", single, "'.lower() not in ('true', '1') and '", activado, "'.lower() in ('true', '1')"
        ]))

    # Mismos parámetros en los dos modos. Sin 'name' en el Node, launch_ros los
    # aplica con comodín a todos los nodos del proceso; cada uno lee los suyos.
    parametros = {
        "device": ParameterValue(LaunchConfiguration("camera_device"), value_type=int),
        "url": ParameterValue(LaunchConfiguration("camera_url"), value_type=str),
        "width": 640, "height": 480, "fps": 5.0, "jpeg_quality": 70,
        "device_index": ParameterValue(LaunchConfiguration("mic_device"), value_type=int),
        "voice": "es", "speed": 150, "pitch": 50,
        "alsa_device": ParameterValue(LaunchConfiguration("alsa_device"), value_type=str),
        "end_margin": ParameterValue(LaunchConfiguration("speech_end_margin"), value_type=float),
        "pico_host": ParameterValue(LaunchConfiguration("pico_host"), value_type=str),
        "jaw_closed": ParameterValue(LaunchConfiguration("jaw_closed"), value_type=float),
        "jaw_open": ParameterValue(LaunchConfiguration("jaw_open"), value_type=float),
    }
    comun = {"package": "tr_robot_head", "output": "screen", "respawn": True, "respawn_delay": 3.0,
             "parameters": [parametros]}

    return LaunchDescription([
        DeclareLaunchArgument("single_process", default_value="True", description="Todos los nodos en un proceso"),
        DeclareLaunchArgument("camera", default_value="True", description="Publicar la cámara"),
        DeclareLaunchArgument("servos", default_value="True", description="Controlar los servos (PCA9685)"),
        DeclareLaunchArgument("leds", default_value="True", description="LEDs de estado por GPIO"),
        DeclareLaunchArgument("camera_device", default_value="0", description="Índice de /dev/videoN"),
        DeclareLaunchArgument("camera_url", default_value="", description="URL de un JPEG en vez de /dev/videoN (webcam de Windows)"),
        DeclareLaunchArgument("mic_device", default_value="-1", description="Índice PyAudio del micro (-1 = por defecto)"),
        DeclareLaunchArgument("alsa_device", default_value="", description="Dispositivo ALSA del altavoz (vacío = por defecto)"),
        DeclareLaunchArgument("speech_end_margin", default_value="0.3", description="Segundos que TR sigue sin escuchar tras terminar una frase"),
        DeclareLaunchArgument("pico_host", default_value="", description="IP de la Pico 2 W (vacío = hardware local o TR_PICO_HOST)"),
        DeclareLaunchArgument("jaw_closed", default_value="90.0", description="Ángulo del servo con la boca cerrada"),
        DeclareLaunchArgument("jaw_open", default_value="60.0", description="Ángulo del servo con la boca abierta"),

        # --- Modo por defecto: un solo proceso ---
        Node(executable="head_all", condition=IfCondition(single), **{
            **comun,
            "parameters": [{**parametros,
                            "enable_camera": ParameterValue(camera, value_type=bool),
                            "enable_servos": ParameterValue(servos, value_type=bool),
                            "enable_leds": ParameterValue(leds, value_type=bool)}],
        }),

        # --- Modo depuración: un proceso por nodo ---
        Node(executable="audio_capture_node", condition=UnlessCondition(single), **comun),
        Node(executable="tts_node", condition=UnlessCondition(single), **comun),
        Node(executable="camera_node", condition=por_separado(camera), **comun),
        Node(executable="servo_node", condition=por_separado(servos), **comun),
        Node(executable="led_node", condition=por_separado(leds), **comun),
    ])
