"""Initial migration - accounts, positions, transactions

Revision ID: 001
Create Date: 2026-01-22
"""
from alembic import op
import sqlalchemy as sa

revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Accounts table
    op.create_table(
        'accounts',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('account_id', sa.String(50), unique=True, index=True, nullable=False),
        sa.Column('broker', sa.String(20), nullable=False, server_default='futu'),
        sa.Column('currency', sa.String(10), nullable=False, server_default='USD'),
        sa.Column('cash', sa.Numeric(18, 4), nullable=False, server_default='0'),
        sa.Column('buying_power', sa.Numeric(18, 4), nullable=False, server_default='0'),
        sa.Column('margin_used', sa.Numeric(18, 4), nullable=False, server_default='0'),
        sa.Column('total_equity', sa.Numeric(18, 4), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('synced_at', sa.DateTime(), nullable=True),
    )

    # Positions table
    op.create_table(
        'positions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('account_id', sa.String(50), sa.ForeignKey('accounts.account_id'), index=True, nullable=False),
        sa.Column('symbol', sa.String(50), index=True, nullable=False),
        sa.Column('asset_type', sa.String(20), nullable=False, server_default='stock'),
        sa.Column('strategy_id', sa.String(50), index=True, nullable=True),
        sa.Column('quantity', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('avg_cost', sa.Numeric(18, 4), nullable=False, server_default='0'),
        sa.Column('current_price', sa.Numeric(18, 4), nullable=False, server_default='0'),
        sa.Column('strike', sa.Numeric(18, 4), nullable=True),
        sa.Column('expiry', sa.Date(), nullable=True),
        sa.Column('put_call', sa.String(10), nullable=True),
        sa.Column('opened_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    # Transactions table
    op.create_table(
        'transactions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('account_id', sa.String(50), sa.ForeignKey('accounts.account_id'), index=True, nullable=False),
        sa.Column('symbol', sa.String(50), index=True, nullable=False),
        sa.Column('action', sa.String(20), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('price', sa.Numeric(18, 4), nullable=False, server_default='0'),
        sa.Column('commission', sa.Numeric(18, 4), nullable=False, server_default='0'),
        sa.Column('realized_pnl', sa.Numeric(18, 4), nullable=False, server_default='0'),
        sa.Column('strategy_id', sa.String(50), index=True, nullable=True),
        sa.Column('order_id', sa.String(50), index=True, nullable=True),
        sa.Column('broker_order_id', sa.String(50), nullable=True),
        sa.Column('executed_at', sa.DateTime(), index=True, nullable=False, server_default=sa.func.now()),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table('transactions')
    op.drop_table('positions')
    op.drop_table('accounts')
