#!/usr/bin/env python3
"""Administrador de la finca. Uso:
  finca.py recoleccion FECHA PERSONA KG [--lote L]
  finca.py actividad FECHA LABOR COSTO [--persona P] [--lote L] [--jornales N]
  finca.py compra FECHA INSUMO TOTAL [--cantidad N --unidad U --proveedor X --lote L]
  finca.py pago FECHA PERSONA TOTAL [--concepto kg|jornal|otro --cantidad N --tarifa T]
  finca.py beneficio KG_PERGAMINO --desde FECHA --hasta FECHA   (agrupa recolecciones sin beneficiar)
  finca.py venta FECHA COMPRADOR KG PRECIO_KG [--beneficio ID]
  finca.py param CLAVE VALOR
  finca.py reporte [--desde FECHA --hasta FECHA]
  finca.py import-csv registro.csv
  finca.py import-xlsx lotes.xlsx   (idempotente)
  finca.py agenda [--desde FECHA]
"""
import argparse, csv, os, sqlite3, sys
D = os.path.dirname(os.path.abspath(__file__)); DB = os.path.join(D, "finca.db")
def con():
    c = sqlite3.connect(DB); c.execute("PRAGMA foreign_keys=ON")
    migrar(c); c.executescript(open(os.path.join(D, "schema.sql")).read()); return c
