# Database Migrations

This directory contains database migrations for the LLM Question Answer Scribe application.

## How It Works

- Migrations are SQL files named with a numeric prefix (e.g., `01_add_family_id.sql`)
- The migration system keeps track of applied migrations in a `migrations` table
- The application runs pending migrations automatically on startup
- Migrations are applied in numerical order

## Running Migrations Manually

You can run migrations manually using the migrate.py script:

```bash
# Run all pending migrations
python migrations/migrate.py

# Check for pending migrations without applying them
python migrations/migrate.py --check
```

## Creating New Migrations

To create a new migration:

1. Create a new SQL file in the migrations directory
2. Name it with the next number in sequence, followed by a descriptive name (e.g., `04_add_new_feature.sql`)
3. Write your SQL statements in the file

Best practices for migrations:

- Each migration should be idempotent (can be run multiple times without errors)
- Use checks to prevent errors (e.g., check if a column exists before adding it)
- Keep migrations small and focused on a specific change
- Use transactions to ensure atomicity
- Add comments to explain the purpose of the migration

## Current Migrations

1. `01_add_family_id_to_users.sql` - Adds family_id to users table
2. `02_add_family_id_to_questions.sql` - Adds family_id to questions table
3. `03_add_user_id_to_answers.sql` - Adds user_id to answers table