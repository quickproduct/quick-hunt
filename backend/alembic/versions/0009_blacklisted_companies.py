"""Create blacklisted_companies table and seed initial list.

Revision ID: 0009
Revises: 0008
Create Date: 2026-03-29
"""
import uuid
from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

SENTINEL_TENANT_ID = "00000000-0000-0000-0000-000000000001"

# Initial blacklist — companies to never scrape or email
_SEED_COMPANIES = [
    # Health (Internet Brands / WebMD group)
    ("WebMD", "Health content network — not hiring for PHP roles"),
    ("Medscape", "Health content network — not hiring for PHP roles"),
    ("MedicineNet", "Health content network — not hiring for PHP roles"),
    # Legal (Internet Brands / legal group)
    ("Avvo", "Legal directory platform"),
    ("Nolo", "Legal self-help publisher"),
    ("Martindale-Hubbell", "Lawyer directory"),
    ("Lawyers.com", "Lawyer directory"),
    ("FindLaw", "Legal content network"),
    # Automotive
    ("CarsDirect", "Automotive marketplace"),
    ("F150Online", "Automotive forum"),
    # Travel & Lifestyle
    ("Fodors Travel", "Travel content publisher"),
    ("FlyerTalk", "Travel forum"),
    # Home / Community / Lifestyle
    ("ApartmentRatings", "Apartment review platform"),
    ("Weddingbee", "Wedding community platform"),
    ("ModelMayhem", "Modeling industry network"),
    # Deals / Finance
    ("Bens Bargains", "Deals aggregator"),
    ("Loan.com", "Finance content site"),
    ("UltimateCoupons", "Coupon aggregator"),
    # SaaS / B2B
    ("Henry Schein One", "Dental SaaS — not a fit"),
    ("PulsePoint", "Ad-tech platform"),
    # Logistics / Fintech / Misc India
    ("iThink Logistics", "Logistics SaaS"),
    ("Pay1", "Fintech platform"),
    ("Qtech Software", "IT services company"),
    ("Impact Guru", "Crowdfunding platform"),
    ("BDM Infotech", "IT outsourcing company"),
]


def upgrade() -> None:
    op.create_table(
        "blacklisted_companies",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("reason", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "name", name="uq_blacklist_tenant_name"),
    )
    op.create_index("ix_blacklisted_companies_tenant_id", "blacklisted_companies", ["tenant_id"])

    # Seed the initial company list for the default (sentinel) tenant
    blacklist_table = sa.table(
        "blacklisted_companies",
        sa.column("id", sa.String),
        sa.column("tenant_id", sa.String),
        sa.column("name", sa.String),
        sa.column("reason", sa.String),
    )
    op.bulk_insert(
        blacklist_table,
        [
            {
                "id": str(uuid.uuid4()),
                "tenant_id": SENTINEL_TENANT_ID,
                "name": name,
                "reason": reason,
            }
            for name, reason in _SEED_COMPANIES
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_blacklisted_companies_tenant_id", table_name="blacklisted_companies")
    op.drop_table("blacklisted_companies")
