"""
pico_link.py — Envía órdenes a la Pico 2 W de la cabeza por Wi-Fi (UDP)
=========================================================================
El protocolo está descrito en pico/main.py. Es UDP: si un paquete se pierde no
pasa nada, porque los nodos reenvían su estado una vez por segundo. Eso también
recupera los servos y los LEDs si la Pico se reinicia.

La IP sale del parámetro pico_host o de la variable de entorno TR_PICO_HOST;
sin ninguna de las dos los nodos usan el hardware local (Pi Zero 2 W).
"""
import os
import socket

PUERTO = 4210


def direccion_pico(parametro: str = "") -> str:
    return (parametro or os.environ.get("TR_PICO_HOST", "")).strip()


class PicoLink:
    def __init__(self, host: str, logger=None, puerto: int = PUERTO):
        self.destino = (host, puerto)
        self.logger = logger
        self.en_error = False
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setblocking(False)

    def _enviar(self, orden: str):
        try:
            self.sock.sendto(orden.encode("ascii"), self.destino)
            self.en_error = False
        except OSError as e:
            if not self.en_error and self.logger is not None:  # avisa una vez, no en cada ciclo
                self.logger.error(f"📡 No puedo enviar a la Pico {self.destino[0]}: {e}")
            self.en_error = True

    def servo(self, canal: int, grados: float):
        self._enviar(f"S {canal} {grados:.1f}")

    def leds(self, estado: str):
        self._enviar(f"L {estado}")

    def close(self):
        self.sock.close()
