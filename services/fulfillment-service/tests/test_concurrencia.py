"""S4-11 / D-02: con 20 conexiones simultáneas reservando la misma donación, exactamente una queda activa."""
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from cumplimiento import repositorio as repo
from cumplimiento.errores import Conflicto
from cumplimiento.modelos import Reserva

CONEXIONES = 20


def test_indice_unico_parcial_en_la_base(db):
    db.execute(text("INSERT INTO reserva (id_donacion, id_receptor, fecha_expiracion, estado_reserva) "
                    "VALUES (1, 5, now() + interval '2 hours', 'EXPIRADA')"))
    db.execute(text("INSERT INTO reserva (id_donacion, id_receptor, fecha_expiracion) "
                    "VALUES (1, 5, now() + interval '2 hours')"))  # una inactiva y una activa conviven
    with pytest.raises(IntegrityError, match="ux_reserva_activa"):
        with db.begin_nested():
            db.execute(text("INSERT INTO reserva (id_donacion, id_receptor, fecha_expiracion, estado_reserva) "
                            "VALUES (1, 7, now() + interval '2 hours', 'CONFIRMADA')"))


def test_20_conexiones_simultaneas_solo_una_reserva_activa(url_base, Sesion):
    motor = create_engine(url_base, pool_size=CONEXIONES, max_overflow=0)
    Sesiones = sessionmaker(bind=motor, expire_on_commit=False)
    barrera = threading.Barrier(CONEXIONES)

    def intentar(id_receptor: int) -> str:
        with Sesiones() as db:
            db.execute(text("SELECT 1"))  # la conexión ya está abierta antes de la carrera
            barrera.wait()
            try:
                repo.reservar(db, id_donacion=42, id_receptor=id_receptor)
                db.commit()
                return "ganó"
            except Conflicto:
                db.rollback()
                return "409"

    try:
        with ThreadPoolExecutor(CONEXIONES) as grupo:
            resultados = list(grupo.map(intentar, range(100, 100 + CONEXIONES)))
    finally:
        motor.dispose()

    assert resultados.count("ganó") == 1
    assert resultados.count("409") == CONEXIONES - 1
    with Sesion() as db:
        activas = db.scalars(select(Reserva).where(Reserva.id_donacion == 42)).all()
        assert len(activas) == 1 and activas[0].estado_reserva == "PENDIENTE"
