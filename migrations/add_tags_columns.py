"""Add tags to API keys and tool items

Revision ID: 2a3b4c5d6e7f
Revises: 1a2b3c4d5e6f
Create Date: 2025-10-29 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '2a3b4c5d6e7f'
down_revision = '1a2b3c4d5e6f'  # The previous migration
branch_labels = None
depends_on = None


def upgrade():
    # Add tags column to api_keys table
    op.add_column(
        'api_keys',
        sa.Column('tags', sa.JSON(), nullable=False, server_default='[]')
    )
    
    # Add tags column to tool_items table
    op.add_column(
        'tool_items',
        sa.Column('tags', sa.JSON(), nullable=False, server_default='[]')
    )


def downgrade():
    # Remove tags column from tool_items table
    op.drop_column('tool_items', 'tags')
    
    # Remove tags column from api_keys table
    op.drop_column('api_keys', 'tags')
