#!/usr/bin/env python3
"""Regenera indicadores_labores.csv desde finca.db. Uso: python3 indicadores.py [YYYY-MM-DD]"""
import sqlite3, csv, sys, datetime as dt
from collections import defaultdict
DB='finca.db'; OUT='indicadores_labores.csv'
hoy=dt.date.fromisoformat(sys.argv[1]) if len(sys.argv)>1 else dt.date.today()
ini=hoy-dt.timedelta(days=hoy.weekday()); fin=ini+dt.timedelta(days=6); mes=hoy.strftime('%Y-%m')
c=sqlite3.connect(DB)
rows=c.execute("""select a.fecha,a.labor,coalesce(l.nombre,'(sin lote)'),coalesce(l.numero,''),
 coalesce(a.jornales,0),coalesce(a.valor_jornal,0),coalesce(a.costo_cop,0),a.persona_id
 from actividad a left join lote l on l.id=a.lote_id""").fetchall()
def stats(rs):
    n=len(rs); j=sum(r[4] for r in rs); co=sum(r[6] for r in rs)
    meses=defaultdict(float)
    for r in rs: meses[r[0][:7]]+=r[4]
    return n,j,co,(j/n if n else 0),(sum(r[5] for r in rs)/n if n else 0),(co/n if n else 0),(sum(meses.values())/len(meses) if meses else 0)
g=defaultdict(list); gl=defaultdict(list)
for r in rows: g[(r[1],r[2],r[3])].append(r); gl[r[1]].append(r)
H=['labor','lote','lote_num','jornales_semana','costo_semana','jornales_mes','costo_mes',
 'hist_ocurrencias','hist_jornales_total','hist_costo_total','hist_prom_jornales_por_vez','hist_prom_valor_jornal',
 'hist_prom_costo_por_vez','hist_prom_jornales_por_mes_activo','labor_todos_lotes_prom_jornales_por_vez',
 'labor_todos_lotes_prom_costo_por_vez','ultima_fecha','alertas']
out=[]
for (lab,lot,num),rs in sorted(g.items()):
    sem=[r for r in rs if ini.isoformat()<=r[0]<=fin.isoformat()]
    mm=[r for r in rs if r[0].startswith(mes)]
    hist=[r for r in rs if r[0]<ini.isoformat()]
    hl=[r for r in gl[lab] if r[0]<ini.isoformat()]
    hs=stats(hist); ls=stats(hl); js=sum(r[4] for r in sem); cs=sum(r[6] for r in sem)
    al=[]
    for r in rs:
        if r[5] and abs(r[5]-50000)>=25000: al.append(f"valor_jornal {r[5]:.0f} el {r[0]}")
    if sem:
        ref=hs[3] or ls[3]
        if not ref: al.append('sin historico para comparar')
        elif js>1.5*ref: al.append(f'jornales semana {js} > 1.5x prom {ref:.2f}')
        if any(r[7] is None for r in sem): al.append('falta persona')
    out.append([lab,lot,num,js,cs,sum(r[4] for r in mm),sum(r[6] for r in mm),hs[0],hs[1],hs[2],
      round(hs[3],2),round(hs[4]),round(hs[5]),round(hs[6],2),round(ls[3],2),round(ls[5]),max(r[0] for r in rs),'; '.join(al)])
with open(OUT,'w',newline='') as f: w=csv.writer(f); w.writerow(H); w.writerows(out)
print(f'Semana {ini}..{fin}, mes {mes}: {len(out)} filas -> {OUT}')
