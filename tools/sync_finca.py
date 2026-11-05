#!/usr/bin/env python3
"""Sincroniza finca.db -> páginas de instancias de la ontología (Obsidian).
Uso: python tools/sync_finca.py [ruta/finca.db]
Genera wiki/ontologia/instancias/{lotes,personas,eventos}, wiki/ontologia/indicadores
y un snapshot CSV en raw/finca-datos/snapshot-AAAA-MM-DD. No borra nada fuera de esas carpetas generadas."""
import sqlite3, sys, os, csv, re, datetime
from collections import defaultdict
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = sys.argv[1] if len(sys.argv) > 1 else 'finca.db'
HOY = datetime.date.today().isoformat()
c = sqlite3.connect(DB); c.row_factory = sqlite3.Row
q = lambda s, *a: [dict(r) for r in c.execute(s, a)]

def cop(v):
    if v is None: return '—'
    s = f"{abs(v):,.0f}".replace(',', '.')
    return ('-' if v < 0 else '') + '$' + s
def num(v, d=2):
    if v is None: return '—'
    s = f"{v:,.{d}f}".replace(',', 'X').replace('.', ',').replace('X', '.')
    return s.rstrip('0').rstrip(',') if ',' in s else s
def safe(n): return re.sub(r'[<>:"/\\|?*]', '-', n).strip()
def tit(n): return ' '.join(w.capitalize() if (i==0 or w.lower() not in ('de','la','el','para','los')) else w.lower() for i,w in enumerate(n.split()))
def lote_page(l): return safe('Lote ' + tit(l['nombre']))
def per_page(p): return safe(p['nombre'] if p['nombre'] != 'SIN_IDENTIFICAR' else 'Persona sin identificar')
def fm(tipo, tags, extra=None):
    s = f"---\ntipo: {tipo}\ntags: [{', '.join(tags)}]\nfuentes: [finca.db]\nactualizado: {HOY}\ngenerado_por: tools/sync_finca.py\n"
    for k, v in (extra or {}).items(): s += f"{k}: {v}\n"
    return s + "---\n"

lotes = {l['id']: l for l in q('select * from lote')}
pers = {p['id']: p for p in q('select * from persona')}
act = q('select * from actividad order by fecha,id')
rec = q('select * from recoleccion order by fecha,id')
pag = q('select * from pago order by fecha,id')
com = q('select * from compra order by fecha,id')
deu = q('select * from deuda')
sie = q('select * from siembra')
flo = q('select * from floracion order by fecha')
ven = q('select * from venta')
ben = q('select * from beneficio')
par = {p['clave']: p for p in q('select * from parametro')}
factor = par.get('factor_cereza_pergamino', {}).get('valor', 5.0)

base = os.path.join(ROOT, 'wiki', 'ontologia')
dirs = {k: os.path.join(base, 'instancias', k) for k in ('lotes', 'personas', 'eventos')}
dirs['indicadores'] = os.path.join(base, 'indicadores')
for d in dirs.values(): os.makedirs(d, exist_ok=True)
def W(d, name, txt):
    open(os.path.join(dirs[d], name + '.md'), 'w', encoding='utf-8').write(txt)

# Eventos (agrupación de actividades por código evento)
ev = defaultdict(list)
for a in act: ev[a['evento'] or f"ACT-{a['id']}"].append(a)

# ---- Lotes
for lid, l in lotes.items():
    A = [a for a in act if a['lote_id'] == lid]; R = [r for r in rec if r['lote_id'] == lid]
    C = [x for x in com if x['lote_id'] == lid]; S = [s for s in sie if s['lote_id'] == lid]
    F = [f for f in flo if f['lote_id'] == lid]
    j = sum(a['jornales'] or 0 for a in A); ca = sum(a['costo_cop'] or 0 for a in A)
    cc = sum(x['total_cop'] for x in C); kg = sum(r['kg_cereza'] for r in R)
    t = fm('objeto/Lote', ['lote', 'finca-la-esperanza'], {'id_db': lid, 'numero': l['numero'] or 'pendiente'})
    t += f"# {lote_page(l)}\n\nObjeto [[Lote]] de [[Finca La Esperanza]].\n\n| Propiedad | Valor |\n|---|---|\n"
    t += f"| Número | {l['numero'] or 'pendiente'} |\n| Hectáreas | {num(l['hectareas']) if l['hectareas'] else 'pendiente (ver [[pendientes]])'} |\n"
    t += f"| Variedad | {l['variedad'] or 'pendiente'} |\n| Árboles | {num(l['arboles'],0) if l['arboles'] else 'pendiente'} |\n| Notas | {l['notas'] or ''} |\n\n"
    if l['variedad'] and 'CASTILLO' in l['variedad']: t += "Variedad: [[Variedad Castillo]].\n\n"
    t += f"## Resumen\n- Jornales registrados: {num(j)}\n- Costo de labores: {cop(ca)}\n- Compras asignadas: {cop(cc)}\n- Café cereza recolectado: {num(kg)} kg (≈ {num(kg/factor)} kg pergamino seco con factor supuesto {num(factor)})\n\n"
    if S:
        t += "## Siembras\n" + ''.join(f"- {s['fecha']}: {s['variedad']}, {s['plantas']} plantas a {num(s['dist_planta_m'])} × {num(s['dist_surco_m'])} m; renovación prevista {s['fecha_renovacion']} → [[Siembra y establecimiento]]\n" for s in S) + "\n"
    if F:
        t += "## Floraciones\n| Fecha | Calificación | Control roya | Control broca | Cosecha estimada |\n|---|---|---|---|---|\n" + ''.join(f"| {f['fecha']} | {f['calificacion']} | {f['control_roya']} | {f['control_broca']} | {f['cosecha_estimada']} |\n" for f in F) + "\nVer [[Roya del cafeto]] y [[Broca del café]].\n\n"
    evs = sorted({a['evento'] or f"ACT-{a['id']}" for a in A})
    if evs: t += "## Eventos\n" + ''.join(f"- [[{safe(e)}]] — {ev[e][0]['labor']}\n" for e in evs) + "\n"
    if R:
        t += "## Recolecciones\n" + ''.join(f"- {r['fecha']}: {num(r['kg_cereza'])} kg — [[{per_page(pers[r['persona_id']])}]]\n" for r in R) + "\n"
    if C: t += "## Compras\n" + ''.join(f"- {x['fecha']}: {x['insumo']} ({num(x['cantidad'])} {x['unidad']}) {cop(x['total_cop'])}\n" for x in C) + "\n"
    W('lotes', lote_page(l), t)

