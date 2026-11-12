"""Datos semilla de catalog-geo-service (S4-08): donaciones y necesidades en Bogotá, Medellín y Cali.

Los id_donante e id_receptor son los usuarios de identity-service (identidad/semilla.py) y los estados
RESERVADA/ENTREGADA corresponden a las reservas de fulfillment-service (cumplimiento/semilla.py).
Referencia cruzada: docs/modelo/datos-semilla.md.
"""
from datetime import timedelta

from geoalchemy2 import WKTElement
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from .modelos import Donacion, NecesidadAlimentaria, UbicacionGeografica

CUND, ANT, VALLE = "Cundinamarca", "Antioquia", "Valle del Cauca"

# id, donante, alimento, categoría, cantidad, unidad, horas para vencer (None = no aplica), estado,
# dirección, ciudad, departamento, lat, lon, condiciones
DONACIONES = [
    (1, 2, "Pan artesanal", 3, 40, "unidades", 20, "DISPONIBLE", "Cra 13 # 57-20, Chapinero", "Bogotá", CUND,
     4.6486, -74.0628, "Recoger entre 6 y 8 p. m."),
    (2, 2, "Leche entera", 2, 60, "litros", 72, "DISPONIBLE", "Calle 39 # 21-10, Teusaquillo", "Bogotá", CUND,
     4.6370, -74.0830, "Traer nevera portátil"),
    (3, 2, "Arroz blanco", 4, 200, "kg", 24 * 60, "DISPONIBLE", "Av. 1 de Mayo # 72-30, Kennedy", "Bogotá", CUND,
     4.6280, -74.1510, "Bodega, puerta 3"),
    (4, 2, "Banano y manzana", 1, 80, "kg", 48, "DISPONIBLE", "Corabastos, bodega 12, Kennedy", "Bogotá", CUND,
     4.6266, -74.1583, "Lunes a sábado, 5 a 10 a. m."),
    (5, 2, "Almuerzos preparados", 6, 50, "porciones", 8, "DISPONIBLE", "Calle 120 # 7-15, Usaquén", "Bogotá",
     CUND, 4.6950, -74.0310, "Recoger antes de las 3 p. m."),
    (6, 2, "Atún enlatado", 4, 120, "latas", 24 * 180, "DISPONIBLE", "Av. Suba # 115-50, Suba", "Bogotá", CUND,
     4.7410, -74.0840, "Portería principal"),
    (7, 2, "Yogur natural", 2, 30, "unidades", 36, "DISPONIBLE", "Calle 17 # 99-40, Fontibón", "Bogotá", CUND,
     4.6730, -74.1460, "Mantener refrigerado"),
    (8, 2, "Papa y zanahoria", 1, 150, "kg", 120, "DISPONIBLE", "Calle 65 Sur # 80-20, Bosa", "Bogotá", CUND,
     4.6180, -74.1900, "Se necesita vehículo"),
    (9, 2, "Agua potable", 7, 300, "litros", None, "DISPONIBLE", "Calle 72 # 110-15, Engativá", "Bogotá", CUND,
     4.7060, -74.1130, "Bidones de 20 L"),
    (10, 2, "Pechuga de pollo", 5, 25, "kg", 30, "DISPONIBLE", "Av. Boyacá # 66-10 Sur, Ciudad Bolívar",
     "Bogotá", CUND, 4.5800, -74.1500, "Cadena de frío obligatoria"),
    (11, 4, "Bandejas paisas", 6, 40, "porciones", 10, "RESERVADA", "Cra 70 # 44-20, Laureles", "Medellín", ANT,
     6.2447, -75.5916, "Recoger en la cocina"),
    (12, 4, "Arepas de maíz", 3, 200, "unidades", 48, "ENTREGADA", "Calle 10 # 43-30, El Poblado", "Medellín", ANT,
     6.2088, -75.5676, "Empacadas por docenas"),
    (13, 4, "Fríjol cargamanto", 4, 80, "kg", 24 * 90, "DISPONIBLE", "Cra 50 # 52-10, Centro", "Medellín", ANT,
     6.2518, -75.5636, "Bultos de 10 kg"),
    (14, 4, "Leche deslactosada", 2, 50, "litros", 96, "CANCELADA", "Calle 30 # 76-15, Belén", "Medellín", ANT,
     6.2310, -75.6040, "Refrigerada"),
    (15, 6, "Mercados familiares", 4, 30, "paquetes", 24 * 60, "RESERVADA", "Av. 9N # 15-20, Granada", "Cali",
     VALLE, 3.4590, -76.5330, "Cada paquete alimenta a 4 personas"),
    (16, 6, "Plátano y yuca", 1, 120, "kg", 72, "DISPONIBLE", "Calle 13 # 8-40, Centro", "Cali", VALLE,
     3.4510, -76.5320, "Canastillas"),
    (17, 6, "Pollo despresado", 5, 40, "kg", 30, "DISPONIBLE", "Calle 5 # 38-10, San Fernando", "Cali", VALLE,
     3.4280, -76.5410, "Cadena de frío obligatoria"),
    (18, 6, "Mango y guayaba", 1, 60, "kg", -24, "VENCIDA", "Calle 16 # 105-30, Ciudad Jardín", "Cali", VALLE,
     3.3700, -76.5320, "Venció sin reservarse"),
]

