-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Add embedding column to knowledge_embeddings table if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'knowledge_embeddings'
        AND column_name = 'embedding'
    ) THEN
        ALTER TABLE knowledge_embeddings ADD COLUMN embedding vector(1536);
    END IF;
END $$;

-- Create index for vector similarity search (IVFFlat for better performance)
-- Only create if the table exists and index doesn't exist
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_name = 'knowledge_embeddings'
    ) AND NOT EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE indexname = 'idx_knowledge_embeddings_vector'
    ) THEN
        CREATE INDEX idx_knowledge_embeddings_vector
        ON knowledge_embeddings
        USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 100);
    END IF;
EXCEPTION
    WHEN others THEN
        -- Index creation might fail if not enough rows, that's OK
        RAISE NOTICE 'Could not create IVFFlat index: %. Will use sequential scan.', SQLERRM;
END $$;
