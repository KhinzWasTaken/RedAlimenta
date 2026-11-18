"""El administrador mantiene el catálogo de categorías (S5-20): el rol de aplicación puede crearlas y editarlas.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-12
"""
from alembic import op

from catalogo.db import ROL_APP

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(f"""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{ROL_APP}') THEN
            GRANT INSERT, UPDATE ON categoria_alimento TO {ROL_APP};
          END IF;
        END $$;
    """)


def downgrade() -> None:
    op.execute(f"""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{ROL_APP}') THEN
            REVOKE INSERT, UPDATE ON categoria_alimento FROM {ROL_APP};
          END IF;
        END $$;
    """)
