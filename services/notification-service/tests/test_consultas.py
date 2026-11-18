"""RF7: crear notificaciones, bandeja, contador de no leídas, leer y archivar (solo las propias)."""
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from notificaciones import repositorio as repo
from notificaciones.errores import ErrorDominio, NoEncontrado, TransicionInvalida
from notificaciones.semilla import sembrar


def test_crear_y_listar_bandeja(db):
    a = repo.crear_notificacion(db, 5, "RESERVA_CREADA", "Reservaste «Arroz».")
    b = repo.crear_notificacion(db, 5, "RESERVA_CONFIRMADA", "El donante confirmó.")
    repo.crear_notificacion(db, 7, "RESERVA_CREADA", "Otra persona")
    db.commit()
    assert [n.id_notificacion for n in repo.bandeja(db, 5)] == [b.id_notificacion, a.id_notificacion]
    assert repo.contar_no_leidas(db, 5) == 2
    with pytest.raises(ErrorDominio):
        repo.crear_notificacion(db, 5, "X", "  ")


def test_leer_archivar_y_contador(db):
    n = repo.crear_notificacion(db, 5, "RESERVA_CREADA", "Hola")
    repo.crear_notificacion(db, 5, "RESERVA_CREADA", "Otra")
    leida = repo.marcar_leida(db, n.id_notificacion, 5)
    assert leida.estado_notificacion == "LEIDA" and leida.fecha_lectura is not None
    assert repo.contar_no_leidas(db, 5) == 1
    repo.archivar(db, n.id_notificacion, 5)
    assert n.id_notificacion not in [x.id_notificacion for x in repo.bandeja(db, 5)]
    assert n.id_notificacion in [x.id_notificacion for x in repo.bandeja(db, 5, incluir_archivadas=True)]
    with pytest.raises(TransicionInvalida):
        repo.marcar_leida(db, n.id_notificacion, 5)
    assert repo.marcar_todas_leidas(db, 5) == 1
    assert repo.contar_no_leidas(db, 5) == 0


def test_solo_el_destinatario_la_modifica(db):
    n = repo.crear_notificacion(db, 5, "RESERVA_CREADA", "Hola")
    with pytest.raises(NoEncontrado):
        repo.marcar_leida(db, n.id_notificacion, 7)


def test_la_base_rechaza_transiciones_y_cambios_de_contenido(db):
    sembrar(db)
    db.commit()
    for sql, mensaje in (
        ("UPDATE notificacion SET estado_notificacion = 'NO_LEIDA' WHERE estado_notificacion = 'ARCHIVADA'",
         "ARCHIVADA → NO_LEIDA"),
        ("UPDATE notificacion SET mensaje = 'otro' WHERE id_notificacion = 1", "no cambia"),
    ):
        with pytest.raises(DBAPIError, match=mensaje):
            with db.begin_nested():
                db.execute(text(sql))


def test_semilla(db):
    assert sembrar(db) is True and sembrar(db) is False
    db.commit()
    assert repo.contar_no_leidas(db, 5) == 1
    assert len(repo.bandeja(db, 4)) == 1  # la archivada no aparece
