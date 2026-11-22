"""Persist synthetic AI evaluation runs separately from escalation evaluations."""
from alembic import op
import sqlalchemy as sa

revision = 'c6_ai_evaluations'
down_revision = '58cb482b691f'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('ai_evaluation_runs',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('dataset_version', sa.String(80), nullable=False),
        sa.Column('model_name', sa.String(150), nullable=False),
        sa.Column('prompt_version', sa.String(80), nullable=False),
        sa.Column('created_by_user_id', sa.Integer, sa.ForeignKey('users.id'), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('configuration', sa.JSON, nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True)))
    op.create_table('ai_evaluation_results',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('run_id', sa.Integer, sa.ForeignKey('ai_evaluation_runs.id', ondelete='CASCADE'), nullable=False),
        sa.Column('case_id', sa.String(80), nullable=False),
        sa.Column('expected', sa.JSON, nullable=False),
        sa.Column('actual', sa.JSON),
        sa.Column('error_category', sa.String(50)),
        sa.Column('latency_ms', sa.Integer, nullable=False),
        sa.Column('input_tokens', sa.Integer),
        sa.Column('output_tokens', sa.Integer),
        sa.UniqueConstraint('run_id', 'case_id', name='uq_ai_evaluation_case'))
    op.create_index('ix_ai_evaluation_results_run_id', 'ai_evaluation_results', ['run_id'])

def downgrade():
    op.drop_index('ix_ai_evaluation_results_run_id', table_name='ai_evaluation_results')
    op.drop_table('ai_evaluation_results')
    op.drop_table('ai_evaluation_runs')
