"""Preserve the original decision when an approval is invalidated."""
from alembic import op
import sqlalchemy as sa
revision = 'b2_approval_outcome'
down_revision = 'a93832257e73'
branch_labels = None
depends_on = None
def upgrade():
    op.add_column('approvals', sa.Column('decision_outcome', sa.String(20), nullable=True))
def downgrade():
    op.drop_column('approvals', 'decision_outcome')
