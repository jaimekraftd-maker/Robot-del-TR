#!/usr/bin/env python3
"""
led_node.py — LEDs de estado de la cabeza
============================================
Muestra en 3 LEDs el estado que llega por /tr/status, por Wi-Fi a través de la
Pico 2 W si hay pico_host o TR_PICO_HOST (allí parpadean solos), y si no, por
GPIO de la Pi Zero 2 W (numeración BCM):

  idle       → verde fijo              (esperando)
  listening  → azul fijo               (alguien está hablando)
  thinking   → azul parpadeando        (el cerebro está pensando)
  speaking   → verde parpadeando rápido
  error      → rojo fijo

Cada LED va con su resistencia (220-330 Ω) entre el pin GPIO y GND.
Cualquier otro valor de /tr/status (p.ej. órdenes como "reset_personality")
se ignora. Sin GPIO disponible funciona en modo simulación (solo logs).
"""
import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from tr_robot_head.pico_link import PicoLink, direccion_pico

try:
    from gpiozero import LED
except Exception:  # ImportError o sin backend de GPIO
    LED = None

# estado → {led: None (fijo) | (t_encendido, t_apagado) (parpadeo)}
PATRONES = {
    "idle": {"verde": None},
    "listening": {"azul": None},
    "thinking": {"azul": (0.25, 0.25)},
    "speaking": {"verde": (0.1, 0.1)},
    "error": {"rojo": None},
}


class LedNode(Node):
    def __init__(self):
        super().__init__("led_node")
        self.declare_parameter("pin_verde", 17)
        self.declare_parameter("pin_azul", 27)
        self.declare_parameter("pin_rojo", 22)
        self.declare_parameter("pico_host", "")
        self.get_logger().info("💡 Iniciando led_node...")

        self.leds = {}
        self.pico = None
        host = direccion_pico(str(self.get_parameter("pico_host").value))
        if host:
            self.pico = PicoLink(host, self.get_logger())
            self.get_logger().info(f"💡 LEDs por Wi-Fi: Pico en {host}.")
            self.create_timer(1.0, lambda: self.pico.leds(self.estado))  # UDP puede perderse
        elif LED is None:
            self.get_logger().warn("💡 gpiozero no disponible: modo SIMULACIÓN.")
        else:
            for color in ("verde", "azul", "rojo"):
                pin = self.get_parameter(f"pin_{color}").value
                try:
                    self.leds[color] = LED(pin)
                except Exception as e:
                    self.get_logger().error(f"💡 No pude usar GPIO{pin} para el LED {color}: {e}")

        self.estado = None
        self.create_subscription(String, "/tr/status", self._on_status, 10)
        self._aplicar("idle")
        self.get_logger().info("💡 led_node listo.")

    def _on_status(self, msg: String):
        estado = msg.data.strip()
        if estado in PATRONES and estado != self.estado:
            self._aplicar(estado)

    def _aplicar(self, estado: str):
        self.estado = estado
        self.get_logger().debug(f"💡 Estado: {estado}")
        if self.pico is not None:
            self.pico.leds(estado)
            return
        patron = PATRONES[estado]
        for color, led in self.leds.items():
            try:
                if color not in patron:
                    led.off()
                elif patron[color] is None:
                    led.on()
                else:
                    encendido, apagado = patron[color]
                    led.blink(on_time=encendido, off_time=apagado, background=True)
            except Exception as e:
                self.get_logger().error(f"💡 Error controlando el LED {color}: {e}")

    def destroy_node(self):
        if self.pico is not None:
            self.pico.leds("off")
            self.pico.close()
        for led in self.leds.values():
            try:
                led.off()
                led.close()
            except Exception:
                pass
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = LedNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
