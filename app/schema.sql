CREATE TABLE IF NOT EXISTS materials (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    branch varchar(10) NOT NULL CHECK (branch IN ('sql', 'python', 'ml')),
    kind varchar(10) NOT NULL CHECK (kind IN ('note', 'question')),
    title varchar(180) NOT NULL CHECK (length(trim(title)) > 0),
    content text NOT NULL CHECK (length(trim(content)) BETWEEN 1 AND 100000),
    answer text NOT NULL DEFAULT '' CHECK (length(answer) <= 100000),
    seed_key text UNIQUE,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS materials_branch_kind_updated_idx
    ON materials (branch, kind, updated_at DESC, id DESC);
