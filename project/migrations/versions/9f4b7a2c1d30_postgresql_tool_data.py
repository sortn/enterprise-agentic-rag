"""store enterprise tool data in PostgreSQL

Revision ID: 9f4b7a2c1d30
Revises: c4b5848bcde8
Create Date: 2026-10-11 21:30:00
"""

from datetime import datetime
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9f4b7a2c1d30"
down_revision: Union[str, Sequence[str], None] = "c4b5848bcde8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    products = op.create_table(
        "products",
        sa.Column("sku", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("list_price", sa.Float(), nullable=False),
        sa.Column("warranty_years", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("sku"),
    )
    departments = op.create_table(
        "departments",
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("contact", sa.String(length=100), nullable=False),
        sa.Column("hotline", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("code"),
    )
    inventory = op.create_table(
        "product_inventory",
        sa.Column("sku", sa.String(length=100), nullable=False),
        sa.Column("available", sa.Integer(), nullable=False),
        sa.Column("reserved", sa.Integer(), nullable=False),
        sa.Column("warehouse", sa.String(length=100), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["sku"], ["products.sku"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("sku"),
    )
    service_statuses = op.create_table(
        "service_statuses",
        sa.Column("service_name", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("service_name"),
    )

    now = datetime.fromisoformat("2026-08-01T09:00:00+08:00")
    op.bulk_insert(
        products,
        [
            {"sku": "NX-MEET-S", "name": "星云会议终端标准版", "list_price": 3999.0, "warranty_years": 2, "created_at": now, "updated_at": now},
            {"sku": "NX-MEET-PRO", "name": "星云会议终端专业版", "list_price": 6999.0, "warranty_years": 3, "created_at": now, "updated_at": now},
            {"sku": "NX-CAM-4K", "name": "星云 4K 智能摄像头", "list_price": 1299.0, "warranty_years": 2, "created_at": now, "updated_at": now},
        ],
    )
    op.bulk_insert(
        departments,
        [
            {"code": "HR", "name": "人力资源部", "contact": "周老师", "hotline": "400-800-1001", "created_at": now, "updated_at": now},
            {"code": "FIN", "name": "财务部", "contact": "李老师", "hotline": "400-800-1002", "created_at": now, "updated_at": now},
            {"code": "IT", "name": "信息技术部", "contact": "陈工", "hotline": "400-800-1003", "created_at": now, "updated_at": now},
        ],
    )
    op.bulk_insert(
        inventory,
        [
            {"sku": "NX-MEET-S", "available": 86, "reserved": 12, "warehouse": "华南仓", "updated_at": now},
            {"sku": "NX-MEET-PRO", "available": 24, "reserved": 6, "warehouse": "华东仓", "updated_at": now},
            {"sku": "NX-CAM-4K", "available": 153, "reserved": 20, "warehouse": "华南仓", "updated_at": now},
        ],
    )
    status_time = datetime.fromisoformat("2026-08-01T09:05:00+08:00")
    op.bulk_insert(
        service_statuses,
        [
            {"service_name": "knowledge-platform", "status": "operational", "latency_ms": 83, "updated_at": status_time},
            {"service_name": "video-conference", "status": "degraded", "latency_ms": 268, "updated_at": status_time},
        ],
    )


def downgrade() -> None:
    op.drop_table("service_statuses")
    op.drop_table("product_inventory")
    op.drop_table("departments")
    op.drop_table("products")
