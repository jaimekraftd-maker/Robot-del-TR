"""
main.py — Firmware de la Raspberry Pi Pico 2 W en la cabeza de TR (MicroPython)
================================================================================
El PC lo hace todo; la Pico solo obedece por Wi-Fi: recibe órdenes UDP y mueve
los servos (por el PCA9685) y los 3 LEDs de estado.

Órdenes (texto, puerto 4210):
    S <canal> <grados>   servo: 0 pan, 1 tilt, 2 mandíbula (se recorta a LIMITES)
    L <estado>           LEDs: idle, listening, thinking, speaking, error, off
    P                    responde "TR-PICO pca=<0|1> ip=<ip>"

Conexiones: PCA9685 SDA → GP4 (pin 6), SCL → GP5 (pin 7), VCC → 3V3 OUT (pin 36),
GND → pin 38. LEDs con 330 Ω: verde GP10 (pin 14), azul GP11 (pin 15), rojo GP12
(pin 16). Los servos se alimentan del V+ del PCA9685 con su propia fuente.

Instalar: copia este main.py y un config.py con WIFI_SSID y WIFI_PASSWORD a la
Pico (ver config_ejemplo.py). El rojo parpadea si no hay Wi-Fi o si lleva más de
5 s sin noticias del PC. Los servos no se mueven hasta la primera orden.
"""
import socket
import time

import network
from machine import Pin, SoftI2C

import config

PUERTO = 4210
PIN_SDA, PIN_SCL = 4, 5  # GP4 (pin físico 6) y GP5 (pin físico 7); GP3 de esta Pico está dañado
LIMITES = {0: (30, 150), 1: (60, 120), 2: (60, 90)}  # topes de la mecánica del cráneo
PULSO_MIN_US, PULSO_MAX_US = 500, 2500               # 0° y 180° del servo
SILENCIO_MS = 5000
REINTENTO_WIFI_MS = 5000

# estado → {led: None (fijo) | (ms_encendido, ms_apagado)}; igual que led_node.py
PATRONES = {
    "idle": {"verde": None},
    "listening": {"azul": None},
    "thinking": {"azul": (250, 250)},
    "speaking": {"verde": (100, 100)},
    "error": {"rojo": None},
    "off": {},
}
PATRON_SIN_CONTACTO = {"rojo": (500, 500)}


class PCA9685:
    """Lo mínimo del chip: 50 Hz y ancho de pulso por canal."""

    def __init__(self, i2c, direccion=0x40):
        self.i2c, self.direccion = i2c, direccion
        self._escribir(0x00, b"\x10")      # MODE1: dormir para poder cambiar la frecuencia
        self._escribir(0xFE, bytes([121]))  # PRESCALE: 25 MHz / (4096 × 50 Hz) − 1
        self._escribir(0x00, b"\x20")      # despertar, autoincremento
        time.sleep_ms(5)
        self._escribir(0x00, b"\xa0")      # reiniciar los PWM

    def _escribir(self, registro, datos):
        self.i2c.writeto_mem(self.direccion, registro, datos)

    def angulo(self, canal, grados):
        pulso_us = PULSO_MIN_US + (PULSO_MAX_US - PULSO_MIN_US) * grados / 180
        fin = int(pulso_us * 4096 / 20000)  # periodo de 20 ms en 4096 pasos
        self._escribir(0x06 + 4 * canal, bytes([0, 0, fin & 0xFF, fin >> 8]))


class Leds:
    def __init__(self):
        self.pines = {"verde": Pin(10, Pin.OUT), "azul": Pin(11, Pin.OUT), "rojo": Pin(12, Pin.OUT)}
        self.patron = None
        self.inicio = 0

    def poner(self, patron, ahora):
        if patron is not self.patron:
            self.patron, self.inicio = patron, ahora

    def actualizar(self, ahora):
        for color, pin in self.pines.items():
            if color not in self.patron:
                pin.value(0)
            elif self.patron[color] is None:
                pin.value(1)
            else:
                encendido, apagado = self.patron[color]
                pin.value(time.ticks_diff(ahora, self.inicio) % (encendido + apagado) < encendido)


