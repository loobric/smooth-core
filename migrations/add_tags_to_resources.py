"""Add tags to resources.

Revision ID: 1234567890ab
Revises: 1234567890aa
Create Date: 2025-10-29 17:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '1234567890ab'
down_revision: Union[str, None] = '1234567890aa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add tags column to tool_assemblies
    op.add_column('tool_assemblies', 
                 sa.Column('tags', 
                          postgresql.JSON(astext_type=sa.Text()), 
                          server_default='[]', 
                          nullable=False))
    
    # Add tags column to tool_instances
    op.add_column('tool_instances', 
                 sa.Column('tags', 
                          postgresql.JSON(astext_type=sa.Text()), 
                          server_default='[]', 
                          nullable=False))
    
    # Add tags column to tool_presets
    op.add_column('tool_presets', 
                 sa.Column('tags', 
                          postgresql.JSON(astext_type=sa.Text()), 
                          server_default='[]', 
                          nullable=False))
    
    # Add tags column to tool_sets
    op.add_column('tool_sets', 
                 sa.Column('tags', 
                          postgresql.JSON(astext_type=sa.Text()), 
                          server_default='[]', 
                          nullable=False))


def downgrade() -> None:
    op.drop_column('tool_assemblies', 'tags')
    op.drop_column('tool_instances', 'tags')
    op.drop_column('tool_presets', 'tags')
    op.drop_column('tool_sets', 'tags')
