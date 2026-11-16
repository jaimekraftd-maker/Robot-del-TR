# TR Robot — Núcleo cognitivo `tr_brain`

Cabeza robótica que **ve, escucha, habla, recuerda, aprende y evoluciona**.
Construida sobre tu base existente de **ROS 2 + Google Gemini**, añadiendo un
**cerebro cognitivo reutilizable** (memoria persistente, aprendizaje,
personalidad e iniciativa) como **librería de Python pura**.

> **Decisión de arquitectura:** *módulos portables (híbrido) + Gemini.*
> El "cerebro" (`tr_brain/`) no depende de ROS ni de hardware, así que se
> **desarrolla y testea en el portátil**, y luego lo **importan los nodos ROS**
> del robot. Lo mejor de los dos mundos: ROS para el hardware, librería limpia
> y testeable para la inteligencia.

---

## 🔴 Seguridad — léelo primero

Tu instalador antiguo tenía una **clave de API de Gemini en texto plano**.
Antes que nada:

1. **Revoca/regenera** esa clave en <https://aistudio.google.com/app/apikey>.
2. Guárdala SOLO como variable de entorno:
   ```bash
   export GEMINI_API_KEY='tu_nueva_clave'      # Linux/Raspberry (~/.bashrc)
   ```
   ```powershell
   setx GEMINI_API_KEY "tu_nueva_clave"          # Windows (reabre la terminal)
   ```
3. Borra los archivos viejos que la contenían (`files/Raspberry Pi instalacion.py`
   y el `install.sh` de dentro de `files.zip`). Usa el nuevo [install.sh](install.sh).

El código **nunca** debe contener la clave: ya se lee de `GEMINI_API_KEY`.

---

## 📁 Estructura

```
Robot_AI/
├── tr_brain/                ← NÚCLEO COGNITIVO (librería pura, sin ROS)
│   ├── config.py            · configuración central (sin secretos)
│   ├── llm.py               · envoltura de Gemini (+ modo OFFLINE)
│   ├── memory.py            · memoria persistente SQLite (personas + recuerdos)
│   ├── learning.py          · extracción de hechos, refuerzo, asociación, olvido
│   ├── personality.py       · personalidad evolutiva (5 rasgos)
│   ├── initiative.py        · cuándo y de qué hablar por iniciativa propia
│   ├── hardware.py          · HAL: simulador hoy, servos/Raspberry mañana
│   ├── voice.py             · oído (Vosk STT) y voz (pyttsx3/espeak TTS)
│   └── cognitive_core.py    · CerebroCognitivo: une todo (lo que usan los nodos)
│
├── demo_robot.py            ← ROBOT COMPLETO en consola (cerebro + voz, sin ROS) ★
├── demo_consola.py          ← prueba solo el cerebro
├── demo_voz.py              ← prueba solo el oído y la voz
│
├── tr_robot/                ← PAQUETE ROS 2 (nodos finos que usan tr_brain)
│   ├── brain_node.py        · cerebro ↔ /tr/speech_*, /tr/persons_detected
│   ├── voice_node.py        · micrófono ↔ /tr/speech_in · /tr/speech_out
│   ├── vision_node.py       · describe la escena (Gemini Vision)
│   └── person_recognition_node.py · identifica personas (Gemini Vision)
├── launch/tr_launch.py      ← arranca los 4 nodos con un comando
├── package.xml · setup.py · setup.cfg · resource/tr_robot  ← metadatos ament_python
│
├── requirements-core.txt    · dependencias del núcleo (puro Python)
├── install.sh               · instala dependencias + compila el paquete ROS
├── README.md · ROADMAP.md
└── files/                   · copia original de tus nodos (referencia/backup)
```

## 🧠 Arquitectura por capas

```
        ┌──────────────────── ROS 2 (la "carcasa" del robot) ────────────────────┐
        │  vision_node   person_recognition_node   [voz_node*]   [hardware_node*] │
        │       │                │                      │ ▲             ▲         │
        │  /vision_description /persons_detected   /speech_in /speech_out /head_cmd│
        │       └────────────────┴───────────┐  ┌───────┘                         │
        │                                  brain_node  ── publica voz / estado    │
        └──────────────────────────────────────┼──────────────────────────────────┘
                                                │  importa
        ┌───────────────────────────────────────▼─────────────────────────────────┐
        │                 tr_brain  ·  CerebroCognitivo  (PURO PYTHON)             │
        │   memoria   ·   aprendizaje   ·   personalidad   ·   iniciativa   ·  llm  │
        └───────────────────────────────────────┬──────────────────────────────────┘
                                                 │
                            SQLite ~/.tr_robot/robot.db  +  personality.json
        (* = nodos a crear; ver ROADMAP)
```

