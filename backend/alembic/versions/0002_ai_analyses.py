"""Persist advisory AI analyses and human review."""
from alembic import op
import sqlalchemy as sa
revision = '0002_ai_analyses'
down_revision = '0001_initial'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('ai_analyses',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('request_id', sa.Integer, sa.ForeignKey('requests.id', ondelete='CASCADE'), nullable=True),
        sa.Column('initiated_by_user_id', sa.Integer, sa.ForeignKey('users.id'), nullable=False),
        sa.Column('source_hash', sa.String(64), nullable=False),
        sa.Column('model_name', sa.String(100), nullable=False),
        sa.Column('model_identifier', sa.String(150), nullable=True),
        sa.Column('analysis_status', sa.String(30), nullable=False),
        sa.Column('structured_result', sa.JSON, nullable=False),
        sa.Column('validation_flags', sa.JSON, nullable=False),
        sa.Column('accepted_fields', sa.JSON, nullable=True),
        sa.Column('submitted_changes', sa.JSON, nullable=True),
        sa.Column('review_decision', sa.String(30), nullable=True),
        sa.Column('input_tokens', sa.Integer, nullable=True),
        sa.Column('output_tokens', sa.Integer, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True))
    op.create_index('ix_ai_analyses_request_id', 'ai_analyses', ['request_id'])
    op.create_index('ix_ai_analyses_initiated_by_user_id', 'ai_analyses', ['initiated_by_user_id'])
def downgrade():
    op.drop_table('ai_analyses')
