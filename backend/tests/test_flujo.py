"""Flujo completo por la API: verificar → publicar → buscar → reservar (409) → confirmar → entregar."""
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.main import app

from .conftest import login

PUNTO_DONACION = {"lat": 4.5700, "lon": -74.1300, "direccion_referencia": "Calle 60 Sur # 20-10",
                  "ciudad": "Bogotá", "departamento": "Cundinamarca"}
PUNTO_RECEPTOR = (4.5560, -74.1420)  # Comedor en Ciudad Bolívar (semilla)


def test_flujo_completo():
    c = TestClient(app)
    admin = login(c, "admin@redalimenta.co")
    donante = login(c, "donante@redalimenta.co")
    receptor = login(c, "receptor@redalimenta.co")

    # 1. El receptor no opera hasta que el administrador lo verifica
    assert c.post("/api/reservas", json={"id_donacion": 1}, headers=receptor).status_code == 403
    pendiente = next(u for u in c.get("/api/admin/usuarios", headers=admin).json()
                     if u["verificacion"]["estado_verificacion"] == "PENDIENTE")
    r = c.post(f"/api/admin/verificaciones/{pendiente['verificacion']['id_verificacion']}",
               json={"decision": "APROBADA", "observaciones": "Documentos en regla"}, headers=admin)
    assert r.status_code == 200
    nuevo = c.post("/api/auth/refresh", headers=receptor).json()
    assert nuevo["usuario"]["estado_verificacion"] == "APROBADA"
    receptor = {"Authorization": f"Bearer {nuevo['token']}"}

    # 2. El donante publica una donación marcando el punto en el mapa
    categorias = {x["nombre_categoria"]: x["id_categoria"] for x in c.get("/api/categorias", headers=donante).json()}
    vence = (datetime.now(UTC) + timedelta(hours=30)).isoformat()
    r = c.post("/api/donaciones", headers=donante, json={
        "nombre_alimento": "Lentejas", "id_categoria": categorias["Granos y enlatados"], "cantidad": 50,
        "unidad_medida": "kg", "fecha_vencimiento": vence, "condiciones_recogida": "Portería",
        "ubicacion": PUNTO_DONACION,
    })
    assert r.status_code == 201, r.text
    id_donacion = r.json()["id_donacion"]
    assert r.json()["estado_donacion"] == "DISPONIBLE"
    # validación: cantidad > 0
    malo = c.post("/api/donaciones", headers=donante, json={**r.json(), "cantidad": 0, "ubicacion": PUNTO_DONACION,
                                                             "fecha_vencimiento": vence})
    assert malo.status_code == 422

    # 3. El receptor ve las disponibles ordenadas por prioridad (D-08) y filtra por categoría
    lat, lon = PUNTO_RECEPTOR
    todas = c.get(f"/api/donaciones/disponibles?lat={lat}&lon={lon}", headers=receptor).json()["resultados"]
    puntajes = [x["prioridad"]["puntaje"] for x in todas]
    assert puntajes == sorted(puntajes, reverse=True)
    primera = todas[0]
    assert primera["id_donacion"] == id_donacion  # cercana, urgencia CRÍTICA y vence pronto
    assert primera["distancia_km"] < 3
    por_distancia = c.get(f"/api/donaciones/disponibles?lat={lat}&lon={lon}&orden=distancia",
                          headers=receptor).json()["resultados"]
    distancias = [x["distancia_km"] for x in por_distancia]
    assert distancias == sorted(distancias)
    filtradas = c.get(f"/api/donaciones/disponibles?id_necesidad=1&id_categoria={categorias['Lácteos y huevos']}",
                      headers=receptor).json()["resultados"]
    assert filtradas and all(x["categoria"] == "Lácteos y huevos" for x in filtradas)

    # 4. Reserva; la segunda solicitud responde 409
    r = c.post("/api/reservas", json={"id_donacion": id_donacion}, headers=receptor)
    assert r.status_code == 201
    reserva = r.json()
    assert reserva["estado_reserva"] == "PENDIENTE" and reserva["fecha_expiracion"]
    assert c.post("/api/reservas", json={"id_donacion": id_donacion}, headers=receptor).status_code == 409
    ids_disponibles = [x["id_donacion"] for x in c.get(
        f"/api/donaciones/disponibles?lat={lat}&lon={lon}", headers=receptor).json()["resultados"]]
    assert id_donacion not in ids_disponibles

    # 5. El donante confirma; luego ambos confirman la entrega
    r = c.post(f"/api/reservas/{reserva['id_reserva']}/confirmar", headers=donante)
    assert r.json()["estado_reserva"] == "CONFIRMADA"
    id_entrega = r.json()["entrega"]["id_entrega"]
    r = c.post(f"/api/entregas/{id_entrega}/confirmar", json={}, headers=receptor)
    assert r.json()["donacion"]["estado_donacion"] == "RESERVADA"
    r = c.post(f"/api/entregas/{id_entrega}/confirmar", json={}, headers=donante)
    assert r.json()["donacion"]["estado_donacion"] == "ENTREGADA"
    assert r.json()["estado_reserva"] == "COMPLETADA"

    # 6. Cada cambio de estado dejó auditoría y notificaciones
    acciones = [a["accion_realizada"] for a in reversed(c.get("/api/admin/auditoria", headers=admin).json())]
    esperado = ["USUARIO_VERIFICADO", "DONACION_CREADA", "RESERVA_CREADA", "DONACION_RESERVADA",
                "RESERVA_CONFIRMADA", "ENTREGA_PROGRAMADA", "ENTREGA_CONFIRMADA", "ENTREGA_CONFIRMADA",
                "ENTREGA_COMPLETADA", "RESERVA_COMPLETADA", "DONACION_ENTREGADA"]
    assert [a for a in acciones if a in esperado] == esperado
    historial = c.get(f"/api/admin/auditoria?entidad=donacion&id_registro={id_donacion}", headers=admin).json()
    assert [(h["valor_anterior"], h["valor_nuevo"]) for h in reversed(historial)] == [
        (None, "DISPONIBLE"), ("DISPONIBLE", "RESERVADA"), ("RESERVADA", "ENTREGADA")]
    assert c.get("/api/admin/auditoria", headers=donante).status_code == 403

    tipos_receptor = {n["tipo_notificacion"] for n in c.get("/api/notificaciones", headers=receptor).json()}
    assert {"USUARIO_VERIFICADO", "RESERVA_CREADA", "RESERVA_CONFIRMADA", "ENTREGA_COMPLETADA"} <= tipos_receptor
    tipos_donante = {n["tipo_notificacion"] for n in c.get("/api/notificaciones", headers=donante).json()}
    assert {"DONACION_CREADA", "DONACION_RESERVADA", "ENTREGA_CONFIRMADA", "DONACION_ENTREGADA"} <= tipos_donante

    no_leidas = c.get("/api/notificaciones/no-leidas", headers=donante).json()["no_leidas"]
    assert no_leidas >= 4
    primera_notif = c.get("/api/notificaciones", headers=donante).json()[0]
    c.post(f"/api/notificaciones/{primera_notif['id_notificacion']}/leer", headers=donante)
    assert c.get("/api/notificaciones/no-leidas", headers=donante).json()["no_leidas"] == no_leidas - 1
    assert c.post(f"/api/notificaciones/{primera_notif['id_notificacion']}/leer",
                  headers=receptor).status_code == 403
