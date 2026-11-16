"""
llm.py — Motores de lenguaje de TR (sin ROS)
==============================================
CerebroTR piensa con Claude a través del Claude Agent SDK, que usa la sesión de
Claude Code de este ordenador (`claude auth login`, con tu plan de Claude): no
hace falta clave de API. Si no hay sesión, no hay internet o Claude falla,
piensa en local con Ollama (gemma2:2b) como respaldo offline. CerebroTR no sabe
qué motor contesta: le pasa una Peticion a MotorLLM y recibe texto.

Los parámetros del agente (modelo y esfuerzo de cada tarea, respaldo...) están en
config/agente_tr.json; ver agente.py. ANTHROPIC_API_KEY es opcional: si existe,
Claude Code la usa en vez de tu plan.

Diferencias entre motores con los mismos parámetros de CerebroTR:
  - num_predict: en Ollama es un tope de tokens. A Claude la longitud de la
    etapa se le pide en palabras (unas 0,6 palabras por token de gemma2).
  - temperature: claude-opus-5-5 no la admite. Lo que en Ollama era
    temperatura baja (tareas de análisis) en Claude es más esfuerzo.
  - historial: Claude recibe la misma transcripción "Usuario: …\\nTR:" que Ollama.
"""
import asyncio
import base64
import re
from dataclasses import dataclass, field
from pathlib import Path
from time import monotonic

import requests

from tr_robot_brain import agente as agente_tr

# --- Claude (Claude Agent SDK) ----------------------------------------------------
# Claude Code trae herramientas, los conectores de claude.ai de tu cuenta (Gmail,
# Drive...), skills, ajustes, CLAUDE.md y memoria. TR no debe tener nada de eso:
# sin herramientas (tools=[]), sin ajustes (setting_sources=[]) y además:
_ENV_SDK = {"ENABLE_CLAUDEAI_MCP_SERVERS": "false"}
_ARGS_SDK = {"strict-mcp-config": None, "no-session-persistence": None,
             "disable-slash-commands": None}
# Carpeta de trabajo neutra: sin CLAUDE.md ni memoria de ningún proyecto
CARPETA_CLAUDE = Path.home() / ".tr_robot_ollama"
# Claude Code añade siempre el correo de la cuenta y datos del PC (carpeta,
# sistema operativo). No se puede desactivar sin perder la sesión, así que TR
# los ignora y, por si acaso, nunca dice una dirección de correo.
_AVISO_ENTORNO = ("Tu contexto puede incluir datos técnicos del ordenador que ejecuta "
                  "tu mente (un correo, carpetas, sistema operativo, nombre del modelo). "
                  "No son tuyos ni de quien te habla: ignóralos y no los digas nunca.")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


@dataclass
class Peticion:
    """Lo que CerebroTR (o vision_node) quiere preguntar al modelo."""
    prompt: str                                   # transcripción "Usuario: …\nTR:" o instrucción
    tarea: str = "conversacion"                   # una de agente.TAREAS: elige modelo y esfuerzo
    system: list[str] = field(default_factory=list)  # partes del system prompt
    num_predict: int = 150
    timeout: float = 120
    temperature: float = 0.7
    imagen: bytes | None = None                   # JPEG para describir (vision_node)

    @property
    def es_conversacion(self) -> bool:
        """TR habla en voz alta (no es una tarea de análisis ni de visión)."""
        return self.tarea == "conversacion"


class ErrorLLM(RuntimeError):
    def __init__(self, mensaje: str, permanente: bool = False):
        super().__init__(mensaje)
        self.permanente = permanente   # p.ej. sin sesión: no vale la pena reintentar


def recortar_a_frase_completa(texto: str) -> str:
    """Si el tope de tokens cortó la respuesta a medias, la deja en la última frase entera."""
    fin = max(texto.rfind(c) for c in ".!?…")
    return texto[:fin + 1] if fin > len(texto) // 3 else texto


