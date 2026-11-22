"""Prevent concurrent synthetic evaluation runs."""
from alembic import op
import sqlalchemy as sa
revision = 'd7_eval_single_run'
down_revision = 'c6_ai_evaluations'
branch_labels = None
depends_on = None

def upgrade():
    op.create_index('uq_ai_evaluation_one_running', 'ai_evaluation_runs', ['status'], unique=True,
                    postgresql_where=sa.text("status = 'Running'"), sqlite_where=sa.text("status = 'Running'"))

def downgrade():
    op.drop_index('uq_ai_evaluation_one_running', table_name='ai_evaluation_runs')
