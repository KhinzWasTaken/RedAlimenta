"""Reserva concurrente (D-02): exactamente una reserva activa por donación."""
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.catalogo.modelos import Donacion
from app.core.seguridad import Actor, emitir_token
from app.core.tiempo import ahora
from app.identidad import servicio as identidad
from app.reservas.modelos import Reserva

from .conftest import leer

SIMULTANEAS = 20


def test_indice_unico_parcial_impide_dos_reservas_activas(db):
    momento = ahora()
    plazo = momento + timedelta(hours=2)
    db.add(Reserva(id_donacion=1, id_receptor=2, fecha_reserva=momento, fecha_expiracion=plazo,
                   estado_reserva="EXPIRADA"))
    db.add(Reserva(id_donacion=1, id_receptor=2, fecha_reserva=momento, fecha_expiracion=plazo,
                   estado_reserva="PENDIENTE"))
    db.commit()  # una inactiva y una activa conviven
    db.add(Reserva(id_donacion=1, id_receptor=3, fecha_reserva=momento, fecha_expiracion=plazo,
                   estado_reserva="CONFIRMADA"))
    with pytest.raises(IntegrityError):
        db.commit()


def test_20_receptores_reservando_a_la_vez_solo_uno_gana(cliente, db):
    cabeceras = []
    for i in range(SIMULTANEAS):
        u = identidad.crear_usuario(db, f"Receptor {i}", f"r{i}@prueba.co", "x", "RECEPTOR",
                                    verificacion="APROBADA")
        cabeceras.append({"Authorization": "Bearer " + emitir_token(
            Actor(u.id_usuario, "RECEPTOR", "APROBADA", u.nombre))})
    db.commit()

    barrera = threading.Barrier(SIMULTANEAS)

    def reservar(cabecera):
        barrera.wait()
        return cliente.post("/api/reservas", json={"id_donacion": 2}, headers=cabecera).status_code

    with ThreadPoolExecutor(SIMULTANEAS) as grupo:
        codigos = list(grupo.map(reservar, cabeceras))

    assert codigos.count(201) == 1
    assert codigos.count(409) == SIMULTANEAS - 1
    activas = db.scalars(select(Reserva).where(
        Reserva.id_donacion == 2, Reserva.estado_reserva.in_(("PENDIENTE", "CONFIRMADA")))).all()
    assert len(activas) == 1
    assert leer(db, Donacion, 2, "estado_donacion") == "RESERVADA"


def test_si_catalogo_rechaza_la_reserva_queda_cancelada(cliente, tokens, db):
    pasado = ahora() - timedelta(hours=1)
    db.execute(update(Donacion).where(Donacion.id_donacion == 3).values(
        fecha_publicacion=pasado - timedelta(days=1), fecha_vencimiento=pasado))
    db.commit()

    r = cliente.post("/api/reservas", json={"id_donacion": 3}, headers=tokens["receptor"])

    assert r.status_code == 409
    reservas = db.scalars(select(Reserva).where(Reserva.id_donacion == 3)).all()
    assert [x.estado_reserva for x in reservas] == ["CANCELADA"]
    assert leer(db, Donacion, 3, "estado_donacion") == "DISPONIBLE"
