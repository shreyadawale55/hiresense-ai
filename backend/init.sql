-- HireSense AI — PostgreSQL Initialization
-- Extensions for full-text search and UUID generation

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";    -- fuzzy search on resume text
CREATE EXTENSION IF NOT EXISTS "btree_gin";  -- GIN index support

-- Helpful comment
COMMENT ON DATABASE hiresense_db IS 'HireSense AI Resume Screening Database — SDG 8 Aligned';
