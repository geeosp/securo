"""add external category to transactions

Revision ID: 031
Revises: 030
Create Date: 2026-04-19
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

revision = "031"
down_revision = "030"
branch_labels = None
depends_on = None


PLUGGY_CATEGORY_TO_SECURO_KEY = {
    "Eating out": "food",
    "Restaurants": "food",
    "Food": "food",
    "Groceries": "groceries",
    "Supermarkets": "groceries",
    "Pharmacy": "health",
    "Health": "health",
    "Taxi and ride-hailing": "transport",
    "Transport": "transport",
    "Gas": "transport",
    "Travel": "transport",
    "Housing": "housing",
    "Rent": "housing",
    "Utilities": "housing",
    "Entertainment": "leisure",
    "Leisure": "leisure",
    "Education": "education",
    "Subscriptions": "subscriptions",
    "Online services": "subscriptions",
    "Transfer": "transfers",
    "Transfers": "transfers",
    "Wire transfers": "transfers",
    "Income": "salary",
    "Salary": "salary",
    "Shopping": "shopping",
    "Taxes": "taxes",
    "Taxes and Fees": "taxes",
    "Personal care": "personal_care",
}


SECURO_CATEGORY_NAMES = {
    "housing": {"Housing", "Moradia"},
    "food": {"Food & Dining", "Alimentação"},
    "transport": {"Transport", "Transporte"},
    "groceries": {"Groceries", "Mercado"},
    "health": {"Health", "Saúde"},
    "leisure": {"Leisure", "Lazer"},
    "subscriptions": {"Subscriptions", "Assinaturas"},
    "education": {"Education", "Educação"},
    "transfers": {"Transfers", "Transferências"},
    "salary": {"Salary & Income", "Salário & Renda"},
    "shopping": {"Shopping", "Compras"},
    "donations": {"Donations", "Doações"},
    "personal_care": {"Personal Care", "Cuidados Pessoais"},
    "taxes": {"Taxes & Fees", "Impostos & Taxas"},
    "other": {"Other", "Outros"},
}


def _category_key_for_external_category(external_category: str | None) -> str | None:
    if not external_category:
        return None
    category_key = PLUGGY_CATEGORY_TO_SECURO_KEY.get(external_category)
    if category_key or " - " not in external_category:
        return category_key
    return PLUGGY_CATEGORY_TO_SECURO_KEY.get(external_category.split(" - ")[0])


def _backfill_category_ids(conn) -> None:
    rows = conn.execute(
        text(
            """
            SELECT id, user_id, external_category
            FROM transactions
            WHERE category_id IS NULL
              AND external_category IS NOT NULL
            """
        )
    ).fetchall()

    for tx_id, user_id, external_category in rows:
        category_key = _category_key_for_external_category(external_category)
        if not category_key:
            continue

        category_names = SECURO_CATEGORY_NAMES.get(category_key)
        if not category_names:
            continue

        category_id = conn.execute(
            text(
                """
                SELECT id
                FROM categories
                WHERE user_id = :user_id
                  AND name IN :category_names
                LIMIT 1
                """
            ).bindparams(sa.bindparam("category_names", expanding=True)),
            {"user_id": user_id, "category_names": list(category_names)},
        ).scalar_one_or_none()
        if not category_id:
            continue

        conn.execute(
            text(
                """
                UPDATE transactions
                SET category_id = :category_id
                WHERE id = :tx_id
                  AND category_id IS NULL
                """
            ),
            {"category_id": category_id, "tx_id": tx_id},
        )


def upgrade() -> None:
    op.add_column(
        "transactions",
        sa.Column("external_category", sa.String(length=255), nullable=True),
    )
    op.create_index(
        "ix_transactions_external_category",
        "transactions",
        ["external_category"],
    )

    conn = op.get_bind()
    if conn.dialect.name == "postgresql":
        conn.execute(
            text(
                """
                UPDATE transactions
                SET external_category = raw_data ->> 'category'
                WHERE external_category IS NULL
                  AND raw_data IS NOT NULL
                  AND raw_data ->> 'category' IS NOT NULL
                """
            )
        )
    elif conn.dialect.name == "sqlite":
        conn.execute(
            text(
                """
                UPDATE transactions
                SET external_category = json_extract(raw_data, '$.category')
                WHERE external_category IS NULL
                  AND raw_data IS NOT NULL
                  AND json_extract(raw_data, '$.category') IS NOT NULL
                """
            )
        )

    _backfill_category_ids(conn)


def downgrade() -> None:
    op.drop_index("ix_transactions_external_category", table_name="transactions")
    op.drop_column("transactions", "external_category")
