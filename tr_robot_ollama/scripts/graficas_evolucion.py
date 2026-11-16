#!/usr/bin/env python3
"""
graficas_evolucion.py — Gráficas de la evolución de TR para el Treball de Recerca
====================================================================================
Lee memory["metrics"] y memory["development_log"] de memory.json y genera:

  - evolucion_tr.png : 3 paneles con el mismo eje X (número de interacción)
        1. Edad mental
        2. Longitud media de frase de TR (palabras)
        3. Preguntas que hace TR por respuesta
     Los puntos claros son cada interacción; la línea, la media móvil.
     Las líneas verticales marcan cada cambio de etapa.
  - metricas_tr.csv  : los mismos datos en tabla (para Excel / anexos del TR)

Uso:
    py -3 scripts\\graficas_evolucion.py                    # Windows
    python3 scripts/graficas_evolucion.py --ventana 20      # media móvil de 20
    python3 scripts/graficas_evolucion.py --memoria otra/memory.json --salida carpeta/

Requiere matplotlib (pip install matplotlib).
"""
import argparse
import csv
import json
import os
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

try:
    import matplotlib
    matplotlib.use("Agg")  # sin ventana: solo genera el PNG
    import matplotlib.pyplot as plt
    import matplotlib.ticker
except ImportError:
    sys.exit("❌ Falta matplotlib:  pip install matplotlib")

# Paleta sobria para imprimir (una sola serie por panel → un solo azul)
AZUL = "#2a78d6"
AZUL_CLARO = "#b7d3f6"
TINTA = "#0b0b0b"
TINTA_SECUNDARIA = "#52514e"
TINTA_TENUE = "#898781"
REJILLA = "#e1e0d9"
FONDO = "#fcfcfb"


def media_movil(valores: list[float], ventana: int) -> list[float]:
    resultado, suma = [], 0.0
    for i, v in enumerate(valores):
        suma += v
        if i >= ventana:
            suma -= valores[i - ventana]
        resultado.append(suma / min(i + 1, ventana))
    return resultado


def estilo_panel(ax, titulo: str, unidad: str):
    ax.set_facecolor(FONDO)
    ax.set_title(titulo, loc="left", fontsize=11, color=TINTA, pad=6)
    ax.set_ylabel(unidad, fontsize=9, color=TINTA_SECUNDARIA)
    ax.grid(axis="y", color=REJILLA, linewidth=0.8)
    ax.set_axisbelow(True)
    for lado in ("top", "right", "left"):
        ax.spines[lado].set_visible(False)
    ax.spines["bottom"].set_color("#c3c2b7")
    ax.tick_params(colors=TINTA_TENUE, labelsize=8, length=0)


def main():
    parser = argparse.ArgumentParser(description="Gráficas de evolución de TR")
    carpeta_por_defecto = Path(os.environ.get("TR_MEMORY_DIR", Path.home() / ".tr_robot_ollama"))
    parser.add_argument("--memoria", type=Path, default=carpeta_por_defecto / "memory.json")
    parser.add_argument("--salida", type=Path, default=Path("."), help="carpeta de salida")
    parser.add_argument("--ventana", type=int, default=10, help="interacciones de la media móvil")
    args = parser.parse_args()

    try:
        memoria = json.loads(args.memoria.read_text(encoding="utf-8"))
    except FileNotFoundError:
        sys.exit(f"❌ No existe {args.memoria}")
    metricas = memoria.get("metrics", [])
    cambios = memoria.get("development_log", [])
    if len(metricas) < 2:
        sys.exit(f"❌ Solo hay {len(metricas)} interacciones con métricas: habla más con TR primero.")

    n = [m["n"] for m in metricas]
    edad = [m["edad"] for m in metricas]
    longitud = [m["longitud_media_frase"] for m in metricas]
    preguntas = [m["preguntas"] for m in metricas]
    ventana = max(1, min(args.ventana, len(metricas)))

    args.salida.mkdir(parents=True, exist_ok=True)

    # --- Tabla CSV -------------------------------------------------------------
    ruta_csv = args.salida / "metricas_tr.csv"
    campos = ["n", "timestamp", "edad", "palabras", "frases", "longitud_media_frase",
              "preguntas", "palabras_usuario", "reintentada", "repetida"]
    with open(ruta_csv, "w", newline="", encoding="utf-8-sig") as f:  # -sig: Excel lee bien los acentos
        escritor = csv.DictWriter(f, fieldnames=campos, extrasaction="ignore", delimiter=";")
        escritor.writeheader()
        escritor.writerows(metricas)

    # --- Gráfica (3 paneles, mismo eje X, nunca doble eje Y) --------------------
    fig, (ax_edad, ax_long, ax_preg) = plt.subplots(
        3, 1, figsize=(10, 8.5), sharex=True, gridspec_kw={"height_ratios": [1, 1.3, 1.3]}
    )
    fig.patch.set_facecolor(FONDO)

    ax_edad.step(n, edad, where="post", color=AZUL, linewidth=2)
    estilo_panel(ax_edad, "Edad mental", "años")
    ax_edad.set_ylim(min(edad) - 1, max(max(edad), 13) + 1)
    ax_edad.yaxis.set_major_locator(matplotlib.ticker.MaxNLocator(integer=True))

    for ax, valores, titulo, unidad in (
        (ax_long, longitud, "Longitud media de frase de TR", "palabras / frase"),
        (ax_preg, preguntas, "Preguntas que hace TR", "preguntas / respuesta"),
    ):
        ax.scatter(n, valores, s=10, color=AZUL_CLARO, linewidths=0, zorder=2)
        ax.plot(n, media_movil(valores, ventana), color=AZUL, linewidth=2, zorder=3)
        estilo_panel(ax, f"{titulo} (media móvil de {ventana})", unidad)
        ax.set_ylim(bottom=0)

    # Cambios de etapa: línea fina en los tres paneles + etiqueta en el de edad
    for cambio in cambios:
        x = cambio.get("interacciones")
        if x is None:
            continue
        for ax in (ax_edad, ax_long, ax_preg):
            ax.axvline(x, color=TINTA_TENUE, linewidth=0.8, linestyle=(0, (3, 3)), zorder=1)
        origen = " (manual)" if cambio.get("origen") == "manual" else ""
        ax_edad.annotate(f"{cambio['edad_anterior']}→{cambio['edad_nueva']}{origen}",
                         xy=(x, cambio["edad_nueva"]), xytext=(4, 4), textcoords="offset points",
                         fontsize=8, color=TINTA_SECUNDARIA)

    ax_preg.set_xlabel("Número de interacción", fontsize=9, color=TINTA_SECUNDARIA)
    fig.suptitle("Evolución del robot TR", x=0.01, ha="left", fontsize=14, color=TINTA)
    fig.text(0.01, 0.945,
             f"{len(metricas)} interacciones · {len(cambios)} cambios de etapa · "
             "puntos = cada interacción, línea = media móvil",
             fontsize=9, color=TINTA_SECUNDARIA)
    fig.tight_layout(rect=(0, 0, 1, 0.94))

    ruta_png = args.salida / "evolucion_tr.png"
    fig.savefig(ruta_png, dpi=200, facecolor=FONDO)
    print(f"✅ Gráfica: {ruta_png.resolve()}")
    print(f"✅ Tabla:   {ruta_csv.resolve()}")


if __name__ == "__main__":
    main()
