#!/usr/bin/env python3
"""
demo_cerebro.py — Habla con el cerebro de TR SIN ROS ni hardware
===================================================================
Usa exactamente el mismo CerebroTR que brain_node (memoria, emociones, etapas
de desarrollo, métricas), pero por consola. Piensa con Claude a través de tu
sesión de Claude Code (pip install claude-agent-sdk + claude auth login); si no,
con Ollama en local.

Uso:
    py -3 scripts\\demo_cerebro.py           # Windows
    python3 scripts/demo_cerebro.py          # Linux
    TR_LLM=ollama python3 scripts/demo_cerebro.py   # forzar Ollama (offline)

Comandos dentro del chat:
    /estado      edad, etapa, hechos, personalidad, emociones y métricas
    /edad N      fija la edad mental (como /tr/set_age en ROS)
    /evaluar     fuerza ahora la evaluación de maduración (normalmente cada 100)
    /prompt      muestra el system prompt que recibe el modelo
    salir        guarda y termina (también Ctrl+C)

Variable de entorno TR_MEMORY_DIR: carpeta de memoria (por defecto ~/.tr_robot_ollama).
Parámetros del agente (modelo, esfuerzo...): tr_robot_brain/config/agente_tr.json.
"""
import json
import os
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")  # acentos correctos en la consola de Windows

# Permite importar tr_robot_brain desde el código fuente, sin instalarlo
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tr_robot_brain"))
from tr_robot_brain.cerebro import CerebroTR  # noqa: E402
from tr_robot_brain.emotions import humanizar_segundos  # noqa: E402


def imprimir_estado(cerebro: CerebroTR):
    estado = cerebro.resumen_estado()
    print(json.dumps(estado, ensure_ascii=False, indent=2))


def main():
    memory_dir = os.environ.get("TR_MEMORY_DIR")
    cerebro = CerebroTR(
        memory_dir=Path(memory_dir) if memory_dir else None,
        log_info=lambda m: print(f"   {m}"),
        log_error=lambda m: print(f"   ⚠️ {m}"),
        learning_async=False,   # en consola, aprender en orden (salida más legible)
        timeout_chat=120,       # CPU de portátil sin GPU: margen amplio
    )
    estado = cerebro.resumen_estado()
    print("=== Demo del cerebro de TR (sin ROS) ===")
    print(f"    modelo: {cerebro.llm.descripcion}")
    print(f"    memoria: {cerebro.memory_file}")
    print(f"    {estado['edad']} años ({estado['etapa']}) · {estado['interacciones']} interacciones · "
          f"{estado['hechos']} hechos")
    if cerebro.segundos_apagado > 0:
        print(f"    💤 ha estado apagado {humanizar_segundos(cerebro.segundos_apagado)}")
    print("    Comandos: /estado  /edad N  /evaluar  /prompt  salir\n")

    comentario = cerebro.comentario_despertar()
    if comentario:
        print(f"TR (espontáneo): {comentario}\n")

    try:
        while True:
            try:
                texto = input("Tú: ").strip()
            except EOFError:
                break
            if not texto:
                continue
            if texto.lower() in ("salir", "exit", "quit"):
                break
            if texto == "/estado":
                imprimir_estado(cerebro)
                continue
            if texto.startswith("/edad"):
                try:
                    anterior, nueva = cerebro.set_edad(int(texto.split()[1]),
                                                       motivo="fijada manualmente (demo)")
                    print(f"   Edad mental: {anterior} → {nueva} años\n")
                    cerebro.guardar_memoria()
                except (IndexError, ValueError):
                    print("   Uso: /edad 14\n")
                continue
            if texto == "/evaluar":
                print(f"   Veredicto: {cerebro.evaluar_maduracion()}\n")
                cerebro.guardar_memoria()
                continue
            if texto == "/prompt":
                print(cerebro.construir_system_prompt() + "\n")
                continue

            print(f"TR: {cerebro.responder(texto)}\n")
            cerebro.guardar_memoria()  # tras cada turno: cerrar la ventana no pierde nada
    except KeyboardInterrupt:
        print()
    finally:
        cerebro.guardar_memoria()
        print(f"👋 Memoria guardada en {cerebro.memory_file}")


if __name__ == "__main__":
    main()
