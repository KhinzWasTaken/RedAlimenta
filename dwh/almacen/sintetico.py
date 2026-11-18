"""Generador de datos sintéticos para el almacén (S7-03).

Produce donaciones con sus reservas y entregas, coherentes entre sí y con las reglas de negocio:
- fechas en orden (publicación < reserva < entrega ≤ vencimiento) y nunca en el futuro;
- una sola reserva activa por donación (D-02) y como máximo una segunda reserva tras expirar o cancelarse;
- ENTREGADA solo con reserva COMPLETADA y entrega COMPLETADA; estados según docs/modelo/estados.md;
- distribución en el tiempo (2025 → hoy, con más actividad entre semana y un pico tras el terremoto del
  10 de agosto de 2026) y en el territorio (ciudades ponderadas por población).

Todo queda con origen_dato = 'SINTETICO' para no confundirlo con la operación real.
La semilla fija hace que dos ejecuciones generen exactamente los mismos datos.
"""
import math
import random
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

ORIGEN = "SINTETICO"
TERREMOTO = date(2026, 8, 10)

# departamento, ciudad, latitud, longitud, peso (≈ población urbana en cientos de miles)
CIUDADES = [
    ("Cundinamarca", "Bogotá", 4.65, -74.10, 78), ("Antioquia", "Medellín", 6.25, -75.57, 26),
    ("Valle del Cauca", "Cali", 3.44, -76.52, 22), ("Atlántico", "Barranquilla", 10.97, -74.80, 13),
    ("Bolívar", "Cartagena", 10.39, -75.51, 10), ("Norte de Santander", "Cúcuta", 7.89, -72.50, 8),
    ("Santander", "Bucaramanga", 7.12, -73.12, 6), ("Tolima", "Ibagué", 4.44, -75.23, 5),
    ("Risaralda", "Pereira", 4.81, -75.69, 5), ("Meta", "Villavicencio", 4.14, -73.63, 5),
    ("Magdalena", "Santa Marta", 11.24, -74.20, 5), ("Huila", "Neiva", 2.93, -75.28, 3.5),
    ("Caldas", "Manizales", 5.07, -75.52, 4), ("Nariño", "Pasto", 1.21, -77.28, 3.9),
    ("Córdoba", "Montería", 8.75, -75.88, 4.9), ("Cesar", "Valledupar", 10.46, -73.25, 5.3),
    ("Quindío", "Armenia", 4.53, -75.68, 3), ("Cauca", "Popayán", 2.44, -76.61, 3.2),
    ("Boyacá", "Tunja", 5.54, -73.36, 2), ("Sucre", "Sincelejo", 9.30, -75.40, 2.8),
]
# id, nombre, peso, unidades posibles, (cantidad mínima, máxima), vida útil en horas (mín, máx) o None
CATEGORIAS = [
    (1, "Frutas y verduras", 20, ("kg",), (10, 300), (48, 240)),
    (2, "Lácteos y huevos", 14, ("litros", "unidades"), (10, 150), (36, 168)),
    (3, "Panadería", 12, ("unidades",), (20, 400), (12, 72)),
    (4, "Granos y enlatados", 22, ("kg", "latas", "paquetes"), (10, 500), (720, 8760)),
    (5, "Carnes y proteínas", 9, ("kg",), (5, 80), (24, 96)),
    (6, "Comidas preparadas", 13, ("porciones",), (20, 300), (4, 24)),
    (7, "Bebidas", 10, ("litros",), (20, 600), None),
]


@dataclass
class Lote:
    usuarios: list = field(default_factory=list)
    categorias: list = field(default_factory=list)
    donaciones: list = field(default_factory=list)
    reservas: list = field(default_factory=list)
    entregas: list = field(default_factory=list)


def _peso_dia(d: date) -> float:
    peso = 1.0 if d.isoweekday() <= 5 else 0.55
    if d >= TERREMOTO:  # pico de solidaridad tras el terremoto, que decae en ~6 semanas
        peso *= 1 + 3.5 * math.exp(-(d - TERREMOTO).days / 42)
    return peso * (1 + 0.15 * math.sin(d.timetuple().tm_yday / 365 * 2 * math.pi))  # estacionalidad leve


