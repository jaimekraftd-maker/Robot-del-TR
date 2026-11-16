# Hoja de ruta — TR Robot (2 años)

Robot que **evoluciona durante años**. El principio rector: el **cerebro
(`tr_brain`) crece independiente del hardware**, y el hardware se añade en fases
sin reescribir la inteligencia. Cada fase deja algo **funcionando y medible**.

Fechas relativas al inicio del proyecto. Ajusta a tu calendario.

---

## ✅ Fase 0 — Cerebro base (Mes 0–1) · *hecho ahora*
- Núcleo cognitivo portable `tr_brain`: memoria SQLite, aprendizaje
  (extracción + refuerzo + olvido), personalidad evolutiva, iniciativa.
- Modo OFFLINE para desarrollar sin clave/conexión.
- Demo de consola para validar comportamiento sin hardware.
- Integración con el `brain_node` de ROS + Gemini existente.
- **Seguridad:** clave de API fuera del código.

## 🟨 Fase 1 — Voz y bucle conversacional completo (Mes 2–3) · *en curso*
- ✅ **Nodo de voz**: STT con **Vosk** (offline) → `/tr/speech_in`; TTS con
  `pyttsx3`/`espeak-ng` ← `/tr/speech_out`; se silencia el micro mientras habla.
  (`tr_brain/voice.py` + `ros_nodes/voice_node.py`; pruébalo con `demo_voz.py`).
- ✅ **Empaquetado ROS**: paquete ament_python `tr_robot` (`package.xml`,
  `setup.py`, `setup.cfg`) + `launch/tr_launch.py` que arranca los 4 nodos con
  `ros2 launch tr_robot tr_launch.py`.
- Conversación continua de principio a fin sobre la mesa (sin cuerpo aún).
- **Hito medible:** mantener una charla hablada de 5 min y recordar datos al día siguiente.

## 🟦 Fase 2 — Memoria semántica y mejor aprendizaje (Mes 4–6)
- **Embeddings** (Gemini `text-embedding-004`) para `buscar_recuerdo` por
  significado, no solo por palabras. Índice vectorial (SQLite + numpy o `sqlite-vec`).
- Consolidación tipo "sueño": resumen nocturno de recuerdos del día en hechos
  duraderos; fortalece lo importante, poda lo trivial.
- Métricas de aprendizaje: nº de hechos, confianza media, tasa de olvido.
- **Hito:** responder "¿qué hablamos la semana pasada de X?" de forma fiable.

## 🟦 Fase 3 — Cuerpo físico v1 (Mes 7–10)
- Cabeza impresa en 3D; **Raspberry Pi 5** (o Jetson Orin Nano si se quiere
  inferencia local), cámara, micro y altavoz integrados.
- **HAL real** (`hardware.py` → `RaspberryPiHardware`): 2–3 servos de cuello
  (yaw/pitch) vía `adafruit-servokit`, envuelto en un `hardware_node` ROS que
  escuche `/tr/head_cmd`.
- **Seguimiento de rostro** con los servos (la cabeza mira a quien habla).
- **Hito:** el robot orienta la cabeza hacia la persona detectada.

## 🟦 Fase 4 — Expresividad (Mes 11–15)
- **Ojos OLED** (2 pantallas SSD1306/redondas): parpadeo, dirección de mirada.
- **Expresiones** ligadas al estado: la personalidad y el tono de la respuesta
  eligen una expresión (`expresion("alegre"/"pensativo"/...)`).
- Sincronización labial básica o indicador de "hablando".
- **Hito:** una persona percibe estados de ánimo distintos sin leer la pantalla.

## 🟦 Fase 5 — Autonomía cognitiva (Mes 16–20)
- **Intereses emergentes**: el robot detecta temas recurrentes y desarrolla
  preferencias propias que sesgan su iniciativa y sus preguntas.
- **Objetivos propios** simples (p. ej. "conocer mejor a las personas nuevas").
- Detección de emoción por voz/rostro como entrada extra al cerebro.
- (Opcional) **LLM local** (Llama/Gemma cuantizado) para privacidad/latencia,
  detrás de la misma interfaz `llm.py` que ya abstrae el proveedor.
- **Hito:** el robot inicia conversaciones coherentes con su "historia" acumulada.

## 🟦 Fase 6 — Investigación y evaluación (Mes 21–24)
- Estudios longitudinales: registrar cómo evoluciona la personalidad y el
  conocimiento a lo largo de meses (los JSON/SQLite ya lo permiten).
- Estudios con usuarios; cuestionarios de percepción ("¿parece que aprende?").
- Dataset reproducible, documentación científica, posible publicación.
- Robustez: tests automáticos del núcleo, *backups* de la BD, recuperación.

---

## Temas transversales (todas las fases)
- **Tests**: el núcleo es puro Python → cubrir con `pytest` (memoria, aprendizaje, olvido).
- **Privacidad**: datos personales en local; política de retención/olvido clara.
- **Versionado del "cerebro"**: guardar instantáneas de `robot.db`/personalidad
  para comparar etapas y poder revertir.
- **Seguridad**: claves solo en entorno; revisar dependencias.

## Lista de compra orientativa (hardware)
Raspberry Pi 5 (8 GB) + fuente · cámara (Pi Camera v3 o USB) · micrófono USB o
ReSpeaker · mini altavoz amplificado · 2–3 servos (MG90S/MG996R) + HAT PCA9685
· 2 OLED (I²C) · piezas impresas en 3D · batería/UPS.
