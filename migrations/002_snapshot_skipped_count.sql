-- Migration: Add skipped_count column to config_snapshots table
-- This column tracks devices that were skipped during a snapshot (disabled, no credentials, etc.)

-- Add skipped_count column with default value of 0
ALTER TABLE config_snapshots
ADD COLUMN IF NOT EXISTS skipped_count INTEGER DEFAULT 0;

-- Update existing records to have 0 for skipped_count if null
UPDATE config_snapshots SET skipped_count = 0 WHERE skipped_count IS NULL;