def generar(n_donaciones: int = 50_000, semilla: int = 2026, ahora: datetime | None = None,
            desde: date = date(2025, 1, 1)) -> Lote:
    azar = random.Random(semilla)
    ahora = ahora or datetime.now(UTC)
    lote = Lote(categorias=[(c[0], c[1]) for c in CATEGORIAS])

    # Participantes por ciudad (ids propios del origen sintético)
    n_donantes, n_receptores = max(20, n_donaciones // 20), max(15, n_donaciones // 28)
    pesos_ciudad = [c[4] for c in CIUDADES]
    donantes = {i: azar.choices(range(len(CIUDADES)), pesos_ciudad)[0] for i in range(1, n_donantes + 1)}
    receptores_por_ciudad: dict[int, list[int]] = {i: [] for i in range(len(CIUDADES))}
    for i in range(n_donantes + 1, n_donantes + n_receptores + 1):
        receptores_por_ciudad[azar.choices(range(len(CIUDADES)), pesos_ciudad)[0]].append(i)
    for ciudad, lista in receptores_por_ciudad.items():  # toda ciudad tiene al menos un receptor
        if not lista:
            nuevo = n_donantes + n_receptores + ciudad + 1
            lista.append(nuevo)
    lote.usuarios = [(ORIGEN, i, "DONANTE", "APROBADA") for i in donantes] + [
        (ORIGEN, r, "RECEPTOR", "APROBADA") for lista in receptores_por_ciudad.values() for r in lista]

    dias = [desde + timedelta(days=i) for i in range((ahora.date() - desde).days)]
    pesos_dia = [_peso_dia(d) for d in dias]
    pesos_categoria = [c[2] for c in CATEGORIAS]
    id_reserva = id_entrega = 0

    for id_donacion in range(1, n_donaciones + 1):
        id_donante = azar.randrange(1, n_donantes + 1)
        ciudad_i = donantes[id_donante]
        depto, ciudad, lat, lon, _ = CIUDADES[ciudad_i]
        cat = azar.choices(CATEGORIAS, pesos_categoria)[0]
        dia = azar.choices(dias, pesos_dia)[0]
        publicada = datetime(dia.year, dia.month, dia.day, tzinfo=UTC) + timedelta(
            hours=azar.uniform(11, 27))  # 6 a. m. a 10 p. m. de Colombia
        if publicada >= ahora:
            publicada = ahora - timedelta(hours=azar.uniform(1, 20))
        vida = None if cat[5] is None else azar.uniform(*cat[5])
        vence = None if vida is None else publicada + timedelta(hours=vida)
        unidad = azar.choice(cat[3])
        cantidad = round(math.exp(azar.uniform(math.log(cat[4][0]), math.log(cat[4][1]))), 1)
        horizonte = vida if vida is not None else 24 * 30

        estado_donacion = None
        intentos = 1 if azar.random() < 0.85 else 2
        for intento in range(intentos):
            if azar.random() > (0.80 if intento == 0 else 0.55):
                break  # nadie (más) la reservó
            previa = lote.reservas[-1][4] if intento else publicada
            reservada = previa + timedelta(hours=azar.uniform(0.02, 0.35) * horizonte + (8 if intento else 0))
            if reservada >= ahora or (vence and reservada >= vence - timedelta(minutes=30)):
                break
            id_reserva += 1
            expira = reservada + timedelta(hours=2)
            if expira > ahora:  # reserva reciente: sigue PENDIENTE
                lote.reservas.append((ORIGEN, id_reserva, id_donacion, None, reservada, expira, "PENDIENTE"))
                estado_donacion = "RESERVADA"
                break
            azar_reserva = azar.random()
            if azar_reserva < 0.12:
                lote.reservas.append((ORIGEN, id_reserva, id_donacion, None, reservada, expira, "EXPIRADA"))
                continue
            if azar_reserva < 0.18:
                lote.reservas.append((ORIGEN, id_reserva, id_donacion, None, reservada, expira, "CANCELADA"))
                continue
            # CONFIRMADA → entrega
            programada = reservada + timedelta(hours=azar.uniform(1, 6))
            if vence and programada >= vence:  # se venció antes de poder entregarla: reserva cancelada
                id_entrega += 1
                lote.reservas.append((ORIGEN, id_reserva, id_donacion, None, reservada, expira, "CANCELADA"))
                lote.entregas.append((ORIGEN, id_entrega, id_reserva, programada, None, "CANCELADA", False))
                break
            if programada >= ahora:  # entrega todavía por hacer
                lote.reservas.append((ORIGEN, id_reserva, id_donacion, None, reservada, expira, "CONFIRMADA"))
                id_entrega += 1
                lote.entregas.append((ORIGEN, id_entrega, id_reserva, programada, None, "PROGRAMADA", False))
                estado_donacion = "RESERVADA"
                break
            entregada = programada + timedelta(minutes=azar.uniform(-30, 90))
            entregada = max(entregada, reservada + timedelta(minutes=20))
            if vence:
                entregada = min(entregada, vence - timedelta(minutes=5))
            id_entrega += 1
            final = azar.random()
            if final < 0.04:
                lote.reservas.append((ORIGEN, id_reserva, id_donacion, None, reservada, expira, "CONFIRMADA"))
                lote.entregas.append((ORIGEN, id_entrega, id_reserva, programada, None, "CON_INCIDENCIA", True))
                estado_donacion = "RESERVADA"
                break
            if final < 0.09:
                lote.reservas.append((ORIGEN, id_reserva, id_donacion, None, reservada, expira, "CANCELADA"))
                lote.entregas.append((ORIGEN, id_entrega, id_reserva, programada, None, "CANCELADA", False))
                continue
            lote.reservas.append((ORIGEN, id_reserva, id_donacion, None, reservada, expira, "COMPLETADA"))
            lote.entregas.append((ORIGEN, id_entrega, id_reserva, programada, entregada, "COMPLETADA", False))
            estado_donacion = "ENTREGADA"
            break

        if estado_donacion is None:  # sin reserva activa ni entrega
            if vence and vence <= ahora:
                estado_donacion = "VENCIDA" if azar.random() < 0.8 else "CANCELADA"
            else:
                estado_donacion = "DISPONIBLE" if azar.random() < 0.9 else "CANCELADA"
        lote.donaciones.append((ORIGEN, id_donacion, id_donante, cat[0], cantidad, unidad, publicada, vence,
                                estado_donacion, ciudad, depto, lat + azar.gauss(0, 0.03), lon + azar.gauss(0, 0.03)))

    # Receptor de cada reserva: alguien de la ciudad de la donación
    ciudad_de = {d[1]: next(i for i, c in enumerate(CIUDADES) if c[1] == d[9]) for d in lote.donaciones}
    lote.reservas = [(o, i, d, azar.choice(receptores_por_ciudad[ciudad_de[d]]), fr, fe, e)
                     for (o, i, d, _, fr, fe, e) in lote.reservas]
    return lote