def liberar_bus():
    """Si un tirón de los servos cortó una transferencia, el PCA9685 puede quedarse
    sujetando SDA abajo. Unos pulsos de reloj le dejan terminar y suelta el bus."""
    sda = Pin(PIN_SDA, Pin.IN)
    scl = Pin(PIN_SCL, Pin.OPEN_DRAIN, value=1)
    for _ in range(9):
        if sda.value():
            break
        scl.value(0)
        time.sleep_us(10)
        scl.value(1)
        time.sleep_us(10)


def crear_pca():
    try:
        liberar_bus()
        # I2C por software: funciona en cualquier pareja de pines; 100 kHz aguanta mejor el ruido
        return PCA9685(SoftI2C(sda=Pin(PIN_SDA), scl=Pin(PIN_SCL), freq=100000))
    except OSError:
        print("No encuentro el PCA9685 (revisa SDA, SCL, VCC y GND)")
        return None


def recortar(canal, grados):
    minimo, maximo = LIMITES[canal]
    return max(minimo, min(maximo, grados))


def conectar_wifi(wlan):
    print("Conectando a", config.WIFI_SSID)
    wlan.active(True)
    wlan.config(pm=0xA11140)  # sin ahorro de energía: mucha menos latencia
    wlan.connect(config.WIFI_SSID, config.WIFI_PASSWORD)


def crear_socket():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("0.0.0.0", PUERTO))
    s.setblocking(False)
    return s


def principal():
    wlan = network.WLAN(network.STA_IF)
    testigo = Pin("LED", Pin.OUT)  # LED de la placa: encendido = Wi-Fi conectado
    leds = Leds()
    pca = crear_pca()
    patron_pedido = PATRONES["idle"]
    ahora = time.ticks_ms()
    ultimo_contacto = time.ticks_add(ahora, -SILENCIO_MS)
    ultimo_intento = ahora
    conectar_wifi(wlan)
    sock = None

    while True:
        ahora = time.ticks_ms()
        if wlan.isconnected():
            if sock is None:
                sock = crear_socket()
                testigo.value(1)
                print("Wi-Fi OK. IP de la Pico:", wlan.ifconfig()[0])
        else:
            if sock is not None:
                sock.close()
                sock = None
                testigo.value(0)
            if time.ticks_diff(ahora, ultimo_intento) > REINTENTO_WIFI_MS:
                ultimo_intento = ahora
                conectar_wifi(wlan)

        if sock is not None:
            try:
                datos, origen = sock.recvfrom(64)
            except OSError:
                datos = None
            if datos:
                partes = datos.decode("ascii", "ignore").split()
                try:
                    if partes[0] == "S" and int(partes[1]) in LIMITES:
                        canal = int(partes[1])
                        if pca is None:
                            pca = crear_pca()
                        if pca is not None:
                            pca.angulo(canal, recortar(canal, float(partes[2])))
                        ultimo_contacto = ahora
                    elif partes[0] == "L" and partes[1] in PATRONES:
                        patron_pedido = PATRONES[partes[1]]
                        ultimo_contacto = ahora
                    elif partes[0] == "P":
                        if pca is None:
                            pca = crear_pca()
                        respuesta = "TR-PICO pca=%d ip=%s" % (pca is not None, wlan.ifconfig()[0])
                        sock.sendto(respuesta.encode(), origen)
                except (IndexError, ValueError):
                    pass  # orden mal formada: se ignora
                except OSError:
                    print("Se perdió el PCA9685")
                    pca = None

        sin_contacto = sock is None or time.ticks_diff(ahora, ultimo_contacto) > SILENCIO_MS
        leds.poner(PATRON_SIN_CONTACTO if sin_contacto else patron_pedido, ahora)
        leds.actualizar(ahora)
        time.sleep_ms(2)


principal()
