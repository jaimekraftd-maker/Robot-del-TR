#!/usr/bin/env python3
"""
probar_pico.py — Prueba la Pico 2 W de la cabeza desde el PC, sin ROS
=======================================================================
Funciona en Windows con el Python normal:

    py -3 scripts\\probar_pico.py 192.168.1.50 ping       # ¿responde?, ¿ve el PCA9685?
    py -3 scripts\\probar_pico.py 192.168.1.50 leds       # recorre los estados
    py -3 scripts\\probar_pico.py 192.168.1.50 centro     # pan y tilt a 90, mandíbula a 60
    py -3 scripts\\probar_pico.py 192.168.1.50 servo 1 100
    py -3 scripts\\probar_pico.py 192.168.1.50 barrer 0   # recorre el canal entre sus topes

Monta las bocinas después de "centro". Canales: 0 pan, 1 tilt, 2 mandíbula.
"""
import argparse
import socket
import time

PUERTO = 4210
TOPES = {0: (30, 150), 1: (60, 120), 2: (60, 90)}  # los mismos que pico/main.py


def main():
    parser = argparse.ArgumentParser(description="Prueba la Pico de la cabeza de TR")
    parser.add_argument("host", help="IP de la Pico (la escribe por USB al conectarse)")
    parser.add_argument("orden", choices=["ping", "leds", "centro", "servo", "barrer"])
    parser.add_argument("canal", nargs="?", type=int, choices=sorted(TOPES))
    parser.add_argument("grados", nargs="?", type=float)
    a = parser.parse_args()
    if a.orden in ("servo", "barrer") and a.canal is None:
        parser.error(f"{a.orden} necesita un canal")
    if a.orden == "servo" and a.grados is None:
        parser.error("servo necesita los grados")

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    enviar = lambda orden: s.sendto(orden.encode(), (a.host, PUERTO))  # noqa: E731

    if a.orden == "ping":
        s.settimeout(2)
        enviar("P")
        try:
            print(s.recvfrom(64)[0].decode())
        except OSError:  # tiempo agotado, o Windows avisa de que nadie escucha
            print("Sin respuesta: revisa la IP y que el PC y la Pico estén en la misma red.")
    elif a.orden == "leds":
        for estado in ("idle", "listening", "thinking", "speaking", "error", "off"):
            print(estado)
            enviar(f"L {estado}")
            time.sleep(2)
    elif a.orden == "centro":
        for canal, grados in ((0, 90), (1, 90), (2, 60)):
            enviar(f"S {canal} {grados}")
    elif a.orden == "servo":
        enviar(f"S {a.canal} {a.grados}")
    else:
        minimo, maximo = TOPES[a.canal]
        recorrido = list(range(minimo, maximo + 1, 2))
        for grados in recorrido + recorrido[::-1]:
            enviar(f"S {a.canal} {grados}")
            time.sleep(0.05)


if __name__ == "__main__":
    main()
