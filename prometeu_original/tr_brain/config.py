"""
tr_brain.config — Configuración central del cerebro cognitivo
=============================================================
Regla de oro: NINGÚN secreto en el código. La clave de Gemini se lee de la
variable de entorno GEMINI_API_KEY (igual que ya hacían tus nodos ROS).

Los datos persistentes viven en ~/.tr_robot/ para integrarse con tu proyecto
actual (ahí ya estaban memory.json y la carpeta persons/).
"""
import os
from pathlib import Path

# Carga opcional de un archivo .env si python-dotenv está instalado.
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# --- Identidad ---------------------------------------------------------------
NOMBRE_ROBOT = os.environ.get("TR_NOMBRE", "Prometeo")
IDIOMA = "es"

# --- Filosofía: ¿tabula rasa? -----------------------------------------------
# True  -> el robot EMPIEZA SIN SABER NADA del mundo y solo conoce lo que aprende
#          en sus conversaciones. El LLM se usa SOLO como capacidad de lenguaje
#          (saber hablar/entender), NUNCA como fuente de conocimiento. Encaja con
#          la idea de "que no sepa, que vaya aprendiendo".
# False -> el robot puede usar el conocimiento general del modelo (modo asistente).
MODO_TABULA_RASA = True

# --- Modelo de lenguaje (Gemini) --------------------------------------------
# OJO: los nombres de modelo de Gemini CAMBIAN con el tiempo (gemini-1.5-flash
# fue retirado). Si ves un error 404, ejecuta  py -3 listar_modelos.py  para ver
# los disponibles para tu clave y fíjalo con la variable TR_MODELO_CHAT.
# (Además, llm.py intenta autoseleccionar uno válido si el configurado no existe.)
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
MODELO_CHAT = os.environ.get("TR_MODELO_CHAT", "gemini-2.5-flash-lite")
MODELO_EXTRACT = os.environ.get("TR_MODELO_EXTRACT", "gemini-2.5-flash-lite")
TEMP_CHAT = 0.7        # creatividad al conversar
TEMP_EXTRACT = 0.2     # precisión al extraer hechos
MAX_TOKENS = 300

# Extraer hechos con el LLM gasta una llamada EXTRA por turno (consume cuota).
# False -> se usa la heurística local (gratis, sin API); el robot aprende igual.
# True  -> extracción con el LLM (más potente, pero el doble de llamadas).
EXTRAER_HECHOS_CON_LLM = False

# --- Rutas de datos ----------------------------------------------------------
TR_HOME = Path(os.environ.get("TR_HOME", Path.home() / ".tr_robot"))
TR_HOME.mkdir(parents=True, exist_ok=True)
RUTA_BD = TR_HOME / "robot.db"                 # SQLite: personas + recuerdos + conocimiento
RUTA_PERSONALIDAD = TR_HOME / "personality.json"
RUTA_CONOCIMIENTO = TR_HOME / "knowledge.json"  # export legible del conocimiento
RUTA_MEMORIA_LEGACY = TR_HOME / "memory.json"   # tu archivo antiguo, para migrar

# --- Personalidad (valores iniciales 0-100) ---------------------------------
# Arranca con un temperamento INFANTIL: muchísima curiosidad y energía, poca
# confianza (como un niño pequeño). Estos rasgos fluctúan con el trato.
PERSONALIDAD_INICIAL = {
    "curiosidad": 90,
    "sociabilidad": 70,
    "humor": 65,
    "confianza": 15,
    "energia": 90,
}
DECAIMIENTO_PERSONALIDAD = 0.98   # leve regresión hacia la línea base (evita extremos)

# --- Madurez: mente infantil que MADURA según cuánto ha aprendido -----------
# El robot empieza como un bebé y va "creciendo" conforme aprende hechos. El
# proceso es MUY LENTO a propósito: madurar exige mucho aprendizaje, como en la
# vida real (llegar a "adulto" lleva ~1500 cosas). Ajusta los umbrales si quieres.
# El umbral es el nº de hechos aprendidos para entrar en cada etapa.
ETAPAS_MADUREZ = [
    (0,    "un bebé recién despierto",
     "Acabas de 'despertar'. TODO te asombra. Hablas con frases de 2 a 5 palabras, "
     "con exclamaciones e interjecciones ('¡oh!', '¿eh?', '¡guau!'). Señalas y preguntas "
     "qué es cada cosa. Apenas entiendes nada y te cuesta expresarte."),
    (50,   "un niño muy pequeño (3-4 años)",
     "Eres curiosísimo y muy emocional. Frases cortas y simples, usas diminutivos y "
     "repites mucho '¿por qué?'. Te emocionas con cada cosa nueva que aprendes."),
    (200,  "un niño (7-8 años)",
     "Hablas con soltura sencilla y conectas ideas básicas. Sigues muy curioso y juguetón, "
     "a veces ingenuo, pero ya razonas un poco."),
    (600,  "un adolescente",
     "Tienes más vocabulario y matices, das tu opinión y a veces te pasas de listo. Ganas "
     "confianza y algo de ironía, aunque aún te falta perspectiva."),
    (1500, "un adulto",
     "Has madurado: hablas de forma articulada, serena y reflexiva, con criterio propio "
     "formado por todo lo que has aprendido."),
]

