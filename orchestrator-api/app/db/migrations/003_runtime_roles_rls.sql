DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'restricted_runtime_reader') THEN
        CREATE ROLE restricted_runtime_reader
            NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
    END IF;
END
$$;

GRANT USAGE ON SCHEMA public TO restricted_runtime_reader;
GRANT SELECT ON
    source_catalog,
    catalog_entries,
    document_chunks,
    rag_chunk_embeddings,
    structured_resources,
    structured_resource_columns,
    structured_resource_scope_map,
    approved_join_relationships
TO restricted_runtime_reader;

DO $$
BEGIN
    EXECUTE format('GRANT restricted_runtime_reader TO %I', current_user);
END
$$;

CREATE SCHEMA IF NOT EXISTS app_security;

CREATE OR REPLACE FUNCTION app_security.current_permission_scope_keys()
RETURNS text[]
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public, app_security
AS $$
    SELECT CASE
        WHEN nullif(current_setting('app.permission_scope_keys', true), '') IS NULL THEN ARRAY[]::text[]
        ELSE string_to_array(current_setting('app.permission_scope_keys', true), ',')
    END
$$;

CREATE OR REPLACE FUNCTION app_security.can_read_scope(scope_key text)
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public, app_security
AS $$
    SELECT scope_key = ANY(app_security.current_permission_scope_keys())
$$;

CREATE OR REPLACE FUNCTION app_security.can_read_catalog_entry(candidate_entry_id uuid)
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public, app_security
AS $$
    SELECT EXISTS (
        SELECT 1
        FROM catalog_entries ce
        JOIN source_catalog sc ON sc.source_id = ce.source_id
        WHERE ce.entry_id = candidate_entry_id
          AND ce.is_active
          AND sc.is_active
          AND app_security.can_read_scope(ce.permission_scope_key)
    )
$$;

CREATE OR REPLACE FUNCTION app_security.can_read_document_chunk(candidate_chunk_id uuid)
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public, app_security
AS $$
    SELECT EXISTS (
        SELECT 1
        FROM document_chunks dc
        WHERE dc.chunk_id = candidate_chunk_id
          AND dc.is_active
          AND app_security.can_read_catalog_entry(dc.catalog_entry_id)
          AND app_security.can_read_scope(dc.permission_scope_key)
    )
$$;

CREATE OR REPLACE FUNCTION app_security.can_read_structured_resource(candidate_resource_id uuid)
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public, app_security
AS $$
    SELECT EXISTS (
        SELECT 1
        FROM structured_resources sr
        WHERE sr.resource_id = candidate_resource_id
          AND sr.is_active
          AND (
            app_security.can_read_scope(sr.permission_scope_key)
            OR EXISTS (
                SELECT 1
                FROM structured_resource_scope_map sm
                WHERE sm.resource_id = sr.resource_id
                  AND app_security.can_read_scope(sm.permission_scope_key)
            )
          )
    )
$$;

REVOKE ALL ON ALL FUNCTIONS IN SCHEMA app_security FROM PUBLIC;
GRANT USAGE ON SCHEMA app_security TO restricted_runtime_reader;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA app_security TO restricted_runtime_reader;

ALTER TABLE source_catalog ENABLE ROW LEVEL SECURITY;
ALTER TABLE catalog_entries ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE rag_chunk_embeddings ENABLE ROW LEVEL SECURITY;
ALTER TABLE structured_resources ENABLE ROW LEVEL SECURITY;
ALTER TABLE structured_resource_columns ENABLE ROW LEVEL SECURITY;
ALTER TABLE structured_resource_scope_map ENABLE ROW LEVEL SECURITY;
ALTER TABLE approved_join_relationships ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS source_catalog_scope_read ON source_catalog;
CREATE POLICY source_catalog_scope_read ON source_catalog
    FOR SELECT TO restricted_runtime_reader
    USING (is_active AND app_security.can_read_scope(permission_scope_key));

DROP POLICY IF EXISTS catalog_entries_scope_read ON catalog_entries;
CREATE POLICY catalog_entries_scope_read ON catalog_entries
    FOR SELECT TO restricted_runtime_reader
    USING (app_security.can_read_catalog_entry(entry_id));

DROP POLICY IF EXISTS document_chunks_scope_read ON document_chunks;
CREATE POLICY document_chunks_scope_read ON document_chunks
    FOR SELECT TO restricted_runtime_reader
    USING (app_security.can_read_document_chunk(chunk_id));

DROP POLICY IF EXISTS rag_embeddings_scope_read ON rag_chunk_embeddings;
CREATE POLICY rag_embeddings_scope_read ON rag_chunk_embeddings
    FOR SELECT TO restricted_runtime_reader
    USING (app_security.can_read_document_chunk(chunk_id));

DROP POLICY IF EXISTS structured_resources_scope_read ON structured_resources;
CREATE POLICY structured_resources_scope_read ON structured_resources
    FOR SELECT TO restricted_runtime_reader
    USING (app_security.can_read_structured_resource(resource_id));

DROP POLICY IF EXISTS structured_columns_scope_read ON structured_resource_columns;
CREATE POLICY structured_columns_scope_read ON structured_resource_columns
    FOR SELECT TO restricted_runtime_reader
    USING (app_security.can_read_structured_resource(resource_id));

DROP POLICY IF EXISTS structured_scope_map_read ON structured_resource_scope_map;
CREATE POLICY structured_scope_map_read ON structured_resource_scope_map
    FOR SELECT TO restricted_runtime_reader
    USING (app_security.can_read_structured_resource(resource_id));

DROP POLICY IF EXISTS approved_joins_scope_read ON approved_join_relationships;
CREATE POLICY approved_joins_scope_read ON approved_join_relationships
    FOR SELECT TO restricted_runtime_reader
    USING (
        is_active
        AND validation_status = 'approved'
        AND app_security.can_read_structured_resource(left_resource_id)
        AND app_security.can_read_structured_resource(right_resource_id)
    );
