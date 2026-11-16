"""
tr_brain.learning — Aprendizaje (extracción, refuerzo, asociación, olvido)
=========================================================================
Convierte conversación en conocimiento estructurado (sujeto-relación-objeto) y
lo mantiene vivo:

  - extraer_hechos()        : saca hechos de una frase (LLM + heurística)
  - aprender()              : pipeline extraer -> guardar
  - guardar_hecho()         : conocimiento repetido SUBE de confianza (refuerzo)
  - asociar_conceptos()     : enlaza hechos que comparten entidades (grafo)
  - recordar_sobre(tema)    : recupera lo que sabe de un tema
  - olvidar_poco_relevante(): decaimiento + poda de lo poco relevante

Comparte la base de datos con Memoria (reutiliza su conexión y su lock).

Ejemplo: "mi perro se llama Toby" -> (perro del usuario, se_llama, Toby)
"""
import json
import time
import re
import random
import logging
from . import config

log = logging.getLogger("tr_brain.learning")


class Aprendizaje:
    def __init__(self, memoria, llm=None):
        self.memoria = memoria        # comparte la conexión SQLite
        self.llm = llm                # para extracción con el modelo (opcional)
        self._crear_tablas()

    def _crear_tablas(self):
        with self.memoria._lock:
            self.memoria.conn.executescript("""
            CREATE TABLE IF NOT EXISTS conocimiento(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sujeto TEXT, relacion TEXT, objeto TEXT,
                confianza REAL DEFAULT 0.5,
                refuerzos INTEGER DEFAULT 1,
                creado REAL, actualizado REAL,
                UNIQUE(sujeto, relacion, objeto));

            CREATE TABLE IF NOT EXISTS asociaciones(
                a INTEGER, b INTEGER, peso REAL DEFAULT 1.0,
                UNIQUE(a, b));
            """)
            self.memoria.conn.commit()

    # ----- EXTRACCIÓN ------------------------------------------------------
    def extraer_hechos(self, texto):
        """Devuelve lista de dicts {sujeto, relacion, objeto}."""
        hechos = []
        # 1) Vía LLM (más potente) solo si se ha activado (consume cuota extra)
        if config.EXTRAER_HECHOS_CON_LLM and self.llm and self.llm.disponible:
            prompt = (
                "Extrae los hechos personales DURADEROS de la frase del usuario. "
                "Devuelve SOLO un array JSON de objetos con campos "
                '"sujeto", "relacion", "objeto". Si no hay hechos, devuelve []. '
                'Ejemplo: entrada "mi perro se llama Toby" -> '
                '[{"sujeto":"perro del usuario","relacion":"se_llama","objeto":"Toby"}].\n'
                f"Frase: {texto}"
            )
            datos = self.llm.parsear_json(self.llm.generar(prompt, temperatura=0.0, max_tokens=200))
            if isinstance(datos, list):
                hechos = [h for h in datos if isinstance(h, dict) and h.get("objeto")]
        # 2) Heurística de respaldo (offline): patrones simples en español
        if not hechos:
            hechos = self._heuristica(texto)
        return hechos

    def _heuristica(self, texto):
        t = texto.strip()
        out = []
        m = re.search(r"\bmi\s+([\wáéíóúñ]+)\s+se\s+llama\s+([\wáéíóúñ]+)", t, re.I)
        if m:
            out.append({"sujeto": f"{m.group(1)} del usuario", "relacion": "se_llama", "objeto": m.group(2)})
        m = re.search(r"\b(?:me\s+llamo|soy)\s+([A-ZÁÉÍÓÚ][\wáéíóúñ]+)", t)
        if m:
            out.append({"sujeto": "usuario", "relacion": "se_llama", "objeto": m.group(1)})
        m = re.search(r"\bme\s+gustan?\s+(.+)", t, re.I)
        if m:
            out.append({"sujeto": "usuario", "relacion": "le_gusta", "objeto": m.group(1).strip(" .")})
        m = re.search(r"\bvivo\s+en\s+(.+)", t, re.I)
        if m:
            out.append({"sujeto": "usuario", "relacion": "vive_en", "objeto": m.group(1).strip(" .")})
        return out

    # ----- ALMACENAMIENTO + REFUERZO --------------------------------------
    def aprender(self, texto):
        """Pipeline completo. Devuelve nº de hechos aprendidos/reforzados."""
        n = 0
        for h in self.extraer_hechos(texto):
            try:
                self.guardar_hecho(h["sujeto"], h["relacion"], h["objeto"],
                                   float(h.get("confianza", 0.6)))
                n += 1
            except Exception as e:
                log.debug(f"Hecho descartado {h}: {e}")
        if n:
            log.info(f"Aprendidos/reforzados {n} hechos de: {texto[:50]}")
        return n

    def guardar_hecho(self, sujeto, relacion, objeto, confianza=0.6):
        ahora = time.time()
        sujeto = sujeto.lower().strip()
        relacion = relacion.lower().strip().replace(" ", "_")
        objeto = str(objeto).strip()
        with self.memoria._lock:
            c = self.memoria.conn.cursor()
            f = c.execute("SELECT id, confianza FROM conocimiento WHERE sujeto=? AND relacion=? AND objeto=?",
                          (sujeto, relacion, objeto)).fetchone()
            if f:
                # REFUERZO: ya lo sabía -> sube la confianza
                nueva = min(1.0, f["confianza"] + 0.15)
                c.execute("UPDATE conocimiento SET confianza=?, refuerzos=refuerzos+1, actualizado=? WHERE id=?",
                          (nueva, ahora, f["id"]))
                id_ = f["id"]
            else:
                c.execute("""INSERT INTO conocimiento(sujeto,relacion,objeto,confianza,refuerzos,creado,actualizado)
                             VALUES (?,?,?,?,1,?,?)""", (sujeto, relacion, objeto, confianza, ahora, ahora))
                id_ = c.lastrowid
            self.memoria.conn.commit()
        self.asociar_conceptos(id_, sujeto, objeto)
        return id_

    def asociar_conceptos(self, id_hecho, sujeto, objeto):
        """Enlaza este hecho con otros que comparten sujeto u objeto (grafo de ideas)."""
        with self.memoria._lock:
            rel = self.memoria.conn.execute(
                "SELECT id FROM conocimiento WHERE (sujeto IN (?,?) OR objeto IN (?,?)) AND id<>?",
                (sujeto, objeto, sujeto, objeto, id_hecho)).fetchall()
            for r in rel:
                a, b = sorted((id_hecho, r["id"]))
                self.memoria.conn.execute(
                    "INSERT INTO asociaciones(a,b,peso) VALUES(?,?,1.0) "
                    "ON CONFLICT(a,b) DO UPDATE SET peso=peso+0.5", (a, b))
            self.memoria.conn.commit()

    # ----- RECUPERACIÓN ----------------------------------------------------
    def recordar_sobre(self, tema, limite=6):
        like = f"%{tema.lower()}%"
        with self.memoria._lock:
            filas = self.memoria.conn.execute(
                "SELECT * FROM conocimiento WHERE sujeto LIKE ? OR objeto LIKE ? OR relacion LIKE ? "
                "ORDER BY confianza DESC, refuerzos DESC LIMIT ?",
                (like, like, like, limite)).fetchall()
        return [dict(f) for f in filas]

    def contar_hechos(self) -> int:
        """Cuántos hechos distintos sabe el robot (mide su madurez)."""
        with self.memoria._lock:
            r = self.memoria.conn.execute("SELECT COUNT(*) AS n FROM conocimiento").fetchone()
        return r["n"] if r else 0

    def todo_lo_que_se(self, limite=50):
        with self.memoria._lock:
            filas = self.memoria.conn.execute(
                "SELECT * FROM conocimiento ORDER BY confianza DESC LIMIT ?", (limite,)).fetchall()
        return [dict(f) for f in filas]

    def hecho_curioso(self):
        """Un hecho al azar ponderado por confianza (para la iniciativa)."""
        hechos = self.todo_lo_que_se(50)
        if not hechos:
            return None
        return random.choices(hechos, weights=[max(0.05, h["confianza"]) for h in hechos])[0]

    # ----- OLVIDO + EXPORT -------------------------------------------------
    def olvidar_poco_relevante(self):
        ahora = time.time()
        with self.memoria._lock:
            filas = self.memoria.conn.execute(
                "SELECT id, confianza, refuerzos, actualizado FROM conocimiento").fetchall()
            for f in filas:
                dias = (ahora - f["actualizado"]) / 86400.0
                nueva = f["confianza"] * (config.FACTOR_OLVIDO ** dias)
                if nueva < config.UMBRAL_OLVIDO and f["refuerzos"] < 2:
                    self.memoria.conn.execute("DELETE FROM conocimiento WHERE id=?", (f["id"],))
                else:
                    self.memoria.conn.execute("UPDATE conocimiento SET confianza=? WHERE id=?",
                                              (nueva, f["id"]))
            self.memoria.conn.commit()
        self.exportar_json()

    def exportar_json(self):
        try:
            config.RUTA_CONOCIMIENTO.write_text(
                json.dumps(self.todo_lo_que_se(10000), indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            log.warning(f"No se pudo exportar conocimiento: {e}")

    # ----- MIGRACIÓN desde memory.json antiguo -----------------------------
    def importar_facts_legacy(self, facts: dict) -> int:
        n = 0
        for k, v in (facts or {}).items():
            try:
                self.guardar_hecho(str(k), "es", str(v), 0.7)
                n += 1
            except Exception:
                pass
        return n