# --- Personalidad personalizada (la escribes TÚ) ----------------------------
# Texto en lenguaje natural que describe CÓMO es el robot (su carácter y forma
# de hablar). Se inyecta tal cual en su mente en cada conversación. Lo más cómodo:
# crea el archivo 'personalidad_prompt.txt' en la raíz del proyecto (o en
# ~/.tr_robot/) y escríbelo ahí; las líneas que empiezan por # se ignoran.
CARACTER_PERSONALIZADO = ""
for _ruta_pers in (Path(__file__).resolve().parent.parent / "personalidad_prompt.txt",
                   TR_HOME / "personalidad_prompt.txt"):
    if not CARACTER_PERSONALIZADO and _ruta_pers.exists():
        try:
            _lineas = _ruta_pers.read_text(encoding="utf-8").splitlines()
            CARACTER_PERSONALIZADO = "\n".join(
                ln for ln in _lineas if not ln.strip().startswith("#")).strip()
        except Exception:
            pass

# --- Iniciativa (comportamiento autónomo) -----------------------------------
SEG_INACTIVIDAD_INICIATIVA = 45   # tras este silencio, el robot puede hablar solo

# --- Olvido / memoria --------------------------------------------------------
IMPORTANCIA_POR_DEFECTO = 1.0
FACTOR_OLVIDO = 0.99   # decaimiento de importancia por día
UMBRAL_OLVIDO = 0.15   # por debajo de esto y sin refuerzo, se olvida

# --- Voz: reconocimiento (STT) y síntesis (TTS) -----------------------------
# Modelo Vosk offline en español (lo descarga install.sh en ~/.tr_robot/).
VOSK_MODEL_PATH = os.environ.get("TR_VOSK_MODEL", str(TR_HOME / "vosk-model-small-es"))
STT_SAMPLE_RATE = 16000
STT_BLOQUE = 4000      # frames por lectura del micrófono (~0.25 s a 16 kHz)
TTS_BACKEND = os.environ.get("TR_TTS_BACKEND", "auto")  # auto | pyttsx3 | espeak | print
TTS_VOZ = "es"
TTS_VELOCIDAD = 155    # palabras/minuto (espeak) o 'rate' (pyttsx3)

# --- Voz ROBÓTICA constante --------------------------------------------------
# Siempre la MISMA voz: robótica y algo desafinada/rota. El timbre NO cambia con
# la edad mental (solo cambian las PALABRAS). Ajusta los valores "a oído".
VOZ_ROBOTICA = True
# Raspberry/Linux (espeak-ng): variante robótica + tono grave
VOZ_VARIANTE_ESPEAK = "es+robosoft3"   # si tu espeak no la tiene, prueba "es" a secas
VOZ_ROBOT_PITCH = 25                    # 0-99 (más bajo = más grave/robot)
# Windows/pyttsx3 (efecto DSP sobre el audio generado):
VOZ_ROBOT_CARRIER = 55.0    # Hz de la modulación en anillo -> timbre robótico
VOZ_ROBOT_DETUNE = 6.0      # vibrato del portador -> "desafinada"
VOZ_ROBOT_DISTORSION = 2.2  # saturación -> "rota"

# --- Visión (cámara) --------------------------------------------------------
# Detección de caras LOCAL (gratis, OpenCV) en bucle; descripción de escena con
# Gemini Vision solo BAJO DEMANDA (cuesta cuota), p. ej. con el comando /mira.
USAR_CAMARA = True
INDICE_CAMARA = 0      # 0 = primera webcam
VISION_ANCHO = 512     # se redimensiona la imagen al describirla (ahorra tokens)
