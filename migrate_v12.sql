-- v12: Add bench_rows column to halls table for per-hall row configuration
ALTER TABLE halls ADD COLUMN bench_rows INTEGER NOT NULL DEFAULT 5;
