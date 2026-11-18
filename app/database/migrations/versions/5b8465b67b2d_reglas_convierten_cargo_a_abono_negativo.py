"""reglas convierten cargo a abono negativo

Revision ID: 5b8465b67b2d
Revises: 6b49f74b1b35
Create Date: 2026-09-11 10:17:59.814636

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5b8465b67b2d'
down_revision: Union[str, None] = '6b49f74b1b35'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "classification_rules",
        sa.Column(
            "invert_to_negative_payment",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("classification_rules", "invert_to_negative_payment")
