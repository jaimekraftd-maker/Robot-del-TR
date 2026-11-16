#!/usr/bin/env bash
# install_head.sh — Instalación LIGERA para la cabeza de TR (Raspberry Pi Zero 2 W)
# ==================================================================================
# Para Ubuntu 22.04 Server arm64. Instala ROS 2 Humble ros-base (si falta), las
# dependencias de los nodos de la cabeza, compila tr_robot_head y deja el
# servicio systemd listo para arrancar solo al encender.
#
# Estructura esperada:  ~/ros2_ws/src/tr_robot_ollama/scripts/install_head.sh
# (o define COLCON_WS=/ruta/al/workspace antes de ejecutarlo)
#
# Uso:
#   chmod +x scripts/install_head.sh
#   ./scripts/install_head.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
WS_DIR="${COLCON_WS:-$(cd "$REPO_DIR/../.." && pwd)}"
PKG_DIR="$REPO_DIR/tr_robot_head"

echo "🤖 === Instalación de la CABEZA de TR (Pi Zero 2 W) ==="
echo "   Workspace: $WS_DIR"
if [ "$(uname -m)" != "aarch64" ]; then
    echo "⚠️  Esto no parece una Raspberry Pi arm64 ($(uname -m)). Continúo igualmente."
fi
if [ ! -d "$WS_DIR/src" ]; then
    echo "❌ $WS_DIR no parece un workspace de colcon (falta src/)."
    echo "   Coloca este repositorio en ~/ros2_ws/src/ o define COLCON_WS."
    exit 1
fi

# --- 1. Swap de 1 GB (512 MB de RAM no bastan para apt + colcon) -------------
SWAP_ACTUAL_MB=$(free -m | awk '/^Swap:/ {print $2}')
if [ "${SWAP_ACTUAL_MB:-0}" -lt 900 ]; then
    echo "💾 [1/8] Creando archivo de swap de 1 GB en /swapfile_tr..."
    if [ ! -f /swapfile_tr ]; then
        sudo fallocate -l 1G /swapfile_tr || sudo dd if=/dev/zero of=/swapfile_tr bs=1M count=1024
        sudo chmod 600 /swapfile_tr
        sudo mkswap /swapfile_tr
    fi
    sudo swapon /swapfile_tr || true
    grep -q '^/swapfile_tr ' /etc/fstab || echo '/swapfile_tr none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
else
    echo "✅ [1/8] Ya hay ${SWAP_ACTUAL_MB} MB de swap."
fi

# --- 2. ROS 2 Humble ros-base (sin GUI) ---------------------------------------
if [ -f /opt/ros/humble/setup.bash ]; then
    echo "✅ [2/8] ROS 2 Humble ya instalado."
