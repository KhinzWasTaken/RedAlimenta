"""Datos semilla en Bogotá: 3 usuarios, categorías, donaciones y necesidades.

Uso:  python -m app.seed            (siembra solo si la base está vacía)
      python -m app.seed --reiniciar (borra todo y vuelve a sembrar)

Las contraseñas de demostración son públicas a propósito y no protegen datos reales.
"""
import sys
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalogo.modelos import CategoriaAlimento, Donacion, NecesidadAlimentaria, UbicacionGeografica
from app.core.db import SesionLocal, borrar_esquema, crear_esquema
from app.core.tiempo import ahora
from app.identidad import servicio as identidad
from app.identidad.modelos import Rol, Usuario

CONTRASENA_DEMO = "demo123"
USUARIOS = [
    # nombre, correo, rol, estado de verificación inicial
    ("Supermercado La Cosecha", "donante@redalimenta.co", "DONANTE", "APROBADA"),
    ("Comedor Comunitario Esperanza", "receptor@redalimenta.co", "RECEPTOR", "PENDIENTE"),
    ("Administración RedAlimenta", "admin@redalimenta.co", "ADMINISTRADOR", "APROBADA"),
]
CATEGORIAS = [
    ("Frutas y verduras", "Productos frescos"),
    ("Lácteos y huevos", "Leche, yogur, queso, huevos"),
    ("Panadería", "Pan y productos horneados"),
    ("Granos y enlatados", "Arroz, fríjol, lentejas, enlatados"),
    ("Carnes y proteínas", "Carne, pollo, pescado"),
    ("Comidas preparadas", "Almuerzos y refrigerios listos"),
    ("Bebidas", "Agua potable, jugos"),
]
# alimento, categoría, cantidad, unidad, horas para vencer, dirección, barrio/localidad, lat, lon, condiciones
DONACIONES = [
    ("Pan artesanal", "Panadería", 40, "unidades", 20, "Cra 13 # 57-20", "Chapinero", 4.6486, -74.0628,
     "Recoger entre 6 y 8 p. m."),
    ("Leche entera", "Lácteos y huevos", 60, "litros", 72, "Calle 39 # 21-10", "Teusaquillo", 4.6370, -74.0830,
     "Traer nevera portátil"),
    ("Arroz blanco", "Granos y enlatados", 200, "kg", 24 * 60, "Av. 1 de Mayo # 72-30", "Kennedy",
     4.6280, -74.1510, "Bodega, puerta 3"),
    ("Banano y manzana", "Frutas y verduras", 80, "kg", 48, "Corabastos, bodega 12", "Kennedy",
     4.6266, -74.1583, "Lunes a sábado, 5 a 10 a. m."),
    ("Almuerzos preparados", "Comidas preparadas", 50, "porciones", 8, "Calle 120 # 7-15", "Usaquén",
     4.6950, -74.0310, "Recoger antes de las 3 p. m."),
    ("Atún enlatado", "Granos y enlatados", 120, "latas", 24 * 180, "Av. Suba # 115-50", "Suba",
     4.7410, -74.0840, "Portería principal"),
    ("Yogur natural", "Lácteos y huevos", 30, "unidades", 36, "Calle 17 # 99-40", "Fontibón",
     4.6730, -74.1460, "Mantener refrigerado"),
    ("Papa y zanahoria", "Frutas y verduras", 150, "kg", 120, "Calle 65 Sur # 80-20", "Bosa",
     4.6180, -74.1900, "Se necesita vehículo"),
    ("Agua potable", "Bebidas", 300, "litros", 24 * 365, "Calle 72 # 110-15", "Engativá",
     4.7060, -74.1130, "Bidones de 20 L"),
    ("Pechuga de pollo", "Carnes y proteínas", 25, "kg", 30, "Av. Boyacá # 66-10 Sur", "Ciudad Bolívar",
     4.5800, -74.1500, "Cadena de frío obligatoria"),
]
# descripción, categoría, cantidad, unidad, urgencia, dirección, barrio, lat, lon, días límite
NECESIDADES = [
    ("Arroz para 120 almuerzos diarios", "Granos y enlatados", 100, "kg", "CRITICA",
     "Calle 70 Sur # 18-25", "Ciudad Bolívar (Lucero)", 4.5560, -74.1420, 5),
    ("Leche para niños del comedor", "Lácteos y huevos", 40, "litros", "ALTA",
     "Calle 70 Sur # 18-25", "Ciudad Bolívar (Lucero)", 4.5560, -74.1420, 3),
    ("Verduras para albergue temporal", "Frutas y verduras", 60, "kg", "MEDIA",
     "Calle 59 Sur # 87-10", "Bosa (albergue)", 4.6100, -74.1850, 7),
    ("Pan para refrigerios", "Panadería", 30, "unidades", "BAJA",
     "Cra 78 # 38-20 Sur", "Kennedy", 4.6300, -74.1400, 10),
]


