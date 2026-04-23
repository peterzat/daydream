-- 005_skills_description: add `description` column to the skills table.
--
-- v1 data-skill author files declare a REQUIRED `description` field
-- (validated in daydream.admin._skill_validate). The value surfaces to
-- the LLM interpreter as candidate-list context (see
-- daydream/llm/prompts.py: `- {s.name}: {s.description}`), so the
-- author's intent is lost on the interpreter path if we don't persist
-- it. This migration adds the column; the CLI INSERT + data-skill
-- loader are updated to write/read it alongside this migration.
--
-- Nullable so the migration is a no-op on existing rows. Loader code
-- falls back to a generic "A data skill: <name>." string when NULL or
-- empty, preserving prior behavior for pre-existing rows until the
-- operator re-runs `bin/game world skill add <file>` to populate it.

ALTER TABLE skills ADD COLUMN description TEXT;
