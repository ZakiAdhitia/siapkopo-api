"""drop resident family_card tables and pending applicant columns

Revision ID: 8525569b8e65
Revises: 96a5250bbc9b
Create Date: 2026-08-05 16:32:36.566144

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8525569b8e65'
down_revision: Union[str, Sequence[str], None] = '96a5250bbc9b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Second half of the "remove Resident/FamilyCard" change -- order matters:
    drop every FK pointing INTO residents/family_cards (submissions,
    users) before dropping the tables themselves (Postgres default is
    RESTRICT, no ondelete set anywhere on these).
    """
    op.drop_constraint(op.f('submissions_applicant_resident_id_fkey'), 'submissions', type_='foreignkey')
    op.drop_constraint(op.f('submissions_pending_applicant_rt_id_fkey'), 'submissions', type_='foreignkey')
    op.drop_column('submissions', 'applicant_resident_id')
    op.drop_column('submissions', 'pending_applicant_nik')
    op.drop_column('submissions', 'pending_applicant_nama')
    op.drop_column('submissions', 'pending_applicant_alamat')
    op.drop_column('submissions', 'pending_applicant_no_kk')
    op.drop_column('submissions', 'pending_applicant_rt_id')
    op.drop_column('submissions', 'pending_applicant_jk')
    op.drop_column('submissions', 'pending_applicant_tempat_lahir')
    op.drop_column('submissions', 'pending_applicant_tanggal_lahir')
    op.drop_column('submissions', 'pending_applicant_pekerjaan')
    op.drop_column('submissions', 'pending_applicant_status_kawin')

    op.drop_constraint(op.f('users_resident_id_fkey'), 'users', type_='foreignkey')
    op.drop_column('users', 'resident_id')

    op.drop_index(op.f('ix_residents_family_card_id'), table_name='residents')
    op.drop_index(op.f('ix_residents_full_name'), table_name='residents')
    op.drop_index(op.f('ix_residents_nik'), table_name='residents')
    op.drop_table('residents')

    op.drop_index(op.f('ix_family_cards_kk_number'), table_name='family_cards')
    op.drop_table('family_cards')


def downgrade() -> None:
    """Downgrade schema."""
    op.create_table(
        'family_cards',
        sa.Column('kk_number', sa.VARCHAR(length=20), autoincrement=False, nullable=False),
        sa.Column('address', sa.VARCHAR(length=255), autoincrement=False, nullable=True),
        sa.Column('head_resident_id', sa.UUID(), autoincrement=False, nullable=True),
        sa.Column('id', sa.UUID(), autoincrement=False, nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False),
        sa.Column('deleted_at', sa.TIMESTAMP(timezone=True), autoincrement=False, nullable=True),
        sa.PrimaryKeyConstraint('id', name=op.f('family_cards_pkey')),
    )
    op.create_index(op.f('ix_family_cards_kk_number'), 'family_cards', ['kk_number'], unique=True)

    op.create_table(
        'residents',
        sa.Column('nik', sa.VARCHAR(length=20), autoincrement=False, nullable=False),
        sa.Column('full_name', sa.VARCHAR(length=150), autoincrement=False, nullable=False),
        sa.Column('family_card_id', sa.UUID(), autoincrement=False, nullable=True),
        sa.Column('rt_id', sa.UUID(), autoincrement=False, nullable=True),
        sa.Column('gender', sa.VARCHAR(length=1), autoincrement=False, nullable=True),
        sa.Column('birth_place', sa.VARCHAR(length=100), autoincrement=False, nullable=True),
        sa.Column('birth_date', sa.DATE(), autoincrement=False, nullable=True),
        sa.Column('occupation', sa.VARCHAR(length=100), autoincrement=False, nullable=True),
        sa.Column('phone', sa.VARCHAR(length=20), autoincrement=False, nullable=True),
        sa.Column('address', sa.VARCHAR(length=255), autoincrement=False, nullable=True),
        sa.Column('id', sa.UUID(), autoincrement=False, nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False),
        sa.Column('deleted_at', sa.TIMESTAMP(timezone=True), autoincrement=False, nullable=True),
        sa.Column('marital_status', sa.VARCHAR(length=30), autoincrement=False, nullable=True),
        sa.ForeignKeyConstraint(['family_card_id'], ['family_cards.id'], name=op.f('residents_family_card_id_fkey')),
        sa.ForeignKeyConstraint(['rt_id'], ['rt.id'], name=op.f('residents_rt_id_fkey')),
        sa.PrimaryKeyConstraint('id', name=op.f('residents_pkey')),
    )
    op.create_index(op.f('ix_residents_nik'), 'residents', ['nik'], unique=True)
    op.create_index(op.f('ix_residents_full_name'), 'residents', ['full_name'], unique=False)
    op.create_index(op.f('ix_residents_family_card_id'), 'residents', ['family_card_id'], unique=False)

    op.add_column('users', sa.Column('resident_id', sa.UUID(), autoincrement=False, nullable=True))
    op.create_foreign_key(op.f('users_resident_id_fkey'), 'users', 'residents', ['resident_id'], ['id'])

    op.add_column('submissions', sa.Column('pending_applicant_status_kawin', sa.VARCHAR(length=30), autoincrement=False, nullable=True))
    op.add_column('submissions', sa.Column('pending_applicant_pekerjaan', sa.VARCHAR(length=100), autoincrement=False, nullable=True))
    op.add_column('submissions', sa.Column('pending_applicant_tanggal_lahir', sa.DATE(), autoincrement=False, nullable=True))
    op.add_column('submissions', sa.Column('pending_applicant_tempat_lahir', sa.VARCHAR(length=100), autoincrement=False, nullable=True))
    op.add_column('submissions', sa.Column('pending_applicant_jk', sa.VARCHAR(length=20), autoincrement=False, nullable=True))
    op.add_column('submissions', sa.Column('pending_applicant_rt_id', sa.UUID(), autoincrement=False, nullable=True))
    op.add_column('submissions', sa.Column('pending_applicant_no_kk', sa.VARCHAR(length=20), autoincrement=False, nullable=True))
    op.add_column('submissions', sa.Column('pending_applicant_alamat', sa.VARCHAR(length=255), autoincrement=False, nullable=True))
    op.add_column('submissions', sa.Column('pending_applicant_nama', sa.VARCHAR(length=150), autoincrement=False, nullable=True))
    op.add_column('submissions', sa.Column('pending_applicant_nik', sa.VARCHAR(length=20), autoincrement=False, nullable=True))
    op.add_column('submissions', sa.Column('applicant_resident_id', sa.UUID(), autoincrement=False, nullable=True))
    op.create_foreign_key(op.f('submissions_pending_applicant_rt_id_fkey'), 'submissions', 'rt', ['pending_applicant_rt_id'], ['id'])
    op.create_foreign_key(op.f('submissions_applicant_resident_id_fkey'), 'submissions', 'residents', ['applicant_resident_id'], ['id'])
