"""Use 64-bit counters for quotas and traffic.

Revision ID: b862c3b8607f
Revises: 61b94d732ada
Create Date: 2026-09-07 15:05:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b862c3b8607f"
down_revision: Union[str, None] = "61b94d732ada"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.alter_column("quota_bytes", existing_type=sa.Integer(), type_=sa.BigInteger())
        batch.alter_column("used_up_bytes", existing_type=sa.Integer(), type_=sa.BigInteger())
        batch.alter_column("used_down_bytes", existing_type=sa.Integer(), type_=sa.BigInteger())
        batch.alter_column("speed_limit_bps", existing_type=sa.Integer(), type_=sa.BigInteger())
    with op.batch_alter_table("connection_sessions") as batch:
        batch.alter_column("uplink_bytes", existing_type=sa.Integer(), type_=sa.BigInteger())
        batch.alter_column("downlink_bytes", existing_type=sa.Integer(), type_=sa.BigInteger())


def downgrade() -> None:
    with op.batch_alter_table("connection_sessions") as batch:
        batch.alter_column("downlink_bytes", existing_type=sa.BigInteger(), type_=sa.Integer())
        batch.alter_column("uplink_bytes", existing_type=sa.BigInteger(), type_=sa.Integer())
    with op.batch_alter_table("users") as batch:
        batch.alter_column("speed_limit_bps", existing_type=sa.BigInteger(), type_=sa.Integer())
        batch.alter_column("used_down_bytes", existing_type=sa.BigInteger(), type_=sa.Integer())
        batch.alter_column("used_up_bytes", existing_type=sa.BigInteger(), type_=sa.Integer())
        batch.alter_column("quota_bytes", existing_type=sa.BigInteger(), type_=sa.Integer())
