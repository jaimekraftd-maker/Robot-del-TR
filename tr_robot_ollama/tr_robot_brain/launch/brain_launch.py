"""
brain_launch.py — Arranca el cerebro de TR (se ejecuta en el PORTÁTIL)
=========================================================================
    ros2 launch tr_robot_brain brain_launch.py
    ros2 launch tr_robot_brain brain_launch.py stt_engine:=vosk      # 100% offline
    ros2 launch tr_robot_brain brain_launch.py vision:=false persons:=false
    ros2 launch tr_robot_brain brain_launch.py sin_cabeza:=true      # sin la Pi: micro, altavoces y webcam del PC

El cerebro y la visión usan Claude con la sesión de Claude Code de este portátil
(claude auth login); si no hay sesión o internet, Ollama (localhost:11434):
gemma2:2b para pensar y moondream para ver.

sin_cabeza:=true añade tr_robot_head/pc_launch.py: los nodos de la cabeza corren
aquí mismo (hay que compilar también tr_robot_head, ver install_sin_cabeza.sh).
"""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument("vision", default_value="true", description="Describir la escena (Claude cada 60 s, o moondream)"),
        DeclareLaunchArgument("persons", default_value="true", description="Reconocimiento facial"),
        DeclareLaunchArgument("stt_engine", default_value="auto", description="auto | vosk | google"),
        DeclareLaunchArgument("sin_cabeza", default_value="false",
                              description="Sin la Pi: oír, hablar y ver con el micro, los altavoces y la webcam del PC"),

        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(PathJoinSubstitution(
                [FindPackageShare("tr_robot_head"), "launch", "pc_launch.py"])),
            condition=IfCondition(LaunchConfiguration("sin_cabeza"))),

        Node(package="tr_robot_brain", executable="stt_node", name="stt_node", output="screen",
             parameters=[{"stt_engine": ParameterValue(LaunchConfiguration("stt_engine"), value_type=str),
                          "energy_threshold": 300.0, "pause_threshold": 0.8}]),
        Node(package="tr_robot_brain", executable="brain_node", name="brain_node", output="screen",
             parameters=[{"chat_timeout": 30.0}]),
        Node(package="tr_robot_brain", executable="vision_node", name="vision_node", output="screen",
             condition=IfCondition(LaunchConfiguration("vision"))),
        Node(package="tr_robot_brain", executable="person_recognition_node",
             name="person_recognition_node", output="screen",
             condition=IfCondition(LaunchConfiguration("persons"))),
    ])
