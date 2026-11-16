"""
cerebro.py — Núcleo cognitivo de TR (sin ROS)
================================================
Toda la "mente" de TR vive aquí, independiente de ROS, para que la usen
igual brain_node.py (en el robot) y scripts/demo_cerebro.py (en cualquier PC):

  - Conversación con Claude (claude-opus-5-5, vía Claude Agent SDK), con
    historial corto; sin sesión de Claude o internet, con Ollama (gemma2:2b) en
    local (ver llm.py)
  - Memoria persistente en ~/.tr_robot_ollama/memory.json
  - Hechos extraídos cada 5 interacciones
  - Personalidad emergente cada 20 interacciones
  - Etapa de desarrollo (edad mental, empieza en 12) y maduración cada 100
  - Métricas por interacción para las gráficas del Treball de Recerca
  - Estado emocional simulado (emotions.py)

Las tareas de aprendizaje (hechos, personalidad, maduración) se ejecutan en un
hilo daemon aparte para no retrasar las respuestas.
"""
import json
import queue
import re
import threading
import unicodedata
from collections import Counter
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

from tr_robot_brain import agente as agente_tr
from tr_robot_brain import development as dev
from tr_robot_brain.emotions import EstadoEmocional, humanizar_segundos, segundos_desde
from tr_robot_brain.llm import MotorLLM, Peticion, crear_motor

# --- Tiempos de espera del modelo ----------------------------------------------
TIMEOUT_CHAT_SEC = 30
TIMEOUT_ANALISIS_SEC = 120

# --- Configuración de memoria ------------------------------------------------
MEMORY_DIR_POR_DEFECTO = Path.home() / ".tr_robot_ollama"
# Cuanto más historial, más material tiene gemma2:2b para copiarse a sí mismo
MAX_HISTORY = 10          # turnos de conversación en el prompt
MAX_LOG = 500             # entradas máximas del log de interacciones
MAX_METRICS = 20000       # métricas guardadas (una por interacción)
MAX_FACTS_EN_PROMPT = 30
FACTS_EVERY = 5
PERSONALITY_EVERY = 20
SOLEDAD_HABLA_SOLA = 75   # umbral de soledad para hablar espontáneamente
VENTANA_REPETICION = 10   # respuestas recientes con las que se compara una nueva
MAX_HECHOS_POR_EXTRACCION = 3
RASGOS_PERSONALIDAD = ("tono", "intereses", "actitud", "vocabulario")
# Prefijo de clave (normalizada) → rasgo. gemma2 inventa variantes como "attitud".
_ALIAS_RASGOS = (("tono", "tono"), ("inter", "intereses"), ("tema", "intereses"),
                 ("actit", "actitud"), ("attit", "actitud"), ("vocab", "vocabulario"),
                 ("mulet", "vocabulario"))

RESPUESTA_FALLBACK = "Uy, me he quedado en blanco. ¿Me lo repites?"

# Emojis y símbolos que el TTS leería en voz alta de forma absurda
_EMOJIS = re.compile("[\U00010000-\U0010FFFF\u2600-\u27BF\uFE0F\u200B-\u200D\u2060]")
# Comentarios "fuera de personaje" que gemma2 a\u00F1ade a veces al final
_META = re.compile(r"(?:(?<=[.!?\u2026])|\n)\s*[\(\[]?(nota|note|aclaraci[o\u00F3]n)\s*:.*$",
                   re.IGNORECASE | re.DOTALL)


