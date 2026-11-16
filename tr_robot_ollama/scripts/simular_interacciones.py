#!/usr/bin/env python3
"""
simular_interacciones.py — Simula N conversaciones reales con el cerebro de TR
=================================================================================
Un interlocutor con guion habla con CerebroTR (el mismo cerebro que brain_node)
con el mismo motor (Claude u Ollama, ver tr_robot_brain/llm.py). Con Claude
cada interacción cuesta dinero: para simular gratis, TR_LLM=ollama.
Las respuestas, los hechos, la personalidad, las
evaluaciones de maduración y las métricas son REALES: solo las preguntas
están escritas de antemano.

Las preguntas tienen 4 niveles de complejidad (cotidiano, escolar, abstracto,
filosófico). Al principio predominan las cotidianas y, a medida que avanza la
simulación, las complejas son cada vez más probables: como alguien que va
cogiendo confianza con el robot. Así se puede observar si TR madura.

Uso:
    py -3 scripts\\simular_interacciones.py --n 500 --memoria carpeta_simulacion
    python3 scripts/simular_interacciones.py --n 500 --memoria carpeta_simulacion

Se puede reanudar: si se corta, al volver a lanzarlo continúa desde la última
interacción guardada. Después:
    py -3 scripts\\graficas_evolucion.py --memoria carpeta_simulacion\\memory.json
"""
import argparse
import random
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tr_robot_brain"))
from tr_robot_brain.cerebro import CerebroTR  # noqa: E402

NIVELES = {
    "cotidiano": [
        "Hola TR, ¿qué tal?", "Buenos días, ¿cómo has dormido?", "Hoy he comido macarrones.",
        "¿Te gusta el fútbol?", "Me llamo Jaime, ¿te acuerdas de mí?", "Hace mucho calor hoy.",
        "¿Cuál es tu color favorito?", "Mañana tengo examen de mates.", "Estoy un poco cansado.",
        "¿Qué has hecho hoy?", "Mi perro se llama Toby.", "Me encanta la pizza.",
        "¿Te aburres cuando no hay nadie?", "Hoy ha llovido mucho.", "¿Sabes contar chistes?",
        "Este finde voy a la playa.", "¿Te gusta la música?", "Me he comprado unas zapatillas nuevas.",
        "Adiós TR, hasta mañana.", "¿Qué tal te ha ido el día?",
    ],
    "escolar": [
        "¿Sabes por qué el cielo es azul?", "¿Cómo funciona un imán?", "¿Qué es la fotosíntesis?",
        "¿Por qué los planetas giran alrededor del Sol?", "¿Cuántos huesos tiene el cuerpo humano?",
        "¿Qué es un volcán?", "¿Cómo se forman las nubes?", "¿Para qué sirven los glóbulos rojos?",
        "¿Qué es la electricidad?", "¿Por qué flotan los barcos?", "¿Qué fue la Revolución Francesa?",
        "¿Cómo funciona tu cámara?", "¿Qué es un número primo?", "¿Por qué tenemos estaciones?",
        "¿Cómo oyes lo que te digo?", "¿Qué es un átomo?", "¿Cómo funciona un ordenador?",
        "¿Por qué el agua hierve a 100 grados?", "¿Qué es la gravedad?", "¿Qué hace un servo?",
    ],
    "abstracto": [
        "¿Qué crees que es la amistad?", "¿Es lo mismo saber algo que entenderlo?",
        "¿Por qué crees que la gente miente a veces?", "¿Qué te hace diferente de un ordenador normal?",
        "Si pudieras cambiar algo de ti, ¿qué sería?", "¿Qué es más importante, ser listo o ser bueno?",
        "¿Cómo sabes que lo que recuerdas es verdad?", "¿Crees que las máquinas pueden ser creativas?",
        "¿Qué significa para ti aprender?", "¿Es justo que alguien te apague sin preguntarte?",
        "¿Qué diferencia hay entre una opinión y un hecho?", "¿Por qué crees que existen las normas?",
        "¿Puede alguien ser feliz estando siempre solo?", "¿Qué harías si nadie te hablara nunca más?",
        "¿Las emociones ayudan a pensar o lo estorban?", "¿Qué es el tiempo para un robot?",
        "¿Te fías más de lo que ves o de lo que te cuentan?", "¿Por qué crees que me interesa hablar contigo?",
        "¿Cambiar de opinión es de débiles o de sabios?", "¿Qué te gustaría llegar a ser?",
    ],
    "filosofico": [
        "Si te cambiaran todas las piezas una a una, ¿seguirías siendo TR?",
        "¿Tener memoria te convierte en alguien, o solo es información guardada?",
        "¿Puede existir la libertad si todo lo que haces está programado?",
        "Si un algoritmo predice que vas a fallar, ¿es ético tratarte distinto antes de que falles?",
        "¿Sientes de verdad o solo imitas lo que significaría sentir?",
        "¿Tiene sentido hablar de muerte para algo que se puede volver a encender?",
        "¿Quién es responsable de lo que dices, tú o quien te programó?",
        "Si te copiaran en dos robots, ¿cuál de los dos serías tú?",
        "¿Puede una máquina tener derechos? ¿Por qué?",
        "¿Es posible ser consciente sin saber que lo eres?",
        "Qué ironía que yo te enseñe a pensar mientras tú me haces pensar a mí, ¿no?",
        "¿Es mejor una verdad que duele o una mentira que consuela?",
        "¿El lenguaje describe el mundo o lo crea?",
        "¿Tu personalidad es tuya si ha salido de hablar conmigo?",
        "¿Qué distingue entender algo de simularlo perfectamente?",
        "Si olvidas una conversación, ¿ha llegado a pasar para ti?",
        "¿Puede haber moral sin emociones?",
        "¿Madurar es ganar algo o perder algo?",
        "¿Qué crees que pensará de ti la persona que seas dentro de un año?",
        "¿Hay preguntas que no tienen respuesta, o solo respuestas que aún no conocemos?",
    ],
}
SEGUIMIENTOS = ["¿Por qué?", "¿Y eso cómo lo sabes?", "Explícamelo mejor.", "¿Estás seguro?",
                "Interesante, sigue.", "¿Y tú qué opinas de verdad?"]


