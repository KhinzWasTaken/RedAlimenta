"""S4-05 y S4-11: reservar, confirmar, cancelar, expirar en lote y confirmación bilateral de la entrega."""
from datetime import timedelta

import pytest
from sqlalchemy import func, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from cumplimiento import repositorio as repo
from cumplimiento.errores import Conflicto, ErrorDominio, TransicionInvalida
from cumplimiento.semilla import sembrar

DONANTE, RECEPTOR = 4, 5


def test_reservar_con_plazo_d09(db):
    r = repo.reservar(db, id_donacion=10, id_receptor=RECEPTOR)
    db.commit()
    assert r.estado_reserva == "PENDIENTE"
    assert r.fecha_expiracion - r.fecha_reserva == timedelta(hours=2)
    assert repo.reserva_activa(db, 10).id_reserva == r.id_reserva
    with pytest.raises(Conflicto):
        repo.reservar(db, id_donacion=10, id_receptor=7)


def test_confirmar_programa_la_entrega(db):
    r = repo.reservar(db, 10, RECEPTOR)
    e = repo.confirmar_reserva(db, r.id_reserva)
    db.commit()
    assert repo.obtener_reserva(db, r.id_reserva).estado_reserva == "CONFIRMADA"
    assert e.estado_entrega == "PROGRAMADA" and repo.entrega_de_reserva(db, r.id_reserva).id_entrega == e.id_entrega
    with pytest.raises(TransicionInvalida):
        repo.confirmar_reserva(db, r.id_reserva)
    with pytest.raises(IntegrityError, match="uq_entrega_id_reserva"):  # una entrega por reserva
        with db.begin_nested():
            db.execute(text("INSERT INTO entrega (id_reserva) VALUES (:r)"), {"r": r.id_reserva})


def test_no_se_confirma_fuera_de_plazo(db):
    r = repo.reservar(db, 10, RECEPTOR, plazo_horas=0.0001)  # ~0,36 s
    db.commit()
    db.execute(text("SELECT pg_sleep(0.5)"))
    db.commit()
    with pytest.raises(Conflicto, match="plazo"):
        repo.confirmar_reserva(db, r.id_reserva)


def test_cancelar_cierra_la_entrega_y_libera_el_cupo(db):
    r = repo.reservar(db, 10, RECEPTOR)
    e = repo.confirmar_reserva(db, r.id_reserva)
    repo.cancelar_reserva(db, r.id_reserva)
    db.commit()
    db.refresh(e)
    assert e.estado_entrega == "CANCELADA"
    assert repo.reserva_activa(db, 10) is None
    assert repo.reservar(db, 10, 7).estado_reserva == "PENDIENTE"  # la donación vuelve a poder reservarse
    with pytest.raises(TransicionInvalida):
        repo.cancelar_reserva(db, r.id_reserva)


def test_expiracion_en_lote_libera_solo_las_vencidas(db):
    ahora = db.scalar(func.now())
    vieja = repo.reservar(db, 1, RECEPTOR)
    nueva = repo.reservar(db, 2, RECEPTOR)
    confirmada = repo.reservar(db, 3, RECEPTOR)
    repo.confirmar_reserva(db, confirmada.id_reserva)
    db.execute(text("UPDATE reserva SET fecha_expiracion = fecha_reserva + interval '1 minute' "
                    "WHERE id_reserva = :r"), {"r": vieja.id_reserva})
    db.commit()
    momento = ahora + timedelta(minutes=30)
    assert repo.expirar_reservas(db, momento) == [(vieja.id_reserva, 1)]
    assert repo.expirar_reservas(db, momento) == []  # segunda corrida: sin efectos
    db.commit()
    for r, estado in ((vieja, "EXPIRADA"), (nueva, "PENDIENTE"), (confirmada, "CONFIRMADA")):
        db.refresh(r)
        assert r.estado_reserva == estado


def test_entrega_requiere_las_dos_confirmaciones(db):
    r = repo.reservar(db, 10, RECEPTOR)
    e = repo.confirmar_reserva(db, r.id_reserva)
    db.commit()
    assert repo.registrar_confirmacion(db, e.id_entrega, DONANTE, id_donante=DONANTE) is False
    with pytest.raises(Conflicto):
        repo.registrar_confirmacion(db, e.id_entrega, DONANTE, id_donante=DONANTE)
    with pytest.raises(ErrorDominio, match="Solo el donante y el receptor"):
        repo.registrar_confirmacion(db, e.id_entrega, 99, id_donante=DONANTE)
    assert repo.registrar_confirmacion(db, e.id_entrega, RECEPTOR, id_donante=DONANTE) is True
    db.commit()
    db.refresh(e)
    assert e.estado_entrega == "COMPLETADA" and e.fecha_entrega is not None
    assert repo.obtener_reserva(db, r.id_reserva).estado_reserva == "COMPLETADA"
    assert len(repo.confirmaciones(db, e.id_entrega)) == 2


def test_incidencia_queda_registrada(db):
    r = repo.reservar(db, 10, RECEPTOR)
    e = repo.confirmar_reserva(db, r.id_reserva)
    assert repo.registrar_confirmacion(db, e.id_entrega, RECEPTOR, DONANTE, "CON_INCIDENCIA", "Llegó la mitad") is False
    assert repo.registrar_confirmacion(db, e.id_entrega, DONANTE, DONANTE) is False  # no se completa
    db.commit()
    db.refresh(e)
    assert e.estado_entrega == "CON_INCIDENCIA" and e.observaciones == "Llegó la mitad"


def test_la_base_rechaza_transiciones_ilegales(db):
    sembrar(db)
    db.commit()
    for sql, mensaje in (
        ("UPDATE reserva SET estado_reserva = 'PENDIENTE' WHERE id_reserva = 4", "EXPIRADA → PENDIENTE"),
        ("UPDATE reserva SET estado_reserva = 'CONFIRMADA' WHERE id_reserva = 3", "COMPLETADA → CONFIRMADA"),
        ("UPDATE reserva SET id_donacion = 99 WHERE id_reserva = 1", "no cambian"),
        ("UPDATE entrega SET estado_entrega = 'PROGRAMADA' WHERE id_entrega = 2", "COMPLETADA → PROGRAMADA"),
        ("INSERT INTO entrega (id_reserva) VALUES (1)", "CONFIRMADA"),  # reserva 1 sigue PENDIENTE
    ):
        with pytest.raises(DBAPIError, match=mensaje):
            with db.begin_nested():
                db.execute(text(sql))


def test_semilla_coherente(db):
    sembrar(db)
    db.commit()
    estados = {r.id_reserva: r.estado_reserva for r in repo.listar_reservas(db)}
    assert estados == {1: "PENDIENTE", 2: "CONFIRMADA", 3: "COMPLETADA", 4: "EXPIRADA", 5: "CANCELADA"}
    assert [r.id_reserva for r in repo.listar_reservas(db, id_receptor=7)] == [4, 2]
    assert len(repo.confirmaciones(db, 2)) == 2
