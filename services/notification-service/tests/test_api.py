"""S5-14: cada evento crea la notificación del destinatario correcto; leer, archivar y contador."""
from notificaciones.consumidor import destinatarios, procesar
from redalimenta_comun.eventos import Evento

from .conftest import token

CTX = {"id_donante": 4, "id_receptor": 5, "nombre_alimento": "Arepas", "id_reserva": 1, "id_donacion": 11}


def evento(tipo, anterior=None, nuevo=None, **datos):
    return Evento(tipo=tipo, entidad="reserva", id_entidad=1, estado_anterior=anterior, estado_nuevo=nuevo,
                  datos={**CTX, **datos})


def test_cada_evento_llega_al_destinatario_correcto():
    casos = {
        "RESERVA_CREADA": {5}, "DONACION_RESERVADA": {4}, "RESERVA_CONFIRMADA": {5}, "ENTREGA_PROGRAMADA": {4, 5},
        "RESERVA_EXPIRADA": {4, 5}, "ENTREGA_COMPLETADA": {4, 5}, "DONACION_ENTREGADA": {4},
        "DONACION_POR_VENCER": {4, 5},
    }
    for tipo, esperados in casos.items():
        assert {u for u, _ in destinatarios(evento(tipo, fecha_expiracion="2026-11-12T17:00:00+00:00",
                                                   fecha_vencimiento="2026-11-13T17:00:00+00:00"))} == esperados, tipo
    # la confirmación de entrega avisa a la otra parte
    assert [u for u, _ in destinatarios(evento("ENTREGA_CONFIRMADA", por="donante"))] == [5]
    assert [u for u, _ in destinatarios(evento("ENTREGA_CONFIRMADA", por="receptor"))] == [4]
    assert destinatarios(evento("EVENTO_DESCONOCIDO")) == []
    # D-11: una donación ofrecida para una solicitud avisa también al receptor que la pidió
    ofrecida = destinatarios(evento("DONACION_CREADA", necesidad="Arroz para 120 almuerzos"))
    assert [u for u, _ in ofrecida] == [4, 5] and "apartada para ti" in ofrecida[1][1]
    verificado = Evento(tipo="USUARIO_VERIFICADO", entidad="verificacion", id_entidad=3, estado_nuevo="APROBADA",
                        datos={"id_usuario": 3})
    assert destinatarios(verificado)[0][0] == 3
    assert "12/11/26 12:00" in destinatarios(evento("RESERVA_CREADA", fecha_expiracion="2026-11-12T17:00:00+00:00"))[0][1]


def test_bandeja_leer_archivar_y_contador(cliente):
    procesar(evento("ENTREGA_PROGRAMADA", None, "PROGRAMADA"))
    procesar(evento("RESERVA_CONFIRMADA", "PENDIENTE", "CONFIRMADA"))
    receptor, donante = token(5, "RECEPTOR"), token(4, "DONANTE")
    bandeja = cliente.get("/api/notificaciones", headers=receptor).json()
    assert [n["tipo_notificacion"] for n in bandeja] == ["RESERVA_CONFIRMADA", "ENTREGA_PROGRAMADA"]
    assert cliente.get("/api/notificaciones/no-leidas", headers=receptor).json() == {"no_leidas": 2}
    primera = bandeja[0]["id_notificacion"]
    assert cliente.post(f"/api/notificaciones/{primera}/leer", headers=donante).status_code == 404  # no es suya
    leida = cliente.post(f"/api/notificaciones/{primera}/leer", headers=receptor).json()
    assert leida["estado_notificacion"] == "LEIDA" and leida["fecha_lectura"]
    assert cliente.get("/api/notificaciones/no-leidas", headers=receptor).json() == {"no_leidas": 1}
    assert cliente.post(f"/api/notificaciones/{primera}/archivar", headers=receptor).json()[
        "estado_notificacion"] == "ARCHIVADA"
    assert len(cliente.get("/api/notificaciones", headers=receptor).json()) == 1
    assert len(cliente.get("/api/notificaciones?archivadas=true", headers=receptor).json()) == 2
    assert cliente.post("/api/notificaciones/leer-todas", headers=receptor).json()["marcadas"] == 1
    assert cliente.get("/api/notificaciones").status_code == 401


def test_evento_repetido_no_duplica_notificaciones(cliente):
    """S6-05: entregar dos veces el mismo id_evento no crea dos notificaciones."""
    e = evento("ENTREGA_COMPLETADA", "PROGRAMADA", "COMPLETADA")
    assert procesar(e) == 2
    assert procesar(Evento.desde_json(e.a_json())) == 0
    assert cliente.get("/api/notificaciones/no-leidas", headers=token(5, "RECEPTOR")).json() == {"no_leidas": 1}
