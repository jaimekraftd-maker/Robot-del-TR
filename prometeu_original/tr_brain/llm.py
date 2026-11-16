"""
tr_brain.llm — Envoltura del modelo de lenguaje (Gemini)
========================================================
Aísla al resto del cerebro de la librería concreta (google-generativeai).

Si no hay clave o la librería no está instalada, entra en MODO OFFLINE: el
robot sigue funcionando (memoria, aprendizaje heurístico, iniciativa) aunque
sin generación de lenguaje rica.

AUTO-REPARACIÓN DE MODELOS: los nombres de modelo de Gemini cambian con el
tiempo (p. ej. gemini-1.5-flash fue retirado). Si el modelo configurado da
404 / NotFound, se consulta la lista de modelos disponibles y se elige uno que
soporte generateContent (preferentemente 'flash'), reintentando una vez.
"""
import json
import logging
from typing import List, Dict
from . import config

log = logging.getLogger("tr_brain.llm")


class LLM:
    def __init__(self):
        self.disponible = False
        self._genai = None
        self._modelo_override = None      # se rellena si hay que autoseleccionar modelo
        try:
            import warnings
            with warnings.catch_warnings():
                # silencia el FutureWarning de deprecación del SDK antiguo
                warnings.simplefilter("ignore")
                import google.generativeai as genai  # import perezoso
            if config.GEMINI_API_KEY:
                genai.configure(api_key=config.GEMINI_API_KEY)
                self._genai = genai
                self.disponible = True
                log.info(f"LLM listo ({config.MODELO_CHAT}).")
            else:
                log.warning("Sin GEMINI_API_KEY: LLM en modo OFFLINE.")
        except Exception as e:
            log.warning(f"google-generativeai no disponible ({e}): modo OFFLINE.")

    def _modelo(self, por_defecto):
        return self._modelo_override or por_defecto

    # --- conversación con historial e instrucción de sistema -----------------
    def chat(self, system_prompt: str, historial: List[Dict], texto_usuario: str) -> str:
        if not self.disponible:
            return self._offline(texto_usuario)
        for intento in (1, 2):
            try:
                model = self._genai.GenerativeModel(
                    model_name=self._modelo(config.MODELO_CHAT),
                    system_instruction=system_prompt,
                    generation_config={"max_output_tokens": config.MAX_TOKENS,
                                       "temperature": config.TEMP_CHAT},
                )
                chat = model.start_chat(history=historial)
                return chat.send_message(texto_usuario).text.strip()
            except Exception as e:
                if intento == 1 and self._es_modelo_no_encontrado(e) and self._autoseleccionar_modelo():
                    continue
                if self._es_cuota(e):
                    log.warning("Cuota de Gemini agotada (free tier). Espera un minuto, usa "
                                "gemini-2.5-flash-lite o activa facturación.")
                    return "Uf, hoy he pensado mucho y necesito descansar un momento. ¿Lo intentamos en un minuto?"
                log.error(f"Error en chat: {e}")
                return "Perdona, me he liado un momento. ¿Me lo repites?"

    # --- generación de un solo turno (extracción de hechos, iniciativa...) ----
    def generar(self, prompt: str, temperatura: float = config.TEMP_EXTRACT,
                max_tokens: int = 256) -> str:
        if not self.disponible:
            return ""
        for intento in (1, 2):
            try:
                model = self._genai.GenerativeModel(
                    model_name=self._modelo(config.MODELO_EXTRACT),
                    generation_config={"max_output_tokens": max_tokens,
                                       "temperature": temperatura},
                )
                return model.generate_content(prompt).text.strip()
            except Exception as e:
                if intento == 1 and self._es_modelo_no_encontrado(e) and self._autoseleccionar_modelo():
                    continue
                if self._es_cuota(e):
                    log.warning("Cuota de Gemini agotada al generar; lo omito por ahora.")
                    return ""
                log.warning(f"Error en generar: {e}")
                return ""

    # --- visión: describir/reaccionar a una imagen --------------------------
    def describir_imagen(self, imagen_jpeg: bytes, prompt: str) -> str:
        """Envía una imagen (JPEG en bytes) + un prompt y devuelve la respuesta.
        Gemini Flash/Flash-Lite son multimodales. Vacío si offline o error."""
        if not self.disponible or not imagen_jpeg:
            return ""
        for intento in (1, 2):
            try:
                model = self._genai.GenerativeModel(
                    model_name=self._modelo(config.MODELO_CHAT),
                    generation_config={"max_output_tokens": config.MAX_TOKENS,
                                       "temperature": config.TEMP_CHAT},
                )
                r = model.generate_content(
                    [{"mime_type": "image/jpeg", "data": imagen_jpeg}, prompt])
                return r.text.strip()
            except Exception as e:
                if intento == 1 and self._es_modelo_no_encontrado(e) and self._autoseleccionar_modelo():
                    continue
                if self._es_cuota(e):
                    log.warning("Cuota de Gemini agotada al mirar la imagen.")
                    return ""
                log.warning(f"Error al describir imagen: {e}")
                return ""

    # --- auto-reparación de nombre de modelo --------------------------------
    @staticmethod
    def _es_modelo_no_encontrado(e) -> bool:
        t = str(e).lower()
        return "404" in t or "not found" in t or "is not supported" in t

    @staticmethod
    def _es_cuota(e) -> bool:
        t = str(e).lower()
        return "429" in t or "quota" in t or "resource_exhausted" in t or "rate limit" in t

    def _autoseleccionar_modelo(self) -> bool:
        """Busca un modelo disponible que soporte generateContent (pref. 'flash')."""
        try:
            disponibles = [
                m.name for m in self._genai.list_models()
                if "generateContent" in getattr(m, "supported_generation_methods", [])
            ]
        except Exception as e:
            log.error(f"No pude listar los modelos de Gemini: {e}")
            return False
        if not disponibles:
            return False
        flash = [m for m in disponibles if "flash" in m.lower()]
        elegido = (flash or disponibles)[0].replace("models/", "")
        self._modelo_override = elegido
        log.warning(f"El modelo configurado no está disponible; uso '{elegido}'. "
                    f"Fíjalo con  setx TR_MODELO_CHAT \"{elegido}\"  para evitar la búsqueda.")
        return True

    @staticmethod
    def _offline(texto: str) -> str:
        return ("(modo sin modelo) Te he escuchado y lo guardé en memoria. "
                "Configura GEMINI_API_KEY para que pueda responderte de verdad.")

    @staticmethod
    def parsear_json(crudo: str):
        """Extrae con tolerancia el primer bloque JSON de una respuesta del modelo."""
        if not crudo:
            return None
        crudo = crudo.replace("```json", "").replace("```", "").strip()
        try:
            return json.loads(crudo)
        except Exception:
            for ab, ce in (("[", "]"), ("{", "}")):
                i, j = crudo.find(ab), crudo.rfind(ce)
                if i != -1 and j != -1 and j > i:
                    try:
                        return json.loads(crudo[i:j + 1])
                    except Exception:
                        pass
        return None
