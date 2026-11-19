"""D-12: chat entre donante y receptor. Se abre por eventos, solo escriben los participantes y no se edita."""
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from notificaciones.consumidor import procesar
from redalimenta_comun.eventos import Evento

from .conftest import ROL_APP, token

DONANTE, RECEPTOR, OTRO = token(4, "DONANTE"), token(5, "RECEPTOR"), token(7, "RECEPTOR")


def evento(tipo, id_entidad=1, **datos):
    base = {"id_donante": 4, "id_receptor": 5, "nombre_alimento": "Arepas", "id_donacion": 11}
    return Evento(tipo=tipo, entidad="reserva", id_entidad=id_entidad, estado_anterior=None, estado_nuevo=None,
                  datos={**base, **datos})


def conversaciones(cliente, cabecera):
    return cliente.get("/api/conversaciones", headers=cabecera).json()


def test_reservar_abre_el_chat_y_solo_escriben_las_dos_partes(cliente):
    assert conversaciones(cliente, DONANTE) == []
    procesar(evento("RESERVA_CREADA"))
    [c] = conversaciones(cliente, DONANTE)
    assert c["id_donacion"] == 11 and c["id_contraparte"] == 5 and c["mi_papel"] == "DONANTE"
    assert c["estado_conversacion"] == "ABIERTA" and c["origen"] == "RESERVA"
    assert conversaciones(cliente, RECEPTOR)[0]["id_contraparte"] == 4
    assert conversaciones(cliente, OTRO) == []

    ruta = f"/api/conversaciones/{c['id_conversacion']}/mensajes"
    r = cliente.post(ruta, json={"texto": "Hola, ¿puedo recoger mañana a las 9?"}, headers=RECEPTOR)
    assert r.status_code == 201 and r.json()["id_autor"] == 5
    cliente.post(ruta, json={"texto": "Sí, en la portería principal."}, headers=DONANTE)
    assert cliente.post(ruta, json={"texto": "Yo también"}, headers=OTRO).status_code == 404
    assert cliente.get(ruta, headers=OTRO).status_code == 404
    assert cliente.post(ruta, json={"texto": "   "}, headers=DONANTE).status_code == 400
    assert cliente.post(ruta, json={"texto": "x" * 1001}, headers=DONANTE).status_code == 422

    datos = cliente.get(ruta, headers=DONANTE).json()
    assert [m["texto"] for m in datos["mensajes"]] == ["Hola, ¿puedo recoger mañana a las 9?",
                                                      "Sí, en la portería principal."]
    primero = datos["mensajes"][0]["id_mensaje"]
    assert len(cliente.get(f"{ruta}?despues_de={primero}", headers=DONANTE).json()["mensajes"]) == 1


def test_no_leidos_por_participante(cliente):
    procesar(evento("RESERVA_CREADA"))
    c = conversaciones(cliente, DONANTE)[0]["id_conversacion"]
    ruta = f"/api/conversaciones/{c}/mensajes"
    cliente.post(ruta, json={"texto": "¿Sigue disponible?"}, headers=RECEPTOR)
    cliente.post(ruta, json={"texto": "¿A qué hora?"}, headers=RECEPTOR)
    assert cliente.get("/api/conversaciones/no-leidos", headers=DONANTE).json() == {"no_leidos": 2}
    assert cliente.get("/api/conversaciones/no-leidos", headers=RECEPTOR).json() == {"no_leidos": 0}  # lo propio
    assert conversaciones(cliente, DONANTE)[0]["ultimo_mensaje"]["texto"] == "¿A qué hora?"
    assert cliente.post(f"/api/conversaciones/{c}/leer", headers=DONANTE).json() == {"no_leidos": 0}
    assert cliente.post(f"/api/conversaciones/{c}/leer", headers=OTRO).status_code == 404


