"""Initial request-management schema."""
from alembic import op
import sqlalchemy as sa
revision = '0001_initial'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('departments', sa.Column('id',sa.Integer,primary_key=True),sa.Column('name',sa.String(100),nullable=False,unique=True))
    op.create_table('users',sa.Column('id',sa.Integer,primary_key=True),sa.Column('name',sa.String(100),nullable=False),sa.Column('email',sa.String(255),nullable=False,unique=True),sa.Column('department_id',sa.Integer,sa.ForeignKey('departments.id'),nullable=False),sa.Column('role',sa.String(40),nullable=False),sa.Column('active',sa.Boolean,nullable=False),sa.CheckConstraint("role IN ('Employee','Department Agent','Department Manager','Finance Approver','Operations Admin')",name='ck_user_role'))
    op.create_index('ix_users_department_id','users',['department_id'])
    op.create_table('requests',sa.Column('id',sa.Integer,primary_key=True),sa.Column('human_readable_id',sa.String(30)),sa.Column('title',sa.String(200),nullable=False),sa.Column('description',sa.Text,nullable=False),sa.Column('request_type',sa.String(40),nullable=False),sa.Column('priority',sa.String(20),nullable=False),sa.Column('status',sa.String(30),nullable=False),sa.Column('requester_id',sa.Integer,sa.ForeignKey('users.id'),nullable=False),sa.Column('assigned_department_id',sa.Integer,sa.ForeignKey('departments.id')),sa.Column('assigned_user_id',sa.Integer,sa.ForeignKey('users.id')),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False),sa.Column('resolved_at',sa.DateTime(timezone=True)),sa.CheckConstraint("request_type IN ('IT Incident','Purchase Request','Cross-Department Project')",name='ck_request_type'),sa.CheckConstraint("priority IN ('Low','Normal','High','Critical')",name='ck_priority'),sa.CheckConstraint("status IN ('Submitted','Needs Information','Triaged','In Progress','Resolved','Closed','Cancelled')",name='ck_status'))
    for name in ('human_readable_id','request_type','priority','status','requester_id','assigned_department_id','assigned_user_id','created_at'):
        op.create_index('ix_requests_'+name,'requests',[name],unique=name=='human_readable_id')
    op.create_table('request_events',sa.Column('id',sa.Integer,primary_key=True),sa.Column('request_id',sa.Integer,sa.ForeignKey('requests.id',ondelete='CASCADE'),nullable=False),sa.Column('actor_id',sa.Integer,sa.ForeignKey('users.id')),sa.Column('event_type',sa.String(50),nullable=False),sa.Column('previous_value',sa.Text),sa.Column('new_value',sa.Text),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
    op.create_index('ix_request_events_request_id','request_events',['request_id'])
    op.create_index('ix_request_events_created_at','request_events',['created_at'])
def downgrade():
    op.drop_table('request_events'); op.drop_table('requests'); op.drop_table('users'); op.drop_table('departments')
