"""Datos semilla de identity-service (S4-08).

Los identificadores son fijos porque catalog-geo, fulfillment y notification los usan
(D-06: sin claves foráneas entre bases). La tabla de referencia está en docs/modelo/datos-semilla.md.
Contraseña de todos: demo123 (solo para demostración; no protege datos reales). En un servidor público se
cambia con la variable CLAVE_DEMO (scripts/nube/instalar.sh la genera al azar).
"""
import os

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .modelos import RegistroAuditoria, Usuario, VerificacionUsuario
from .repositorio import hash_contrasena

CONTRASENA_DEMO = os.environ.get("CLAVE_DEMO") or "demo123"
ID_ADMIN = 1

# id, nombre, correo, rol, estado de verificación inicial, ciudad (solo informativa)
USUARIOS = [
    (1, "Administración RedAlimenta", "admin@redalimenta.co", 3, "APROBADA"),
    (2, "Supermercado La Cosecha", "donante@redalimenta.co", 1, "APROBADA"),
    (3, "Comedor Comunitario Esperanza", "receptor@redalimenta.co", 2, "PENDIENTE"),
    (4, "Restaurante El Fogón Paisa", "donante.medellin@redalimenta.co", 1, "APROBADA"),
    (5, "Fundación Manos Unidas", "receptor.medellin@redalimenta.co", 2, "APROBADA"),
    (6, "Banco de Alimentos del Valle", "donante.cali@redalimenta.co", 1, "APROBADA"),
    (7, "Albergue Temporal Siloé", "receptor.cali@redalimenta.co", 2, "APROBADA"),
    (8, "Panadería Don Julio", "donante.nuevo@redalimenta.co", 1, "PENDIENTE"),
]


def sembrar(db: Session) -> bool:
    """Inserta los datos si la base está vacía. Devuelve True si sembró."""
    if db.scalar(select(Usuario.id_usuario).limit(1)) is not None:
        return False
    hash_demo = hash_contrasena(CONTRASENA_DEMO)
    for id_usuario, nombre, correo, id_rol, _ in USUARIOS:
        db.add(Usuario(id_usuario=id_usuario, id_rol=id_rol, nombre=nombre, correo_electronico=correo,
                       contrasena_hash=hash_demo, telefono="3000000000"))
    db.flush()
    for id_usuario, _, _, _, estado in USUARIOS:
        resuelta = estado != "PENDIENTE"
        db.add(VerificacionUsuario(
            id_verificacion=id_usuario, id_usuario=id_usuario, estado_verificacion=estado,
            id_administrador=ID_ADMIN if resuelta else None,
            fecha_resolucion=text("now()") if resuelta else None,
            observaciones="Cuenta semilla verificada" if resuelta else None,
        ))
        if resuelta:
            db.add(RegistroAuditoria(id_usuario=ID_ADMIN, entidad_afectada="verificacion",
                                     id_registro_afectado=id_usuario, accion_realizada="USUARIO_VERIFICADO",
                                     valor_anterior="PENDIENTE", valor_nuevo=estado))
    db.flush()
    for tabla, columna in (("usuario", "id_usuario"), ("verificacion_usuario", "id_verificacion"),
                           ("registro_auditoria", "id_auditoria")):
        db.execute(text(f"SELECT setval(pg_get_serial_sequence('{tabla}', '{columna}'), "
                        f"(SELECT coalesce(max({columna}), 1) FROM {tabla}))"))
    return True
