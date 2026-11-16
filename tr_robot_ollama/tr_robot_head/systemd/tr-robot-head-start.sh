#!/usr/bin/env bash
# tr-robot-head-start — lo ejecuta el servicio systemd tr-robot-head.
# Espera a tener IP por Wi-Fi y lanza head_launch.py.
#
# ¿Por qué esperar? Si ROS 2 (Fast DDS) arranca antes de que haya red, solo
# escucha en la interfaz local y nunca llega a ver al portátil.
set -u

for _ in $(seq 1 90); do
    if hostname -I 2>/dev/null | grep -qE '([0-9]{1,3}\.){3}[0-9]{1,3}'; then
        break
    fi
    sleep 1
done
echo "tr-robot-head: IP = $(hostname -I 2>/dev/null)"

# Los setup.bash de ROS usan variables sin definir: desactivar 'set -u' al cargarlos
set +u
source /opt/ros/humble/setup.bash
source "${TR_WS:-$HOME/ros2_ws}/install/setup.bash"

# TR_HEAD_ARGS (en /etc/default/tr-robot-head) permite, p.ej., "servos:=false"
# shellcheck disable=SC2086
exec ros2 launch tr_robot_head head_launch.py ${TR_HEAD_ARGS:-}
