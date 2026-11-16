"""
agente.py — Parámetros del agente de Claude que hace de TR (sin ROS)
======================================================================
Carga config/agente_tr.json: la identidad de TR, qué modelo y cuánto esfuerzo
usa Claude en cada tarea (conversación, hechos, personalidad, maduración y
visión), cada cuánto mira la cámara y el respaldo local con Ollama.

Prioridad: variables de entorno TR_* > agente_tr.json > POR_DEFECTO (los mismos
valores que trae el fichero, por si falta o está roto).
"""
import copy
import json
import os
from pathlib import Path

TAREAS = ("conversacion", "hechos", "personalidad", "maduracion", "vision")
ESFUERZOS = ("low", "medium", "high", "xhigh", "max")
MOTORES = ("claude", "ollama")

POR_DEFECTO = {
    "motor": "claude",
    "identidad": (
        "Eres TR, un robot físico con cuerpo propio: una cabeza con cámara, "
        "micrófono, altavoz y una mandíbula que se mueve cuando hablas. "
        "Habla siempre en español. Todo lo que dices se pronuncia en voz alta, "
        "así que no uses emojis, listas ni formato."
    ),
    "claude": {
        "modelo": "claude-opus-5-5",
        "modelo_alternativo": "",
        "palabras_por_token": 0.6,
        "pausa_tras_fallo_s": 60,
    },
    "tareas": {
        "conversacion": {"esfuerzo": "low", "modelo": ""},
        "hechos": {"esfuerzo": "medium", "modelo": ""},
        "personalidad": {"esfuerzo": "medium", "modelo": ""},
        "maduracion": {"esfuerzo": "medium", "modelo": ""},
        "vision": {"esfuerzo": "low", "modelo": "", "cada_s": 60, "max_palabras": 60, "timeout_s": 30},
    },
    "ollama": {
        "modelo": "gemma2:2b",
        "respaldo": True,
        "url": "http://localhost:11434/api/generate",
    },
}


def ruta_por_defecto() -> Path:
    """Busca agente_tr.json: variable de entorno, share de ROS o código fuente."""
    ruta_env = os.environ.get("TR_AGENT_FILE")
    if ruta_env:
        return Path(ruta_env)
    try:
        from ament_index_python.packages import get_package_share_directory
        ruta = Path(get_package_share_directory("tr_robot_brain")) / "config" / "agente_tr.json"
        if ruta.exists():
            return ruta
    except Exception:
        pass  # sin ROS (demo de consola) o paquete no instalado
    return Path(__file__).resolve().parents[1] / "config" / "agente_tr.json"


def cargar(ruta: Path | None = None, log=print) -> dict:
    """Devuelve los parámetros del agente, ya mezclados y validados."""
    agente = copy.deepcopy(POR_DEFECTO)
    ruta = ruta or ruta_por_defecto()
    try:
        # utf-8-sig: el Bloc de notas y PowerShell de Windows a veces añaden un BOM
        with open(ruta, "r", encoding="utf-8-sig") as f:
            _mezclar(agente, json.load(f), "", log)
    except FileNotFoundError:
        log(f"🧠 No encuentro {ruta}; uso los parámetros del agente por defecto.")
    except Exception as e:
        log(f"🧠 No pude leer {ruta} ({e}); uso los parámetros del agente por defecto.")
    _aplicar_entorno(agente, log)
    _validar(agente, log)
    return agente


def modelo_de(agente: dict, tarea: str) -> str:
    return agente["tareas"].get(tarea, {}).get("modelo") or agente["claude"]["modelo"]


def esfuerzo_de(agente: dict, tarea: str) -> str:
    return agente["tareas"].get(tarea, agente["tareas"]["conversacion"])["esfuerzo"]


def _mezclar(base: dict, nuevo: dict, ruta: str, log):
    """Copia los valores del fichero sobre los de por defecto, avisando de claves raras."""
    for clave, valor in nuevo.items():
        if clave.startswith("_"):
            continue  # comentarios
        if clave not in base:
            log(f"🧠 agente_tr.json: '{ruta}{clave}' no es un parámetro conocido; lo ignoro.")
        elif isinstance(base[clave], dict):
            if isinstance(valor, dict):
                _mezclar(base[clave], valor, f"{ruta}{clave}.", log)
            else:
                log(f"🧠 agente_tr.json: '{ruta}{clave}' debería ser un objeto; lo ignoro.")
        elif isinstance(base[clave], bool) != isinstance(valor, bool) or \
                (isinstance(base[clave], (int, float)) and not isinstance(valor, (int, float))):
            log(f"🧠 agente_tr.json: '{ruta}{clave}' tiene un tipo incorrecto ({valor!r}); lo ignoro.")
        else:
            base[clave] = valor


def _aplicar_entorno(agente: dict, log):
    env = os.environ
    if env.get("TR_LLM"):
        agente["motor"] = env["TR_LLM"].strip().lower()
    if env.get("TR_CLAUDE_MODEL"):
        agente["claude"]["modelo"] = env["TR_CLAUDE_MODEL"].strip()
    if env.get("TR_CLAUDE_EFFORT"):
        agente["tareas"]["conversacion"]["esfuerzo"] = env["TR_CLAUDE_EFFORT"].strip()
    if env.get("TR_CLAUDE_EFFORT_ANALISIS"):
        for tarea in ("hechos", "personalidad", "maduracion"):
            agente["tareas"][tarea]["esfuerzo"] = env["TR_CLAUDE_EFFORT_ANALISIS"].strip()
    if env.get("TR_OLLAMA_MODEL"):
        agente["ollama"]["modelo"] = env["TR_OLLAMA_MODEL"].strip()
    if env.get("TR_OLLAMA_FALLBACK"):
        agente["ollama"]["respaldo"] = env["TR_OLLAMA_FALLBACK"].strip() != "0"
    if env.get("TR_VISION_CLAUDE_SEC"):
        try:
            agente["tareas"]["vision"]["cada_s"] = float(env["TR_VISION_CLAUDE_SEC"])
        except ValueError:
            log(f"🧠 TR_VISION_CLAUDE_SEC={env['TR_VISION_CLAUDE_SEC']!r} no es un número; lo ignoro.")


def _validar(agente: dict, log):
    if agente["motor"] not in MOTORES:
        log(f"🧠 motor '{agente['motor']}' no válido (claude | ollama); uso claude.")
        agente["motor"] = "claude"
    for tarea in TAREAS:
        esfuerzo = agente["tareas"][tarea]["esfuerzo"]
        if esfuerzo not in ESFUERZOS:
            por_defecto = POR_DEFECTO["tareas"][tarea]["esfuerzo"]
            log(f"🧠 esfuerzo '{esfuerzo}' de '{tarea}' no válido ({' | '.join(ESFUERZOS)}); "
                f"uso {por_defecto}.")
            agente["tareas"][tarea]["esfuerzo"] = por_defecto
    vision = agente["tareas"]["vision"]
    for clave in ("cada_s", "max_palabras", "timeout_s"):
        if vision[clave] <= 0:
            log(f"🧠 tareas.vision.{clave} debe ser mayor que 0; uso {POR_DEFECTO['tareas']['vision'][clave]}.")
            vision[clave] = POR_DEFECTO["tareas"]["vision"][clave]
