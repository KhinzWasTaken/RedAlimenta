"""analytics-service lee el almacén para la API de indicadores (S8-01): solo SELECT sobre dw y el control de cargas.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-12
"""
import os
import re

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

ROL_LECTURA = os.environ.get("ANALYTICS_APP_ROLE", "analytics_app")
if not re.fullmatch(r"[a-z_][a-z0-9_]*", ROL_LECTURA):
    raise ValueError("ANALYTICS_APP_ROLE no es un identificador válido")


def upgrade() -> None:
    op.execute(f"""
    DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{ROL_LECTURA}') THEN
        GRANT USAGE ON SCHEMA dw, etl TO {ROL_LECTURA};
        GRANT SELECT ON ALL TABLES IN SCHEMA dw TO {ROL_LECTURA};
        GRANT SELECT ON etl.ejecucion, etl.resultado_calidad TO {ROL_LECTURA};
      END IF;
    END $$;
    """)


def downgrade() -> None:
    op.execute(f"""
    DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{ROL_LECTURA}') THEN
        REVOKE ALL ON ALL TABLES IN SCHEMA dw, etl FROM {ROL_LECTURA};
        REVOKE USAGE ON SCHEMA dw, etl FROM {ROL_LECTURA};
      END IF;
    END $$;
    """)