def _ubicacion(db: Session, direccion: str, barrio: str, lat: float, lon: float) -> int:
    u = UbicacionGeografica(direccion_referencia=f"{direccion}, {barrio}", ciudad="Bogotá",
                            departamento="Cundinamarca", latitud=lat, longitud=lon)
    db.add(u)
    db.flush()
    return u.id_ubicacion


def sembrar(db: Session) -> None:
    if db.scalars(select(Rol)).first() is not None:
        return
    for nombre, descripcion in (("DONANTE", "Publica donaciones"), ("RECEPTOR", "Publica necesidades y reserva"),
                                ("ADMINISTRADOR", "Verifica cuentas y supervisa")):
        db.add(Rol(nombre_rol=nombre, descripcion=descripcion))
    for nombre, descripcion in CATEGORIAS:
        db.add(CategoriaAlimento(nombre_categoria=nombre, descripcion=descripcion))
    db.flush()

    ids = {}
    for nombre, correo, rol, verificacion in USUARIOS:
        ids[rol] = identidad.crear_usuario(db, nombre, correo, CONTRASENA_DEMO, rol,
                                           telefono="3000000000", verificacion=verificacion).id_usuario

    categorias = {c.nombre_categoria: c.id_categoria for c in db.scalars(select(CategoriaAlimento))}
    momento = ahora()
    for alimento, cat, cantidad, unidad, horas, direccion, barrio, lat, lon, condiciones in DONACIONES:
        db.add(Donacion(
            id_donante=ids["DONANTE"], id_categoria=categorias[cat],
            id_ubicacion=_ubicacion(db, direccion, barrio, lat, lon), nombre_alimento=alimento,
            descripcion=f"Donación semilla en {barrio}", cantidad=cantidad, unidad_medida=unidad,
            fecha_publicacion=momento, fecha_vencimiento=momento + timedelta(hours=horas),
            condiciones_recogida=condiciones, estado_donacion="DISPONIBLE",
        ))
    for descripcion, cat, cantidad, unidad, urgencia, direccion, barrio, lat, lon, dias in NECESIDADES:
        db.add(NecesidadAlimentaria(
            id_receptor=ids["RECEPTOR"], id_categoria=categorias[cat],
            id_ubicacion=_ubicacion(db, direccion, barrio, lat, lon), descripcion=descripcion,
            cantidad_requerida=cantidad, unidad_medida=unidad, nivel_urgencia=urgencia,
            fecha_limite=momento + timedelta(days=dias), estado_necesidad="ABIERTA",
        ))
    db.commit()


def main(argv: list[str]) -> None:
    if "--reiniciar" in argv:
        borrar_esquema()
    crear_esquema()
    with SesionLocal() as db:
        ya_habia = db.scalars(select(Usuario)).first() is not None
        sembrar(db)
    print("Base ya sembrada; nada que hacer." if ya_habia else "Datos semilla creados.")
    for nombre, correo, rol, verificacion in USUARIOS:
        print(f"  {rol:<14} {correo:<26} contraseña: {CONTRASENA_DEMO}  ({verificacion})")


if __name__ == "__main__":
    main(sys.argv[1:])