**Ciclo en cada turno (`CerebroCognitivo.procesar`)**: consultar memoria →
construir prompt con personalidad + lo que ve + recuerdos → pensar (Gemini) →
recordar → aprender hechos → evolucionar personalidad.

---

## 🚀 Probarlo AHORA (sin robot, sin ROS)

Funciona aunque no tengas clave (modo OFFLINE) y aunque no tengas `google-generativeai`.

```bash
# 1. (opcional) instalar dependencias del núcleo
pip install -r requirements-core.txt

# 2. (opcional) tu clave para respuestas reales de Gemini
export GEMINI_API_KEY='tu_clave'        # o setx en Windows

# 3. ejecutar el demo de consola
python demo_consola.py
```

Prueba esta secuencia y observa cómo **recuerda y aprende**:
```
tú> Mi perro se llama Toby
tú> Me gusta el ajedrez
tú> /que_se                     ← verás los hechos aprendidos
tú> /quien Jaime                ← simula reconocer una cara
tú> /personalidad               ← verás los rasgos cambiando
tú> (Enter en vacío varias veces) ← el robot acabará hablando solo
```

> En Windows, si `python` abre la Microsoft Store, usa `py -3 demo_consola.py`.

---

## 🤖 Arrancar en el robot (ROS 2)

El proyecto **es** un paquete ROS 2 `ament_python` llamado `tr_robot`. En la Raspberry:

```bash
# 1. coloca el proyecto como paquete del workspace
mkdir -p ~/ros2_ws/src
cp -r Robot_AI ~/ros2_ws/src/tr_robot          # o: git clone ... tr_robot

# 2. dependencias + compilación (install.sh hace ambas)
cd ~/ros2_ws/src/tr_robot && ./install.sh
source ~/ros2_ws/install/setup.bash

# 3. arranca TODO con un comando
ros2 launch tr_robot tr_launch.py              # cerebro + voz + visión + personas
ros2 launch tr_robot tr_launch.py vision:=false  # sin cámara (solo voz)
```

Topics (compatibles con tus nodos): `/tr/speech_in`, `/tr/speech_out`,
`/tr/vision_description`, `/tr/persons_detected`, `/tr/status`.

Migra tu memoria antigua (memory.json) una sola vez:  `python demo_consola.py --migrar`

## 💾 Dónde viven los datos

Todo en `~/.tr_robot/` (configurable con la variable `TR_HOME`):
`robot.db` (SQLite con personas, recuerdos y conocimiento), `personality.json`
(rasgos actuales) y `knowledge.json` (export legible de lo aprendido).

## 🔊 Voz (ya disponible)

Motores en [tr_brain/voice.py](tr_brain/voice.py) (puros, testeables) + nodo
[tr_robot/voice_node.py](tr_robot/voice_node.py). Pruébalo SIN ROS:

```bash
pip install -e ".[voice]"     # vosk + pyaudio + pyttsx3 (sobre todo en el robot)
python demo_voz.py            # en Windows: py -3 demo_voz.py
```

- **STT**: Vosk offline (modelo español de `~/.tr_robot/`). Sin micro/Vosk → modo teclado.
- **TTS**: pyttsx3 (Windows/dev) o espeak-ng (Raspberry), autodetectado. Sin TTS → imprime.
- El reconocedor **se silencia mientras el robot habla** para no oírse a sí mismo.
- En el robot, `voice_node` publica lo oído en `/tr/speech_in` y pronuncia `/tr/speech_out`.

## 🔜 Qué falta (ver ROADMAP.md)

- **Empaquetado ROS** (`package.xml`, `setup.py`, `tr_launch.py`) para arrancar todo junto.
- **Embeddings** para memoria semántica (hoy: búsqueda léxica + recencia).
- **Hardware real**: servos de cuello, ojos OLED, expresiones.