# ======================================================================
# Claude
# ======================================================================
class MotorClaude:
    """Claude a través del Claude Agent SDK (un proceso de Claude Code por petición)."""

    def __init__(self, agente: dict):
        self.agente = agente

    @property
    def modelo(self) -> str:
        return self.agente["claude"]["modelo"]

    @property
    def descripcion(self) -> str:
        return (f"Claude {self.modelo} vía Claude Code "
                f"(esfuerzo {agente_tr.esfuerzo_de(self.agente, 'conversacion')})")

    def generar(self, p: Peticion) -> str:
        from claude_agent_sdk import ClaudeSDKError, CLINotFoundError, ResultError

        try:
            texto = asyncio.run(asyncio.wait_for(self._preguntar(p), timeout=p.timeout))
        except (asyncio.TimeoutError, TimeoutError) as e:
            raise ErrorLLM(f"Claude no respondió a tiempo (timeout de {p.timeout:.0f}s).") from e
        except CLINotFoundError as e:
            raise ErrorLLM("No encuentro Claude Code (reinstala claude-agent-sdk).",
                           permanente=True) from e
        except ResultError as e:
            detalle = f"{e.result or ''} {e}"
            estado = getattr(e, "api_error_status", None)
            if "not logged in" in detalle.lower() or estado in (401, 403):
                raise ErrorLLM("Claude Code no tiene sesión iniciada: ejecuta 'claude auth login'.",
                               permanente=True) from e
            if estado == 429:
                raise ErrorLLM("Has llegado al límite de uso de tu plan de Claude.") from e
            raise ErrorLLM(f"Claude devolvió un error: {(e.result or str(e))[:200]}") from e
        except ClaudeSDKError as e:
            raise ErrorLLM(f"Error del Claude Agent SDK: {str(e)[:200]}") from e
        return _EMAIL.sub("", texto).strip()

    async def _preguntar(self, p: Peticion) -> str:
        from claude_agent_sdk import (AssistantMessage, ClaudeAgentOptions, ResultMessage,
                                      TextBlock, query)

        system = [t for t in p.system if t]
        if p.es_conversacion:
            por_token = self.agente["claude"]["palabras_por_token"]
            palabras = max(15, round(p.num_predict * por_token))
            system.append("Hablas en tiempo real y la persona espera: empieza a responder "
                          f"enseguida y di como mucho unas {palabras} palabras.")
        system.append(_AVISO_ENTORNO)
        CARPETA_CLAUDE.mkdir(parents=True, exist_ok=True)
        opciones = ClaudeAgentOptions(
            system_prompt="\n\n".join(system),
            model=agente_tr.modelo_de(self.agente, p.tarea),
            fallback_model=self.agente["claude"]["modelo_alternativo"] or None,
            effort=agente_tr.esfuerzo_de(self.agente, p.tarea),
            tools=[], setting_sources=[], max_turns=1, cwd=str(CARPETA_CLAUDE),
            env=dict(_ENV_SDK), extra_args=dict(_ARGS_SDK),
        )
        # Las imágenes solo se pueden mandar en modo streaming (un generador de mensajes)
        prompt = p.prompt if p.imagen is None else _mensaje_con_imagen(p.prompt, p.imagen)

        partes, resultado, error = [], None, None
        async for m in query(prompt=prompt, options=opciones):
            if isinstance(m, AssistantMessage):
                error = error or m.error
                partes += [b.text for b in m.content if isinstance(b, TextBlock)]
            elif isinstance(m, ResultMessage):
                resultado = m

        if error in ("authentication_failed", "billing_error"):
            raise ErrorLLM(f"Claude Code no puede usar tu cuenta ({error}): ejecuta "
                           "'claude auth login'.", permanente=True)
        if error:
            raise ErrorLLM(f"Claude devolvió un error ({error}).")
        if resultado is not None and resultado.stop_reason == "refusal":
            # No se reintenta con Ollama: lo que Claude rechaza no lo debe decir TR
            return ""
        if resultado is not None and resultado.result:
            return resultado.result
        return "".join(partes)


async def _mensaje_con_imagen(texto: str, jpeg: bytes):
    yield {"type": "user", "message": {"role": "user", "content": [
        {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                     "data": base64.standard_b64encode(jpeg).decode("ascii")}},
        {"type": "text", "text": texto},
    ]}}


