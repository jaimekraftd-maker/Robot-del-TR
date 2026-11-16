#!/usr/bin/env bash
# install_sin_cabeza.sh — Modo sin cabeza: TR oye, habla y ve con el PC
# =======================================================================
# Para cuando la Pi Zero 2 W no está: los nodos de la cabeza (micro, voz y
# cámara) corren en el mismo PC que el cerebro. Ejecútalo DESPUÉS de
# install_brain.sh, en el mismo Ubuntu (nativo o dentro de WSL2).
#
#   1. Paquetes de sonido: PyAudio (micro) y espeak-ng (voz). En WSL, además,
#      el enchufe de ALSA a PulseAudio: el PulseAudio de WSLg lleva el sonido
#      al micro y a los altavoces de Windows.
#   2. En WSL: el perfil de Fast DDS sin el que ROS 2 falla entre procesos.
#   3. Compila tr_robot_head (y vuelve a compilar tr_robot_brain).
#   4. En WSL: comprueba el sonido de WSLg y el Python de Windows con OpenCV,
#      que es quien lee la webcam (WSL no ve las webcams de Windows).
#
# Uso:    bash scripts/install_sin_cabeza.sh
# Luego:  ros2 launch tr_robot_brain brain_launch.py sin_cabeza:=true
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
WS_DIR="${COLCON_WS:-$(cd "$REPO_DIR/../.." && pwd)}"
EN_WSL=0
if grep -qi microsoft /proc/version 2>/dev/null; then
    EN_WSL=1
fi

echo "🤖 === TR sin cabeza: micro, altavoces y webcam de este PC ==="

# --- 1. Paquetes de sonido ---------------------------------------------------------
PAQUETES_APT=(python3-pyaudio espeak-ng alsa-utils)
if [ "$EN_WSL" = 1 ]; then
    PAQUETES_APT+=(libasound2-plugins pulseaudio-utils)
fi
FALTAN=()
for PAQUETE in "${PAQUETES_APT[@]}"; do
    dpkg -s "$PAQUETE" >/dev/null 2>&1 || FALTAN+=("$PAQUETE")
done
if [ ${#FALTAN[@]} -eq 0 ]; then
    echo "✅ [1/4] Paquetes de sonido ya instalados."
else
    echo "📦 [1/4] Instalando: ${FALTAN[*]}..."
    sudo apt-get update
    sudo apt-get install -y -o Acquire::Retries=5 "${FALTAN[@]}"
fi
# PyAudio usa ALSA: en WSL, su dispositivo por defecto debe ser el PulseAudio de WSLg
if [ "$EN_WSL" = 1 ] && [ ! -f ~/.asoundrc ]; then
    printf 'pcm.!default pulse\nctl.!default pulse\n' > ~/.asoundrc
    echo "   ~/.asoundrc: el sonido por defecto de ALSA es ahora PulseAudio (WSLg)."
fi

# --- 2. Perfil de Fast DDS para WSL -------------------------------------------------
if [ "$EN_WSL" = 1 ]; then
    LINEA="export FASTRTPS_DEFAULT_PROFILES_FILE=$REPO_DIR/scripts/wsl/fastdds_wsl.xml"
    if grep -qxF "$LINEA" ~/.bashrc; then
        echo "✅ [2/4] Perfil de Fast DDS para WSL ya activado en ~/.bashrc."
    else
        echo "$LINEA" >> ~/.bashrc
        echo "🌐 [2/4] Perfil de Fast DDS para WSL añadido a ~/.bashrc."
    fi
    export FASTRTPS_DEFAULT_PROFILES_FILE="$REPO_DIR/scripts/wsl/fastdds_wsl.xml"
else
    echo "✅ [2/4] Linux nativo: no hace falta perfil de Fast DDS."
fi

# --- 3. Compilar ----------------------------------------------------------------------
echo "🔨 [3/4] Compilando tr_robot_head y tr_robot_brain..."
set +u
source /opt/ros/humble/setup.bash
set -u
export PATH="$HOME/.local/bin:$PATH"
(cd "$WS_DIR" && colcon build --packages-select tr_robot_head tr_robot_brain --symlink-install)
# El daemon de ros2 se arrancó sin el perfil: que vuelva a arrancar con él
ros2 daemon stop >/dev/null 2>&1 || true

# --- 4. Comprobaciones ------------------------------------------------------------------
echo "🔎 [4/4] Comprobando..."
if [ "$EN_WSL" = 1 ]; then
    if pactl info >/dev/null 2>&1; then
        echo "✅ Sonido de WSLg: $(pactl get-default-source 2>/dev/null) → $(pactl get-default-sink 2>/dev/null)"
    else
        echo "⚠️  No hay PulseAudio de WSLg (PULSE_SERVER=${PULSE_SERVER:-vacío}). Actualiza WSL en"
        echo "   Windows (wsl --update) y reinícialo (wsl --shutdown)."
    fi
    if ! command -v py.exe >/dev/null 2>&1; then
        echo "⚠️  No encuentro py.exe: instala Python en Windows para que TR vea por la webcam."
    elif py.exe -3 -c "import cv2" >/dev/null 2>&1; then
        echo "✅ Python de Windows con OpenCV: TR verá por la webcam."
    else
        echo "⚠️  Al Python de Windows le falta OpenCV. En PowerShell:  py -3 -m pip install --user opencv-python"
    fi
    echo "   En Windows, Configuración > Privacidad > Cámara y Micrófono: deja que las"
    echo "   aplicaciones de escritorio usen la cámara y el micrófono."
else
    ls /dev/video* >/dev/null 2>&1 && echo "✅ Cámara: $(ls /dev/video* | head -1)" \
        || echo "⚠️  No hay /dev/video*: TR no verá."
fi

echo ""
echo "🎉 Listo. Abre una terminal nueva (para cargar ~/.bashrc) y lanza TR entero en este PC:"
echo "      ros2 launch tr_robot_brain brain_launch.py sin_cabeza:=true"
