-- Initial PostgreSQL setup for AI Asset Discovery
-- The application creates schemas and tables dynamically via SQLAlchemy
-- This script runs once when the container is first created

-- Enable useful extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";  -- for text search

-- Ensure public schema exists
CREATE SCHEMA IF NOT EXISTS public;

-- Grant necessary permissions
GRANT ALL ON SCHEMA public TO postgres;
