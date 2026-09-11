"""reglas dividen cargo domiciliacion en base e iva

Revision ID: 30be5ee0b3ff
Revises: 5b8465b67b2d
Create Date: 2026-09-11 12:30:14.238007

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '30be5ee0b3ff'
down_revision: Union[str, None] = '5b8465b67b2d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "classification_rules",
        sa.Column(
            "split_vat_from_charge",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "movements",
        sa.Column("split_from_movement_id", sa.Integer(), nullable=True),
    )
    with op.batch_alter_table("movements") as batch_op:
        batch_op.create_foreign_key(
            "fk_movements_split_from_movement_id",
            "movements",
            ["split_from_movement_id"],
            ["id"],
        )
        batch_op.create_index(
            "ix_movements_split_from_movement_id", ["split_from_movement_id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("movements") as batch_op:
        batch_op.drop_index("ix_movements_split_from_movement_id")
        batch_op.drop_constraint(
            "fk_movements_split_from_movement_id", type_="foreignkey"
        )
        batch_op.drop_column("split_from_movement_id")
    op.drop_column("classification_rules", "split_vat_from_charge")