# id, receptor, descripción, categoría, cantidad, unidad, urgencia, estado, dirección, ciudad, depto, lat, lon, días
NECESIDADES = [
    (1, 3, "Arroz para 120 almuerzos diarios", 4, 100, "kg", "CRITICA", "ABIERTA",
     "Calle 70 Sur # 18-25, Lucero, Ciudad Bolívar", "Bogotá", CUND, 4.5560, -74.1420, 5),
    (2, 3, "Leche para niños del comedor", 2, 40, "litros", "ALTA", "ABIERTA",
     "Calle 70 Sur # 18-25, Lucero, Ciudad Bolívar", "Bogotá", CUND, 4.5560, -74.1420, 3),
    (3, 3, "Verduras para albergue temporal", 1, 60, "kg", "MEDIA", "ABIERTA",
     "Calle 59 Sur # 87-10, Bosa", "Bogotá", CUND, 4.6100, -74.1850, 7),
    (4, 3, "Pan para refrigerios", 3, 30, "unidades", "BAJA", "ABIERTA",
     "Cra 78 # 38-20 Sur, Kennedy", "Bogotá", CUND, 4.6300, -74.1400, 10),
    (5, 5, "Almuerzos para 80 niños", 6, 80, "porciones", "ALTA", "ABIERTA",
     "Calle 92 # 35-10, Manrique", "Medellín", ANT, 6.2760, -75.5490, 4),
    (6, 5, "Granos para mercados comunitarios", 4, 150, "kg", "MEDIA", "ABIERTA",
     "Cra 52 # 82-20, Moravia", "Medellín", ANT, 6.2770, -75.5650, 15),
    (7, 7, "Proteína para el albergue", 5, 50, "kg", "CRITICA", "ABIERTA",
     "Calle 1 Oeste # 50-10, Siloé", "Cali", VALLE, 3.4250, -76.5600, 3),
    (8, 7, "Frutas para refrigerios", 1, 40, "kg", "BAJA", "ABIERTA",
     "Cra 28 # 72-15, Aguablanca", "Cali", VALLE, 3.4220, -76.4870, 10),
    (9, 7, "Pan para el desayuno", 3, 100, "unidades", "MEDIA", "CERRADA",
     "Calle 1 Oeste # 50-10, Siloé", "Cali", VALLE, 3.4250, -76.5600, 2),
]


def _ubicacion(db: Session, direccion, ciudad, departamento, lat, lon) -> int:
    u = UbicacionGeografica(direccion_referencia=direccion, ciudad=ciudad, departamento=departamento,
                            coordenada_geografica=WKTElement(f"POINT({lon} {lat})", srid=4326))
    db.add(u)
    db.flush()
    return u.id_ubicacion


def sembrar(db: Session) -> bool:
    if db.scalar(select(Donacion.id_donacion).limit(1)) is not None:
        return False
    ahora = db.scalar(func.now())
    for (id_d, donante, alimento, cat, cant, unidad, horas, estado, direccion, ciudad, depto, lat, lon,
         condiciones) in DONACIONES:
        publicada = ahora - timedelta(days=3) if horas is not None and horas < 0 else ahora - timedelta(hours=2)
        db.add(Donacion(
            id_donacion=id_d, id_donante=donante, id_categoria=cat,
            id_ubicacion=_ubicacion(db, direccion, ciudad, depto, lat, lon), nombre_alimento=alimento,
            descripcion=f"Donación semilla en {ciudad}", cantidad=cant, unidad_medida=unidad,
            fecha_publicacion=publicada,
            fecha_vencimiento=None if horas is None else ahora + timedelta(hours=horas),
            condiciones_recogida=condiciones, estado_donacion=estado,
        ))
    for (id_n, receptor, descripcion, cat, cant, unidad, urgencia, estado, direccion, ciudad, depto, lat, lon,
         dias) in NECESIDADES:
        db.add(NecesidadAlimentaria(
            id_necesidad=id_n, id_receptor=receptor, id_categoria=cat,
            id_ubicacion=_ubicacion(db, direccion, ciudad, depto, lat, lon), descripcion=descripcion,
            cantidad_requerida=cant, unidad_medida=unidad, nivel_urgencia=urgencia,
            fecha_limite=ahora + timedelta(days=dias), estado_necesidad=estado,
        ))
    db.flush()
    for tabla, columna in (("donacion", "id_donacion"), ("necesidad_alimentaria", "id_necesidad")):
        db.execute(text(f"SELECT setval(pg_get_serial_sequence('{tabla}', '{columna}'), "
                        f"(SELECT max({columna}) FROM {tabla}))"))
    return True
