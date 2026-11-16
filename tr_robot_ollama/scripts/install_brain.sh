#!/usr/bin/env bash
# install_brain.sh — Instalación completa del CEREBRO de TR (portátil)
# =====================================================================
# Para Ubuntu 22.04 (amd64) con ROS 2 Humble. Instala el Claude Agent SDK
# (trae Claude Code; el cerebro usa tu sesión de Claude, sin clave de API),
# Ollama con gemma2:2b (respaldo offline del cerebro) y moondream (visión),
# reconocimiento de voz (Vosk + Google), reconocimiento facial, y compila
# tr_robot_brain. Al final dice cómo iniciar sesión en Claude si hace falta.
#
# También vale para Ubuntu 22.04 dentro de WSL2 en Windows (README, "Cerebro en
# Windows con WSL2"): entonces usa el Ollama de Windows en vez de instalar otro.
#
# Estructura esperada:  ~/ros2_ws/src/tr_robot_ollama/scripts/install_brain.sh
# (o define COLCON_WS=/ruta/al/workspace antes de ejecutarlo)
#
# Uso:
#   bash scripts/install_brain.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
WS_DIR="${COLCON_WS:-$(cd "$REPO_DIR/../.." && pwd)}"
DATA_DIR="$HOME/.tr_robot_ollama"
EN_WSL=0
if grep -qi microsoft /proc/version 2>/dev/null; then
    EN_WSL=1
fi

echo "🤖 === Instalación del CEREBRO de TR (portátil) ==="
echo "   Workspace: $WS_DIR"
if [ "$EN_WSL" = 1 ]; then
    echo "   Ubuntu dentro de WSL2 (Windows)."
    if command -v wslinfo >/dev/null 2>&1 && [ "$(wslinfo --networking-mode 2>/dev/null)" != "mirrored" ]; then
        echo "⚠️  WSL no está en modo de red 'mirrored': la cabeza no encontrará al cerebro."
        echo "   Pon networkingMode=mirrored en %USERPROFILE%\\.wslconfig y, en Windows: wsl --shutdown"
    fi
fi
if [ ! -d "$WS_DIR/src" ]; then
    echo "❌ $WS_DIR no parece un workspace de colcon (falta src/)."
    echo "   Coloca este repositorio en ~/ros2_ws/src/ o define COLCON_WS."
    exit 1
fi

# --- 1. ROS 2 Humble ------------------------------------------------------------
if [ -f /opt/ros/humble/setup.bash ]; then
    echo "✅ [1/7] ROS 2 Humble ya instalado."
else
    echo "🐢 [1/7] Instalando ROS 2 Humble (ros-base + herramientas)..."
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

# --- 2. Dependencias apt ----------------------------------------------------------
# Solo usa sudo si falta algo: así el script se puede volver a lanzar sin contraseña.
# colcon va por pip en el paso 3: el repo de ROS a veces responde 403 a apt con sus paquetes.
PAQUETES_APT=(python3-pip python3-dev python3-opencv python3-numpy
              python3-requests libopenblas-dev cmake build-essential curl unzip)
FALTAN=()
for PAQUETE in "${PAQUETES_APT[@]}"; do
    dpkg -s "$PAQUETE" >/dev/null 2>&1 || FALTAN+=("$PAQUETE")
