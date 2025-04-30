-- Migration: 02_add_family_id_to_questions.sql
-- Adds family_id column to questions table and associates existing questions with families

-- First check if the family_id column already exists
DO $$
BEGIN
    -- Check if family_id column already exists in questions table
    IF NOT EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_name = 'questions' AND column_name = 'family_id'
    ) THEN
        -- Add the column
        ALTER TABLE questions ADD COLUMN family_id UUID REFERENCES families(id);
        
        -- Create index on family_id
        CREATE INDEX idx_questions_family_id ON questions(family_id);
        
        -- Get the first family as a default
        DECLARE
            default_family_id UUID;
        BEGIN
            -- Try to find a family
            SELECT id INTO default_family_id FROM families LIMIT 1;
            
            -- If no family exists, create one
            IF default_family_id IS NULL THEN
                INSERT INTO families (family_name) VALUES ('Default Family')
                RETURNING id INTO default_family_id;
                RAISE NOTICE 'Created default family: %', default_family_id;
            END IF;
            
            -- Update all questions to use the default family
            UPDATE questions SET family_id = default_family_id WHERE family_id IS NULL;
            RAISE NOTICE 'Updated all questions to use family_id: %', default_family_id;
        END;
    ELSE
        RAISE NOTICE 'Column family_id already exists in questions table, skipping...';
    END IF;
END
$$;