def migrar(c):
    c.executescript("CREATE TABLE IF NOT EXISTS lote(id INTEGER PRIMARY KEY, nombre TEXT UNIQUE NOT NULL, hectareas REAL, variedad TEXT, arboles INTEGER, notas TEXT);")
    for t, col in [("lote", "numero INTEGER"), ("lote", "numero_alterno INTEGER"), ("actividad", "cultivo TEXT"), ("actividad", "valor_jornal REAL"), ("actividad", "ref TEXT"), ("compra", "ref TEXT"), ("recoleccion", "ref TEXT")]:
        if t in [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")] and col.split()[0] not in [r[1] for r in c.execute(f"PRAGMA table_info({t})")]:
            c.execute(f"ALTER TABLE {t} ADD COLUMN {col}")
    for t in ("lote", "actividad", "compra", "recoleccion"):
        if t in [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")]:
            col = "numero" if t == "lote" else "ref"
            c.execute(f"CREATE UNIQUE INDEX IF NOT EXISTS ux_{t}_{col} ON {t}({col})")
def lnum(c, num, nombre):
    """Lote por número del Excel (o número alterno). Crea si no existe."""
    if num is None: return lid(c, None)
    r = c.execute("SELECT id FROM lote WHERE numero=? OR numero_alterno=?", (num, num)).fetchone()
    if r: return r[0]
    r = c.execute("SELECT id FROM lote WHERE upper(nombre)=upper(?)", (nombre,)).fetchone() if nombre else None
    if r: c.execute("UPDATE lote SET numero=? WHERE id=? AND numero IS NULL", (num, r[0])); return r[0]
    return c.execute("INSERT INTO lote(numero,nombre) VALUES(?,?)", (num, nombre or f"LOTE {num}")).lastrowid
def import_xlsx(c, path):
    import openpyxl
    wb = openpyxl.load_workbook(path, data_only=True); d = lambda v: v.strftime("%Y-%m-%d") if hasattr(v, "strftime") else v
    n = {}
    def ins(k, sql, args):
        cur = c.execute(sql, args); n[k] = n.get(k, 0) + cur.rowcount
    # Fusionar lotes existentes del chat
    for viejo, num, nuevo in [("Lote Sur", 13, "LOTE SUR"), ("Lote Este", 10, "LOTE ESTE")]:
        c.execute("UPDATE lote SET numero=?, nombre=?, notas='Fusionado desde \"'||?||'\" (chat)' WHERE nombre=? AND numero IS NULL", (num, nuevo, viejo, viejo))
    for _, num, nom in wb["LOTES"].iter_rows(min_row=2, values_only=True):
        if isinstance(num, int): lnum(c, num, nom)
    for r in wb["SIEMBRAS"].iter_rows(min_row=2, values_only=True):
        if not hasattr(r[0], "strftime"): continue
        if r[2] == 12 and r[3] == "LOTE_EJEMPLO":
            l = lnum(c, 15, "LOTE_EJEMPLO")
            c.execute("UPDATE lote SET numero_alterno=12, notas='INCONSISTENCIA: LOTES dice 15, SIEMBRAS dice 12' WHERE id=?", (l,))
        else: l = lnum(c, r[2], r[3])
        ins("siembra", "INSERT OR IGNORE INTO siembra(lote_id,fecha,tipo,variedad,dist_planta_m,dist_surco_m,plantas,fecha_renovacion,ref) VALUES(?,?,?,?,?,?,?,?,?)", (l, d(r[0]), r[1], r[4], r[5], r[6], r[7], d(r[8]), f"SIEMBRAS:{d(r[0])}:{r[2]}"))
        c.execute("UPDATE lote SET variedad=?, arboles=? WHERE id=?", (r[4], r[7], l))
    for r in wb["FLORACIONES"].iter_rows(min_row=2, values_only=True):
        if not hasattr(r[1], "strftime"): continue
        ins("floracion", "INSERT OR IGNORE INTO floracion(lote_id,fecha,calificacion,control_roya,control_broca,cosecha_estimada,ref) VALUES(?,?,?,?,?,?,?)", (lnum(c, r[2], r[3]), d(r[1]), r[4], d(r[5]), d(r[6]), d(r[7]), f"FLORACIONES:{d(r[1])}:{r[2]}"))
    for i, r in enumerate(wb["ACTIVIDADES"].iter_rows(min_row=2, values_only=True), 2):
        if not hasattr(r[0], "strftime"): continue  # fila TOTAL / vacías
        ins("actividad", "INSERT OR IGNORE INTO actividad(fecha,labor,lote_id,cultivo,jornales,valor_jornal,costo_cop,ref,notas) VALUES(?,?,?,?,?,?,?,?,?)", (d(r[0]), r[1], lnum(c, r[2], None) if r[2] is not None else None, r[3], r[4], r[5], r[6], f"ACTIVIDADES:{i}", None if r[2] is not None else "Sin lote en Excel"))
    for i, r in enumerate(wb["COMPRAS"].iter_rows(min_row=2, values_only=True), 2):
        if not hasattr(r[0], "strftime"): continue
        ins("compra", "INSERT OR IGNORE INTO compra(fecha,cantidad,unidad,insumo,total_cop,ref) VALUES(?,?,?,?,?,?)", (d(r[0]), r[1], r[2], r[3], r[4], f"COMPRAS:{i}"))
    for i, r in enumerate(wb["RECOLECCIÓN"].iter_rows(min_row=2, values_only=True), 2):
        if not hasattr(r[1], "strftime"): continue
        ins("recoleccion", "INSERT OR IGNORE INTO recoleccion(fecha,persona_id,lote_id,kg_cereza,fuente,ref,notas) VALUES(?,?,?,?,?,?,?)", (d(r[1]), pid(c, r[2] or "SIN_IDENTIFICAR"), lid(c, None), r[3], "excel", f"RECOLECCION:{i}", None if r[2] else "Recolector no indicado en Excel"))
    print("Nuevos registros:", n or "ninguno (ya importado)")
def pid(c, n, rol="recolector"):
    if not n: return None
    c.execute("INSERT OR IGNORE INTO persona(nombre,rol) VALUES(?,?)", (n.strip(), rol))
    return c.execute("SELECT id FROM persona WHERE nombre=?", (n.strip(),)).fetchone()[0]
def lid(c, n):
    n = n or "SIN_ASIGNAR"; c.execute("INSERT OR IGNORE INTO lote(nombre) VALUES(?)", (n,))
    return c.execute("SELECT id FROM lote WHERE nombre=?", (n,)).fetchone()[0]
def show(c, title, sql, args=()):
    cur = c.execute(sql, args); rows = cur.fetchall(); print(f"\n== {title} ==")
    if not rows: print("(sin datos)"); return
    print(" | ".join(d[0] for d in cur.description))
    for r in rows: print(" | ".join("" if v is None else str(v) for v in r))
def main():
    a = sys.argv[1:]
    if not a: print(__doc__); return
    p = argparse.ArgumentParser(); s = p.add_subparsers(dest="cmd")
    x = s.add_parser("recoleccion"); x.add_argument("fecha"); x.add_argument("persona"); x.add_argument("kg", type=float); x.add_argument("--lote"); x.add_argument("--fuente", default="chat")
    x = s.add_parser("actividad"); x.add_argument("fecha"); x.add_argument("labor"); x.add_argument("costo", type=float); x.add_argument("--persona"); x.add_argument("--lote"); x.add_argument("--jornales", type=float)
    x = s.add_parser("compra"); x.add_argument("fecha"); x.add_argument("insumo"); x.add_argument("total", type=float)
    for o in ("--cantidad", "--unidad", "--proveedor", "--lote"): x.add_argument(o)
    x = s.add_parser("pago"); x.add_argument("fecha"); x.add_argument("persona"); x.add_argument("total", type=float); x.add_argument("--concepto", default="otro"); x.add_argument("--cantidad", type=float); x.add_argument("--tarifa", type=float)
    x = s.add_parser("beneficio"); x.add_argument("kg_pergamino", type=float); x.add_argument("--desde", required=True); x.add_argument("--hasta", required=True)
    x = s.add_parser("venta"); x.add_argument("fecha"); x.add_argument("comprador"); x.add_argument("kg", type=float); x.add_argument("precio", type=float); x.add_argument("--beneficio", type=int)
    x = s.add_parser("param"); x.add_argument("clave"); x.add_argument("valor", type=float)
    x = s.add_parser("reporte"); x.add_argument("--desde", default="0000"); x.add_argument("--hasta", default="9999")
    x = s.add_parser("import-csv"); x.add_argument("path")
    x = s.add_parser("import-xlsx"); x.add_argument("path")
    x = s.add_parser("agenda"); x.add_argument("--desde", default=__import__("datetime").date.today().isoformat())
    g = p.parse_args(a); c = con()
    if g.cmd == "recoleccion":
        c.execute("INSERT INTO recoleccion(fecha,persona_id,lote_id,kg_cereza,fuente) VALUES(?,?,?,?,?)", (g.fecha, pid(c, g.persona), lid(c, g.lote), g.kg, g.fuente))
    elif g.cmd == "actividad":
        c.execute("INSERT INTO actividad(fecha,labor,persona_id,lote_id,jornales,costo_cop) VALUES(?,?,?,?,?,?)", (g.fecha, g.labor, pid(c, g.persona, "trabajador"), lid(c, g.lote) if g.lote else None, g.jornales, g.costo))
    elif g.cmd == "compra":
        c.execute("INSERT INTO compra(fecha,insumo,proveedor,cantidad,unidad,total_cop,lote_id) VALUES(?,?,?,?,?,?,?)", (g.fecha, g.insumo, g.proveedor, g.cantidad, g.unidad, g.total, lid(c, g.lote) if g.lote else None))
    elif g.cmd == "pago":
        c.execute("INSERT INTO pago(fecha,persona_id,concepto,cantidad,tarifa_cop,total_cop) VALUES(?,?,?,?,?,?)", (g.fecha, pid(c, g.persona), g.concepto, g.cantidad, g.tarifa, g.total))
    elif g.cmd == "beneficio":
        ids = [r[0] for r in c.execute("SELECT id FROM recoleccion WHERE fecha BETWEEN ? AND ? AND id NOT IN (SELECT recoleccion_id FROM beneficio_recoleccion)", (g.desde, g.hasta))]
        kg = c.execute(f"SELECT SUM(kg_cereza) FROM recoleccion WHERE id IN ({','.join('?'*len(ids)) or 'NULL'})", ids).fetchone()[0] or 0
        f = c.execute("SELECT valor FROM parametro WHERE clave='factor_cereza_pergamino'").fetchone()[0]
        b = c.execute("INSERT INTO beneficio(fecha_inicio,fecha_fin,kg_cereza,kg_pergamino_seco,factor_supuesto) VALUES(?,?,?,?,?)", (g.desde, g.hasta, kg, g.kg_pergamino, f)).lastrowid
        c.executemany("INSERT INTO beneficio_recoleccion VALUES(?,?)", [(b, i) for i in ids])
        print(f"Beneficio {b}: {kg} kg cereza -> {g.kg_pergamino} kg pergamino (factor real {kg/g.kg_pergamino:.2f})")
    elif g.cmd == "venta":
        v = c.execute("INSERT INTO venta(fecha,comprador,kg,precio_kg_cop) VALUES(?,?,?,?)", (g.fecha, g.comprador, g.kg, g.precio)).lastrowid
        if g.beneficio: c.execute("INSERT INTO venta_beneficio VALUES(?,?,?)", (v, g.beneficio, g.kg))
    elif g.cmd == "param":
        c.execute("INSERT INTO parametro(clave,valor) VALUES(?,?) ON CONFLICT(clave) DO UPDATE SET valor=excluded.valor", (g.clave, g.valor))
    elif g.cmd == "import-csv":
        n = 0
        for r in csv.DictReader(open(g.path, encoding="utf-8")):
            if r["tipo"] == "recoleccion":
                pi = pid(c, r["persona"])
                if c.execute("SELECT 1 FROM recoleccion WHERE fecha=? AND persona_id=? AND kg_cereza=?", (r["fecha"], pi, float(r["cantidad"]))).fetchone(): continue
                c.execute("INSERT INTO recoleccion(fecha,persona_id,lote_id,kg_cereza,fuente) VALUES(?,?,?,?,?)", (r["fecha"], pi, lid(c, None), float(r["cantidad"]), r["fuente"])); n += 1
            elif r["tipo"] == "compra":
                c.execute("INSERT INTO compra(fecha,insumo,cantidad,unidad,total_cop) VALUES(?,?,?,?,?)", (r["fecha"], r["descripcion"], r["cantidad"] or None, r["unidad"], float(r["valor_cop"] or 0))); n += 1
            elif r["tipo"] == "actividad":
                c.execute("INSERT INTO actividad(fecha,labor,persona_id,costo_cop) VALUES(?,?,?,?)", (r["fecha"], r["descripcion"], pid(c, r["persona"], "trabajador"), float(r["valor_cop"] or 0))); n += 1
            elif r["tipo"] == "venta":
                q = float(r["cantidad"]); c.execute("INSERT INTO venta(fecha,comprador,kg,precio_kg_cop) VALUES(?,?,?,?)", (r["fecha"], r["persona"], q, float(r["valor_cop"]) / q)); n += 1
        print(f"Importados {n} registros")
    elif g.cmd == "import-xlsx": import_xlsx(c, g.path)
    elif g.cmd == "agenda":
        show(c, "Agenda (roya, broca, cosechas, renovaciones)", "SELECT * FROM v_agenda WHERE fecha>=? ORDER BY fecha, numero", (g.desde,))
    elif g.cmd == "reporte":
        w = (g.desde, g.hasta)
        show(c, "Recolección por día", "SELECT r.fecha, p.nombre, l.nombre lote, r.kg_cereza FROM recoleccion r JOIN persona p ON p.id=r.persona_id LEFT JOIN lote l ON l.id=r.lote_id WHERE r.fecha BETWEEN ? AND ? ORDER BY r.fecha", w)
        show(c, "Rendimiento por recolector", "SELECT p.nombre, COUNT(DISTINCT fecha) dias, SUM(kg_cereza) kg, ROUND(SUM(kg_cereza)/COUNT(DISTINCT fecha),1) kg_dia FROM recoleccion r JOIN persona p ON p.id=r.persona_id WHERE fecha BETWEEN ? AND ? GROUP BY p.id", w)
        show(c, "Rendimiento por lote", "SELECT * FROM v_rend_lote WHERE kg_cereza IS NOT NULL")
        show(c, "Conversión cereza→pergamino", "SELECT * FROM v_conversion")
        show(c, "Ficha por lote", "SELECT * FROM v_lote_ficha")
        show(c, "Próximos eventos", "SELECT * FROM v_agenda WHERE fecha>=date('now') ORDER BY fecha LIMIT 20")
        show(c, "Actividades", "SELECT fecha, labor, (SELECT numero FROM lote WHERE id=lote_id) lote, jornales, costo_cop FROM actividad WHERE fecha BETWEEN ? AND ?", w)
        show(c, "Compras", "SELECT fecha, insumo, cantidad, unidad, total_cop FROM compra WHERE fecha BETWEEN ? AND ?", w)
        show(c, "Pagos", "SELECT pg.fecha, p.nombre, concepto, total_cop FROM pago pg JOIN persona p ON p.id=pg.persona_id WHERE coalesce(pg.estado,'')<>'ANULADO' AND pg.fecha BETWEEN ? AND ?", w)
        show(c, "Costo por kg (acumulado)", "SELECT * FROM v_costo_kg")
        show(c, "Ventas y margen", "SELECT * FROM v_margen_venta")
        show(c, "Supuestos", "SELECT clave, valor, notas FROM parametro WHERE es_supuesto=1")
    c.commit()
if __name__ == "__main__": main()