def test_la_reserva_que_termina_cierra_el_chat_en_solo_lectura(cliente):
    procesar(evento("RESERVA_CREADA"))
    c = conversaciones(cliente, DONANTE)[0]["id_conversacion"]
    ruta = f"/api/conversaciones/{c}/mensajes"
    cliente.post(ruta, json={"texto": "Te espero"}, headers=DONANTE)
    procesar(evento("RESERVA_EXPIRADA"))
    datos = cliente.get(ruta, headers=RECEPTOR).json()
    assert datos["estado_conversacion"] == "CERRADA" and len(datos["mensajes"]) == 1  # se sigue leyendo
    r = cliente.post(ruta, json={"texto": "¿Sigue?"}, headers=RECEPTOR)
    assert r.status_code == 409 and "cerrada" in r.json()["detail"]
    # Si vuelve a reservar, la misma conversación se reabre con su historial
    procesar(evento("RESERVA_CREADA"))
    assert cliente.post(ruta, json={"texto": "Reservé de nuevo"}, headers=RECEPTOR).status_code == 201
    assert len(conversaciones(cliente, DONANTE)) == 1
    # La entrega cierra todas las conversaciones de la donación
    procesar(evento("DONACION_ENTREGADA", id_entidad=11))
    assert conversaciones(cliente, RECEPTOR)[0]["estado_conversacion"] == "CERRADA"


def test_la_oferta_para_una_solicitud_abre_el_chat_y_sobrevive_a_una_reserva_vencida(cliente):
    """D-11 + D-12: el donante ofrece a la solicitud del receptor; pueden hablar antes de reservar."""
    procesar(evento("DONACION_CREADA", id_entidad=20, id_necesidad=5, necesidad="Almuerzos"))
    [c] = conversaciones(cliente, RECEPTOR)
    assert c["id_donacion"] == 20 and c["origen"] == "OFERTA"
    procesar(evento("RESERVA_CREADA", id_donacion=20))
    procesar(evento("RESERVA_EXPIRADA", id_donacion=20))
    assert conversaciones(cliente, RECEPTOR)[0]["estado_conversacion"] == "ABIERTA"  # sigue apartada para él
    procesar(evento("DONACION_CANCELADA", id_entidad=20))
    assert conversaciones(cliente, RECEPTOR)[0]["estado_conversacion"] == "CERRADA"
    # Una donación publicada para todos no abre chat hasta que alguien la reserve
    procesar(evento("DONACION_CREADA", id_entidad=21, id_receptor=None))
    assert len(conversaciones(cliente, DONANTE)) == 1


def test_evento_repetido_no_duplica_la_conversacion(cliente):
    e = evento("RESERVA_CREADA")
    procesar(e)
    procesar(e)
    assert len(conversaciones(cliente, DONANTE)) == 1


def test_la_base_impide_editar_borrar_o_escribir_en_cerrada(cliente, motor):
    procesar(evento("RESERVA_CREADA"))
    c = conversaciones(cliente, DONANTE)[0]["id_conversacion"]
    cliente.post(f"/api/conversaciones/{c}/mensajes", json={"texto": "Hola"}, headers=DONANTE)
    for sql in ("UPDATE mensaje SET texto = 'cambiado'", "DELETE FROM mensaje",
                f"INSERT INTO mensaje (id_conversacion, id_autor, texto) VALUES ({c}, 99, 'intruso')"):
        with motor.connect() as con, pytest.raises(DBAPIError):
            con.execute(text(sql))
    with motor.begin() as con:
        con.execute(text("UPDATE conversacion SET estado_conversacion = 'CERRADA', fecha_cierre = now()"))
    with motor.connect() as con, pytest.raises(DBAPIError):
        con.execute(text(f"INSERT INTO mensaje (id_conversacion, id_autor, texto) VALUES ({c}, 4, 'tarde')"))
    # El rol de la aplicación no tiene UPDATE ni DELETE sobre los mensajes
    with motor.connect() as con:
        permisos = con.execute(text("SELECT privilege_type FROM information_schema.role_table_grants "
                                    "WHERE grantee = :r AND table_name = 'mensaje'"), {"r": ROL_APP}).scalars().all()
    assert set(permisos) == {"SELECT", "INSERT"}
