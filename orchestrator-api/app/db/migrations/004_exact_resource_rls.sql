CREATE OR REPLACE FUNCTION app_security.current_permission_resource_keys()
RETURNS text[]
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public, app_security
AS $$
    SELECT CASE
        WHEN nullif(current_setting('app.permission_resource_keys', true), '') IS NULL THEN ARRAY[]::text[]
        ELSE string_to_array(current_setting('app.permission_resource_keys', true), ',')
    END
$$;

CREATE OR REPLACE FUNCTION app_security.can_read_resource_key(candidate_resource_key text)
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public, app_security
AS $$
    SELECT candidate_resource_key = ANY(app_security.current_permission_resource_keys())
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
            OR app_security.can_read_resource_key(sr.resource_key)
            OR EXISTS (
                SELECT 1
                FROM structured_resource_scope_map sm
                WHERE sm.resource_id = sr.resource_id
                  AND app_security.can_read_scope(sm.permission_scope_key)
            )
          )
    )
$$;

REVOKE ALL ON FUNCTION app_security.current_permission_resource_keys() FROM PUBLIC;
REVOKE ALL ON FUNCTION app_security.can_read_resource_key(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION app_security.can_read_structured_resource(uuid) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION app_security.current_permission_resource_keys() TO restricted_runtime_reader;
GRANT EXECUTE ON FUNCTION app_security.can_read_resource_key(text) TO restricted_runtime_reader;
GRANT EXECUTE ON FUNCTION app_security.can_read_structured_resource(uuid) TO restricted_runtime_reader;
