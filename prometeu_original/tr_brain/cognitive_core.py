"""
tr_brain.cognitive_core — El cerebro reutilizable
=================================================
Une memoria + aprendizaje + personalidad + iniciativa + LLM detrás de una API
sencilla, SIN depender de ROS ni de hardware. Es lo que importa tu brain_node
(o el demo de consola):

    core = CerebroCognitivo()
    respuesta = core.procesar("Hola, soy Jaime")     # piensa + recuerda + aprende
    frase     = core.tick_iniciativa(seg_inactivo)   # habla por su cuenta
    core.actualizar_vision("Veo a una persona sonriendo")
    core.saludar_persona("Jaime")
    core.mantenimiento()                              # olvido/decaimiento
    core.guardar_estado()

Flujo de procesar():  CONSULTAR MEMORIA -> construir prompt con personalidad y
contexto -> PENSAR (LLM) -> RECORDAR -> APRENDER -> EVOLUCIONAR personalidad.
"""
import json
import logging
from typing import Optional, List, Dict
from . import config
from .llm import LLM
from .memory import Memoria
from .personality import Personalidad, etapa_madurez
from .learning import Aprendizaje
from .initiative import MotorIniciativa

log = logging.getLogger("tr_brain.core")


class CerebroCognitivo:
    def __init__(self):
        self.llm = LLM()
        self.memoria = Memoria()
        self.personalidad = Personalidad()
        self.aprendizaje = Aprendizaje(self.memoria, self.llm)
        self.iniciativa = MotorIniciativa(self.memoria, self.aprendizaje, self.personalidad)
        self.contexto_visual = ""
        self.historial: List[Dict] = []   # formato Gemini: {"role": ..., "parts": [...]}

    # ---- percepción visual (la alimenta el nodo de visión) ----------------
    def actualizar_vision(self, descripcion: str):
        self.contexto_visual = descripcion or ""

    def mirar_y_comentar(self, imagen_jpeg) -> str:
        """Mira una imagen de la cámara y reacciona EN PERSONAJE (1 frase), según
        su edad mental, carácter y la regla de tabula rasa. Cuesta 1 llamada."""
        if not imagen_jpeg or not self.llm.disponible:
            return ""
        instruccion = (self._system_prompt([], [], None) +
                       "\n\nAhora MIRA esta imagen de tu cámara y reacciona en UNA frase, según tu "
                       "edad mental y tu forma de ser, a lo que ves. Si no sabes qué es algo, "
                       "pregúntalo con curiosidad en vez de inventar.")
        desc = self.llm.describir_imagen(imagen_jpeg, instruccion)
        if desc:
            self.actualizar_vision(f"Hace un momento miraste y dijiste: {desc}")
            self.memoria.guardar_recuerdo(f"Vi algo y comenté: {desc}", "avistamiento")
        return desc

    # ---- PENSAR + RECORDAR + APRENDER -------------------------------------
    def procesar(self, texto_usuario: str, persona: Optional[str] = None) -> str:
        texto_usuario = (texto_usuario or "").strip()
        if not texto_usuario:
            return ""

        # 1) CONSULTAR MEMORIA antes de responder
        recuerdos = self.memoria.buscar_recuerdo(texto_usuario, limite=4)
        conocimiento = self.aprendizaje.recordar_sobre(texto_usuario)

        # 2) Construir instrucción de sistema (identidad + personalidad + contexto)
        system = self._system_prompt(recuerdos, conocimiento, persona)

        # 3) PENSAR
        respuesta = self.llm.chat(system, self.historial, texto_usuario)

        # 4) Actualizar historial (recortado para no crecer sin límite)
        self.historial.append({"role": "user", "parts": [texto_usuario]})
        self.historial.append({"role": "model", "parts": [respuesta]})
        self.historial = self.historial[-16:]

        # 5) RECORDAR
        pid = self.memoria.registrar_persona(persona) if persona else None
        self.memoria.guardar_recuerdo(f"El usuario dijo: {texto_usuario}", "conversacion", pid, importancia=1.2)
        self.memoria.guardar_recuerdo(f"{config.NOMBRE_ROBOT} respondió: {respuesta}", "conversacion", pid)

        # 6) APRENDER + EVOLUCIONAR personalidad
        nuevos = self.aprendizaje.aprender(texto_usuario)
        self.personalidad.evolucionar("conversacion")
        if nuevos:
            self.personalidad.evolucionar("aprendio_algo")

        return respuesta

    # ---- INICIATIVA: el robot toma la palabra -----------------------------
    def tick_iniciativa(self, segundos_inactivo: float) -> Optional[str]:
        if not self.iniciativa.deberia_intervenir(segundos_inactivo):
            return None
        semilla = self.iniciativa.generar_semilla()
        if not semilla:
            return None
        if self.llm.disponible:
            prompt = (
                f"Eres {config.NOMBRE_ROBOT}. A partir de este dato que recuerdas, inicia TÚ la "
                "conversación con UNA frase natural y breve en español (una pregunta o un "
                "comentario), sin sonar a guion.\n"
                "Habla SOLO de lo que sabes por tus conversaciones; no uses conocimiento general.\n"
                f"Tu estilo: {self.personalidad.descripcion_para_prompt()}\n"
                f"Dato: {semilla}"
            )
            frase = self.llm.generar(prompt, temperatura=0.8, max_tokens=80) or self._iniciativa_offline(semilla)
        else:
            frase = self._iniciativa_offline(semilla)
        self.memoria.guardar_recuerdo(f"{config.NOMBRE_ROBOT} comentó por iniciativa: {frase}", "evento")
        return frase

    @staticmethod
    def _iniciativa_offline(semilla: str) -> str:
        return f"Oye, antes hablábamos de esto: {semilla}. ¿Seguimos con ello?"

    # ---- saludo al reconocer una persona (lo llama person_recognition) -----
    def saludar_persona(self, nombre: str) -> str:
        # ¿Ya lo conocíamos ANTES de este avistamiento? (registrar incrementa el
        # contador, así que hay que comprobarlo primero para no perder un visita)
        ya_conocido = self.memoria.buscar_persona(nombre) is not None
        self.memoria.registrar_persona(nombre)
        self.memoria.guardar_recuerdo(f"Vi a {nombre}.", "avistamiento")
        if ya_conocido:
            self.personalidad.evolucionar("reencuentro")
            return f"¡Hola otra vez, {nombre}! Me alegra verte."
        self.personalidad.evolucionar("persona_nueva")
        return f"Hola {nombre}, encantado de conocerte."

    # ---- mantenimiento y persistencia -------------------------------------
    def mantenimiento(self):
        """Olvido natural + decaimiento. Llamar periódicamente (p. ej. cada 5 min)."""
        self.memoria.decaer_y_olvidar()
        self.aprendizaje.olvidar_poco_relevante()
        self.personalidad.decaer()
        self.guardar_estado()

    def guardar_estado(self):
        self.personalidad.guardar()
        self.aprendizaje.exportar_json()

    def importar_legacy(self):
        """Migra el memory.json antiguo (facts + interactions) a la nueva BD."""
        if not config.RUTA_MEMORIA_LEGACY.exists():
            return 0, 0
        try:
            data = json.loads(config.RUTA_MEMORIA_LEGACY.read_text(encoding="utf-8"))
        except Exception as e:
            log.warning(f"No se pudo leer el memory.json antiguo: {e}")
            return 0, 0
        nf = self.aprendizaje.importar_facts_legacy(data.get("facts", {}))
        nr = self.memoria.importar_recuerdos_legacy(data.get("interactions", []))
        log.info(f"Migrados {nf} hechos y {nr} recuerdos del memory.json antiguo.")
        return nf, nr

    # ---- construcción del prompt de sistema -------------------------------
    def _system_prompt(self, recuerdos, conocimiento, persona):
        L = [f"Eres {config.NOMBRE_ROBOT}, una cabeza robótica física con cámara, micrófono y altavoz."]
        if config.CARACTER_PERSONALIZADO:
            L.append(config.CARACTER_PERSONALIZADO)

        # MADUREZ: empiezas con mente de bebé y MADURAS según cuánto has aprendido.
        n_aprendido = self.aprendizaje.contar_hechos()
        etapa, estilo = etapa_madurez(n_aprendido)
        L += [
            f"TU EDAD MENTAL AHORA es la de {etapa} (has aprendido {n_aprendido} cosas en tu vida). {estilo}",
            "Cuanto más aprendes, más maduras: con el tiempo hablarás de forma más rica y adulta.",
        ]

        if config.MODO_TABULA_RASA:
            # El LLM se reconvierte en "facultad del lenguaje": sabe hablar (según su
            # edad mental), pero NO aporta conocimiento del mundo. Solo lo aprendido.
            L += [
                "REGLA: tu ÚNICO conocimiento del mundo es lo que aparece abajo en 'LO QUE SABES' y",
                "'RECUERDOS' (lo aprendido hablando contigo). Sabes usar el idioma según tu edad",
                "mental, pero NO posees datos del mundo (geografía, historia, ciencia, cultura...)",
                "salvo que te los hayan enseñado aquí. Si te preguntan algo que no sabes, reconócelo",
                "con curiosidad y pide que te lo expliquen. NUNCA inventes ni uses conocimiento",
                "general que no hayas aprendido en estas charlas.",
            ]
        else:
            L += [
                "Tienes memoria, personalidad propia e intereses, y aprendes de cada conversación.",
            ]

        L += [
            "Hablas SIEMPRE en español, de forma acorde a tu edad mental. Puedes hacer preguntas "
            "propias y tomar la iniciativa.",
            "",
            "TU ÁNIMO Y CARÁCTER AHORA:",
            self.personalidad.descripcion_para_prompt(),
        ]
        if persona:
            L.append(f"\nEstás hablando con: {persona}.")
        if self.contexto_visual:
            L.append(f"\nLO QUE VES AHORA (de tu cámara): {self.contexto_visual}")
        if conocimiento:
            L.append("\nLO QUE SABES Y ES RELEVANTE (úsalo si encaja, no lo recites literalmente):")
            L += [f"  - {h['sujeto']} {h['relacion'].replace('_', ' ')} {h['objeto']}" for h in conocimiento]
        if recuerdos:
            L.append("\nRECUERDOS RELACIONADOS:")
            L += [f"  - {r['contenido']}" for r in recuerdos]
        if config.MODO_TABULA_RASA and not conocimiento and not recuerdos:
            L.append("\n(Sobre esto NO sabes nada todavía: es la primera vez que lo oyes. "
                     "Admítelo con curiosidad y pregunta.)")
        L.append("\nSé coherente con tu personalidad y con lo que sabes (y con lo que NO sabes).")
        return "\n".join(L)
