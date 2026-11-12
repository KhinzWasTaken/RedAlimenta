"""Operaciones sobre las cuatro bases transaccionales (Sprint 4).

    python scripts/bd.py migrar        crea las bases que falten y aplica las migraciones (alembic upgrade head)
    python scripts/bd.py revertir      las revierte todas (alembic downgrade base)
    python scripts/bd.py sembrar       inserta los datos semilla (solo si las tablas están vacías)
    python scripts/bd.py reiniciar     revertir + migrar + sembrar
    python scripts/bd.py verificar     comprueba la coherencia entre bases (D-06: no hay FK entre ellas)
    python scripts/bd.py diccionario   regenera docs/modelo/diccionario-datos.md desde las bases

Conexión: usa <SERVICIO>_DATABASE_URL si existe (p. ej. IDENTITY_DATABASE_URL); si no, arma la URL
con infra/.env (POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_PORT) contra localhost.
"""
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
SERVICIOS = [  # (nombre, carpeta, paquete)
    ("identity", "identity-service", "identidad"),
    ("catalog", "catalog-geo-service", "catalogo"),
    ("fulfillment", "fulfillment-service", "cumplimiento"),
    ("notification", "notification-service", "notificaciones"),
    ("analytics", "analytics-service", "analitica"),
    ("dwh", "../dwh", "almacen"),  # almacén de datos (Sprint 7); no es un servicio pero se migra igual
]
FUENTES_DWH = ("identity", "catalog", "fulfillment", "analytics")  # bases que el ETL lee (solo lectura)
for _, carpeta, _ in SERVICIOS:
    sys.path.insert(0, str(RAIZ / "services" / carpeta))

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import URL, make_url  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402


def _leer_env() -> dict:
    valores = {}
    archivo = RAIZ / "infra" / ".env"
    if archivo.exists():
        for linea in archivo.read_text(encoding="utf-8").splitlines():
            if "=" in linea and not linea.lstrip().startswith("#"):
                clave, valor = linea.split("=", 1)
                valores[clave.strip()] = valor.strip()
    return valores


def url(nombre: str) -> str:
    propia = os.environ.get(f"{nombre.upper()}_DATABASE_URL")
    if propia:
        return propia
    env = {**_leer_env(), **{k: v for k, v in os.environ.items() if k.startswith(("POSTGRES_", "PGHOST"))}}
    return URL.create(
        "postgresql+psycopg", username=env.get("POSTGRES_USER", "postgres"), password=env.get("POSTGRES_PASSWORD"),
        host=env.get("PGHOST", "localhost"), port=int(env.get("POSTGRES_PORT", 5432)),
        database=f"redalimenta_{nombre}",
    ).render_as_string(hide_password=False)


def _cfg(nombre: str, carpeta: str) -> Config:
    cfg = Config(str(RAIZ / "services" / carpeta / "alembic.ini"))
    cfg.attributes["url"] = url(nombre)
    return cfg


