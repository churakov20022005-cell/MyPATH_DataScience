-- Additive and idempotent: existing records stay unassigned until their owner chooses a section.
ALTER TABLE materials ADD COLUMN IF NOT EXISTS section varchar(20) NOT NULL DEFAULT ''
    CHECK (section IN ('', 'yandex', 'books', 'tasks'));
CREATE INDEX IF NOT EXISTS materials_branch_section_updated_idx
    ON materials (branch, section, updated_at DESC, id DESC);
