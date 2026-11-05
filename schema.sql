PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS persona(id INTEGER PRIMARY KEY, nombre TEXT UNIQUE NOT NULL, rol TEXT DEFAULT 'recolector', telefono TEXT, activo INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS lote(id INTEGER PRIMARY KEY, nombre TEXT UNIQUE NOT NULL, hectareas REAL, variedad TEXT, arboles INTEGER, notas TEXT);
CREATE TABLE IF NOT EXISTS parametro(clave TEXT PRIMARY KEY, valor REAL, es_supuesto INTEGER DEFAULT 1, notas TEXT);
CREATE TABLE IF NOT EXISTS recoleccion(id INTEGER PRIMARY KEY, fecha TEXT NOT NULL, persona_id INTEGER NOT NULL REFERENCES persona(id), lote_id INTEGER REFERENCES lote(id), kg_cereza REAL NOT NULL CHECK(kg_cereza>0), fuente TEXT, notas TEXT);
CREATE TABLE IF NOT EXISTS beneficio(id INTEGER PRIMARY KEY, fecha_inicio TEXT, fecha_fin TEXT, kg_cereza REAL, kg_pergamino_seco REAL, factor_supuesto REAL, notas TEXT);
CREATE TABLE IF NOT EXISTS beneficio_recoleccion(beneficio_id INTEGER REFERENCES beneficio(id), recoleccion_id INTEGER UNIQUE REFERENCES recoleccion(id), PRIMARY KEY(beneficio_id,recoleccion_id));
CREATE TABLE IF NOT EXISTS actividad(id INTEGER PRIMARY KEY, fecha TEXT NOT NULL, labor TEXT NOT NULL, persona_id INTEGER REFERENCES persona(id), lote_id INTEGER REFERENCES lote(id), jornales REAL, costo_cop REAL DEFAULT 0, notas TEXT);
CREATE TABLE IF NOT EXISTS compra(id INTEGER PRIMARY KEY, fecha TEXT NOT NULL, insumo TEXT NOT NULL, proveedor TEXT, cantidad REAL, unidad TEXT, total_cop REAL NOT NULL, lote_id INTEGER REFERENCES lote(id), actividad_id INTEGER REFERENCES actividad(id), notas TEXT);
CREATE TABLE IF NOT EXISTS pago(id INTEGER PRIMARY KEY, fecha TEXT NOT NULL, persona_id INTEGER NOT NULL REFERENCES persona(id), concepto TEXT CHECK(concepto IN('kg','jornal','otro')), cantidad REAL, tarifa_cop REAL, total_cop REAL NOT NULL, recoleccion_id INTEGER REFERENCES recoleccion(id), actividad_id INTEGER REFERENCES actividad(id), notas TEXT);
CREATE TABLE IF NOT EXISTS venta(id INTEGER PRIMARY KEY, fecha TEXT NOT NULL, comprador TEXT, producto TEXT DEFAULT 'pergamino seco', kg REAL NOT NULL, precio_kg_cop REAL NOT NULL, total_cop REAL GENERATED ALWAYS AS (kg*precio_kg_cop) STORED, factor_rendimiento REAL, notas TEXT);
CREATE TABLE IF NOT EXISTS venta_beneficio(venta_id INTEGER REFERENCES venta(id), beneficio_id INTEGER REFERENCES beneficio(id), kg REAL, PRIMARY KEY(venta_id,beneficio_id));

INSERT OR IGNORE INTO parametro VALUES('factor_cereza_pergamino',5.0,1,'SUPUESTO: ~5 kg cereza = 1 kg pergamino seco. Ajustar con datos reales.');
INSERT OR IGNORE INTO parametro VALUES('tarifa_kg_recoleccion',NULL,1,'Pendiente: COP pagado por kg cereza');
INSERT OR IGNORE INTO lote(nombre,notas) VALUES('SIN_ASIGNAR','Lote desconocido; reasignar');

CREATE VIEW IF NOT EXISTS v_rend_recolector AS SELECT p.nombre, COUNT(DISTINCT r.fecha) dias, SUM(r.kg_cereza) kg_cereza, ROUND(SUM(r.kg_cereza)*1.0/COUNT(DISTINCT r.fecha),1) kg_dia FROM recoleccion r JOIN persona p ON p.id=r.persona_id GROUP BY p.id;
CREATE VIEW IF NOT EXISTS v_rend_lote AS SELECT l.nombre lote, l.hectareas, SUM(r.kg_cereza) kg_cereza, ROUND(SUM(r.kg_cereza)/(SELECT valor FROM parametro WHERE clave='factor_cereza_pergamino'),1) kg_pergamino_estimado, ROUND(SUM(r.kg_cereza)/NULLIF(l.hectareas,0),1) kg_cereza_ha FROM lote l LEFT JOIN recoleccion r ON r.lote_id=l.id GROUP BY l.id;
CREATE VIEW IF NOT EXISTS v_conversion AS SELECT b.id beneficio, b.kg_cereza, b.kg_pergamino_seco, ROUND(b.kg_cereza/NULLIF(b.kg_pergamino_seco,0),2) factor_real, (SELECT valor FROM parametro WHERE clave='factor_cereza_pergamino') factor_supuesto FROM beneficio b;
CREATE VIEW IF NOT EXISTS v_costos AS SELECT (SELECT IFNULL(SUM(costo_cop),0) FROM actividad) actividades, (SELECT IFNULL(SUM(total_cop),0) FROM compra) compras, (SELECT IFNULL(SUM(total_cop),0) FROM pago) pagos, (SELECT IFNULL(SUM(kg_cereza),0) FROM recoleccion) kg_cereza, (SELECT IFNULL(SUM(kg_pergamino_seco),0) FROM beneficio) kg_pergamino_real;
CREATE VIEW IF NOT EXISTS v_costo_kg AS SELECT actividades+compras+pagos costo_total, kg_cereza, ROUND((actividades+compras+pagos)/NULLIF(kg_cereza,0),0) costo_kg_cereza, ROUND((actividades+compras+pagos)/NULLIF(CASE WHEN kg_pergamino_real>0 THEN kg_pergamino_real ELSE kg_cereza/(SELECT valor FROM parametro WHERE clave='factor_cereza_pergamino') END,0),0) costo_kg_pergamino FROM v_costos;
CREATE VIEW IF NOT EXISTS v_margen_venta AS SELECT v.id, v.fecha, v.comprador, v.kg, v.precio_kg_cop, v.total_cop, c.costo_kg_pergamino, ROUND(v.total_cop - v.kg*c.costo_kg_pergamino,0) margen_cop, ROUND(100.0*(v.precio_kg_cop-c.costo_kg_pergamino)/v.precio_kg_cop,1) margen_pct FROM venta v, v_costo_kg c;
CREATE VIEW IF NOT EXISTS v_trazabilidad AS SELECT v.id venta_id, v.fecha fecha_venta, vb.beneficio_id, r.fecha fecha_recoleccion, p.nombre recolector, l.nombre lote, r.kg_cereza FROM venta v JOIN venta_beneficio vb ON vb.venta_id=v.id JOIN beneficio_recoleccion br ON br.beneficio_id=vb.beneficio_id JOIN recoleccion r ON r.id=br.recoleccion_id JOIN persona p ON p.id=r.persona_id LEFT JOIN lote l ON l.id=r.lote_id;

-- v2: siembras y floraciones (ligadas a Lote)
CREATE TABLE IF NOT EXISTS siembra(id INTEGER PRIMARY KEY, lote_id INTEGER NOT NULL REFERENCES lote(id), fecha TEXT NOT NULL, tipo TEXT, variedad TEXT, dist_planta_m REAL, dist_surco_m REAL, plantas INTEGER, fecha_renovacion TEXT, ref TEXT UNIQUE, notas TEXT);
CREATE TABLE IF NOT EXISTS floracion(id INTEGER PRIMARY KEY, lote_id INTEGER NOT NULL REFERENCES lote(id), fecha TEXT NOT NULL, calificacion TEXT, control_roya TEXT, control_broca TEXT, cosecha_estimada TEXT, ref TEXT UNIQUE, notas TEXT);
CREATE VIEW IF NOT EXISTS v_agenda AS
  SELECT f.control_roya fecha, 'Control roya' evento, l.numero, l.nombre lote, f.fecha floracion, f.calificacion FROM floracion f JOIN lote l ON l.id=f.lote_id
  UNION ALL SELECT f.control_broca, 'Control broca', l.numero, l.nombre, f.fecha, f.calificacion FROM floracion f JOIN lote l ON l.id=f.lote_id
  UNION ALL SELECT f.cosecha_estimada, 'Cosecha estimada', l.numero, l.nombre, f.fecha, f.calificacion FROM floracion f JOIN lote l ON l.id=f.lote_id
  UNION ALL SELECT s.fecha_renovacion, 'Renovación', l.numero, l.nombre, s.fecha, s.variedad FROM siembra s JOIN lote l ON l.id=s.lote_id;
CREATE VIEW IF NOT EXISTS v_lote_ficha AS SELECT l.numero, l.numero_alterno, l.nombre, l.variedad, l.arboles,
  (SELECT MAX(fecha) FROM siembra WHERE lote_id=l.id) ultima_siembra,
  (SELECT COUNT(*) FROM floracion WHERE lote_id=l.id) floraciones,
  (SELECT IFNULL(SUM(kg_cereza),0) FROM recoleccion WHERE lote_id=l.id) kg_cereza,
  (SELECT IFNULL(SUM(costo_cop),0) FROM actividad WHERE lote_id=l.id) costo_labores,
  (SELECT IFNULL(SUM(total_cop),0) FROM compra WHERE lote_id=l.id) costo_compras
  FROM lote l ORDER BY l.numero;
