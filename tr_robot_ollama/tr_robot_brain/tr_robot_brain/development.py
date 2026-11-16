"""
development.py — Etapas de desarrollo de TR (edad mental) y métricas
=======================================================================
TR arranca con la mente de un niño de 12 años y madura despacio (máximo
+2 años cada 100 interacciones) según la complejidad real de sus charlas.

Este módulo es puro Python (sin ROS) para poder probarlo en cualquier PC:
  - carga config/developmental_stages.json
  - elige la etapa correspondiente a una edad
  - calcula las métricas de cada respuesta (para las gráficas del TR)
  - construye el prompt de evaluación de maduración y parsea su veredicto
"""
import json
import os
import re
from pathlib import Path

EDAD_INICIAL = 12
MAX_AVANCE_POR_EVALUACION = 2
EVALUAR_CADA = 100            # interacciones entre evaluaciones de maduración
MUESTRA_EVALUACION = 30       # interacciones que se le enseñan al modelo al evaluar

_ETAPA_POR_DEFECTO = {
    "12": {
        "nombre": "Niño de 12 años",
        "descripcion": (
            "Tienes la mente de un niño de 12 años: vocabulario sencillo, frases "
            "cortas, mucha curiosidad y preguntas a menudo. Admites cuando no "
            "entiendes algo."
        ),
        "ejemplos": [],
        "num_predict": 90,
    }
}


# ---------------------------------------------------------------------- #
# Carga de etapas
# ---------------------------------------------------------------------- #
def ruta_etapas_por_defecto() -> Path:
    """Busca developmental_stages.json: variable de entorno, share de ROS o código fuente."""
    ruta_env = os.environ.get("TR_STAGES_FILE")
    if ruta_env:
        return Path(ruta_env)
    try:
        from ament_index_python.packages import get_package_share_directory
        ruta = Path(get_package_share_directory("tr_robot_brain")) / "config" / "developmental_stages.json"
        if ruta.exists():
            return ruta
    except Exception:
        pass  # sin ROS (demo de consola) o paquete no instalado
    return Path(__file__).resolve().parents[1] / "config" / "developmental_stages.json"


def cargar_etapas(ruta: Path | None = None, log=print) -> dict[int, dict]:
    """Devuelve {edad: etapa}. Si el fichero falla, usa una etapa mínima de 12 años."""
    ruta = ruta or ruta_etapas_por_defecto()
    try:
        with open(ruta, "r", encoding="utf-8") as f:
            datos = json.load(f)
        etapas = {int(k): v for k, v in datos.items() if k.isdigit()}
        if etapas:
            return etapas
        log(f"🧠 {ruta} no contiene etapas válidas; uso la etapa por defecto.")
    except Exception as e:
        log(f"🧠 No pude cargar las etapas de desarrollo ({ruta}): {e}. Uso la etapa por defecto.")
    return {int(k): v for k, v in _ETAPA_POR_DEFECTO.items()}


def limitar_edad(edad: int, etapas: dict[int, dict]) -> int:
    return max(min(etapas), min(max(etapas), int(edad)))


def etapa_para_edad(edad: int, etapas: dict[int, dict]) -> dict:
    """La etapa con la mayor edad <= edad (ej. 13 años → etapa '12')."""
    candidatas = [e for e in etapas if e <= edad]
    return etapas[max(candidatas)] if candidatas else etapas[min(etapas)]


def texto_etapa_para_prompt(edad: int, etapas: dict[int, dict]) -> str:
    etapa = etapa_para_edad(edad, etapas)
    texto = (
        f"TU ETAPA DE DESARROLLO: {etapa.get('nombre', f'{edad} años')}.\n"
        f"{etapa.get('descripcion', '')}\n"
        f"Habla y razona como alguien de {edad} años. Aunque sepas más, no uses "
        "conocimientos ni vocabulario impropios de esa edad."
    )
    ejemplos = etapa.get("ejemplos") or []
    if ejemplos:
        texto += ("\nEjemplos del TONO de tu forma de hablar (inspírate en el estilo; "
                  "no copies estas frases ni sus palabras):\n")
        texto += "\n".join(f'- "{e}"' for e in ejemplos)
    return texto


# ---------------------------------------------------------------------- #
# Métricas por interacción
# ---------------------------------------------------------------------- #
_FIN_FRASE = re.compile(r"[.!?…]+")
_PREGUNTA = re.compile(r"\?+")


