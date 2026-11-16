"""
tr_brain.memory — Memoria persistente (SQLite)
==============================================
Sustituye al memory.json plano por una base de datos que escala a años:
  - personas   : gente conocida (veces vista, primera/última vez)
  - recuerdos  : memoria episódica (conversaciones, eventos, avistamientos)

API solicitada: guardar_recuerdo, buscar_recuerdo, actualizar_recuerdo,
olvidar_recuerdo. Usable desde un nodo ROS o desde Python puro.

La conexión usa check_same_thread=False + un lock, porque varios hilos/timers
(ROS) pueden tocarla. El conocimiento semántico vive en la MISMA base de datos
y lo gestiona learning.py (que reutiliza esta conexión y este lock).
"""
import sqlite3
import json
import time
import threading
import logging
from . import config

log = logging.getLogger("tr_brain.memory")


class Memoria:
    def __init__(self, ruta_bd=None):
        ruta = str(ruta_bd or config.RUTA_BD)
        self.conn = sqlite3.connect(ruta, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._crear_tablas()

    def _crear_tablas(self):
        with self._lock:
            self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS personas(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT UNIQUE,
                primera_vez REAL, ultima_vez REAL,
                veces_visto INTEGER DEFAULT 0, notas TEXT);

            CREATE TABLE IF NOT EXISTS recuerdos(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tipo TEXT,                 -- conversacion | evento | avistamiento | pregunta
                contenido TEXT,
                persona_id INTEGER,
                importancia REAL DEFAULT 1.0,
                timestamp REAL,
                ultimo_acceso REAL,
                accesos INTEGER DEFAULT 0,
                metadatos TEXT,
                FOREIGN KEY(persona_id) REFERENCES personas(id));

            CREATE INDEX IF NOT EXISTS idx_rec_tipo ON recuerdos(tipo);
            CREATE INDEX IF NOT EXISTS idx_rec_ts ON recuerdos(timestamp);
            """)
            self.conn.commit()

    # ----- PERSONAS ---------------------------------------------------------
    def registrar_persona(self, nombre, notas=""):
        if not nombre:
            return None
        ahora = time.time()
        with self._lock:
            c = self.conn.cursor()
            fila = c.execute("SELECT id FROM personas WHERE nombre=?", (nombre,)).fetchone()
            if fila:
                c.execute("UPDATE personas SET ultima_vez=?, veces_visto=veces_visto+1 WHERE id=?",
                          (ahora, fila["id"]))
                self.conn.commit()
                return fila["id"]
            c.execute("INSERT INTO personas(nombre,primera_vez,ultima_vez,veces_visto,notas) VALUES(?,?,?,1,?)",
                      (nombre, ahora, ahora, notas))
            self.conn.commit()
            return c.lastrowid

    def buscar_persona(self, nombre):
        with self._lock:
            f = self.conn.execute("SELECT * FROM personas WHERE nombre=?", (nombre,)).fetchone()
        return dict(f) if f else None

    # ----- RECUERDOS (API solicitada) --------------------------------------
    def guardar_recuerdo(self, contenido, tipo="conversacion", persona_id=None,
                         importancia=config.IMPORTANCIA_POR_DEFECTO, metadatos=None):
        ahora = time.time()
        with self._lock:
            c = self.conn.cursor()
            c.execute("""INSERT INTO recuerdos
                (tipo, contenido, persona_id, importancia, timestamp, ultimo_acceso, accesos, metadatos)
                VALUES (?,?,?,?,?,?,0,?)""",
                      (tipo, contenido, persona_id, importancia, ahora, ahora,
                       json.dumps(metadatos or {})))
            self.conn.commit()
            return c.lastrowid

    def buscar_recuerdo(self, consulta="", tipo=None, limite=5):
        """
        Recupera recuerdos relevantes combinando importancia + recencia +
        coincidencia de palabras. Cada acceso REFUERZA el recuerdo (sube su
        importancia y lo hace más difícil de olvidar) -> memoria asociativa.
        """
        with self._lock:
            q = "SELECT * FROM recuerdos" + (" WHERE tipo=?" if tipo else "")
            filas = self.conn.execute(q, ((tipo,) if tipo else ())).fetchall()

        ahora = time.time()
        palabras = set(consulta.lower().split())
        puntuados = []
        for f in filas:
            score = f["importancia"]
            dias = (ahora - f["timestamp"]) / 86400.0
            score += max(0.0, 2.0 - dias * 0.1)           # recencia
            if palabras:
                texto = f["contenido"].lower()
                score += sum(1 for p in palabras if p in texto)  # relevancia léxica
            puntuados.append((score, f))

        puntuados.sort(key=lambda x: x[0], reverse=True)
        top = [dict(f) for _, f in puntuados[:limite]]
        self._reforzar_accesos([r["id"] for r in top])
        return top

    def actualizar_recuerdo(self, id_recuerdo, **campos):
        if not campos:
            return
        with self._lock:
            sets = ", ".join(f"{k}=?" for k in campos)
            self.conn.execute(f"UPDATE recuerdos SET {sets} WHERE id=?",
                              (*campos.values(), id_recuerdo))
            self.conn.commit()

    def olvidar_recuerdo(self, id_recuerdo):
        with self._lock:
            self.conn.execute("DELETE FROM recuerdos WHERE id=?", (id_recuerdo,))
            self.conn.commit()
            log.info(f"Recuerdo {id_recuerdo} olvidado.")

    def _reforzar_accesos(self, ids):
        if not ids:
            return
        ahora = time.time()
        with self._lock:
            self.conn.executemany(
                "UPDATE recuerdos SET accesos=accesos+1, ultimo_acceso=?, "
                "importancia=importancia+0.05 WHERE id=?",
                [(ahora, i) for i in ids])
            self.conn.commit()

    def resumen_reciente(self, n=8):
        with self._lock:
            filas = self.conn.execute(
                "SELECT * FROM recuerdos ORDER BY timestamp DESC LIMIT ?", (n,)).fetchall()
        return [dict(f) for f in reversed(filas)]

    # ----- OLVIDO NATURAL ---------------------------------------------------
    def decaer_y_olvidar(self):
        """La importancia decae con el tiempo; los recuerdos poco importantes y
        poco accedidos se eliminan. Llamar periódicamente (mantenimiento)."""
        ahora = time.time()
        with self._lock:
            filas = self.conn.execute(
                "SELECT id, importancia, timestamp, accesos FROM recuerdos").fetchall()
            for f in filas:
                dias = (ahora - f["timestamp"]) / 86400.0
                nueva = f["importancia"] * (config.FACTOR_OLVIDO ** dias)
                if nueva < config.UMBRAL_OLVIDO and f["accesos"] < 2:
                    self.conn.execute("DELETE FROM recuerdos WHERE id=?", (f["id"],))
                else:
                    self.conn.execute("UPDATE recuerdos SET importancia=? WHERE id=?",
                                      (nueva, f["id"]))
            self.conn.commit()

    # ----- MIGRACIÓN desde el memory.json antiguo --------------------------
    def importar_recuerdos_legacy(self, interactions: list) -> int:
        n = 0
        for it in interactions or []:
            u = it.get("user")
            r = it.get("tr")
            if u:
                self.guardar_recuerdo(f"El usuario dijo: {u}", "conversacion")
                n += 1
            if r:
                self.guardar_recuerdo(f"{config.NOMBRE_ROBOT} respondió: {r}", "conversacion")
        return n

    def cerrar(self):
        with self._lock:
            self.conn.close()
