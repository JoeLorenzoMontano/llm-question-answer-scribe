-- Migration: 01_add_family_id_to_users.sql
-- Adds family_id column to users and creates default families for existing users

-- First check if the family_id column already exists
DO $$
BEGIN
    -- Check if family_id column already exists in users table
    IF NOT EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_name = 'users' AND column_name = 'family_id'
    ) THEN
        -- Add the column
        ALTER TABLE users ADD COLUMN family_id UUID REFERENCES families(id);
        
        -- Create index on family_id
        CREATE INDEX idx_users_family_id ON users(family_id);
        
        -- Create a single default family
        DECLARE
            default_family_id UUID;
        BEGIN
            -- Create default family
            INSERT INTO families (family_name) 
            VALUES ('Default Family')
            RETURNING id INTO default_family_id;
            
            -- Update all users to use this family
            UPDATE users SET family_id = default_family_id WHERE family_id IS NULL;
            
            RAISE NOTICE 'Created default family % for all users', default_family_id;
        END;
    ELSE
        RAISE NOTICE 'Column family_id already exists in users table, skipping...';
    END IF;
END
$$;