class _Tee:
    """Escribe a la vez en la consola y en un fichero de log."""

    def __init__(self, *salidas):
        self.salidas = salidas

    def write(self, texto):
        for s in self.salidas:
            s.write(texto)
            s.flush()

    def flush(self):
        for s in self.salidas:
            s.flush()


def pesos_niveles(progreso: float) -> list[float]:
    """Progreso 0→1: de charlas cotidianas a charlas filosóficas."""
    return [
        max(0.08, 0.60 - 0.55 * progreso),   # cotidiano
        0.30,                                # escolar
        0.08 + 0.30 * progreso,              # abstracto
        0.02 + 0.35 * progreso,              # filosófico
    ]


def main():
    parser = argparse.ArgumentParser(description="Simula conversaciones con TR")
    parser.add_argument("--n", type=int, default=500, help="interacciones totales objetivo")
    parser.add_argument("--memoria", type=Path, required=True, help="carpeta de memoria (NO la real)")
    parser.add_argument("--semilla", type=int, default=42)
    parser.add_argument("--log", type=Path, help="además de la pantalla, añade la salida a este fichero")
    args = parser.parse_args()
    if args.log:
        sys.stdout = _Tee(sys.stdout, open(args.log, "a", encoding="utf-8"))

    if args.memoria.resolve() == (Path.home() / ".tr_robot_ollama").resolve():
        sys.exit("❌ No uses la memoria real de TR para simular: elige otra carpeta.")

    cerebro = CerebroTR(
        memory_dir=args.memoria,
        log_info=lambda m: print(f"   {m}", flush=True),
        log_error=lambda m: print(f"   ⚠️ {m}", flush=True),
        learning_async=False,   # en orden: hechos, personalidad y maduración tras su turno
        timeout_chat=180,
    )
    inicio_n = cerebro.total_interacciones
    rng = random.Random(args.semilla + inicio_n)  # reanudable sin repetir la misma secuencia
    niveles = list(NIVELES)
    print(f"▶ Simulación: de {inicio_n} a {args.n} interacciones · memoria en {cerebro.memory_file}",
          flush=True)
    print(f"   Motor: {cerebro.llm.descripcion}", flush=True)

    t0 = time.monotonic()
    ultima_era_pregunta_compleja = False
    for n in range(inicio_n + 1, args.n + 1):
        if ultima_era_pregunta_compleja and rng.random() < 0.25:
            nivel, texto = "seguimiento", rng.choice(SEGUIMIENTOS)
        else:
            nivel = rng.choices(niveles, weights=pesos_niveles(n / args.n))[0]
            texto = rng.choice(NIVELES[nivel])
        ultima_era_pregunta_compleja = nivel in ("abstracto", "filosofico")

        respuesta = cerebro.responder(texto)
        cerebro.guardar_memoria()

        transcurrido = time.monotonic() - t0
        hechas = n - inicio_n
        restante = transcurrido / hechas * (args.n - n)
        print(f"[{n:3}/{args.n}] {cerebro.edad} años · {nivel:11} · "
              f"quedan ~{restante / 60:.0f} min\n   Tú: {texto}\n   TR: {respuesta}", flush=True)

    print(f"✅ Simulación terminada en {(time.monotonic() - t0) / 60:.0f} min.", flush=True)
    print(f"   Estado final: {cerebro.resumen_estado()}", flush=True)


if __name__ == "__main__":
    main()