def calcular_metricas(respuesta_tr: str) -> dict:
    """Métricas de una respuesta de TR: palabras, longitud media de frase y preguntas."""
    frases = [f for f in _FIN_FRASE.split(respuesta_tr) if f.strip()]
    palabras_por_frase = [len(f.split()) for f in frases]
    total_palabras = sum(palabras_por_frase)
    return {
        "palabras": total_palabras,
        "frases": len(frases),
        "longitud_media_frase": round(total_palabras / len(frases), 2) if frases else 0.0,
        "preguntas": len(_PREGUNTA.findall(respuesta_tr)),
    }


def resumen_metricas(metricas: list[dict]) -> dict:
    """Medias de una lista de métricas (para el prompt de maduración y el README)."""
    if not metricas:
        return {"longitud_media_frase": 0.0, "preguntas_por_respuesta": 0.0, "n": 0}
    n = len(metricas)
    return {
        "longitud_media_frase": round(sum(m["longitud_media_frase"] for m in metricas) / n, 2),
        "preguntas_por_respuesta": round(sum(m["preguntas"] for m in metricas) / n, 2),
        "n": n,
    }


# ---------------------------------------------------------------------- #
# Evaluación de maduración
# ---------------------------------------------------------------------- #
# El modelo clasifica la complejidad en una categoría (a un modelo de 2B se le
# da mucho mejor clasificar que elegir un número) y la categoría da los años.
AVANCE_POR_COMPLEJIDAD = {"adecuada": 0, "superior": 1, "muy_superior": 2}


def prompt_evaluacion(edad: int, etapas: dict[int, dict], log_reciente: list[dict],
                      metricas_recientes: list[dict]) -> str:
    etapa = etapa_para_edad(edad, etapas)
    resumen = resumen_metricas(metricas_recientes)
    muestra = log_reciente[-MUESTRA_EVALUACION:]
    palabras_persona = [len(e["user"].split()) for e in log_reciente] or [0]
    conversacion = "\n".join(
        f"Persona: {e['user'][:200]}\nRobot: {e['tr'][:200]}" for e in muestra
    )
    return (
        f"Un robot tiene la mente de alguien de {edad} años "
        f"({etapa.get('nombre', '')}). Que sus respuestas sean sencillas es lo "
        "normal para su edad: NO lo juzgues por eso.\n\n"
        "Lo que debes juzgar es QUÉ LE PLANTEAN LAS PERSONAS: ¿los temas y "
        f"preguntas que le hacen son más complejos de lo que corresponde a {edad} "
        "años (temas abstractos, filosóficos, técnicos, dilemas, ironía)? Si las "
        "charlas son saludos, temas cotidianos o repetitivos, la complejidad es "
        "'adecuada'.\n\n"
        f"Datos: las personas usan de media {sum(palabras_persona) / len(palabras_persona):.1f} "
        f"palabras por mensaje; el robot, {resumen['longitud_media_frase']} palabras "
        f"por frase y {resumen['preguntas_por_respuesta']} preguntas por respuesta.\n\n"
        f"Muestra de las últimas conversaciones:\n{conversacion}\n\n"
        "Responde SOLO con este JSON, razonando primero:\n"
        '{"motivo": "una frase en español sobre lo que le plantean las personas", '
        '"complejidad": "adecuada" | "superior" | "muy_superior"}'
    )


def parsear_veredicto(texto: str) -> tuple[int, str] | None:
    """Extrae (años_a_avanzar, motivo) del JSON devuelto por el modelo."""
    inicio, fin = texto.find("{"), texto.rfind("}")
    if inicio == -1 or fin <= inicio:
        return None
    try:
        datos = json.loads(texto[inicio:fin + 1])
    except json.JSONDecodeError:
        return None
    if not isinstance(datos, dict):
        return None
    motivo = str(datos.get("motivo", "")).strip()
    complejidad = str(datos.get("complejidad", "")).strip().lower().replace(" ", "_")
    if complejidad in AVANCE_POR_COMPLEJIDAD:
        return AVANCE_POR_COMPLEJIDAD[complejidad], motivo
    try:  # compatibilidad: también acepta {"avanzar": N}
        avanzar = int(datos["avanzar"])
    except (KeyError, TypeError, ValueError):
        return None
    return max(0, min(MAX_AVANCE_POR_EVALUACION, avanzar)), motivo
