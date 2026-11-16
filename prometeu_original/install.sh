#!/bin/bash
# ============================================================
#  TR Robot - Instalación (Raspberry Pi / Ubuntu 22.04)
#  ROS 2 Humble + Google Gemini + núcleo cognitivo tr_brain
#  >>> Versión corregida: SIN clave de API en el código <<<
# ============================================================
set -e
echo "🤖 Instalando TR Robot..."

# ── 1. Dependencias del sistema ─────────────────────────────
echo "📦 Dependencias del sistema..."
sudo apt update -qq
sudo apt install -y \
    python3-pip python3-opencv espeak-ng portaudio19-dev \
    ros-humble-cv-bridge ros-humble-vision-msgs unzip wget

# ── 2. Dependencias Python (nodos del robot) ────────────────
echo "🐍 Paquetes Python..."
pip3 install --upgrade pip
pip3 install \
    google-generativeai Pillow SpeechRecognition pyaudio pyttsx3 vosk \
    opencv-python-headless python-dotenv

# ── 3. Instalar el núcleo cognitivo (tr_brain) en modo editable ──
#     Ejecuta este script DESDE LA RAÍZ del proyecto (donde está pyproject.toml)
echo "🧠 Instalando el núcleo cognitivo tr_brain..."
pip3 install -e .

# ── 4. Modelo de voz offline (Vosk español, ~50 MB) ─────────
echo "🗣️  Modelo de voz offline (Vosk español)..."
mkdir -p ~/.tr_robot
VOSK_DIR="$HOME/.tr_robot/vosk-model-small-es"
if [ ! -d "$VOSK_DIR" ]; then
    wget -q --show-progress \
        "https://alphacephei.com/vosk/models/vosk-model-small-es-0.42.zip" -O /tmp/vosk-es.zip
    unzip -q /tmp/vosk-es.zip -d ~/.tr_robot/
    mv ~/.tr_robot/vosk-model-small-es-0.42 "$VOSK_DIR"
    rm /tmp/vosk-es.zip
    echo "✅ Modelo Vosk instalado"
else
    echo "✅ Modelo Vosk ya estaba instalado"
fi

# ── 5. API key de Gemini — NUNCA en el código ───────────────
#     Se comprueba la VARIABLE DE ENTORNO (esto sí funciona; el chequeo
#     original con la clave literal estaba roto y además la filtraba).
echo ""
if [ -z "${GEMINI_API_KEY}" ]; then
    echo "⚠️  Falta GEMINI_API_KEY. Añádela a tu ~/.bashrc:"
    echo "      export GEMINI_API_KEY='tu_clave_secreta'"
    echo "    Consíguela gratis en https://aistudio.google.com/app/apikey"
else
    echo "✅ GEMINI_API_KEY detectada en el entorno."
fi

# ── 6. Compilar el paquete ROS 2 (si ROS está disponible) ───
if command -v colcon >/dev/null 2>&1 && [ -n "${ROS_DISTRO}" ]; then
    echo "🔨 Compilando el paquete ROS 2 'tr_robot'..."
    WS="$HOME/ros2_ws"
    mkdir -p "$WS/src"
    # enlaza este proyecto como paquete del workspace si aún no está
    if [ ! -e "$WS/src/tr_robot" ]; then
        ln -s "$(pwd)" "$WS/src/tr_robot"
    fi
    ( cd "$WS" && colcon build --packages-select tr_robot --symlink-install )
    echo "✅ Compilado. Arranca con:"
    echo "     source $WS/install/setup.bash && ros2 launch tr_robot tr_launch.py"
else
    echo "ℹ️  ROS 2 no detectado; me salto colcon. Haz 'source /opt/ros/<distro>/setup.bash' y reejecuta para compilar."
fi

echo ""
echo "═══════════════════════════════════════════════════"
echo "✅ Instalación completada."
echo "   Probar solo el cerebro (sin ROS):  python3 demo_consola.py"
echo "   Probar solo la voz   (sin ROS):     python3 demo_voz.py"
echo "═══════════════════════════════════════════════════"
