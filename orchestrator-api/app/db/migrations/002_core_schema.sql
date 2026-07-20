CREATE TABLE IF NOT EXISTS permission_scopes (
    scope_key text PRIMARY KEY,
    display_name text NOT NULL,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS app_users (
    user_key text PRIMARY KEY,
    email text NOT NULL UNIQUE,
    display_name text,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS app_groups (
    group_key text PRIMARY KEY,
    display_name text NOT NULL,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS app_user_groups (
    user_key text NOT NULL REFERENCES app_users(user_key) ON DELETE CASCADE,
    group_key text NOT NULL REFERENCES app_groups(group_key) ON DELETE CASCADE,
    PRIMARY KEY (user_key, group_key)
);

CREATE TABLE IF NOT EXISTS source_catalog (
    source_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_type text NOT NULL,
    source_uri text NOT NULL,
    display_name text NOT NULL,
    permission_scope_key text NOT NULL REFERENCES permission_scopes(scope_key),
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS catalog_entries (
    entry_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id uuid NOT NULL REFERENCES source_catalog(source_id) ON DELETE CASCADE,
    entry_type text NOT NULL,
    title text NOT NULL,
    safe_path text,
    permission_scope_key text NOT NULL REFERENCES permission_scopes(scope_key),
    active_dataset_id text,
    source_catalog_version text,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS document_chunks (
    chunk_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    catalog_entry_id uuid NOT NULL REFERENCES catalog_entries(entry_id) ON DELETE CASCADE,
    chunk_index integer NOT NULL,
    chunk_text text NOT NULL,
    citation jsonb NOT NULL DEFAULT '{}'::jsonb,
    permission_scope_key text NOT NULL REFERENCES permission_scopes(scope_key),
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (catalog_entry_id, chunk_index)
);

CREATE TABLE IF NOT EXISTS rag_chunk_embeddings (
    embedding_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    chunk_id uuid NOT NULL UNIQUE REFERENCES document_chunks(chunk_id) ON DELETE CASCADE,
    embedding vector,
    embedding_model text NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS structured_resources (
    resource_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    catalog_entry_id uuid REFERENCES catalog_entries(entry_id) ON DELETE SET NULL,
    resource_key text NOT NULL UNIQUE,
    runtime_relation_name text NOT NULL UNIQUE,
    display_name text NOT NULL,
    permission_scope_key text NOT NULL REFERENCES permission_scopes(scope_key),
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS structured_resource_columns (
    column_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    resource_id uuid NOT NULL REFERENCES structured_resources(resource_id) ON DELETE CASCADE,
    column_name text NOT NULL,
    data_type text NOT NULL,
    safe_description text,
    ordinal_position integer NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    is_active boolean NOT NULL DEFAULT true,
    UNIQUE (resource_id, column_name)
);

CREATE TABLE IF NOT EXISTS structured_resource_scope_map (
    resource_id uuid NOT NULL REFERENCES structured_resources(resource_id) ON DELETE CASCADE,
    permission_scope_key text NOT NULL REFERENCES permission_scopes(scope_key),
    PRIMARY KEY (resource_id, permission_scope_key)
);

CREATE TABLE IF NOT EXISTS approved_join_relationships (
    join_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    left_resource_id uuid NOT NULL REFERENCES structured_resources(resource_id) ON DELETE CASCADE,
    left_column_id uuid NOT NULL REFERENCES structured_resource_columns(column_id) ON DELETE CASCADE,
    right_resource_id uuid NOT NULL REFERENCES structured_resources(resource_id) ON DELETE CASCADE,
    right_column_id uuid NOT NULL REFERENCES structured_resource_columns(column_id) ON DELETE CASCADE,
    join_type text NOT NULL DEFAULT 'inner',
    validation_status text NOT NULL DEFAULT 'approved',
    confidence text NOT NULL,
    validation_source text NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS audit_events (
    event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id text,
    event_type text NOT NULL,
    actor_user_key text,
    status text NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO permission_scopes (scope_key, display_name)
VALUES
    ('employee_guidelines', 'Employee Guidelines'),
    ('file_server', 'File Server'),
    ('finance', 'Finance'),
    ('hr', 'HR')
ON CONFLICT (scope_key) DO NOTHING;
