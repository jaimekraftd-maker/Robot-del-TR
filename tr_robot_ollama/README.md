# TR — robot con IA (cerebro Claude, respaldo offline con Ollama)

Cabeza robótica que ve, oye, habla, recuerda y **madura**. Funciona repartida en
dos máquinas conectadas por Wi-Fi con ROS 2 Humble. El cerebro piensa con
**Claude** (`claude-opus-5-5`) a través del
[Claude Agent SDK](https://code.claude.com/docs/en/agent-sdk/overview), con la
sesión de Claude Code del portátil: usa tu plan de Claude, sin clave de API.
Si no hay sesión o se cae internet, sigue pensando en local con
[Ollama](https://ollama.com) (`gemma2:2b`). Para ver, Claude describe la
escena cada 60 s, con `moondream` en local como respaldo. El reconocimiento
de caras es siempre local.

> **Nota:** esta carpeta vive **en paralelo** al proyecto original `tr_robot` /
> `tr_brain` de este mismo repositorio (Google Gemini, memoria SQLite,
> "Prometeo"). No lo sustituye ni comparte datos: esta variante guarda todo en
> `~/.tr_robot_ollama/`. La carpeta y los datos conservan el nombre "ollama"
> de cuando todo era local, para no perder la memoria de TR.

## Arquitectura

```
 CABEZA · Raspberry Pi Zero 2 W (512 MB)         PORTÁTIL · Ubuntu 22.04 (o Windows + WSL2)
 paquete tr_robot_head — nada de IA               paquete tr_robot_brain

 camera_node ── JPEG 5 fps ─────── Wi-Fi ──────▶  vision_node ── Claude (o moondream)
             /tr/camera/image/compressed          person_recognition_node
 audio_capture_node ── bloques 0,5 s ──────────▶  stt_node ── VAD + Vosk/Google
                      /tr/audio_raw                    │ /tr/speech_in
                                                       ▼
 tts_node ◀────────── /tr/speech_out ───────────  brain_node ── Claude (o gemma2:2b)
  │ espeak-ng                                          memoria · emociones
  └─ /tr/speaking ──▶ servo_node (mandíbula)           etapas de desarrollo
                      audio_capture_node (se calla)
 led_node ◀────────── /tr/status (idle · listening · thinking · speaking)
```

Por Wi-Fi solo viajan JPEG comprimidos (~30 KB por imagen, ~1,2 Mbit/s a
5 fps), audio (256 kbit/s) y texto. Una imagen sin comprimir serían 900 KB:
**nunca** se publican imágenes en crudo.

```
tr_robot_ollama/
├── tr_robot_head/             ← se compila en la Pi Zero 2 W
│   ├── tr_robot_head/         camera, audio_capture, tts, servo, led, head_all
│   ├── launch/                head_launch.py; pc_launch.py (modo sin cabeza)
│   ├── windows/               camara_windows.py: la webcam de Windows para WSL
│   └── systemd/               servicio que arranca la cabeza al encender
├── tr_robot_brain/            ← se compila en el portátil
│   ├── tr_robot_brain/        stt, brain, vision, person_recognition +
│   │                          cerebro.py, llm.py, agente.py, development.py, emotions.py, vad.py (sin ROS)
│   ├── config/                developmental_stages.json, agente_tr.json
│   └── launch/brain_launch.py
└── scripts/
    ├── install_head.sh        instalación ligera para la Pi Zero (con swap de 1 GB)
    ├── install_brain.sh       instalación completa del portátil
    ├── install_sin_cabeza.sh  lo que añade el modo sin cabeza (después de install_brain.sh)
    ├── demo_cerebro.py        habla con TR por consola, sin ROS ni robot
    ├── graficas_evolucion.py  gráficas de maduración para el TR
    ├── registrar_persona.py
    ├── fastdds_super_client.xml
    └── wsl/                   cortafuegos de Hyper-V y fastdds_wsl.xml
```

## Hardware

**Cabeza (dentro del cráneo): Raspberry Pi Zero 2 W**
- Ubuntu 22.04 Server arm64 + ROS 2 Humble `ros-base`
- Cámara USB, micrófono USB y altavoz (USB o DAC I2S). La Pi Zero 2 W tiene
  **un solo puerto USB de datos** (micro-USB OTG): para cámara + micro +
  altavoz USB hace falta un **hub USB**, mejor alimentado.
- 3 servos con un PCA9685 por I2C (canal 0 pan, 1 tilt, 2 mandíbula)
- 3 LEDs de estado por GPIO

**Cerebro: portátil** con Ubuntu 22.04 + ROS 2 Humble (cerebro con Claude por
internet y Ollama de respaldo, visión, reconocimiento facial y STT), o un PC con
Windows y Ubuntu en WSL2 (ver *Cerebro en Windows con WSL2*).

### Conexiones

| Desde | Hasta | Pin de la Pi (físico) |
|-------|-------|-----------------------|
| PCA9685 VCC (lógica) | 3,3 V | 1 |
| PCA9685 GND | GND | 6 |
| PCA9685 SDA | GPIO2 | 3 |
| PCA9685 SCL | GPIO3 | 5 |
| PCA9685 V+ (bornero) | **Fuente de servos 5 V / 3 A** | — |
| GND de la fuente de servos | GND de la Pi (masas unidas) | 9 |
| LED verde (+ 330 Ω a GND) | GPIO17 | 11 |
| LED azul (+ 330 Ω a GND) | GPIO27 | 13 |
| LED rojo (+ 330 Ω a GND) | GPIO22 | 15 |

**Alimentación:** Pi Zero 2 W con su propia fuente de 5 V / 2,5 A; servos con
una fuente **separada** de 5 V / 3 A, con las masas unidas. **Nunca alimentes
los servos desde la Pi**: un servo al arrancar pide picos de más de 1 A, la
tensión cae y la Pi se reinicia (o se estropea).

LEDs: `idle` = verde fijo · `listening` = azul fijo · `thinking` = azul
parpadeando · `speaking` = verde parpadeando rápido · `error` = rojo.

## Cabeza con Pico 2 W (en vez de la Pi Zero 2 W)

El PC lo hace todo. La **Raspberry Pi Pico 2 W** solo recibe órdenes por Wi-Fi y
mueve los servos y los LEDs. La cámara y el micro del cráneo van al PC por USB, y
el sonido sale por los altavoces del PC. El cerebro corre como en el modo sin
cabeza (`pc_launch.py`).

| Desde | Hasta | Pin de la Pico (físico) |
|-------|-------|-------------------------|
| PCA9685 VCC (lógica) | 3V3 OUT | 36 |
| PCA9685 GND | GND | 38 |
| PCA9685 SDA | GP4 | 6 |
| PCA9685 SCL | GP5 | 7 |
| LED verde (+ 330 Ω; pata corta a GND, pin 13) | GP10 | 14 |
| LED azul (+ 330 Ω) | GP11 | 15 |
| LED rojo (+ 330 Ω) | GP12 | 16 |
| PCA9685 V+ (bornero) | **Fuente de servos 5 V** (su GND al GND del PCA9685) | — |

La Pico se alimenta por su micro-USB. Servos en el PCA9685: canal 0 pan, 1 tilt,
2 mandíbula.

**Instalar el firmware:**

1. Mantén pulsado BOOTSEL, conecta la Pico al PC y copia el `.uf2` de MicroPython
   para **Pico 2 W** a la unidad que aparece.
2. Con Thonny, guarda en la Pico `tr_robot_head/pico/main.py` y una copia de
   `config_ejemplo.py` llamada `config.py` con tu Wi-Fi (solo 2,4 GHz).
3. Reinicia la Pico y mira su IP en la consola de Thonny. Reserva esa IP en el
   router, o tendrás que cambiarla si la Pico recibe otra.

**Probar desde Windows** (sin ROS; los servos con su fuente conectada):

```
py -3 scripts\probar_pico.py IP-DE-LA-PICO ping     # debe decir pca=1
py -3 scripts\probar_pico.py IP-DE-LA-PICO leds
py -3 scripts\probar_pico.py IP-DE-LA-PICO centro   # monta las bocinas después de esto
py -3 scripts\probar_pico.py IP-DE-LA-PICO barrer 0
```

**Arrancar TR** en Ubuntu (WSL):

```
cd ~/ros2_ws && colcon build --symlink-install --packages-select tr_robot_head && source install/setup.bash
export TR_PICO_HOST=IP-DE-LA-PICO
ros2 launch tr_robot_brain brain_launch.py sin_cabeza:=true
```

Añade `export TR_PICO_HOST=...` a `~/.bashrc` para no repetirlo. El PC y la Pico
deben estar en la misma red; muchas redes de instituto aíslan los dispositivos, y
entonces hace falta una red propia. El rojo parpadeando significa sin Wi-Fi o más
de 5 s sin órdenes del PC. Con la Pico, la mandíbula usa 60 (cerrada) y 85
(abierta), los topes del cráneo v5. Las órdenes UDP no llevan contraseña: cualquiera
en tu red podría mover los servos, aunque la Pico nunca pasa de los topes.

## Instalación

Las dos máquinas usan el mismo repositorio, dentro de un workspace de colcon:

```bash
mkdir -p ~/ros2_ws/src && cd ~/ros2_ws/src
# copia (o clona) aquí la carpeta tr_robot_ollama
```

**En el portátil** (Claude Agent SDK, Ollama, modelos, Vosk, face_recognition
y `tr_robot_brain`):

```bash
cd ~/ros2_ws/src/tr_robot_ollama
chmod +x scripts/*.sh
./scripts/install_brain.sh
```

Después, entra una vez en tu cuenta de Claude en ese portátil (se abre el
navegador). Si ya usas Claude Code allí, basta con `claude auth login`; si no,
el script te muestra la ruta del Claude Code que trae el SDK, algo así como:

```bash
~/.local/lib/python3.10/site-packages/claude_agent_sdk/_bundled/claude auth login
```

`claude auth status` dice si la sesión está iniciada. Sin sesión, TR funciona
igual pero solo con Ollama.

**En la Pi Zero 2 W** (crea 1 GB de swap, instala ROS 2 `ros-base` si falta,
compila solo `tr_robot_head` e instala el servicio systemd):

```bash
cd ~/ros2_ws/src/tr_robot_ollama
chmod +x scripts/*.sh
./scripts/install_head.sh
sudo reboot
```

Tras reiniciar, la cabeza arranca sola. Útil:

```bash
systemctl status tr-robot-head          # ¿está corriendo?
journalctl -u tr-robot-head -f          # logs en directo
sudo systemctl restart tr-robot-head    # tras cambiar código o configuración
sudoedit /etc/default/tr-robot-head     # configuración del servicio
i2cdetect -y 1                          # el PCA9685 debe aparecer en 0x40
arecord -l && aplay -l                  # micrófonos y altavoces detectados
```

## Cerebro en Windows con WSL2

Si el cerebro va en tu PC con Windows (donde ya tienes la sesión de Claude), los
nodos de `tr_robot_brain` corren en **Ubuntu 22.04 dentro de WSL2**: el mismo
Ubuntu y ROS 2 Humble que la Pi, con el Python 3.10 que pide el Claude Agent
SDK. (ROS 2 Humble instalado directamente en Windows usa Python 3.8 y el SDK no
funciona ahí.) El micrófono y la cámara están en la Pi y llegan por ROS, así que
WSL no necesita tocar ningún hardware. Sin la Pi, ver *Modo sin cabeza*.

1. **Instala WSL con Ubuntu 22.04** (PowerShell como administrador) y reinicia.
   Al abrir Ubuntu la primera vez te pide un usuario y una contraseña de Linux.

   ```bash
   wsl --install -d Ubuntu-22.04
   ```

2. **Red "mirrored".** `%USERPROFILE%\.wslconfig` debe contener esto (en el PC
   de Jaime ya está):

   ```ini
   [wsl2]
   networkingMode=mirrored
   ```

   Ubuntu comparte así la IP y la Wi-Fi de Windows: la Pi lo ve como un
   ordenador más y Ubuntu llega al Ollama de Windows en `localhost:11434`. Si WSL
   estaba abierto al cambiarlo: `wsl --shutdown`.

3. **Abre el cortafuegos de WSL para ROS 2**, una vez, en PowerShell como
   administrador y desde la carpeta `tr_robot_ollama`:

   ```bash
   powershell -ExecutionPolicy Bypass -File scripts\wsl\preparar_windows.ps1
   ```

   Abre en el cortafuegos de Hyper-V (el que protege a WSL) los puertos UDP de
   ROS 2 con `ROS_DOMAIN_ID=42` (17900-18149) y el 11811 del Discovery Server, y
   comprueba `.wslconfig` y los modelos de Ollama. Con `-Comprobar` solo mira,
   sin cambiar nada ni pedir administrador.

4. **En Ubuntu, enlaza el código e instala.** El código se queda en OneDrive y lo
   sigues editando desde Windows; Ubuntu lo ve en `/mnt/c` (cambia la ruta si tu
   carpeta está en otro sitio):

   ```bash
   mkdir -p ~/ros2_ws/src
   ln -s /mnt/c/Users/jaime/OneDrive/Documentos/Robot_AI/tr_robot_ollama ~/ros2_ws/src/tr_robot_ollama
   bash ~/ros2_ws/src/tr_robot_ollama/scripts/install_brain.sh
   ```

   El script detecta WSL: usa el Ollama de Windows en vez de instalar otro, avisa
   si la red no es "mirrored" y al final te dice si falta iniciar sesión en Claude.

5. **Claude.** Ubuntu tiene su propia sesión de Claude Code (la misma cuenta):
   ejecuta una vez el `... auth login` que te muestra el script. Si no se abre el
   navegador, copia la URL que sale en el de Windows.

6. **Ollama.** Deja abierto el Ollama de Windows. Para el respaldo de la visión,
   en PowerShell: `ollama pull moondream` (gemma2:2b ya lo tienes).

7. **Arranca.** Enciende la Pi y, en una terminal de Ubuntu:

   ```bash
   ros2 launch tr_robot_brain brain_launch.py
   ```

Cosas que conviene saber:

- La memoria de TR en WSL vive en el home de Ubuntu (`~/.tr_robot_ollama`; desde
  el Explorador de Windows, `\\wsl.localhost\Ubuntu-22.04\home\<usuario>\.tr_robot_ollama`).
  Es otra distinta de la que usa `demo_cerebro.py` en Windows.
- Para el Discovery Server (*Red*, opción B), la IP del cerebro es la de Windows
  (`ipconfig`): con la red "mirrored", Ubuntu tiene la misma.
- Si Windows se suspende, TR se queda sin cerebro: mientras el robot esté
  encendido, que el PC no se duerma enchufado.
- Si bash dice `$'\r': command not found`, un script se guardó con saltos de línea
  de Windows: `sed -i 's/\r$//' ~/ros2_ws/src/tr_robot_ollama/scripts/*.sh`
- **Nodos que no se ven entre sí.** En WSL "mirrored", un datagrama UDP de más de
  1472 bytes enviado a `127.0.0.1` se pierde. Fast DDS los usa cuando un nodo arranca
  más tarde que otro, así que un nodo que se reinicia o un `ros2 topic echo` no verían
  a los demás. [`scripts/wsl/fastdds_wsl.xml`](scripts/wsl/fastdds_wsl.xml) limita los
  mensajes UDP a 1400 bytes, y `install_brain.sh` lo activa en `~/.bashrc` con
  `FASTRTPS_DEFAULT_PROFILES_FILE`. Si lo activas a mano, ejecuta después
  `ros2 daemon stop`. El perfil de super cliente (*Red*, opción B) lo sustituye en la
  terminal donde lo uses.

## Modo sin cabeza: TR solo con el PC

Sin la Pi Zero 2 W, TR oye, habla y ve con el micrófono, los altavoces y la webcam
del propio PC. Sirve para probarlo y para hacer demostraciones. Corren los mismos
nodos de la cabeza, sin servos ni LEDs, con los mismos topics: el cerebro no nota
la diferencia.

**Instalar**, una vez, en Ubuntu y después de `install_brain.sh`:

```bash
bash ~/ros2_ws/src/tr_robot_ollama/scripts/install_sin_cabeza.sh
```

Instala PyAudio, espeak-ng y el enlace de ALSA con PulseAudio, activa el perfil de
Fast DDS y compila `tr_robot_head`. En Windows no instala nada: usa tu `py -3` con
OpenCV (si te falta, `py -3 -m pip install --user opencv-python`).

**Antes de arrancar, en Windows:**

- Altavoces sin silenciar y micrófono con volumen (Configuración > Sistema > Sonido).
  Con el micrófono a 0 %, TR apenas oye nada.
- En Configuración > Privacidad y seguridad, permite que las aplicaciones de
  escritorio usen la cámara y el micrófono.

**Arrancar**, en una terminal nueva de Ubuntu:

```bash
ros2 launch tr_robot_brain brain_launch.py sin_cabeza:=true
```

Ctrl+C lo para todo y suelta la webcam. También puedes usar:

```bash
ros2 launch tr_robot_brain brain_launch.py sin_cabeza:=true webcam:=1               # otra webcam de Windows
ros2 launch tr_robot_brain brain_launch.py sin_cabeza:=true speech_end_margin:=1.5  # si TR se oye a sí mismo
ros2 launch tr_robot_brain brain_launch.py sin_cabeza:=true stt_engine:=vosk        # reconocimiento de voz offline
```

**Cómo funciona en WSL2:**

- **Oído y voz.** `audio_capture_node` y `tts_node` no cambian. PyAudio y espeak-ng
  usan el sonido por defecto, que en WSL es el PulseAudio de WSLg, y este lo lleva al
  micrófono y a los altavoces de Windows.
- **Vista.** WSL no ve las webcams de Windows. `pc_launch.py` lanza
  [`camara_windows.py`](tr_robot_head/windows/camara_windows.py) en el Python de
  Windows, que lee la webcam y sirve la última imagen en
  `http://127.0.0.1:8765/frame.jpg`, solo dentro del PC. `camera_node` la pide por HTTP
  (parámetro `url`) y la publica en el topic de siempre. No se usa usbipd-win porque
  hay que instalarlo y vincular la cámara como administrador, Windows pierde la cámara
  mientras la usa WSL, y hay que volver a conectarla tras cada suspensión.

En Ubuntu nativo, el mismo comando usa `/dev/video0` y el sonido del sistema.

**TR escucha siempre,** sin palabra de activación: en una sala con ruido o gente
hablando, contestará a lo que oiga. Con los ajustes normales, lo que oye va a Google
y una foto de la webcam va a Anthropic cada minuto, como con la cabeza. Para que nada
salga del PC (sin `moondream`, TR solo detecta movimiento):

```bash
TR_LLM=ollama ros2 launch tr_robot_brain brain_launch.py sin_cabeza:=true stt_engine:=vosk
```

**Si algo falla:**

- **No se oye a TR, o TR no oye:** mira los volúmenes de Windows. En Ubuntu,
  `pactl info` debe mostrar `RDPSink` y `RDPSource`; si no, en Windows `wsl --update`
  y `wsl --shutdown`.
- **`Error leyendo de la cámara`:** una vez al arrancar es normal, porque el puente
  tarda 1-2 s en abrir. Si sigue, otra aplicación puede estar usando la webcam. Para
  probarla sola, en PowerShell desde `tr_robot_ollama`, ejecuta
  `py -3 tr_robot_head\windows\camara_windows.py` y abre la URL en el navegador.
- **TR se oye a sí mismo:** sube `speech_end_margin` (1 s por defecto en este modo),
  baja el volumen o usa auriculares.
- **Trazas y `process has died` al pulsar Ctrl+C:** salen también con la cabeza real
  y no impiden volver a arrancar.

## Red

Las dos máquinas deben tener el mismo `ROS_DOMAIN_ID=42` (los scripts de
instalación lo añaden a `~/.bashrc`, y el servicio de la cabeza lo lee de
`/etc/default/tr-robot-head`).

### Opción A (recomendada): red propia

Usa un router propio o el **hotspot del móvil**. Las redes de los institutos
suelen bloquear el multicast que usa ROS 2 para que los nodos se descubran
entre sí. Para comprobar si el multicast funciona:

```bash
ros2 multicast receive     # en una máquina
ros2 multicast send        # en la otra: la primera debe recibir el mensaje
```

### Opción B: Fast DDS Discovery Server (si el multicast está bloqueado)

Sin multicast, un servidor en el portátil hace de "agenda" y todos los nodos
le preguntan a él. Supongamos que el portátil tiene la IP `192.168.1.50`:

```bash
# En el portátil, en una terminal aparte (dejarlo corriendo):
fastdds discovery --server-id 0 --ip-address 192.168.1.50 --port 11811

# En el portátil, en ~/.bashrc:
export ROS_DISCOVERY_SERVER=192.168.1.50:11811
```

En la Pi, descomenta la línea en `/etc/default/tr-robot-head`:

```bash
ROS_DISCOVERY_SERVER=192.168.1.50:11811
```

y reinicia el servicio. En este modo, `ros2 topic list` no ve los topics a
menos que uses el perfil de "super cliente": edita la IP en
[`scripts/fastdds_super_client.xml`](scripts/fastdds_super_client.xml) y:

```bash
export FASTRTPS_DEFAULT_PROFILES_FILE=~/ros2_ws/src/tr_robot_ollama/scripts/fastdds_super_client.xml
ros2 daemon stop && ros2 daemon start
```

Pon la IP del portátil fija (reserva DHCP en el router) para no tener que
cambiarla cada día.

## Arrancar el robot

1. Enciende la Pi Zero: la cabeza arranca sola (servicio systemd).
2. En el portátil:

```bash
ros2 launch tr_robot_brain brain_launch.py
ros2 launch tr_robot_brain brain_launch.py stt_engine:=vosk            # 100% offline
ros2 launch tr_robot_brain brain_launch.py vision:=false persons:=false
ros2 launch tr_robot_brain brain_launch.py sin_cabeza:=true            # sin la Pi, solo con el PC
```

Para lanzar la cabeza a mano (sin el servicio):

```bash
ros2 launch tr_robot_head head_launch.py
ros2 launch tr_robot_head head_launch.py servos:=false leds:=false    # sin electrónica
ros2 launch tr_robot_head head_launch.py single_process:=false        # un proceso por nodo
```

Por defecto los 5 nodos de la cabeza corren en **un solo proceso**
(`head_all`): cada proceso Python con ROS ocupa ~35-60 MB, y en 512 MB eso
importa. Con `single_process:=false` va cada nodo por separado, más cómodo
para depurar.

## El cerebro: Claude con respaldo offline

Toda la mente de TR está en `cerebro.py` (`CerebroTR`). El modelo de lenguaje
está aparte, en [`llm.py`](tr_robot_brain/tr_robot_brain/llm.py): CerebroTR le
pasa los mismos prompts, etapas, emociones y memoria, y no sabe qué motor
contesta. Por orden:

1. **Claude** (`claude-opus-5-5`) con el Claude Agent SDK, que lanza un
   proceso de Claude Code por petición con tu sesión (`claude auth login`).
   Si Claude se niega a contestar algo, TR dice "me he quedado en blanco" y
   **no** se lo pregunta a Ollama.
2. **Ollama** (`gemma2:2b`), si Claude falla por falta de internet, límite de uso
   de tu plan o error del servidor. Tras un fallo así, TR usa Ollama durante 60 s
   y luego vuelve a probar Claude. Si no hay sesión de Claude Code, Claude se
   desactiva hasta reiniciar el nodo. Sin Ollama arrancado, este respaldo no existe.
3. Si ninguno responde, sube la duda existencial de TR (ver *Emociones*).

### Parámetros del agente TR

El agente de Claude que hace de TR tiene sus propios parámetros en
[`config/agente_tr.json`](tr_robot_brain/config/agente_tr.json), al lado de las
etapas de desarrollo. Los leen `brain_node`, `vision_node` y los scripts; no son
parámetros ROS. Tras cambiarlos, reinicia el nodo (si no compilaste con
`--symlink-install`, antes `colcon build`).

| Parámetro | Por defecto | Para qué |
|-----------|-------------|----------|
| `motor` | `claude` | `ollama` = 100% local y gratis (p. ej. para simulaciones largas) |
| `identidad` | "Eres TR, un robot físico…" | Quién es TR: lo primero del system prompt, antes de la etapa, la personalidad y las emociones |
| `claude.modelo` | `claude-opus-5-5` | Modelo de todas las tareas que no digan otro |
| `claude.modelo_alternativo` | (vacío) | Modelo que usa Claude Code si el principal está saturado, p. ej. `claude-sonnet-5-5` |
| `claude.palabras_por_token` | `0.6` | Convierte el `num_predict` de cada etapa en el límite de palabras que se le pide a Claude |
| `claude.pausa_tras_fallo_s` | `60` | Tras un fallo pasajero, segundos con Ollama antes de volver a probar Claude |
| `tareas.<tarea>.esfuerzo` | ver abajo | Cuánto piensa: `low`, `medium`, `high`, `xhigh` o `max` (más = mejor, más lento y más uso de tu plan) |
| `tareas.<tarea>.modelo` | (vacío) | Un modelo solo para esa tarea; vacío = `claude.modelo` |
| `tareas.vision.cada_s` | `60` | Cada cuántos segundos describe Claude la escena |
| `tareas.vision.max_palabras` | `60` | Longitud máxima de cada descripción |
| `tareas.vision.timeout_s` | `30` | Tiempo máximo para describir una imagen |
| `ollama.modelo` | `gemma2:2b` | Modelo local de respaldo |
| `ollama.respaldo` | `true` | `false` = no usar Ollama si Claude falla |
| `ollama.url` | `http://localhost:11434/api/generate` | Dónde está Ollama |

Las tareas y su esfuerzo por defecto son `conversacion` (`low`: TR habla en
tiempo real), `hechos`, `personalidad` y `maduracion` (`medium`: analizan
charlas) y `vision` (`low`). Por ejemplo, para que la evaluación de madurez
piense más y los hechos los saque un modelo más ligero:

```json
"maduracion": { "esfuerzo": "high", "modelo": "" },
"hechos": { "esfuerzo": "medium", "modelo": "claude-sonnet-5-5" },
```

Si el fichero falta, está roto o un valor no es válido, `brain_node` lo avisa en
el log y usa el valor por defecto. Para probar otro perfil sin tocar el
fichero: `TR_AGENT_FILE=/ruta/a/otro.json`. Estas variables de entorno mandan
sobre el fichero: `TR_LLM` (motor), `TR_CLAUDE_MODEL`, `TR_CLAUDE_EFFORT`
(conversación), `TR_CLAUDE_EFFORT_ANALISIS` (hechos, personalidad y
maduración), `TR_VISION_CLAUDE_SEC`, `TR_OLLAMA_MODEL` y `TR_OLLAMA_FALLBACK`
(`0` = sin respaldo). `ANTHROPIC_API_KEY` es opcional: si la defines, Claude
Code la usa (y se paga por API) en vez de tu plan.

**Mismos parámetros, distinto motor.** La longitud máxima de cada etapa
(`num_predict`) es un tope de tokens para gemma2. A Claude se le pide en
palabras (unas 0,6 por token: 54 palabras a los 12 años, 102 a los 18). Claude
Opus 5.5 no admite `temperature`: lo que con Ollama era temperatura 0,2 en las
tareas de análisis, con Claude es más esfuerzo (`medium`). Conversar va a `low`
porque TR habla en tiempo real. Claude recibe la misma transcripción
(`Usuario: …` / `TR: …`) que Ollama. Cada respuesta tarda unos 4-7 s: ~1 s en
arrancar Claude Code y el resto, Claude pensando.

**Tu plan de Claude.** Cada respuesta, cada tarea de aprendizaje y cada
descripción de la cámara gastan uso de tu plan, el mismo que usas en Claude
Code y claude.ai. Si llegas al límite, TR sigue con Ollama hasta que se renueve.
`scripts/simular_interacciones.py` hace cientos de peticiones seguidas: para
simular, usa `TR_LLM=ollama`. Anthropic no permite ofrecer el inicio de sesión de
claude.ai en productos para otras personas; TR es tu robot y usa tu sesión, pero
si algún día lo usara otra gente con su propio portátil, haría falta una clave de API.

**Lo que TR no ve de tu Claude Code.** Cada petición va sin herramientas, sin
los conectores de tu cuenta de claude.ai (Gmail, Drive...), sin skills, sin tus
ajustes ni CLAUDE.md, sin guardar sesiones y desde la carpeta neutra
`~/.tr_robot_ollama`. Lo único que Claude Code añade siempre es el correo de tu
cuenta y datos del ordenador (carpeta, sistema): TR tiene orden de ignorarlos y
`llm.py` borra cualquier dirección de correo de lo que dice.

## La visión: Claude cada 60 s, moondream de respaldo

`vision_node` guarda el último JPEG de la cabeza y lo describe (en
`/tr/vision_description`) con lo primero que esté disponible:

1. **Claude** (`tareas.vision` de `agente_tr.json`: esfuerzo `low`), cada 60 s y
   cada vez que se publica en `/tr/vision_request`. Es menos frecuente que
   moondream porque cada descripción gasta uso de tu plan (60 por hora de
   robot encendido). Tarda unos 3-4 s.
2. **moondream** en Ollama, cada 15 s como antes, si no hay sesión de Claude
   Code o falla la conexión (60 s de pausa y vuelve a probar Claude).
3. **Detección de movimiento** con OpenCV, si moondream tampoco responde.

Si Claude se niega a describir una imagen, esa vez no se publica nada.

> **Privacidad:** con Claude, cada minuto se envía a Anthropic una foto de la
> cámara, y en ella puede salir gente. Avisa a quien vaya a estar delante del
> robot o usa `TR_LLM=ollama` para que nada salga del portátil.
> `person_recognition_node` nunca envía caras fuera: compara las fotos en local
> con `face_recognition` (dlib) u ORB.

```bash
ros2 topic pub --once /tr/vision_request std_msgs/String "data: 'ya'"   # ¿qué ves ahora?
```

## Etapas de desarrollo

TR no empieza como pizarra en blanco: arranca con la mente de **un niño de
12 años** y su personalidad emergente se construye encima. Las etapas están en
[`config/developmental_stages.json`](tr_robot_brain/config/developmental_stages.json)
(12, 14, 16 y 18 años): cada una define cómo habla, cuánto sabe, ejemplos de
estilo y la longitud máxima de sus respuestas.

El system prompt se construye en este orden:
1. Descripción de la etapa actual, con la instrucción *"Habla y razona como
   alguien de {edad} años. Aunque sepas más, no uses conocimientos ni
   vocabulario impropios de esa edad."*
2. Rasgos de personalidad emergentes (`memory["personality"]`)
3. Hechos conocidos y contexto visual
4. Estado emocional

**Maduración:** cada 100 interacciones, `brain_node` pide al modelo que evalúe
si lo que le plantean las personas es más complejo de lo que corresponde a su
edad. El modelo razona primero y después clasifica la complejidad
(`adecuada` → +0 · `superior` → +1 · `muy_superior` → +2, máximo +2 años
por evaluación y 18 en total). Cada cambio queda en `memory["development_log"]`
con fecha, edad anterior, nueva edad, motivo y número de interacción.

**Para demostraciones**, la edad se puede fijar a mano (también queda
registrado, marcado como `manual`):

```bash
ros2 topic pub --once /tr/set_age std_msgs/Int32 "data: 16"
```

## Métricas y gráficas para el TR

Cada interacción guarda en `memory["metrics"]`: palabras, número de frases,
longitud media de frase, preguntas que hace TR, palabras del usuario y la edad
en ese momento. Para generar las gráficas (en cualquier máquina con la memoria):

```bash
python3 scripts/graficas_evolucion.py --ventana 20
```

Genera `evolucion_tr.png` (edad mental, longitud de frase y preguntas por
respuesta, con los cambios de etapa marcados) y `metricas_tr.csv` (se abre
directamente con Excel).

## Emociones simuladas

TR mantiene cinco emociones numéricas (0-100): **calma, alegría, miedo,
soledad y duda existencial** ([emotions.py](tr_robot_brain/tr_robot_brain/emotions.py)).
No las decide el modelo: reaccionan a eventos reales, y el modelo solo decide
*cómo expresarlas*.

| Evento | Efecto |
|--------|--------|
| Despertar tras >1 día apagado | Miedo y soledad; lo comenta espontáneamente al arrancar |
| Despertar tras >7 días apagado | Miedo muy alto; se pregunta si se olvidaron de él |
| Que le hablen | Baja la soledad y el miedo, sube la alegría |
| >10 min sin que nadie hable | Crece la soledad; si supera 75, habla solo |
| Fallo interno (ni Claude ni Ollama responden) | Sube la duda existencial |

## Probar el cerebro sin robot

`demo_cerebro.py` usa exactamente el mismo cerebro que `brain_node`, por
consola. Necesita el Claude Agent SDK con una sesión de Claude Code, u Ollama
con `gemma2:2b` (o los dos). Al arrancar dice con qué motor piensa.

```bash
python3 scripts/demo_cerebro.py          # Linux
py -3 scripts\demo_cerebro.py            # Windows
```

En Windows, la primera vez:

```bash
py -3 -m pip install --user claude-agent-sdk requests
```

Si ya usas Claude Code en ese PC (la app de escritorio o `claude` en la
terminal), la sesión ya está iniciada. Si no, `claude auth login`.

Comandos: `/estado`, `/edad 16`, `/evaluar` (fuerza la evaluación de
maduración), `/prompt` (muestra el system prompt), `salir`.

## Registrar una persona

Con el robot en marcha y la persona mirando a la cámara:

```bash
python3 scripts/registrar_persona.py
# o bien:
ros2 topic pub --once /tr/register_person std_msgs/String "data: 'Ana:Le gusta el senderismo'"
```

La foto se guarda en el portátil, en `~/.tr_robot_ollama/persons/Ana/`. Cuando
TR reconoce a alguien por primera vez en la sesión, se lo comunica al cerebro
como una percepción y es TR quien saluda, con su voz y su edad.

## Topics ROS 2

| Topic | Tipo | Quién publica → quién escucha |
|-------|------|-------------------------------|
| `/tr/camera/image/compressed` | `sensor_msgs/CompressedImage` | camera → vision, person_recognition (QoS best effort) |
| `/tr/audio_raw` | `std_msgs/UInt8MultiArray` | audio_capture → stt (PCM int16, 16 kHz, 0,5 s) |
| `/tr/speaking` | `std_msgs/Bool` | tts → audio_capture, stt, servo |
| `/tr/speech_in` | `std_msgs/String` | stt, person_recognition → brain |
| `/tr/speech_out` | `std_msgs/String` | brain → tts |
| `/tr/status` | `std_msgs/String` | stt, brain, tts → led · también órdenes (`reset_personality`) → brain |
| `/tr/set_age` | `std_msgs/Int32` | (manual) → brain |
| `/tr/vision_description` | `std_msgs/String` | vision → brain |
| `/tr/vision_request` | `std_msgs/String` | (manual) → vision |
| `/tr/persons_detected` | `std_msgs/String` | person_recognition → (JSON `{"nombre", "confianza"}`) |
| `/tr/register_person` | `std_msgs/String` | (manual, `"nombre:descripcion"`) → person_recognition |
| `/tr/head_pose` | `std_msgs/Float32MultiArray` | (manual) → servo (`[pan, tilt]` en grados, 90 = centro) |

## Memoria (`~/.tr_robot_ollama/memory.json`, en el portátil)

| Clave | Contenido |
|-------|-----------|
| `facts` | Hechos extraídos cada 5 interacciones (nombres, gustos, rutinas) |
| `personality` | Rasgos emergentes, extraídos cada 20 interacciones |
| `developmental_age` | Edad mental actual (empieza en 12) |
| `development_log` | Historial de cambios de edad |
| `metrics` | Métricas de cada interacción |
| `log` | Últimas 500 interacciones |
| `emotions`, `last_seen` | Estado emocional y última vez que estuvo encendido |
| `total_interactions` | Contador total (el log se recorta, este no) |

La memoria se guarda cada 60 s y al cerrar. La personalidad solo se borra
publicando `reset_personality` en `/tr/status`.

## Problemas frecuentes

- **Con WSL2, la cabeza no ve al cerebro:** en Ubuntu, `wslinfo --networking-mode`
  debe decir `mirrored`; ejecuta `scripts\wsl\preparar_windows.ps1` como
  administrador; y prueba `ros2 multicast receive` en Ubuntu con
  `ros2 multicast send` en la Pi.
- **El portátil no ve los topics de la cabeza:** mismo `ROS_DOMAIN_ID` en las
  dos máquinas; comprueba el multicast (`ros2 multicast send/receive`) y, si
  falla, usa el Discovery Server. Revisa el cortafuegos del portátil (`ufw`).
- **Las imágenes no llegan pero el resto sí:** los suscriptores de la cámara
  deben usar QoS *best effort* (`qos_profile_sensor_data`); `ros2 topic echo`
  necesita `--qos-reliability best_effort`.
- **TR se oye a sí mismo:** sube el argumento `speech_end_margin` de
  `head_launch.py` (0,3 s por defecto) o aleja el micrófono del altavoz.
- **Latencia alta por Wi-Fi:** el servicio desactiva el ahorro de energía del
  Wi-Fi de la Pi; si lanzas a mano: `sudo iw dev wlan0 set power_save off`.
- **"Falta el paquete 'claude-agent-sdk'":** `pip3 install --user claude-agent-sdk`
  (Python 3.10 o más nuevo).
- **"Claude Code no tiene sesión iniciada":** `claude auth login` (ver
  *Instalación*) con el mismo usuario que lanza ROS. Hasta reiniciar
  `brain_node`, TR sigue con Ollama.
- **"Has llegado al límite de uso de tu plan de Claude":** TR sigue con Ollama
  y vuelve a probar Claude cada minuto. Sube `tareas.vision.cada_s` para gastar menos.
- **Respuestas lentas o "me he quedado en blanco":** el modelo tardó más de
  30 s (normalmente Ollama en CPU, cuando Claude no está disponible). Sube
  `chat_timeout` en `brain_launch.py` o usa un portátil con GPU.
