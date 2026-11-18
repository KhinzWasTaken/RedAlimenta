"""S4-09: crear, consultar, actualizar y desactivar usuarios; resolver verificaciones; auditoría."""
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from identidad import repositorio as repo
from identidad.errores import Conflicto, ErrorDominio, TransicionInvalida
from identidad.modelos import Usuario
from identidad.semilla import sembrar


def test_crear_y_consultar_usuario(db):
    u = repo.crear_usuario(db, "Comedor San José", "Comedor@Ejemplo.co", "clave-segura", "RECEPTOR", "3101234567")
    db.commit()
    assert u.estado_cuenta == "ACTIVA"
    assert u.contrasena_hash != "clave-segura" and u.contrasena_hash.startswith("pbkdf2_sha256$")
    assert repo.obtener_usuario(db, u.id_usuario).correo_electronico == "comedor@ejemplo.co"
    assert repo.buscar_por_correo(db, "COMEDOR@ejemplo.co").id_usuario == u.id_usuario
    assert repo.autenticar(db, "comedor@ejemplo.co", "clave-segura").id_usuario == u.id_usuario
    with pytest.raises(ErrorDominio):
        repo.autenticar(db, "comedor@ejemplo.co", "otra")
    assert repo.verificacion_actual(db, u.id_usuario).estado_verificacion == "PENDIENTE"
    with pytest.raises(Conflicto):
        repo.crear_usuario(db, "Otro", "comedor@ejemplo.co", "x", "DONANTE")


def test_listar_usuarios_con_su_verificacion(db):
    sembrar(db)
    db.commit()
    todos = repo.listar_usuarios(db)
    assert len(todos) == 8
    pendientes = repo.listar_usuarios(db, estado_verificacion="PENDIENTE")
    assert {f["usuario"].correo_electronico for f in pendientes} == {
        "receptor@redalimenta.co", "donante.nuevo@redalimenta.co"}
    assert all(f["rol"] == "RECEPTOR" for f in repo.listar_usuarios(db, rol="RECEPTOR"))


def test_actualizar_solo_datos_permitidos(db):
    u = repo.crear_usuario(db, "Ana", "ana@ejemplo.co", "x", "DONANTE")
    repo.actualizar_usuario(db, u.id_usuario, nombre="Ana María", telefono="3200000000")
    db.commit()
    assert repo.obtener_usuario(db, u.id_usuario).nombre == "Ana María"
    with pytest.raises(ErrorDominio, match="no editables"):
        repo.actualizar_usuario(db, u.id_usuario, correo_electronico="otro@x.co")


def test_desactivar_no_borra_la_fila(db):
    u = repo.crear_usuario(db, "Ana", "ana@ejemplo.co", "x", "DONANTE")
    repo.desactivar_usuario(db, u.id_usuario)
    db.commit()
    db.expire_all()
    fila = db.get(Usuario, u.id_usuario)
    assert fila is not None and fila.estado_cuenta == "DESACTIVADA"
    with pytest.raises(ErrorDominio, match="desactivada"):
        repo.autenticar(db, "ana@ejemplo.co", "x")
    with pytest.raises(TransicionInvalida):
        repo.desactivar_usuario(db, u.id_usuario)


def test_verificacion_resuelta_no_vuelve_a_pendiente(db):
    sembrar(db)
    db.commit()
    v = repo.verificacion_actual(db, 3)  # receptor PENDIENTE
    repo.resolver_verificacion(db, v.id_verificacion, "APROBADA", id_administrador=1, observaciones="OK")
    db.commit()
    assert repo.verificacion_actual(db, 3).estado_verificacion == "APROBADA"
    with pytest.raises(TransicionInvalida):
        repo.resolver_verificacion(db, v.id_verificacion, "RECHAZADA", id_administrador=1)
    # Aunque la aplicación se salte la regla, la base la impide
    with pytest.raises(DBAPIError, match="resuelta"):
        with db.begin_nested():
            db.execute(text("UPDATE verificacion_usuario SET estado_verificacion = 'PENDIENTE', "
                            "fecha_resolucion = NULL, id_administrador = NULL WHERE id_verificacion = :v"),
                       {"v": v.id_verificacion})


def test_solo_un_administrador_resuelve(db):
    sembrar(db)
    db.commit()
    v = repo.verificacion_actual(db, 8)
    with pytest.raises(DBAPIError, match="administrador"):
        with db.begin_nested():
            repo.resolver_verificacion(db, v.id_verificacion, "APROBADA", id_administrador=2)  # un donante


def test_tras_un_rechazo_se_puede_solicitar_de_nuevo(db):
    sembrar(db)
    db.commit()
    v = repo.verificacion_actual(db, 8)
    repo.resolver_verificacion(db, v.id_verificacion, "RECHAZADA", 1, "Falta RUT")
    nueva = repo.solicitar_verificacion(db, 8)
    db.commit()
    assert nueva.estado_verificacion == "PENDIENTE" and nueva.id_verificacion != v.id_verificacion
    with pytest.raises(Conflicto):
        repo.solicitar_verificacion(db, 8)  # ya tiene una PENDIENTE


def test_registrar_y_consultar_auditoria(db):
    sembrar(db)
    repo.registrar_auditoria(db, "donacion", 10, "DONACION_CREADA", 2, None, "DISPONIBLE")
    repo.registrar_auditoria(db, "donacion", 10, "DONACION_RESERVADA", 3, "DISPONIBLE", "RESERVADA")
    repo.registrar_auditoria(db, "reserva", 1, "RESERVA_CREADA", 3, None, "PENDIENTE")
    db.commit()
    historial = repo.consultar_auditoria(db, entidad="donacion", id_registro=10)
    assert [(h.valor_anterior, h.valor_nuevo) for h in reversed(historial)] == [
        (None, "DISPONIBLE"), ("DISPONIBLE", "RESERVADA")]
    assert {h.accion_realizada for h in repo.consultar_auditoria(db, id_usuario=3)} == {
        "DONACION_RESERVADA", "RESERVA_CREADA"}
