-- Migration: 04_add_admin_flag_to_users.sql
-- Adds is_admin flag to users table and sets up the first admin user

-- First check if the is_admin column already exists
DO $$
BEGIN
    -- Check if is_admin column already exists in users table
    IF NOT EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_name = 'users' AND column_name = 'is_admin'
    ) THEN
        -- Add the column with default false
        ALTER TABLE users ADD COLUMN is_admin BOOLEAN DEFAULT FALSE;
        
        -- Find the first user and make them an admin
        DECLARE
            first_user_id UUID;
        BEGIN
            -- Get the first user by ID
            SELECT id INTO first_user_id FROM users ORDER BY created_at LIMIT 1;
            
            -- If we found a user, make them an admin
            IF first_user_id IS NOT NULL THEN
                UPDATE users SET is_admin = TRUE WHERE id = first_user_id;
                RAISE NOTICE 'Set user % as the first admin', first_user_id;
            ELSE
                RAISE NOTICE 'No users found to set as admin';
            END IF;
        END;
        
        RAISE NOTICE 'Added is_admin column to users table';
    ELSE
        RAISE NOTICE 'Column is_admin already exists in users table, skipping...';
    END IF;
END
$$;