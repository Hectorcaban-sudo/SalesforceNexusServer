<<<<<<< Updated upstream
"""Baseline placeholder — document store still in use."""
=======
"""Baseline placeholder — app still uses the JSON/SQLite document store.

Revision ID: 001
Revises:
Create Date: 2026-09-27
"""
>>>>>>> Stashed changes
revision = "001"
down_revision = None
branch_labels = None
depends_on = None

<<<<<<< Updated upstream
def upgrade():
    pass

def downgrade():
=======

def upgrade() -> None:
    # When SQL tables replace Tinydb, add CREATE TABLE here and run:
    #   alembic upgrade head
    pass


def downgrade() -> None:
>>>>>>> Stashed changes
    pass