def preparar() -> None:
    """Crea las bases y roles que falten (p. ej. analytics en un volumen creado en el Sprint 4).

    Solo aplica a las URLs armadas con infra/.env (servidor local de desarrollo).
    """
    env = {**_leer_env(), **{k: v for k, v in os.environ.items() if k in ("APP_DB_PASSWORD",)}}
    if any(os.environ.get(f"{n.upper()}_DATABASE_URL") for n, _, _ in SERVICIOS) or not env.get("APP_DB_PASSWORD"):
        return
    admin = create_engine(make_url(url("identity")).set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        for nombre, _, _ in SERVICIOS:
            rol, base = f"{nombre}_app", f"redalimenta_{nombre}"
            clave = env["APP_DB_PASSWORD"].replace("'", "''")
            puede_entrar = c.scalar(text("SELECT rolcanlogin FROM pg_roles WHERE rolname = :r"), {"r": rol})
            if puede_entrar is None:
                c.execute(text(f"CREATE ROLE {rol} LOGIN PASSWORD '{clave}'"))
            elif not puede_entrar:  # creado sin login por las pruebas
                c.execute(text(f"ALTER ROLE {rol} LOGIN PASSWORD '{clave}'"))
            if not c.scalar(text("SELECT 1 FROM pg_database WHERE datname = :b"), {"b": base}):
                print(f"» Creando la base {base}…")
                c.execute(text(f"CREATE DATABASE {base}"))
                c.execute(text(f"REVOKE ALL ON DATABASE {base} FROM PUBLIC"))
                c.execute(text(f"GRANT CONNECT, TEMPORARY ON DATABASE {base} TO {rol}"))
        # Rol de solo lectura del ETL (S7-04): puede conectarse a las bases fuente y solo hacer SELECT
        clave = env["APP_DB_PASSWORD"].replace("'", "''")
        if not c.scalar(text("SELECT 1 FROM pg_roles WHERE rolname = 'dwh_lector'")):
            c.execute(text(f"CREATE ROLE dwh_lector LOGIN PASSWORD '{clave}'"))
        for nombre in FUENTES_DWH:
            c.execute(text(f"GRANT CONNECT ON DATABASE redalimenta_{nombre} TO dwh_lector"))
        # analytics-service lee el almacén para la API de indicadores (S8-01)
        c.execute(text("GRANT CONNECT ON DATABASE redalimenta_dwh TO analytics_app"))
    admin.dispose()


def permisos_lectura_dwh() -> None:
    """Tras migrar: dwh_lector puede leer (y solo leer) las tablas de las bases fuente."""
    for nombre in FUENTES_DWH:
        motor = create_engine(url(nombre))
        with motor.begin() as c:
            if c.scalar(text("SELECT 1 FROM pg_roles WHERE rolname = 'dwh_lector'")):
                c.execute(text("GRANT USAGE ON SCHEMA public TO dwh_lector; "
                               "GRANT SELECT ON ALL TABLES IN SCHEMA public TO dwh_lector"))
        motor.dispose()


def migrar() -> None:
    for nombre, carpeta, _ in SERVICIOS:
        print(f"» Migrando {nombre}…")
        command.upgrade(_cfg(nombre, carpeta), "head")
    permisos_lectura_dwh()


def revertir() -> None:
    for nombre, carpeta, _ in reversed(SERVICIOS):
        print(f"» Revirtiendo {nombre}…")
        command.downgrade(_cfg(nombre, carpeta), "base")


def sembrar() -> None:
    for nombre, carpeta, paquete in SERVICIOS:
        if not (RAIZ / "services" / carpeta / paquete / "semilla.py").exists():
            continue
        modulo = __import__(f"{paquete}.semilla", fromlist=["sembrar"])
        motor = create_engine(url(nombre))
        with Session(motor) as db:
            sembro = modulo.sembrar(db)
            db.commit()
        motor.dispose()
        print(f"» {nombre}: {'datos semilla creados' if sembro else 'ya tenía datos; no se tocó'}")


def verificar() -> int:
    """Conciliación entre bases: referencias lógicas (D-06) y estados coherentes (D-01, D-02)."""
    motores = {n: create_engine(url(n)) for n, _, _ in SERVICIOS}

    def filas(nombre, sql):
        with motores[nombre].connect() as c:
            return c.execute(text(sql)).all()

    usuarios = {i: r for i, r in filas("identity", "SELECT u.id_usuario, r.nombre_rol FROM usuario u "
                                                   "JOIN rol r ON r.id_rol = u.id_rol")}
    donaciones = {i: (d, e) for i, d, e in filas("catalog", "SELECT id_donacion, id_donante, estado_donacion "
                                                            "FROM donacion")}
    necesidades = filas("catalog", "SELECT id_necesidad, id_receptor FROM necesidad_alimentaria")
    reservas = filas("fulfillment", "SELECT id_reserva, id_donacion, id_receptor, estado_reserva FROM reserva")
    destinatarios = filas("notification", "SELECT DISTINCT id_usuario FROM notificacion")
    problemas = []
    for i, (donante, _) in donaciones.items():
        if usuarios.get(donante) != "DONANTE":
            problemas.append(f"donación {i}: id_donante {donante} no es un DONANTE")
    for i, receptor in necesidades:
        if usuarios.get(receptor) != "RECEPTOR":
            problemas.append(f"necesidad {i}: id_receptor {receptor} no es un RECEPTOR")
    activas = {}
    for i, donacion, receptor, estado in reservas:
        if donacion not in donaciones:
            problemas.append(f"reserva {i}: la donación {donacion} no existe")
        if usuarios.get(receptor) != "RECEPTOR":
            problemas.append(f"reserva {i}: id_receptor {receptor} no es un RECEPTOR")
        if estado in ("PENDIENTE", "CONFIRMADA"):
            activas[donacion] = i
        if estado == "COMPLETADA" and donaciones.get(donacion, (None, None))[1] != "ENTREGADA":
            problemas.append(f"reserva {i} COMPLETADA pero la donación {donacion} no está ENTREGADA")
    for i, (_, estado) in donaciones.items():
        if (estado == "RESERVADA") != (i in activas):
            problemas.append(f"donación {i} está {estado} y {'sí' if i in activas else 'no'} tiene reserva activa")
    for (id_usuario,) in destinatarios:
        if id_usuario not in usuarios:
            problemas.append(f"notificación para el usuario {id_usuario}, que no existe")
    for m in motores.values():
        m.dispose()
    if problemas:
        print("✗ Inconsistencias entre bases:")
        for p in problemas:
            print("  -", p)
        return 1
    print(f"✓ Bases coherentes: {len(usuarios)} usuarios, {len(donaciones)} donaciones, "
          f"{len(necesidades)} necesidades, {len(reservas)} reservas, {len(destinatarios)} destinatarios.")
    return 0


def main(argv: list[str]) -> int:
    acciones = {"migrar": migrar, "revertir": revertir, "sembrar": sembrar, "verificar": verificar}
    if not argv or argv[0] not in (*acciones, "reiniciar", "diccionario"):
        print(__doc__)
        return 2
    if argv[0] in ("migrar", "revertir", "reiniciar"):
        preparar()
    if argv[0] == "reiniciar":
        revertir()
        migrar()
        sembrar()
        return verificar()
    if argv[0] == "diccionario":
        from diccionario import generar
        generar({n: url(n) for n, _, _ in SERVICIOS}, RAIZ / "docs" / "modelo" / "diccionario-datos.md")
        return 0
    return acciones[argv[0]]() or 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
