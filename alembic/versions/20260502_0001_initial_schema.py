"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-05-02

Creates the full Cloud SQL config schema. Mirrors services/models.py exactly.
All tables InnoDB / utf8mb4 / utf8mb4_0900_ai_ci. CHAR(36) UUID primary IDs,
audit columns on every table, snake_case names, FK cascades per the migration
plan at /root/.claude/plans/i-want-to-get-partitioned-coral.md.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.mysql import JSON


revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TABLE_OPTS = {
    "mysql_engine": "InnoDB",
    "mysql_charset": "utf8mb4",
    "mysql_collate": "utf8mb4_0900_ai_ci",
}


def _audit_cols() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at", sa.DateTime, nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at", sa.DateTime, nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
            server_onupdate=sa.text("CURRENT_TIMESTAMP"),
        ),
    ]


def upgrade() -> None:
    # ── instances ────────────────────────────────────────────────
    op.create_table(
        "instances",
        sa.Column("instance_id", sa.CHAR(36), primary_key=True),
        sa.Column("instance_name", sa.String(255), nullable=False),
        sa.Column("primary_contact_name", sa.String(255)),
        sa.Column("primary_contact_email", sa.String(255)),
        sa.Column("primary_contact_uid", sa.String(128)),
        sa.Column("google_ads_customer_id", sa.String(32)),
        sa.Column("invoca_profile_id", sa.String(32)),
        *_audit_cols(),
        **_TABLE_OPTS,
    )

    # ── clinics ──────────────────────────────────────────────────
    op.create_table(
        "clinics",
        sa.Column("clinic_id", sa.CHAR(36), primary_key=True),
        sa.Column(
            "instance_id", sa.CHAR(36),
            sa.ForeignKey("instances.instance_id", ondelete="RESTRICT"),
            nullable=False, index=True,
        ),
        sa.Column("clinic_name", sa.String(255), nullable=False),
        sa.Column("address", sa.String(512)),
        sa.Column("place_id", sa.String(255)),
        sa.Column("gbp_location_id", sa.String(64)),
        sa.Column(
            "pms_type",
            sa.Enum("blueprint", "audit_data", "none", name="pms_type_enum"),
            nullable=False, server_default="none",
        ),
        sa.Column("etl_enabled", sa.Boolean, nullable=False, server_default=sa.text("0")),
        sa.Column("country", sa.CHAR(2)),
        sa.Column("deleted_at", sa.DateTime),
        *_audit_cols(),
        **_TABLE_OPTS,
    )

    # ── clinic_location_details (1:1) ────────────────────────────
    op.create_table(
        "clinic_location_details",
        sa.Column(
            "clinic_id", sa.CHAR(36),
            sa.ForeignKey("clinics.clinic_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("hours_monday", sa.String(64)),
        sa.Column("hours_tuesday", sa.String(64)),
        sa.Column("hours_wednesday", sa.String(64)),
        sa.Column("hours_thursday", sa.String(64)),
        sa.Column("hours_friday", sa.String(64)),
        sa.Column("hours_saturday", sa.String(64)),
        sa.Column("hours_sunday", sa.String(64)),
        sa.Column("about_us", sa.Text),
        sa.Column("email", sa.String(255)),
        sa.Column("phone", sa.String(32)),
        sa.Column("time_zone", sa.String(64)),
        *_audit_cols(),
        **_TABLE_OPTS,
    )

    # ── clinic_voice_agent_configuration (1:1) ───────────────────
    op.create_table(
        "clinic_voice_agent_configuration",
        sa.Column(
            "clinic_id", sa.CHAR(36),
            sa.ForeignKey("clinics.clinic_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "voice_agent_status",
            sa.Enum("inactive", "provisioning", "active", "error",
                    name="voice_agent_status_enum"),
            nullable=False, server_default="inactive",
        ),
        sa.Column("twilio_phone_number", sa.String(32)),
        sa.Column("twilio_phone_sid", sa.String(64)),
        sa.Column(
            "twilio_verified_caller_id", sa.Boolean,
            nullable=False, server_default=sa.text("0"),
        ),
        sa.Column("vapi_assistant_id", sa.String(64)),
        sa.Column("vapi_phone_number_id", sa.String(64)),
        *_audit_cols(),
        **_TABLE_OPTS,
    )

    # ── clinic_blueprint_config (1:1) ────────────────────────────
    op.create_table(
        "clinic_blueprint_config",
        sa.Column(
            "clinic_id", sa.CHAR(36),
            sa.ForeignKey("clinics.clinic_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("clinic_code", sa.String(64)),
        sa.Column("api_url", sa.String(512)),
        sa.Column("aws_url", sa.String(512)),
        *_audit_cols(),
        **_TABLE_OPTS,
    )

    # ── voice_agent_capabilities (composite PK) ──────────────────
    op.create_table(
        "voice_agent_capabilities",
        sa.Column(
            "clinic_id", sa.CHAR(36),
            sa.ForeignKey("clinics.clinic_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("capability_id", sa.String(64), primary_key=True),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.text("0")),
        sa.Column("config", JSON),
        sa.Column("updated_by", sa.String(255)),
        *_audit_cols(),
        **_TABLE_OPTS,
    )

    # ── google_ads_campaigns ─────────────────────────────────────
    op.create_table(
        "google_ads_campaigns",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "clinic_id", sa.CHAR(36),
            sa.ForeignKey("clinics.clinic_id", ondelete="CASCADE"),
            nullable=False, index=True,
        ),
        sa.Column("google_ads_campaign_id", sa.String(32), nullable=False),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.text("1")),
        *_audit_cols(),
        sa.UniqueConstraint("clinic_id", "google_ads_campaign_id",
                            name="uq_clinic_gads_campaign"),
        **_TABLE_OPTS,
    )

    # ── invoca_campaigns ─────────────────────────────────────────
    op.create_table(
        "invoca_campaigns",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "clinic_id", sa.CHAR(36),
            sa.ForeignKey("clinics.clinic_id", ondelete="CASCADE"),
            nullable=False, index=True,
        ),
        sa.Column("invoca_campaign_id", sa.String(32), nullable=False),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.text("1")),
        *_audit_cols(),
        sa.UniqueConstraint("clinic_id", "invoca_campaign_id",
                            name="uq_clinic_invoca_campaign"),
        **_TABLE_OPTS,
    )

    # ── clinic_admins ────────────────────────────────────────────
    op.create_table(
        "clinic_admins",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("uid", sa.String(128), nullable=False, index=True),
        sa.Column(
            "instance_id", sa.CHAR(36),
            sa.ForeignKey("instances.instance_id", ondelete="CASCADE"),
            nullable=False, index=True,
        ),
        *_audit_cols(),
        sa.UniqueConstraint("uid", "instance_id", name="uq_uid_instance"),
        **_TABLE_OPTS,
    )


def downgrade() -> None:
    # Reverse order to respect FKs.
    op.drop_table("clinic_admins")
    op.drop_table("invoca_campaigns")
    op.drop_table("google_ads_campaigns")
    op.drop_table("voice_agent_capabilities")
    op.drop_table("clinic_blueprint_config")
    op.drop_table("clinic_voice_agent_configuration")
    op.drop_table("clinic_location_details")
    op.drop_table("clinics")
    op.drop_table("instances")
