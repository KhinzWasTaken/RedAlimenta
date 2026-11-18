"""Eventos de dominio sobre RabbitMQ (plan, sección 4: sobre común y catálogo de eventos).

- Exchange `redalimenta.eventos` de tipo topic y duradero; la clave de enrutamiento es el tipo del evento.
- Cada consumidor tiene su propia cola duradera (p. ej. `identity.auditoria`, `notification.bandeja`).
- Los servicios publican después de confirmar la transacción (`Lote.publicar`), así nunca se anuncia un
  cambio que la base no guardó.
- EVENTOS_BACKEND=rabbit (por defecto) usa RabbitMQ; =memoria guarda los eventos en una lista (pruebas).
"""
import json
import logging
import os
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

import pika
from pika.exceptions import AMQPError

from . import correlacion

log = logging.getLogger("redalimenta.eventos")
EXCHANGE = "redalimenta.eventos"


def _ahora() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


@dataclass
class Evento:
    tipo: str
    entidad: str
    id_entidad: int
    estado_anterior: str | None = None
    estado_nuevo: str | None = None
    id_actor: int | None = None
    datos: dict[str, Any] = field(default_factory=dict)
    origen: str = ""
    id_evento: str = field(default_factory=lambda: str(uuid.uuid4()))
    version: int = 1
    fecha: str = field(default_factory=_ahora)
    id_correlacion: str = field(default_factory=correlacion.actual)

    def a_json(self) -> bytes:
        return json.dumps(asdict(self), ensure_ascii=False, default=str).encode()

    @classmethod
    def desde_json(cls, cuerpo: bytes | str) -> "Evento":
        datos = json.loads(cuerpo)
        return cls(**{k: v for k, v in datos.items() if k in cls.__dataclass_fields__})


def url_rabbit() -> str:
    return os.environ.get("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/%2F")


class PublicadorMemoria:
    """Para pruebas: guarda los eventos publicados."""

    def __init__(self) -> None:
        self.eventos: list[Evento] = []

    def publicar(self, evento: Evento) -> None:
        self.eventos.append(evento)

    def tipos(self) -> list[str]:
        return [e.tipo for e in self.eventos]


class PublicadorRabbit:
    """Publicador real: mensajes persistentes con confirmación del broker y reintentos acotados."""

    def __init__(self, url: str | None = None, reintentos: int = 3) -> None:
        self.url = url or url_rabbit()
        self.reintentos = reintentos
        self._candado = threading.Lock()
        self._conexion = None
        self._canal = None

    def _canal_abierto(self):
        if self._conexion is None or self._conexion.is_closed:
            parametros = pika.URLParameters(self.url)
            parametros.blocked_connection_timeout = 5
            parametros.socket_timeout = 5
            self._conexion = pika.BlockingConnection(parametros)
            self._canal = self._conexion.channel()
            self._canal.exchange_declare(EXCHANGE, exchange_type="topic", durable=True)
            self._canal.confirm_delivery()
        return self._canal

    def publicar(self, evento: Evento) -> None:
        with self._candado:
            for intento in range(1, self.reintentos + 1):
                try:
                    self._canal_abierto().basic_publish(
                        EXCHANGE, evento.tipo, evento.a_json(),
                        pika.BasicProperties(content_type="application/json", delivery_mode=2,
                                             message_id=evento.id_evento, type=evento.tipo,
                                             correlation_id=evento.id_correlacion))
                    return
                except AMQPError:
                    self._conexion = None
                    if intento == self.reintentos:
                        log.error("No se pudo publicar %s (%s) tras %d intentos",
                                  evento.tipo, evento.id_evento, intento)
                        return
                    time.sleep(0.5 * intento)


_publicador = None


def publicador():
    """Publicador del proceso, según EVENTOS_BACKEND."""
    global _publicador
    if _publicador is None:
        _publicador = PublicadorMemoria() if os.environ.get("EVENTOS_BACKEND") == "memoria" else PublicadorRabbit()
    return _publicador


def usar_publicador(nuevo) -> None:
    global _publicador
    _publicador = nuevo


class Lote:
    """Eventos de una operación: se acumulan durante la transacción y se publican tras el commit."""

    def __init__(self, origen: str) -> None:
        self.origen = origen
        self.eventos: list[Evento] = []

    def agregar(self, tipo: str, entidad: str, id_entidad: int, anterior: str | None, nuevo: str | None,
                id_actor: int | None, **datos) -> Evento:
        evento = Evento(tipo=tipo, entidad=entidad, id_entidad=id_entidad, estado_anterior=anterior,
                        estado_nuevo=nuevo, id_actor=id_actor, datos=datos, origen=self.origen)
        self.eventos.append(evento)
        return evento

    def publicar(self) -> None:
        for evento in self.eventos:
            publicador().publicar(evento)
        self.eventos.clear()


class Consumidor(threading.Thread):
    """Consume una cola duradera en segundo plano; confirma (ack) solo si el manejador terminó bien."""

    def __init__(self, cola: str, claves: list[str], manejador: Callable[[Evento], None],
                 url: str | None = None) -> None:
        super().__init__(name=f"consumidor-{cola}", daemon=True)
        self.cola, self.claves, self.manejador = cola, claves, manejador
        self.url = url or url_rabbit()
        self._detener = threading.Event()

    def detener(self) -> None:
        self._detener.set()

    def run(self) -> None:
        while not self._detener.is_set():
            try:
                conexion = pika.BlockingConnection(pika.URLParameters(self.url))
                canal = conexion.channel()
                canal.exchange_declare(EXCHANGE, exchange_type="topic", durable=True)
                canal.queue_declare(self.cola, durable=True)
                for clave in self.claves:
                    canal.queue_bind(self.cola, EXCHANGE, routing_key=clave)
                canal.basic_qos(prefetch_count=20)
                log.info("Consumiendo %s (%s)", self.cola, ", ".join(self.claves))
                for metodo, _props, cuerpo in canal.consume(self.cola, inactivity_timeout=1):
                    if self._detener.is_set():
                        break
                    if metodo is None:
                        continue
                    try:
                        evento = Evento.desde_json(cuerpo)
                        correlacion.fijar(evento.id_correlacion)
                        self.manejador(evento)
                        canal.basic_ack(metodo.delivery_tag)
                        log.info("%s procesado en %s (%s)", evento.tipo, self.cola, evento.id_evento)
                    except Exception:
                        log.exception("Fallo procesando un evento de %s; se reintentará", self.cola)
                        canal.basic_nack(metodo.delivery_tag, requeue=True)
                        time.sleep(1)
                canal.cancel()
                conexion.close()
            except AMQPError:
                log.warning("RabbitMQ no disponible para %s; reintento en 3 s", self.cola)
                self._detener.wait(3)


def primera_vez(db, evento: Evento, cola: str) -> bool:
    """S6-05: registra el evento como procesado en la misma transacción del consumidor.

    Devuelve False si ya se había procesado (el broker lo entregó de nuevo): el consumidor no repite efectos.
    Requiere la tabla `evento_procesado` en la base del servicio.
    """
    from sqlalchemy import text
    fila = db.execute(text("INSERT INTO evento_procesado (id_evento, cola) VALUES (:id, :cola) "
                           "ON CONFLICT (id_evento) DO NOTHING RETURNING id_evento"),
                      {"id": evento.id_evento, "cola": cola}).first()
    return fila is not None