# ---- Personas
for pid, p in pers.items():
    A = [a for a in act if a['persona_id'] == pid]; R = [r for r in rec if r['persona_id'] == pid]; P = [x for x in pag if x['persona_id'] == pid]
    t = fm('objeto/Persona', ['persona', (p['rol'] or '').lower()], {'id_db': pid, 'rol': p['rol']})
    t += f"# {per_page(p)}\n\nObjeto [[Persona]] · rol: {p['rol']}\n\n## Resumen\n- Jornales: {num(sum(a['jornales'] or 0 for a in A))} ({cop(sum(a['costo_cop'] or 0 for a in A))})\n- Kg cereza recolectados: {num(sum(r['kg_cereza'] for r in R))}\n- Pagos recibidos: {cop(sum(x['total_cop'] for x in P))}\n\n"
    evs = sorted({a['evento'] or f"ACT-{a['id']}" for a in A})
    if evs: t += "## Eventos en los que participó\n" + ''.join(f"- [[{safe(e)}]]\n" for e in evs) + "\n"
    ls = sorted({r['lote_id'] for r in R if r['lote_id']})
    if ls: t += "## Lotes recolectados\n" + ''.join(f"- [[{lote_page(lotes[x])}]]\n" for x in ls) + "\n"
    if P: t += "## Pagos\n" + ''.join(f"- {x['fecha']}: {x['concepto']} {num(x['cantidad'])} × {cop(x['tarifa_cop'])} = {cop(x['total_cop'])}{' — ' + x['notas'] if x['notas'] else ''}\n" for x in P) + "\n"
    D = [d for d in deu if d['deudor_id'] == pid]
    if D: t += "## Deudas\n" + ''.join(f"- {d['fecha']}: con {d['acreedor']} — saldo {cop(d['saldo_cop'])} ({d['estado']}) → [[Deuda]]\n" for d in D) + "\n"
    W('personas', per_page(p), t)

# ---- Eventos
for e, A in ev.items():
    l = lotes.get(A[0]['lote_id']); j = sum(a['jornales'] or 0 for a in A); ca = sum(a['costo_cop'] or 0 for a in A)
    t = fm('objeto/Evento', ['evento', 'actividad'], {'codigo': e, 'labor': f"\"{A[0]['labor']}\""})
    t += f"# {e}\n\nObjeto [[Actividad-Evento]] · labor **{A[0]['labor']}**" + (f" · lote [[{lote_page(l)}]]" if l else '') + "\n\n"
    t += f"- Fechas: {A[0]['fecha']} → {A[-1]['fecha']}\n- Jornales: {num(j)}\n- Costo: {cop(ca)}\n\n| Fecha | Persona | Jornales | Valor jornal | Costo | Notas |\n|---|---|---|---|---|---|\n"
    for a in A:
        pn = f"[[{per_page(pers[a['persona_id']])}]]" if a['persona_id'] else '—'
        t += f"| {a['fecha']} | {pn} | {num(a['jornales'])} | {cop(a['valor_jornal'])} | {cop(a['costo_cop'])} | {(a['notas'] or '').replace('|','/')} |\n"
    W('eventos', safe(e), t)

