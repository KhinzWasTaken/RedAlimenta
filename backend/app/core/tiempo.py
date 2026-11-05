"""Fechas: se guardan en UTC sin zona; se muestran en hora de Bogotá (UTC-5)."""
from datetime import UTC, datetime, timedelta, timezone

BOGOTA = timezone(timedelta(hours=-5))


def ahora() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def a_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(UTC).replace(tzinfo=None)


def iso(dt: datetime | None) -> str | None:
    return None if dt is None else dt.isoformat(timespec="seconds") + "Z"


def hora_bogota(dt: datetime) -> str:
    return dt.replace(tzinfo=UTC).astimezone(BOGOTA).strftime("%d/%m %H:%M")
