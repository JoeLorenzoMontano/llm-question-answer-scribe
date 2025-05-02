-- Migration: Add MQTT configuration to families table
-- This migration adds MQTT-related configuration columns to the families table 
-- to support MQTT client integration

BEGIN;

-- Check if mqtt_enabled column already exists before adding
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'families' AND column_name = 'mqtt_enabled'
    ) THEN
        ALTER TABLE families ADD COLUMN mqtt_enabled BOOLEAN DEFAULT FALSE;
        ALTER TABLE families ADD COLUMN mqtt_client_id VARCHAR(255);
        ALTER TABLE families ADD COLUMN mqtt_username VARCHAR(255);
        ALTER TABLE families ADD COLUMN mqtt_password VARCHAR(255);
        ALTER TABLE families ADD COLUMN mqtt_topic_prefix VARCHAR(255);
        ALTER TABLE families ADD COLUMN mqtt_allowed_devices JSONB DEFAULT '[]'::jsonb;
        ALTER TABLE families ADD COLUMN mqtt_last_connection TIMESTAMP;
        
        -- Add an index on mqtt_enabled for performance
        CREATE INDEX idx_families_mqtt_enabled ON families(mqtt_enabled);
        
        RAISE NOTICE 'Added MQTT configuration columns to families table';
    ELSE
        RAISE NOTICE 'MQTT configuration columns already exist in families table';
    END IF;
END $$;

COMMIT;