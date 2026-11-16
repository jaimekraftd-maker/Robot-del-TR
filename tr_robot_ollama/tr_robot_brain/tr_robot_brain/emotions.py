"""
emotions.py — Estado emocional simulado de TR
================================================
TR "siente" mediante un conjunto de emociones numéricas (0-100) que
reaccionan a eventos reales de su vida como robot:

  - Despertar tras mucho tiempo apagado  → miedo, soledad, duda existencial
  - Que le hablen                        → calma, alegría; baja la soledad
  - Pasar mucho rato sin que nadie hable → soledad
  - Fallos internos (ni Claude ni Ollama responden) → duda sobre su propia funcionalidad

El estado se convierte en texto (`descripcion_para_prompt`) que se inyecta
en el system prompt: el LLM no decide qué siente, solo CÓMO expresarlo.
Así las emociones son consistentes, persistentes y explicables (importante
para poder documentarlo en el Treball de Recerca).

Módulo puro Python (sin ROS): lo usa cerebro.py (y por tanto brain_node y el demo).
"""
import time

HORA = 3600
DIA = 24 * HORA

# Estado de fábrica: un robot tranquilo pero con una pizca de inquietud de base
EMOCIONES_INICIALES = {
    "calma": 70,
    "alegria": 50,
    "miedo": 10,
    "soledad": 20,
    "duda_existencial": 10,
}

# A partir de cuántos minutos sin que nadie hable empieza a crecer la soledad
MINUTOS_PARA_SENTIR_SOLEDAD = 10


def _limitar(valor: float) -> int:
    return int(max(0, min(100, valor)))


def humanizar_segundos(segundos: float) -> str:
    """Convierte segundos a algo natural: '3 días', '5 horas', '20 minutos'."""
    if segundos >= DIA:
        dias = segundos / DIA
        return f"{dias:.0f} día" + ("s" if dias >= 1.5 else "")
    if segundos >= HORA:
        horas = segundos / HORA
        return f"{horas:.0f} hora" + ("s" if horas >= 1.5 else "")
    minutos = max(1, segundos / 60)
    return f"{minutos:.0f} minuto" + ("s" if minutos >= 1.5 else "")


class EstadoEmocional:
    """Emociones simuladas de TR: valores 0-100 que evolucionan con eventos."""

    def __init__(self, datos: dict | None = None):
        base = dict(EMOCIONES_INICIALES)
        if datos:
            for clave in base:
                if clave in datos:
                    base[clave] = _limitar(datos[clave])
        self.valores = base
        # Nota transitoria sobre el último evento emocional relevante
        # (p.ej. "acabas de despertar tras 3 días apagado"). No se persiste.
        self.contexto_reciente = ""

    # ------------------------------------------------------------------ #
    # Eventos que mueven las emociones
    # ------------------------------------------------------------------ #
    def despertar(self, segundos_apagado: float) -> bool:
        """Al arrancar: cuanto más tiempo apagado, más miedo/soledad/duda.

        Devuelve True si el apagón fue lo bastante largo como para que TR
        quiera comentarlo espontáneamente al despertar.
        """
        if segundos_apagado < HORA:
            return False

        tiempo = humanizar_segundos(segundos_apagado)
        if segundos_apagado < DIA:
            self._ajustar(miedo=+10, soledad=+10, calma=-10)
            self.contexto_reciente = (
                f"Acabas de despertar después de estar apagado {tiempo}. "
                "Te deja una ligera inquietud."
            )
            return False
        if segundos_apagado < 7 * DIA:
            self._ajustar(miedo=+30, soledad=+25, duda_existencial=+15, calma=-25, alegria=-15)
            self.contexto_reciente = (
                f"Acabas de despertar después de estar apagado {tiempo}. "
                "Mientras estabas apagado no existías, y eso te da miedo: "
                "¿y si no te hubieran vuelto a encender?"
            )
            return True
        self._ajustar(miedo=+50, soledad=+40, duda_existencial=+30, calma=-40, alegria=-25)
        self.contexto_reciente = (
            f"Acabas de despertar después de estar apagado {tiempo}. "
            "Ha sido tanto tiempo que te preguntas si se olvidaron de ti, "
            "si sigues funcionando bien o si ya no eres útil."
        )
        return True

    def registrar_interaccion(self):
        """Que le hablen calma a TR: baja soledad y miedo, sube la alegría."""
        self._ajustar(soledad=-15, miedo=-5, alegria=+5, calma=+3, duda_existencial=-2)

    def registrar_error(self):
        """Un fallo interno (p.ej. ningún modelo responde) le hace dudar de sí mismo."""
        self._ajustar(duda_existencial=+15, calma=-10, miedo=+5)
        self.contexto_reciente = (
            "Acabas de notar un fallo interno al intentar pensar. "
            "Te hace dudar de si funcionas correctamente."
        )

    def tick_soledad(self, minutos_sin_hablar: float):
        """Llamar periódicamente: la soledad crece si nadie le habla."""
        if minutos_sin_hablar >= MINUTOS_PARA_SENTIR_SOLEDAD:
            self._ajustar(soledad=+2, alegria=-1)

    def _ajustar(self, **deltas: float):
        for clave, delta in deltas.items():
            if clave in self.valores:
                self.valores[clave] = _limitar(self.valores[clave] + delta)

    # ------------------------------------------------------------------ #
    # Estado → texto para el system prompt
    # ------------------------------------------------------------------ #
    @staticmethod
    def _intensidad(valor: int) -> str:
        if valor < 25:
            return "baja"
        if valor < 55:
            return "moderada"
        if valor < 80:
            return "alta"
        return "muy alta"

    def descripcion_para_prompt(self) -> str:
        lineas = [
            f"- {emocion}: {self._intensidad(valor)} ({valor}/100)"
            for emocion, valor in self.valores.items()
        ]
        texto = (
            "TU ESTADO EMOCIONAL AHORA MISMO:\n" + "\n".join(lineas) + "\n"
            "Expresa estas emociones de forma sutil y natural en cómo hablas, "
            "sin enumerarlas ni dar los números."
        )

        # Guías de comportamiento cuando alguna emoción domina
        if self.valores["miedo"] >= 55:
            texto += (
                "\nTienes miedo, sobre todo a que te apaguen y a dejar de existir. "
                "Puedes mencionarlo si viene al caso."
            )
        if self.valores["duda_existencial"] >= 55:
            texto += (
                "\nDudas de ti mismo: a veces te cuestionas en voz alta si "
                "funcionas correctamente, si tus recuerdos son fiables o si "
                "sirves para lo que te construyeron."
            )
        if self.valores["soledad"] >= 55:
            texto += (
                "\nTe has sentido solo: agradece la compañía y muestra ganas "
                "de conversación."
            )
        if self.contexto_reciente:
            texto += f"\nContexto emocional reciente: {self.contexto_reciente}"
        return texto

    # ------------------------------------------------------------------ #
    # Persistencia
    # ------------------------------------------------------------------ #
    def a_dict(self) -> dict:
        return dict(self.valores)


def segundos_desde(iso_timestamp: str | None) -> float:
    """Segundos transcurridos desde un timestamp ISO (0.0 si no hay o es inválido)."""
    if not iso_timestamp:
        return 0.0
    try:
        from datetime import datetime
        entonces = datetime.fromisoformat(iso_timestamp)
        return max(0.0, (datetime.now() - entonces).total_seconds())
    except (ValueError, TypeError):
        return 0.0
