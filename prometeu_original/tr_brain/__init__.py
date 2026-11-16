"""
tr_brain — Núcleo cognitivo reutilizable del robot TR.

Librería PURA de Python (sin ROS, sin hardware) que aporta memoria persistente,
aprendizaje, personalidad evolutiva e iniciativa. La importan tanto los nodos
ROS 2 del robot como el demo de consola (demo_consola.py).

Importar este paquete NO requiere tener instalado google-generativeai: el LLM
se carga de forma perezosa y, si falta, el cerebro funciona en modo OFFLINE.
"""
from .cognitive_core import CerebroCognitivo  # noqa: F401

__all__ = ["CerebroCognitivo"]
__version__ = "0.1.0"