# ---- Indicadores
kg_tot = sum(r['kg_cereza'] for r in rec)
costo_lab = sum(a['costo_cop'] or 0 for a in act); costo_com = sum(x['total_cop'] for x in com)
costo_rec = sum(x['total_cop'] for x in pag if x['concepto'] == 'kg')
costo_tot = costo_lab + costo_com + costo_rec
ps = sum(b['kg_pergamino_seco'] or 0 for b in ben)
real = (sum(b['kg_cereza'] or 0 for b in ben) / ps) if ps else None
perg = ps if ps else kg_tot / factor
I = fm('objeto/Indicador', ['indicador', 'costos'])
I += f"# Costo por kg cereza y pergamino seco\n\nObjeto [[Indicador]]. Calculado desde finca.db (todo el registro, 2026).\n\n| Componente | Valor |\n|---|---|\n| Labores (actividad) | {cop(costo_lab)} |\n| Compras de insumos | {cop(costo_com)} |\n| Pagos de recolección por kg | {cop(costo_rec)} |\n| **Costo total registrado** | **{cop(costo_tot)}** |\n| Café cereza recolectado | {num(kg_tot)} kg |\n| Pergamino seco {'real' if ps else 'estimado (factor supuesto ' + num(factor) + ')'} | {num(perg)} kg |\n| **Costo por kg cereza** | **{cop(costo_tot/kg_tot) if kg_tot else '—'}** |\n| **Costo por kg pergamino seco** | **{cop(costo_tot/perg) if perg else '—'}** |\n\n"
I += "> Advertencia: el costo incluye inversión de establecimiento (siembra, hoyada, colinos de [[Lote San Juan]] y [[Lote Muñeca]]) y fertilizante comprado para varios lotes; por eso no es comparable directamente con el costo de sostenimiento de referencia. Ver [[Costos de la finca vs referencia nacional]].\n\nRelacionado: [[Conversión cereza a pergamino]], [[Jornales por lote]], [[Costos de producción]].\n"
W('indicadores', 'Costo por kg cereza y pergamino seco', I)
I = fm('objeto/Indicador', ['indicador', 'beneficio'])
I += f"# Conversión cereza a pergamino\n\nObjeto [[Indicador]].\n\n- Factor en uso: **{num(factor)} kg cereza / kg pergamino seco** ({'supuesto' if par.get('factor_cereza_pergamino',{}).get('es_supuesto') else 'confirmado'}).\n- Factor real medido: {num(real) if real else 'sin beneficios pesados todavía (tabla beneficio vacía)'}.\n- Referencia Cenicafé (Avance Técnico 370): ≈ 4,50 para café seleccionado y 4,94 sin seleccionar → [[Fuente - Propiedades físicas y factores de conversión (AT 370)]].\n\nAcción recomendada: registrar un [[Beneficio]] pesando cereza que entra y pergamino seco (10–12 % humedad) que sale. Ver [[Beneficio y lavado]] y [[Secado del café]].\n"
W('indicadores', 'Conversión cereza a pergamino', I)
I = fm('objeto/Indicador', ['indicador', 'labores'])
I += "# Jornales por lote\n\nObjeto [[Indicador]].\n\n| Lote | Jornales | Costo labores | Labores principales |\n|---|---|---|---|\n"
for lid, l in sorted(lotes.items(), key=lambda kv: -sum(a['jornales'] or 0 for a in act if a['lote_id'] == kv[0])):
    A = [a for a in act if a['lote_id'] == lid]
    if not A: continue
    lab = defaultdict(float)
    for a in A: lab[a['labor']] += a['jornales'] or 0
    top = ', '.join(f"{k} ({num(v)})" for k, v in sorted(lab.items(), key=lambda kv: -kv[1])[:3])
    I += f"| [[{lote_page(l)}]] | {num(sum(a['jornales'] or 0 for a in A))} | {cop(sum(a['costo_cop'] or 0 for a in A))} | {top} |\n"
I += "\nSin hectáreas por lote no se puede calcular jornales/ha (ver [[pendientes]]). Comparar con [[Manejo integrado de arvenses]].\n"
W('indicadores', 'Jornales por lote', I)
I = fm('objeto/Indicador', ['indicador', 'deuda'])
I += "# Deudas vigentes\n\nObjeto [[Indicador]] sobre [[Deuda]].\n\n" + ''.join(f"- {d['fecha']} · acreedor {d['acreedor']} · deudor [[{per_page(pers[d['deudor_id']])}]] · lote [[{lote_page(lotes[d['lote_id']])}]] · monto {cop(d['monto_cop'])} · saldo **{cop(d['saldo_cop'])}** · {d['estado']}\n  - {d['concepto']}\n" for d in deu)
I += "\n## Ventas registradas\n" + ''.join(f"- {v['fecha']}: {v['producto']} {num(v['kg'])} kg × {cop(v['precio_kg_cop'])} = {cop(v['total_cop'])} — {v['notas']}\n" for v in ven)
W('indicadores', 'Deudas y ventas', I)

# ---- Snapshot CSV
snap = os.path.join(ROOT, 'raw', 'finca-datos', f'snapshot-{HOY}')
os.makedirs(snap, exist_ok=True)
for (tname,) in c.execute("select name from sqlite_master where type='table'"):
    cur = c.execute(f'select * from {tname}')
    with open(os.path.join(snap, tname + '.csv'), 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f); w.writerow([d[0] for d in cur.description]); w.writerows(cur.fetchall())
print(f"lotes={len(lotes)} personas={len(pers)} eventos={len(ev)} indicadores=4 kg={kg_tot} costo={costo_tot}")
