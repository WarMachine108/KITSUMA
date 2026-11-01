-- Fresh schema. Apply with python load.py db-init; existing prototype DBs are refused.
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE TABLE IF NOT EXISTS kitsuma_schema (version INTEGER PRIMARY KEY);
INSERT INTO kitsuma_schema VALUES (1) ON CONFLICT DO NOTHING;
CREATE TABLE IF NOT EXISTS users (login TEXT PRIMARY KEY, password TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_login TEXT NOT NULL REFERENCES users ON DELETE CASCADE,
    expires_at TIMESTAMPTZ NOT NULL DEFAULT now() + interval '14 days'
);
CREATE TABLE IF NOT EXISTS container (
    container_no SERIAL PRIMARY KEY,
    container_name TEXT NOT NULL UNIQUE,
    login TEXT NOT NULL REFERENCES users
);
CREATE TABLE IF NOT EXISTS folders (
    container_no INTEGER NOT NULL REFERENCES container ON DELETE CASCADE,
    folder_path TEXT NOT NULL,
    PRIMARY KEY (container_no, folder_path)
);
CREATE TABLE IF NOT EXISTS folder_hierarchy (
    container_no INTEGER NOT NULL,
    folder_path TEXT NOT NULL,
    user_login TEXT NOT NULL REFERENCES users,
    rank INTEGER NOT NULL CHECK (rank > 0),
    PRIMARY KEY (container_no, folder_path, user_login),
    UNIQUE (container_no, folder_path, rank),
    FOREIGN KEY (container_no, folder_path) REFERENCES folders ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS folder_heads (
    container_no INTEGER NOT NULL,
    folder_path TEXT NOT NULL,
    user_login TEXT NOT NULL,
    PRIMARY KEY (container_no, folder_path),
    FOREIGN KEY (container_no, folder_path, user_login) REFERENCES folder_hierarchy ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS file (
    fileno SERIAL PRIMARY KEY,
    container_no INTEGER NOT NULL REFERENCES container ON DELETE CASCADE,
    filename TEXT NOT NULL,
    folder_path TEXT,
    file_content TEXT NOT NULL DEFAULT '',
    revision INTEGER NOT NULL DEFAULT 0,
    UNIQUE (container_no, filename),
    FOREIGN KEY (container_no, folder_path) REFERENCES folders
);
CREATE TABLE IF NOT EXISTS pushes (
    push_id SERIAL PRIMARY KEY,
    fileno INTEGER NOT NULL REFERENCES file ON DELETE CASCADE,
    base_revision INTEGER NOT NULL,
    base_content TEXT NOT NULL,
    file_content TEXT NOT NULL,
    message TEXT NOT NULL,
    user_login TEXT NOT NULL REFERENCES users,
    reviewer TEXT NOT NULL REFERENCES users,
    merged BOOLEAN NOT NULL DEFAULT false,
    merged_by TEXT REFERENCES users,
    merged_at TIMESTAMPTZ,
    pushed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS one_pending_push_per_author_file
    ON pushes(fileno,user_login) WHERE merged=false;
CREATE TABLE IF NOT EXISTS push_reviews (
    review_id SERIAL PRIMARY KEY,
    push_id INTEGER NOT NULL REFERENCES pushes ON DELETE CASCADE,
    user_login TEXT NOT NULL REFERENCES users,
    reviewed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS revisions (
    fileno INTEGER NOT NULL REFERENCES file ON DELETE CASCADE,
    revision INTEGER NOT NULL,
    file_content TEXT NOT NULL,
    push_id INTEGER REFERENCES pushes,
    merged_by TEXT NOT NULL REFERENCES users,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (fileno,revision)
);

-- The CLI connects as the database owner. Do not expose these custom accounts
-- or session records through Supabase's public Data API (no API policies needed).
DO $$
DECLARE table_name TEXT;
BEGIN
    FOREACH table_name IN ARRAY ARRAY['kitsuma_schema','users','sessions','container',
        'folders','folder_hierarchy','folder_heads','file','pushes','push_reviews','revisions']
    LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', table_name);
    END LOOP;
END $$;
