"""add stable keys to categories

Revision ID: 032
Revises: 031
Create Date: 2026-04-19
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text

revision = "032"
down_revision = "031"
branch_labels = None
depends_on = None


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


def _has_column(conn, table_name: str, column_name: str) -> bool:
    return any(col["name"] == column_name for col in inspect(conn).get_columns(table_name))


def _has_index(conn, table_name: str, index_name: str) -> bool:
    return any(idx["name"] == index_name for idx in inspect(conn).get_indexes(table_name))


def _category_key_for_external_category(external_category: str | None) -> str | None:
    if not external_category:
        return None
    category_key = PLUGGY_CATEGORY_TO_SECURO_KEY.get(external_category)
    if category_key or " - " not in external_category:
        return category_key
    return PLUGGY_CATEGORY_TO_SECURO_KEY.get(external_category.split(" - ")[0])


def _backfill_category_keys(conn) -> None:
    for category_key, names in SECURO_CATEGORY_NAMES.items():
        conn.execute(
            text(
                """
                UPDATE categories
                SET key = :category_key
                WHERE key IS NULL
                  AND name IN :category_names
                """
            ).bindparams(sa.bindparam("category_names", expanding=True)),
            {"category_key": category_key, "category_names": list(names)},
        )


def _backfill_transaction_category_ids(conn) -> None:
    if not _has_column(conn, "transactions", "external_category"):
        return

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

        category_id = conn.execute(
            text(
                """
                SELECT id
                FROM categories
                WHERE user_id = :user_id
                  AND key = :category_key
                LIMIT 1
                """
            ),
            {"user_id": user_id, "category_key": category_key},
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
    conn = op.get_bind()

    if not _has_column(conn, "categories", "key"):
        op.add_column("categories", sa.Column("key", sa.String(length=50), nullable=True))
    if not _has_index(conn, "categories", "ix_categories_key"):
        op.create_index("ix_categories_key", "categories", ["key"])

    _backfill_category_keys(conn)
    _backfill_transaction_category_ids(conn)


def downgrade() -> None:
    conn = op.get_bind()
    if _has_index(conn, "categories", "ix_categories_key"):
        op.drop_index("ix_categories_key", table_name="categories")
    if _has_column(conn, "categories", "key"):
        op.drop_column("categories", "key")