done
if [ ${#FALTAN[@]} -eq 0 ]; then
    echo "✅ [2/7] Dependencias apt ya instaladas."
else
    echo "📦 [2/7] Instalando dependencias apt: ${FALTAN[*]}..."
    sudo apt-get update
    sudo apt-get install -y -o Acquire::Retries=5 "${FALTAN[@]}"
fi

# --- 3. Dependencias pip ----------------------------------------------------------
echo "🐍 [3/7] Instalando dependencias Python..."
# numpy<2: el OpenCV de Ubuntu 22.04 (python3-opencv) está compilado para NumPy 1;
# sin el límite, matplotlib arrastra NumPy 2 y 'import cv2' deja de funcionar.
# colcon (la herramienta de compilación de ROS) solo si no está ya instalado por apt.
EXTRA_PIP=()
command -v colcon >/dev/null 2>&1 || EXTRA_PIP+=(colcon-common-extensions)
pip3 install --user --upgrade \
    requests SpeechRecognition vosk matplotlib claude-agent-sdk "numpy<2" "${EXTRA_PIP[@]}"
# pip --user deja los programas (colcon...) en ~/.local/bin
export PATH="$HOME/.local/bin:$PATH"
# dlib no está en apt en Ubuntu 22.04: pip lo compila (cmake + python3-dev, 10-20 min)
pip3 install --user face_recognition \
    || echo "⚠️  face_recognition no se pudo instalar; se usará la comparación ORB de OpenCV."

# --- 4. Ollama ----------------------------------------------------------------------
# En WSL con red 'mirrored', localhost:11434 es el Ollama de Windows: se reutiliza
# (y sus modelos) en vez de instalar y descargar otra copia dentro de Ubuntu.
MODELOS_WINDOWS=""
if [ "$EN_WSL" = 1 ]; then
    MODELOS_WINDOWS="$(curl -fsS -m 3 http://localhost:11434/api/tags 2>/dev/null || true)"
fi
if [ -n "$MODELOS_WINDOWS" ]; then
    echo "✅ [4/7] WSL: uso el Ollama de Windows (localhost:11434); no instalo otro."
    for MODELO in gemma2:2b moondream; do
        if ! grep -q "\"$MODELO" <<< "$MODELOS_WINDOWS"; then
            echo "⚠️  Al Ollama de Windows le falta $MODELO. En PowerShell:  ollama pull $MODELO"
        fi
    done
else
    if [ "$EN_WSL" = 1 ]; then
        echo "⚠️  No veo el Ollama de Windows en localhost:11434 (¿está abierto? ¿red 'mirrored'?)."
        echo "   Instalo otro dentro de Ubuntu."
    fi
    if command -v ollama >/dev/null 2>&1; then
        echo "✅ [4/7] Ollama ya está instalado."
    else
        echo "⬇️  [4/7] Instalando Ollama..."
        curl -fsSL https://ollama.com/install.sh | sh
    fi
    echo "🧠 Descargando modelos locales (gemma2:2b ≈ 1,6 GB, respaldo sin internet; moondream ≈ 1,7 GB)..."
    ollama pull gemma2:2b
    ollama pull moondream
fi

# --- 5. Modelo Vosk en español (STT offline) ----------------------------------------
VOSK_MODEL_DIR="$DATA_DIR/vosk-model-small-es"
if [ -d "$VOSK_MODEL_DIR" ]; then
    echo "✅ [5/7] Modelo Vosk ya presente."
else
    echo "⬇️  [5/7] Descargando el modelo Vosk español pequeño..."
    mkdir -p "$DATA_DIR"
    TMP_ZIP="$(mktemp --suffix=.zip)"
    curl -L -o "$TMP_ZIP" "https://alphacephei.com/vosk/models/vosk-model-small-es-0.42.zip"
    unzip -q "$TMP_ZIP" -d "$DATA_DIR"
    mv "$DATA_DIR"/vosk-model-small-es-0.42 "$VOSK_MODEL_DIR"
    rm -f "$TMP_ZIP"
fi

# --- 6. Variables de entorno de ROS ----------------------------------------------------
echo "🌐 [6/7] Configurando ~/.bashrc (ROS_DOMAIN_ID=42)..."
add_line() { grep -qxF "$1" ~/.bashrc || echo "$1" >> ~/.bashrc; }
add_line "source /opt/ros/humble/setup.bash"
add_line "export ROS_DOMAIN_ID=42"
add_line "export ROS_LOCALHOST_ONLY=0"
add_line "[ -f $WS_DIR/install/setup.bash ] && source $WS_DIR/install/setup.bash"
if [ "$EN_WSL" = 1 ]; then
    # WSL "mirrored" pierde los UDP de más de 1472 bytes a 127.0.0.1: sin este perfil,
    # un nodo que arranca más tarde que otro no lo ve nunca (ver scripts/wsl/fastdds_wsl.xml)
    add_line "export FASTRTPS_DEFAULT_PROFILES_FILE=$REPO_DIR/scripts/wsl/fastdds_wsl.xml"
fi

# --- 7. Compilar tr_robot_brain ---------------------------------------------------------
echo "🔨 [7/7] Compilando tr_robot_brain..."
set +u
source /opt/ros/humble/setup.bash
set -u
(cd "$WS_DIR" && colcon build --packages-select tr_robot_brain --symlink-install)

if [ "$EN_WSL" = 1 ]; then
    echo ""
    echo "🪟 WSL: para que la cabeza encuentre al cerebro, abre el cortafuegos de WSL una vez."
    echo "   En Windows, PowerShell como administrador:"
    echo "      powershell -ExecutionPolicy Bypass -File \"$(wslpath -w "$(readlink -f "$REPO_DIR")")\\scripts\\wsl\\preparar_windows.ps1\""
elif command -v ufw >/dev/null 2>&1 && sudo ufw status | grep -q "Status: active"; then
    echo ""
    echo "⚠️  El cortafuegos ufw está activo y puede bloquear ROS 2 (DDS usa UDP)."
    echo "   Permite tu red local, p.ej.:  sudo ufw allow from 192.168.1.0/24"
fi

echo ""
# El cerebro usa la sesión de Claude Code de este usuario (tu plan de Claude).
# Se comprueba el Claude Code que trae el SDK, que es el que usa TR. (En WSL,
# 'command -v claude' podría encontrar el de Windows, que tiene otra sesión.)
CLAUDE_CLI="$(python3 -c 'import claude_agent_sdk, pathlib; print(pathlib.Path(claude_agent_sdk.__file__).parent / "_bundled" / "claude")' 2>/dev/null || true)"
if [ ! -x "$CLAUDE_CLI" ]; then
    CLAUDE_CLI="$(command -v claude || true)"
fi
if [ -n "$CLAUDE_CLI" ] && [ -x "$CLAUDE_CLI" ] && "$CLAUDE_CLI" auth status >/dev/null 2>&1; then
    echo "✅ Sesión de Claude Code iniciada: el cerebro pensará con Claude."
else
    echo "🔑 Inicia sesión en Claude una vez (si no se abre el navegador, copia la URL que sale):"
    echo "      ${CLAUDE_CLI:-claude} auth login"
    echo "   Sin sesión, TR piensa solo con Ollama (gemma2:2b)."
fi
echo "🎉 Cerebro instalado. Abre una terminal nueva (para cargar ~/.bashrc) y lanza:"
echo "      ros2 launch tr_robot_brain brain_launch.py"
echo "   Para probar el cerebro sin robot:  python3 $REPO_DIR/scripts/demo_cerebro.py"