else
    echo "🐢 [2/8] Instalando ROS 2 Humble ros-base..."
    sudo apt-get update
    sudo apt-get install -y software-properties-common curl locales
    sudo locale-gen en_US en_US.UTF-8
    sudo add-apt-repository -y universe
    ROS_APT_SOURCE_VERSION=$(curl -s https://api.github.com/repos/ros-infrastructure/ros-apt-source/releases/latest | grep -F '"tag_name"' | awk -F'"' '{print $4}')
    curl -L -o /tmp/ros2-apt-source.deb \
        "https://github.com/ros-infrastructure/ros-apt-source/releases/download/${ROS_APT_SOURCE_VERSION}/ros2-apt-source_${ROS_APT_SOURCE_VERSION}.$(. /etc/os-release && echo "$VERSION_CODENAME")_all.deb"
    sudo dpkg -i /tmp/ros2-apt-source.deb
    rm -f /tmp/ros2-apt-source.deb
    sudo apt-get update
    sudo apt-get install -y ros-humble-ros-base
fi

# --- 3. Dependencias apt de los nodos de la cabeza ----------------------------
echo "📦 [3/8] Instalando dependencias apt..."
sudo apt-get update
sudo apt-get install -y \
    python3-pip python3-colcon-common-extensions \
    python3-opencv python3-numpy python3-pyaudio \
    espeak-ng alsa-utils i2c-tools iw \
    v4l-utils
# GPIO (LEDs) y soporte de Blinka (servos); en algunas imágenes faltan: no es fatal
for paquete in python3-gpiozero python3-lgpio python3-rpi.gpio; do
    sudo apt-get install -y "$paquete" \
        || echo "⚠️  $paquete no está disponible; los LEDs/servos pueden quedar en modo simulación."
done

# --- 4. Dependencias pip ------------------------------------------------------
echo "🐍 [4/8] Instalando adafruit-circuitpython-servokit..."
pip3 install --user adafruit-circuitpython-servokit \
    || echo "⚠️  No se pudo instalar servokit; servo_node usará modo simulación."

# --- 5. I2C y permisos --------------------------------------------------------
echo "🔌 [5/8] Activando I2C y permisos de hardware..."
CONFIG_TXT=/boot/firmware/config.txt
if [ -f "$CONFIG_TXT" ] && ! grep -q '^dtparam=i2c_arm=on' "$CONFIG_TXT"; then
    echo 'dtparam=i2c_arm=on' | sudo tee -a "$CONFIG_TXT" >/dev/null
    echo "   I2C activado en $CONFIG_TXT (hace falta reiniciar)."
fi
for grupo in audio video i2c gpio dialout; do
    if getent group "$grupo" >/dev/null; then
        sudo usermod -aG "$grupo" "$USER"
    fi
done

# --- 6. Variables de entorno de ROS en ~/.bashrc -------------------------------
echo "🌐 [6/8] Configurando ~/.bashrc (ROS_DOMAIN_ID=42)..."
add_line() { grep -qxF "$1" ~/.bashrc || echo "$1" >> ~/.bashrc; }
add_line "source /opt/ros/humble/setup.bash"
add_line "export ROS_DOMAIN_ID=42"
add_line "export ROS_LOCALHOST_ONLY=0"
add_line "[ -f $WS_DIR/install/setup.bash ] && source $WS_DIR/install/setup.bash"

# --- 7. Compilar SOLO tr_robot_head (secuencial para no agotar la RAM) --------
echo "🔨 [7/8] Compilando tr_robot_head..."
set +u
source /opt/ros/humble/setup.bash
set -u
(cd "$WS_DIR" && MAKEFLAGS=-j1 colcon build --packages-select tr_robot_head \
    --symlink-install --executor sequential)

# --- 8. Servicio systemd -------------------------------------------------------
echo "⚙️  [8/8] Instalando el servicio systemd tr-robot-head..."
sudo install -m 755 "$PKG_DIR/systemd/tr-robot-head-start.sh" /usr/local/bin/tr-robot-head-start
if [ ! -f /etc/default/tr-robot-head ]; then
    sed "s|__WS__|$WS_DIR|g" "$PKG_DIR/systemd/tr-robot-head.env" \
        | sudo tee /etc/default/tr-robot-head >/dev/null
else
    echo "   /etc/default/tr-robot-head ya existe: lo conservo."
fi
sed "s|__USER__|$USER|g" "$PKG_DIR/systemd/tr-robot-head.service" \
    | sudo tee /etc/systemd/system/tr-robot-head.service >/dev/null
sudo systemctl daemon-reload
sudo systemctl enable tr-robot-head.service

echo ""
echo "🎉 Cabeza instalada. Reinicia la Pi para aplicar I2C, grupos y swap:"
echo "      sudo reboot"
echo "   Tras reiniciar, los nodos arrancan solos. Comprobar con:"
echo "      systemctl status tr-robot-head"
echo "      journalctl -u tr-robot-head -f"
echo "   Comprobar hardware:  i2cdetect -y 1 (PCA9685 = 0x40) · arecord -l · aplay -l"
