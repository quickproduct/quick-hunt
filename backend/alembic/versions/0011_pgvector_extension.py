"""Enable pgvector extension and add native vector column to embeddings table

Revision ID: 0011
Revises: 0010
Create Date: 2026-04-01 00:00:00.000000

Adds native vector similarity search to the embeddings table:
  - Installs the pgvector PostgreSQL extension (ships with pgvector/pgvector:pg16)
  - Adds embedding_vector vector(768) column (768 dims = nomic-embed-text default)
  - Creates an HNSW index with cosine distance ops for fast ANN search
  - Drops the Python cosine-similarity workaround in PgVectorAdapter.query()

Dimension note:
  nomic-embed-text (Ollama default) → 768 dims
  text-embedding-ada-002 (OpenAI)   → 1536 dims
  If you switch embedding models, create a new migration to drop/re-add the column.
"""
from alembic import op
from sqlalchemy import text

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

# Vector dimension — must match the embedding model configured in settings.
# nomic-embed-text (default Ollama model) produces 768-dimensional vectors.
_VECTOR_DIM = 768


def upgrade() -> None:
    # Enable pgvector extension (ships with pgvector/pgvector:pg16 image)
    op.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

    # Add native vector column — nullable so existing rows without embeddings
    # are unaffected; populated on next embedding generation run.
    op.execute(text(
        f"ALTER TABLE embeddings ADD COLUMN IF NOT EXISTS "
        f"embedding_vector vector({_VECTOR_DIM})"
    ))

    # HNSW index with cosine distance ops.
    # HNSW is better than IVFFlat for small-to-medium datasets:
    #   - No minimum row count requirement (IVFFlat needs > lists rows)
    #   - Faster query performance at low row counts
    #   - m=16, ef_construction=64 are reasonable defaults
    op.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_embeddings_vector_hnsw "
        "ON embeddings USING hnsw (embedding_vector vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    ))


def downgrade() -> None:
    op.execute(text("DROP INDEX IF EXISTS ix_embeddings_vector_hnsw"))
    op.execute(text("ALTER TABLE embeddings DROP COLUMN IF EXISTS embedding_vector"))
    # Note: we intentionally do NOT drop the vector extension on downgrade
    # as other tables/columns might depend on it.