# ======================================================================
# Ollama
# ======================================================================
class MotorOllama:
    def __init__(self, modelo: str, url: str):
        self.modelo = modelo
        self.url = url

    @property
    def descripcion(self) -> str:
        return f"Ollama {self.modelo} (local)"

    def generar(self, p: Peticion) -> str:
        opciones = {"num_predict": p.num_predict, "temperature": p.temperature, "top_p": 0.9}
        if p.es_conversacion:
            # Corta si el modelo empieza a alucinar el turno siguiente
            opciones["stop"] = ["Usuario:", "\nTR:"]
            opciones["repeat_penalty"] = 1.15
        payload = {
            "model": self.modelo,
            "prompt": p.prompt,
            "system": "\n\n".join(t for t in p.system if t),
            "stream": False,
            "options": opciones,
        }
        try:
            response = requests.post(self.url, json=payload, timeout=p.timeout)
            response.raise_for_status()
            datos = response.json()
        except requests.exceptions.Timeout as e:
            raise ErrorLLM(f"Ollama no respondió a tiempo (timeout de {p.timeout:.0f}s).") from e
        except requests.exceptions.ConnectionError as e:
            raise ErrorLLM("No puedo conectar con Ollama en localhost:11434. "
                           "¿Está arrancado el servicio ('ollama serve')?") from e
        except Exception as e:
            raise ErrorLLM(f"Error llamando a Ollama: {e}") from e
        texto = datos.get("response", "").strip()
        if p.es_conversacion and datos.get("done_reason") == "length":
            texto = recortar_a_frase_completa(texto)
        return texto


# ======================================================================
# Motor principal con respaldo
# ======================================================================
class MotorLLM:
    """Prueba el motor principal y, si falla, el de respaldo."""

    def __init__(self, principal, respaldo=None, log_info=print, log_error=print,
                 pausa_tras_fallo_s: float = 60):
        self.principal = principal
        self.respaldo = respaldo
        self.log_info = log_info
        self.log_error = log_error
        self.pausa_tras_fallo_s = pausa_tras_fallo_s
        self._pausado_hasta = 0.0

    @property
    def descripcion(self) -> str:
        if self.principal is None:
            return self.respaldo.descripcion
        if self.respaldo is None:
            return self.principal.descripcion
        return f"{self.principal.descripcion}, con {self.respaldo.descripcion} de respaldo"

    def generar(self, p: Peticion) -> str | None:
        """Devuelve el texto, o None si ningún motor ha podido responder."""
        if self.principal is not None and monotonic() >= self._pausado_hasta:
            try:
                return self.principal.generar(p)
            except ErrorLLM as e:
                if e.permanente:
                    self.log_error(f"🧠 {e} Dejo de usar {self.principal.descripcion} en esta sesión.")
                    self.principal = None
                elif self.respaldo is not None:
                    self._pausado_hasta = monotonic() + self.pausa_tras_fallo_s
                    self.log_error(f"🧠 {e} Uso {self.respaldo.descripcion} durante "
                                   f"{self.pausa_tras_fallo_s:g} s.")
                else:
                    self.log_error(f"🧠 {e}")
                    return None
        if self.respaldo is None:
            return None
        try:
            return self.respaldo.generar(p)
        except ErrorLLM as e:
            self.log_error(f"🧠 {e}")
            return None


def crear_claude(agente: dict, log_error=print, prefijo: str = "🧠") -> MotorClaude | None:
    """Claude con los parámetros del agente, o None si el motor es ollama o falta
    el paquete claude-agent-sdk. La sesión de Claude Code se comprueba en la
    primera petición. Lo usan crear_motor y vision_node."""
    if agente["motor"] == "ollama":
        return None
    try:
        import claude_agent_sdk  # noqa: F401
    except ImportError:
        log_error(f"{prefijo} Falta el paquete 'claude-agent-sdk' "
                  "(pip install claude-agent-sdk): uso solo Ollama.")
        return None
    return MotorClaude(agente)


def crear_motor(agente: dict, log_info=print, log_error=print) -> MotorLLM:
    """Monta el motor de CerebroTR según los parámetros del agente (agente.py)."""
    ollama = MotorOllama(agente["ollama"]["modelo"], agente["ollama"]["url"])
    claude = crear_claude(agente, log_error)
    if claude is None:
        return MotorLLM(ollama, log_info=log_info, log_error=log_error)
    return MotorLLM(claude, ollama if agente["ollama"]["respaldo"] else None,
                    log_info=log_info, log_error=log_error,
                    pausa_tras_fallo_s=agente["claude"]["pausa_tras_fallo_s"])