class CerebroTR:
    """Mente de TR: memoria, desarrollo, emociones y conversación con el LLM."""

    def __init__(self, memory_dir: Path | None = None, log_info=print, log_error=print,
                 learning_async: bool = True, timeout_chat: float = TIMEOUT_CHAT_SEC,
                 stages_file: Path | None = None, llm: MotorLLM | None = None,
                 agente_file: Path | None = None):
        self.log_info = log_info
        self.log_error = log_error
        self.timeout_chat = timeout_chat
        # Parámetros del agente (config/agente_tr.json): identidad, modelo y
        # esfuerzo de cada tarea, respaldo de Ollama...
        self.agente = agente_tr.cargar(agente_file, log=log_error)
        self.llm = llm or crear_motor(self.agente, log_info=log_info, log_error=log_error)
        self.memory_dir = Path(memory_dir) if memory_dir else MEMORY_DIR_POR_DEFECTO
        self.memory_file = self.memory_dir / "memory.json"

        self._lock = threading.RLock()
        self.memory = self._cargar_memoria()
        self.history: list[dict] = []
        self.vision_context = ""
        self._ultima_interaccion = datetime.now()

        # --- Etapas de desarrollo ---
        self.etapas = dev.cargar_etapas(stages_file, log=log_error)
        self.memory["developmental_age"] = dev.limitar_edad(
            self.memory.get("developmental_age", dev.EDAD_INICIAL), self.etapas
        )

        # --- Emociones: reaccionan al tiempo que ha estado apagado ---
        self.emotions = EstadoEmocional(self.memory.get("emotions"))
        self.segundos_apagado = segundos_desde(self.memory.get("last_seen"))
        self.despertar_inquieto = self.emotions.despertar(self.segundos_apagado)
        if self.segundos_apagado > 0:
            self.log_info(
                f"🧠 He estado apagado {humanizar_segundos(self.segundos_apagado)}. "
                f"Emociones: {self.emotions.a_dict()}"
            )

        # --- Aprendizaje en segundo plano ---
        self._learning_async = learning_async
        self._tareas: "queue.Queue[str]" = queue.Queue()
        if learning_async:
            threading.Thread(target=self._worker_aprendizaje, daemon=True).start()

    # ------------------------------------------------------------------ #
    # Propiedades
    # ------------------------------------------------------------------ #
    @property
    def edad(self) -> int:
        with self._lock:
            return int(self.memory["developmental_age"])

    @property
    def total_interacciones(self) -> int:
        with self._lock:
            return int(self.memory["total_interactions"])

    # ------------------------------------------------------------------ #
    # Memoria persistente
    # ------------------------------------------------------------------ #
    def _cargar_memoria(self) -> dict:
        datos = {}
        try:
            self.memory_dir.mkdir(parents=True, exist_ok=True)
            if self.memory_file.exists():
                with open(self.memory_file, "r", encoding="utf-8") as f:
                    datos = json.load(f)
        except Exception as e:
            self.log_error(f"🧠 Error cargando memoria, empiezo de cero: {e}")
            datos = {}
        datos.setdefault("facts", [])
        datos.setdefault("personality", {})
        datos.setdefault("log", [])
        datos.setdefault("metrics", [])
        datos.setdefault("development_log", [])
        datos.setdefault("developmental_age", dev.EDAD_INICIAL)
        # El log se recorta a 500 entradas, así que el contador total va aparte
        datos.setdefault("total_interactions", len(datos["log"]))

        # Limpia basura de versiones anteriores (fragmentos de diálogo como
        # "hechos", claves de personalidad inventadas, tics como vocabulario)
        datos["facts"] = [h for h in (self._hecho_valido(f) for f in datos["facts"]) if h]
        tics = self._tics(datos["log"][-40:])
        datos["personality"] = {k: v for k, v in self._rasgos_validos(datos["personality"]).items()
                                if not self._contiene_tic(v, tics)}
        return datos

    def guardar_memoria(self):
        """Guarda la memoria de forma atómica (fichero temporal + rename)."""
        try:
            with self._lock:
                # last_seen permite saber, al arrancar, cuánto tiempo estuvo apagado
                self.memory["last_seen"] = datetime.now().isoformat(timespec="seconds")
                self.memory["emotions"] = self.emotions.a_dict()
                self.memory_dir.mkdir(parents=True, exist_ok=True)
                tmp = self.memory_file.with_suffix(".tmp")
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(self.memory, f, ensure_ascii=False, indent=2)
                tmp.replace(self.memory_file)
            return True
        except Exception as e:
            self.log_error(f"🧠 Error guardando memoria: {e}")
            return False

    # ------------------------------------------------------------------ #
    # Entradas externas
    # ------------------------------------------------------------------ #
    def set_vision(self, descripcion: str):
        with self._lock:
            self.vision_context = descripcion.strip()

    def reset_personality(self):
        with self._lock:
            self.memory["personality"] = {}
        self.log_info("🧠 Personalidad reseteada por orden explícita del usuario.")

    def set_edad(self, edad: int, motivo: str = "fijada manualmente (/tr/set_age)",
                 origen: str = "manual") -> tuple[int, int]:
        """Cambia la edad mental y lo apunta en development_log. Devuelve (anterior, nueva)."""
        nueva = dev.limitar_edad(edad, self.etapas)
        if nueva != edad:
            self.log_error(f"🧠 Edad {edad} fuera de rango; la limito a {nueva}.")
        with self._lock:
            anterior = int(self.memory["developmental_age"])
            if nueva == anterior:
                return anterior, nueva
            self.memory["developmental_age"] = nueva
            self.memory["development_log"].append({
                "fecha": datetime.now().isoformat(timespec="seconds"),
                "edad_anterior": anterior,
                "edad_nueva": nueva,
                "motivo": motivo,
                "origen": origen,
                "interacciones": self.memory["total_interactions"],
            })
        self.log_info(f"🧠 Edad mental: {anterior} → {nueva} años ({motivo}).")
        return anterior, nueva

    # ------------------------------------------------------------------ #
    # Conversación
    # ------------------------------------------------------------------ #
    def responder(self, texto_usuario: str) -> str:
        """Genera la respuesta de TR, la registra y lanza el aprendizaje periódico."""
        self._ultima_interaccion = datetime.now()
        self.emotions.registrar_interaccion()

        system = self._partes_system_prompt()
        with self._lock:
            historial = list(self.history[-MAX_HISTORY:])
            num_predict = int(dev.etapa_para_edad(self.edad, self.etapas).get("num_predict", 150))

        contexto = "".join(f"Usuario: {t['user']}\nTR: {t['tr']}\n" for t in historial)
        prompt = f"{contexto}Usuario: {texto_usuario}\nTR:"

        respuesta = self.limpiar_respuesta(self._pensar(
            prompt, system=system, num_predict=num_predict,
            timeout=self.timeout_chat, tarea="conversacion"))

        # Un modelo pequeño tiende a copiar sus propias respuestas del historial
        # hasta repetir siempre lo mismo. Si pasa, se regenera una vez avisándole.
        reintentada = False
        motivo = self._motivo_repeticion(respuesta, historial)
        if motivo:
            reintentada = True
            aviso = (f"\n\nATENCIÓN: {motivo} Eso suena a robot averiado. Responde de "
                     "forma distinta, concreta y relacionada con lo que te acaban de decir.")
            # Sin sus propias respuestas a la vista no tiene de dónde copiarse;
            # solo conserva lo que le dijeron para no perder el hilo.
            solo_persona = "".join(f"Usuario: {t['user']}\n" for t in historial[-3:])
            otra = self.limpiar_respuesta(self._pensar(
                f"{solo_persona}Usuario: {texto_usuario}\nTR:",
                system=system[:-1] + [system[-1] + aviso],
                num_predict=num_predict, timeout=self.timeout_chat,
                tarea="conversacion", temperature=0.95))
            if otra and not self._motivo_repeticion(otra, historial):
                respuesta = otra

        respuesta = respuesta or RESPUESTA_FALLBACK
        repetida = bool(self._motivo_repeticion(respuesta, historial))
        self._registrar_interaccion(texto_usuario, respuesta,
                                    reintentada=reintentada, repetida=repetida)
        return respuesta

    @staticmethod
    def _normalizar(texto: str) -> str:
        """Minúsculas, sin acentos ni signos: para comparar respuestas."""
        texto = unicodedata.normalize("NFKD", texto.lower()).encode("ascii", "ignore").decode()
        return " ".join(re.sub(r"[^a-z0-9 ]+", " ", texto).split())

    def _motivo_repeticion(self, respuesta: str, historial: list[dict]) -> str:
        """Devuelve por qué la respuesta es repetitiva, o "" si no lo es."""
        nueva = self._normalizar(respuesta)
        if not nueva:
            return ""
        recientes = [self._normalizar(t["tr"]) for t in historial[-VENTANA_REPETICION:]]
        for vieja in recientes:
            if vieja and SequenceMatcher(None, nueva, vieja).ratio() > 0.85:
                return "Esa respuesta es casi idéntica a otra que ya has dado."
        primera = nueva.split()[0]
        ultimas = [r.split()[0] for r in recientes[-3:] if r]
        if len(ultimas) == 3 and all(p == primera for p in ultimas):
            return f"Tus últimas respuestas empiezan todas por «{primera}»."
        return ""

    def construir_system_prompt(self) -> str:
        """Orden: identidad → etapa de desarrollo → personalidad → hechos → visión → emociones."""
        return "\n\n".join(self._partes_system_prompt())

    def _partes_system_prompt(self) -> list[str]:
        """El system prompt en dos trozos: [estable, cambiante].

        Las partes estables van primero para que el modelo reutilice su caché de
        prompt entre turnos; las que cambian a menudo (visión, emociones), al
        final. Los motores reciben los dos trozos y los unen.
        """
        with self._lock:
            edad = int(self.memory["developmental_age"])
            personalidad = dict(self.memory.get("personality", {}))
            hechos = list(self.memory.get("facts", []))[-MAX_FACTS_EN_PROMPT:]
            vision = self.vision_context

        partes = [
            self.agente["identidad"],   # config/agente_tr.json
            # a) Etapa de desarrollo
            dev.texto_etapa_para_prompt(edad, self.etapas),
        ]

        # b) Personalidad emergente (se construye encima de la etapa)
        if personalidad:
            rasgos = "\n".join(f"- {k}: {v}" for k, v in personalidad.items())
            partes.append(
                "TU PERSONALIDAD, que ha ido emergiendo con el tiempo:\n"
                f"{rasgos}\n"
                "Actúa de forma coherente con estos rasgos sin forzarlos. Si "
                "aprendes algo nuevo sobre cómo eres, adáptate naturalmente. Usa "
                "tus expresiones características con moderación: de vez en cuando, "
                "no en cada respuesta."
            )

        # c) Hechos conocidos y contexto visual
        if hechos:
            partes.append("COSAS QUE RECUERDAS:\n" + "\n".join(f"- {h}" for h in hechos))

        cambiantes = []
        if vision:
            cambiantes.append(f"LO QUE VES AHORA MISMO: {vision}")

        # Estado emocional: el LLM no decide qué siente, solo cómo expresarlo
        cambiantes.append(self.emotions.descripcion_para_prompt())

        cambiantes.append(
            "Responde a lo que te dicen en cada momento. No empieces dos "
            "respuestas seguidas igual ni repitas frases que ya hayas dicho. "
            "Nunca hables de tu 'etapa de desarrollo', de tu 'personalidad "
            "emergente' ni de tus 'niveles emocionales': simplemente sé así."
        )
        return ["\n\n".join(partes), "\n\n".join(cambiantes)]

    @staticmethod
    def limpiar_respuesta(texto: str) -> str:
        """Quita artefactos que el modelo imita del formato de transcripción.

        gemma2:2b a veces antepone 'TR:' a sus respuestas o alucina el turno
        siguiente del usuario. También quita emojis y markdown (van al TTS).
        """
        texto = (texto or "").strip()
        texto = re.sub(r"^(\W*TR\W{0,3}:[*\s]*)+", "", texto, flags=re.IGNORECASE)
        for marcador in ("\nUsuario:", "\nTR:", "\nusuario:"):
            pos = texto.find(marcador)
            if pos != -1:
                texto = texto[:pos]
        texto = _META.sub("", texto)
        texto = _EMOJIS.sub("", texto)
        texto = re.sub(r"[*#_`]+", "", texto)
        return re.sub(r"\s{2,}", " ", texto).strip()

    # ------------------------------------------------------------------ #
    # Modelo de lenguaje (Claude, u Ollama de respaldo: ver llm.py)
    # ------------------------------------------------------------------ #
    def _pensar(self, prompt: str, *, tarea: str, system: str | list[str] = "",
                num_predict: int = 150, timeout: float = TIMEOUT_ANALISIS_SEC,
                temperature: float = 0.7) -> str:
        """Pregunta al modelo. Devuelve "" si ningún motor ha podido responder."""
        texto = self.llm.generar(Peticion(
            prompt=prompt, system=[system] if isinstance(system, str) else list(system),
            num_predict=num_predict, timeout=timeout,
            tarea=tarea, temperature=temperature,
        ))
        if texto is None:
            # Un fallo al "pensar" hace dudar a TR de su propia funcionalidad
            self.emotions.registrar_error()
            return ""
        return texto

    # ------------------------------------------------------------------ #
    # Vida emocional
    # ------------------------------------------------------------------ #
    def comentario_despertar(self) -> str:
        """Tras un apagón largo, TR expresa espontáneamente cómo se siente."""
        if not self.despertar_inquieto:
            return ""
        self.despertar_inquieto = False
        prompt = (
            "Acabas de despertar y quieres decir en voz alta cómo te sientes. "
            "Di 1 o 2 frases, en primera persona, sin saludar a nadie en concreto."
        )
        return self.limpiar_respuesta(
            self._pensar(prompt, system=self._partes_system_prompt(),
                         timeout=self.timeout_chat, tarea="conversacion")
        )

    def tick_emocional(self) -> str:
        """Llamar cada minuto. Si la soledad es muy alta, devuelve algo que decir solo."""
        minutos_solo = (datetime.now() - self._ultima_interaccion).total_seconds() / 60.0
        self.emotions.tick_soledad(minutos_solo)
        if self.emotions.valores["soledad"] < SOLEDAD_HABLA_SOLA:
            return ""
        # "Gasta" soledad para no repetirse cada minuto
        self.emotions.valores["soledad"] -= 20
        prompt = (
            "Llevas mucho rato sin que nadie te hable y te sientes solo. Di en voz "
            "alta 1 frase corta, en primera persona, por si hay alguien cerca."
        )
        return self.limpiar_respuesta(
            self._pensar(prompt, system=self._partes_system_prompt(),
                         timeout=self.timeout_chat, tarea="conversacion")
        )

    # ------------------------------------------------------------------ #
    # Registro de interacciones, métricas y aprendizaje periódico
    # ------------------------------------------------------------------ #
    def _registrar_interaccion(self, usuario: str, tr: str, reintentada: bool = False,
                               repetida: bool = False):
        ahora = datetime.now().isoformat(timespec="seconds")
        with self._lock:
            self.history.append({"user": usuario, "tr": tr})
            self.history = self.history[-MAX_HISTORY:]

            self.memory["log"].append({"timestamp": ahora, "user": usuario, "tr": tr})
            self.memory["log"] = self.memory["log"][-MAX_LOG:]

            self.memory["total_interactions"] += 1
            n = self.memory["total_interactions"]

            metricas = dev.calcular_metricas(tr)
            metricas.update({
                "n": n,
                "timestamp": ahora,
                "edad": int(self.memory["developmental_age"]),
                "palabras_usuario": len(usuario.split()),
                "reintentada": reintentada,   # el detector de repeticiones tuvo que actuar
                "repetida": repetida,         # y aun así la respuesta quedó repetitiva
            })
            self.memory["metrics"].append(metricas)
            self.memory["metrics"] = self.memory["metrics"][-MAX_METRICS:]

        if n % FACTS_EVERY == 0:
            self._programar("hechos")
        if n % PERSONALITY_EVERY == 0:
            self._programar("personalidad")
        if n % dev.EVALUAR_CADA == 0:
            self._programar("maduracion")

    def _programar(self, tarea: str):
        if self._learning_async:
            self._tareas.put(tarea)
        else:
            self._ejecutar_tarea(tarea)

    def _worker_aprendizaje(self):
        while True:
            tarea = self._tareas.get()
            self._ejecutar_tarea(tarea)

    def _ejecutar_tarea(self, tarea: str):
        try:
            if tarea == "hechos":
                self._extraer_hechos()
            elif tarea == "personalidad":
                self._extraer_personalidad()
            elif tarea == "maduracion":
                self.evaluar_maduracion()
        except Exception as e:
            self.log_error(f"🧠 Error en la tarea de aprendizaje '{tarea}': {e}")

    def _extraer_hechos(self):
        with self._lock:
            recientes = list(self.memory["log"][-FACTS_EVERY:])
        texto = "\n".join(f"Usuario: {e['user']}\nTR: {e['tr']}" for e in recientes)
        prompt = (
            "Analiza esta conversación reciente entre un robot y una persona. "
            "Extrae SOLO hechos sobre la PERSONA que convenga recordar: su nombre, "
            "gustos, mascotas, familia, rutinas o planes. NO apuntes nada sobre el "
            "robot ni sobre qué preguntó la persona. Devuelve como mucho "
            f"{MAX_HECHOS_POR_EXTRACCION} hechos, uno por línea, en frases completas "
            "(ejemplo: 'El usuario tiene un perro llamado Toby'). Sin numerar ni "
            "viñetas. Si no hay ninguno, responde únicamente NINGUNO.\n\n"
            f"Conversación:\n{texto}"
        )
        respuesta = self._pensar(
            prompt, tarea="hechos",
            system="Eres un extractor de hechos. Responde solo con la lista pedida.",
            num_predict=150, temperature=0.2,
        )
        nuevos = [h for h in (self._hecho_valido(linea) for linea in respuesta.splitlines()) if h]
        if not nuevos:
            return
        with self._lock:
            hechos = self.memory["facts"]
            conocidos = {self._normalizar(h) for h in hechos}
            anadidos = []
            for h in nuevos[:MAX_HECHOS_POR_EXTRACCION]:
                if self._normalizar(h) not in conocidos:
                    conocidos.add(self._normalizar(h))
                    anadidos.append(h)
            hechos.extend(anadidos)
        if anadidos:
            self.log_info(f"🧠 Hechos nuevos: {anadidos}")

    @staticmethod
    def _hecho_valido(linea: str) -> str:
        """Descarta fragmentos de diálogo, hechos sobre el propio robot y preguntas.

        Los hechos sobre TR (p.ej. 'TR dice mucho Uf') vuelven al prompt y
        refuerzan sus propios tics: es un bucle de retroalimentación.
        """
        hecho = re.sub(r"^[\s\-•*\d.)]+", "", linea).strip()
        bajo = hecho.lower()
        if not (12 <= len(hecho) <= 160) or bajo.strip(".") == "ninguno":
            return ""
        if re.match(r"^(tr\b|el robot\b|robot\b|usuario\s*:|persona\s*:)", bajo):
            return ""
        if "pregunt" in bajo or hecho.endswith("?"):
            return ""
        return hecho

    def _extraer_personalidad(self):
        with self._lock:
            recientes = list(self.memory["log"][-PERSONALITY_EVERY:])
        interacciones = "\n".join(f"Usuario: {e['user']}\nTR: {e['tr']}" for e in recientes)
        prompt = (
            f"Analiza estas {len(recientes)} interacciones de un robot con personas y "
            "describe en un JSON los rasgos de carácter que han emergido "
            "naturalmente: tono, intereses, actitud, vocabulario característico. "
            "Sé específico y observacional, no inventes.\n"
            f"Interacciones: {interacciones}\n"
            "Responde SOLO con JSON plano clave:valor, con exactamente estas claves y "
            "una frase descriptiva corta en cada una:\n"
            '{"tono": "...", "intereses": "...", "actitud": "...", "vocabulario": "..."}\n'
            "Si el robot repite casi siempre la misma palabra o frase, eso es un tic "
            "que se debe corregir, no un rasgo: no lo pongas en 'vocabulario'."
        )
        respuesta = self._pensar(
            prompt, tarea="personalidad",
            system="Respondes únicamente con JSON válido, sin texto adicional.",
            num_predict=250, temperature=0.3,
        )
        rasgos = self._rasgos_validos(_parsear_json_dict(respuesta) or {})
        tics = self._tics(recientes)
        for clave in [k for k, v in rasgos.items() if self._contiene_tic(v, tics)]:
            self.log_info(f"🧠 Descarto '{rasgos.pop(clave)}' como {clave}: es un tic.")
        if not rasgos:
            self.log_error(f"🧠 No se pudo interpretar la personalidad: {respuesta[:150]!r}")
            return
        with self._lock:
            self.memory["personality"].update(rasgos)
        self.log_info(f"🧠 Personalidad actualizada: {rasgos}")

    @classmethod
    def _tics(cls, log: list[dict]) -> set[str]:
        """Palabras con las que empieza más del 20% de las respuestas, y
        respuestas repetidas 3 veces o más. Guardarlas como 'vocabulario'
        realimentaría el bucle (con un tercio, "Uf" se colaba al 30%)."""
        respuestas = [cls._normalizar(e["tr"]) for e in log if e.get("tr")]
        if not respuestas:
            return set()
        tics = set()
        primeras = Counter(r.split()[0] for r in respuestas if r)
        tics.update(p for p, k in primeras.items() if k >= 3 and k > len(respuestas) * 0.2)
        tics.update(r for r, k in Counter(respuestas).items() if k >= 3)
        return tics

    @classmethod
    def _contiene_tic(cls, texto: str, tics: set[str]) -> bool:
        norm = cls._normalizar(texto)
        palabras = set(norm.split())
        return any((t in norm) if " " in t else (t in palabras) for t in tics)

    @classmethod
    def _rasgos_validos(cls, datos: dict) -> dict:
        """Solo las 4 claves esperadas, con alias (p.ej. 'vocabulario característico')."""
        rasgos = {}
        for clave, valor in datos.items():
            clave_norm = cls._normalizar(str(clave)).replace(" ", "_")
            destino = next((r for prefijo, r in _ALIAS_RASGOS if clave_norm.startswith(prefijo)), None)
            if isinstance(valor, list):
                valor = ", ".join(str(v) for v in valor)
            valor = str(valor).strip()
            # Un rasgo que describe repetirse ("tendencia a la repetición")
            # también empujaría a TR de vuelta al bucle
            if destino and len(valor) >= 4 and "repet" not in valor.lower():
                rasgos[destino] = valor[:200]
        return rasgos

    def evaluar_maduracion(self) -> tuple[int, str] | None:
        """Pregunta al modelo si TR debe madurar (máx. +2 años). Devuelve (avance, motivo)."""
        with self._lock:
            edad = int(self.memory["developmental_age"])
            log_reciente = list(self.memory["log"][-dev.EVALUAR_CADA:])
            metricas = list(self.memory["metrics"][-dev.EVALUAR_CADA:])
        if edad >= max(self.etapas):
            self.log_info(f"🧠 Evaluación de maduración omitida: ya tengo la edad máxima ({edad}).")
            return None

        prompt = dev.prompt_evaluacion(edad, self.etapas, log_reciente, metricas)
        respuesta = self._pensar(
            prompt, tarea="maduracion",
            system="Eres un evaluador del desarrollo. Respondes solo con JSON válido.",
            num_predict=150, temperature=0.2,
        )
        veredicto = dev.parsear_veredicto(respuesta)
        if veredicto is None:
            self.log_error(f"🧠 No se pudo interpretar la evaluación de maduración: {respuesta[:200]!r}")
            return None

        avance, motivo = veredicto
        if avance > 0:
            self.set_edad(edad + avance, motivo=motivo or "evaluación de maduración",
                          origen="evaluacion")
        else:
            self.log_info(f"🧠 Evaluación de maduración: sigo con {edad} años ({motivo}).")
        return veredicto

    # ------------------------------------------------------------------ #
    def resumen_estado(self) -> dict:
        with self._lock:
            return {
                "edad": int(self.memory["developmental_age"]),
                "etapa": dev.etapa_para_edad(self.memory["developmental_age"], self.etapas).get("nombre"),
                "interacciones": self.memory["total_interactions"],
                "hechos": len(self.memory["facts"]),
                "personalidad": dict(self.memory["personality"]),
                "emociones": self.emotions.a_dict(),
                "metricas_recientes": dev.resumen_metricas(self.memory["metrics"][-20:]),
            }


def _parsear_json_dict(texto: str) -> dict | None:
    """Extrae el primer bloque {...} del texto y lo parsea como dict JSON."""
    inicio, fin = texto.find("{"), texto.rfind("}")
    if inicio == -1 or fin <= inicio:
        return None
    try:
        datos = json.loads(texto[inicio:fin + 1])
        return datos if isinstance(datos, dict) else None
    except json.JSONDecodeError:
        return None
