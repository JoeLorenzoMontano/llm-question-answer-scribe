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
        
        -- Create default family for each existing user
        CREATE TEMPORARY TABLE temp_families AS
        SELECT id, username FROM users WHERE family_id IS NULL;

        -- For each user, create a family and update the user
        DO $$
        DECLARE
            user_rec RECORD;
            new_family_id UUID;
        BEGIN
            FOR user_rec IN SELECT id, username FROM temp_families LOOP
                -- Create a new family for this user
                INSERT INTO families (family_name) 
                VALUES (user_rec.username || '''s Family')
                RETURNING id INTO new_family_id;
                
                -- Update the user with the new family_id
                UPDATE users SET family_id = new_family_id WHERE id = user_rec.id;
                
                RAISE NOTICE 'Created family % for user %', new_family_id, user_rec.id;
            END LOOP;
        END$$;
        
        -- Drop temporary table
        DROP TABLE temp_families;
    ELSE
        RAISE NOTICE 'Column family_id already exists in users table, skipping...';
    END IF;
END
$$;