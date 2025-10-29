"""Remove machine_id from api_keys table

Revision ID: 1a2b3c4d5e6f
Revises: 
Create Date: 2025-10-29 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '1a2b3c4d5e6f'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Remove the machine_id column from api_keys table
    op.drop_column('api_keys', 'machine_id')


def downgrade():
    # Add back the machine_id column (nullable)
    op.add_column(
        'api_keys',
        sa.Column('machine_id', sa.String(255), nullable=True)
    )
