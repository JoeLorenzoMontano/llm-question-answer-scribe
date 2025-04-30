-- Migration: 03_add_user_id_to_answers.sql
-- Adds user_id column to answers table to track which user provided each answer

-- First check if the user_id column already exists
DO $$
BEGIN
    -- Check if user_id column already exists in answers table
    IF NOT EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_name = 'answers' AND column_name = 'user_id'
    ) THEN
        -- Add the column
        ALTER TABLE answers ADD COLUMN user_id UUID REFERENCES users(id);
        
        -- Create index on user_id
        CREATE INDEX idx_answers_user_id ON answers(user_id);
        
        RAISE NOTICE 'Added user_id column to answers table. Existing answers will have NULL user_id.';
    ELSE
        RAISE NOTICE 'Column user_id already exists in answers table, skipping...';
    END IF;
END
$$;