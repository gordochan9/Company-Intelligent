# Architecture — Company Intelligent

This document describes the internal workflow architecture of the Company Intelligent system.

The system is composed of 8 interconnected workflows. Each workflow owns its own boundary. Crossing a boundary is a design violation.

---

## 1. System Overview

How a user question travels from Open WebUI into the backend and back.

```mermaid
flowchart TD
    A[Open WebUI] -->|User submits question| B["company_intelligent\n(tool / pipe)"]
    B -->|"POST /openwebui/ask"| C["Enter main graph\n(orchestrator-api)"]
    C -->|main graph output| D["Return final answer JSON\nto company_intelligent"]
    D --> A
```

---

## 2. Main Graph

The main graph is the central orchestrator. It is **strictly a router** — it does not build SQL context, perform retrieval, or evaluate evidence.

```mermaid
flowchart TD
    A[request_intake] --> B[get_user_permission_schema]
    B -->|"access ok"| C["tool_selection_planner\n\n(This node only receives:\n1. user question\n2. tool_capability_cards)"]
    B -->|"denied / access_failed"| F[final_answer_composer]
    C --> D[tool_dispatch]
    D -.->|selected| E1[rag/sql tool]
    D -.->|future| E2[other tool]
    E1 --> F
    E2 --> F

    B --> G["build state\n[user_permission_schema]"]
```

---

## 3. `get_user_permission_schema`

Resolves who the user is and exactly what data they are permitted to access. The result becomes the single permission source for the entire request — no downstream node re-resolves permissions.

```mermaid
flowchart TD
    A["request_intake\n(receive user identity from Open WebUI)"] --> B["resolve_trusted_identity\n(confirm authenticated company identity)"]
    B --> C[permission_cache_lookup]

    C -->|"if cache found"| D["cache_validation\n- cache key belongs to trusted identity\n- TTL not expired\n- schema_version matches\n- active_dataset_id matches\n- source_catalog_version matches\n- permission_snapshot_hash acceptable"]
    C -->|"if cache not found"| E["resolve_user_groups\nresolve_share_drive_permissions"]

    D -->|"cache valid"| I[emit_permission_schema]
    E --> F["build_allowed_resource_map\n(Convert trusted Share Drive permissions into\ncanonical allowed scopes, source IDs,\nRAG namespaces, structured resources,\nand approved resource boundaries)"]
    F --> G[build_user_permission_schema]
    G --> H[validate_permission_schema]
    H --> J[cache_permission_schema]
    J --> I[emit_permission_schema]
```

---

## 4. `tool_selection_planner`

Uses the LLM to select which backend tool workflow should handle the request. This node **only selects a route** — it does not decide how the tool executes, does not check permissions, and does not build SQL or RAG context.

> **Design note:** In the current demo, only one tool workflow exists (`sql_rag`), so this planner will always route there. However, this subgraph is intentionally designed as a standalone workflow so that adding future tool workflows (e.g., a mailbox agent, a calendar reader, a web retriever) requires **no changes to the main graph** — only a new tool capability card and a new workflow entrypoint. This architecture demonstrates forward compatibility, not just current functionality.

```mermaid
flowchart TD
    A["tool_selection_intake\n(Receive the user question from main graph state)"] --> B[load_tool_capability_cards]
    B --> C["build_tool_selection_prompt\n(Give user question and tool cards to LLM.\nBuild one static, hard-worded LLM prompt.)"]
    C --> D[llm_select_tool_workflow]
    D --> E["parse_tool_selection_output\n(Parse the LLM output into\nthe expected route-level contract.)"]
    E --> F[emit_tool_selection]
```

---

## 5. `rag/sql` Tool Workflow

The main backend AI agent that handles company data questions. It plans how many SQL and RAG steps are needed, executes them deterministically, and bundles the validated results.

```mermaid
flowchart TD
    A[sql_rag_agent] --> B["runtime_obligation_planner\n(LLM involved)"]
    B --> C["multi_step_runtime_executor\n(Validate obligation plan structure.\nCheck all obligation IDs are assigned to steps.\nHand current step to perform_rag_sql.)"]
    C --> D[perform_rag_sql]
    D --> E[normalizer_transformer]
    E -->|"next step ready"| C
    C -->|"when final result ready"| F[final_result_bundle]
    F --> G[adapter]
```

---

## 6. RAG Subgraph

Handles document retrieval steps. Operates only within the permission boundary set by `get_user_permission_schema`. Never writes a final answer directly.

```mermaid
flowchart TD
    FAIL["Any node if failed:\nemit_rag_failure"]

    A[rag_intake] --> B["build_permission_filtered_rag_schema\n(get state from user_permission_schema)"]
    B --> C[read_filtered_rag_schema]
    C --> D[build_rag_search_plan]
    D --> E[select_relevant_documents]
    E --> F[retrieve_relevant_chunks]
    F --> G[validate_rag_evidence]
    G --> H[emit_rag_result]
```

---

## 7. SQL Subgraph

Handles structured data query steps. SQL is generated from a permission-filtered schema, validated by AST parser (SQLGlot), and executed under a restricted database role with Row-Level Security enforced.

```mermaid
flowchart TD
    FAIL["Any node failed:\nemit_sql_failure"]

    A[sql_intake] --> B[build_permission_filtered_sql_schema]
    B --> C[load_approved_join_relationships]
    C --> D[read_filtered_sql_schema]
    D --> E["build_sql_query_intent\n(LLM involved)"]
    E --> F[select_relevant_structured_resources]
    F --> G[generate_candidate_sql]
    G --> H["validate_sql_before_execution\n(AST parser by SQLGlot)\n1. SQL contains selected permission data only\n2. No edit/delete action in SQL\n3. Detect unbound parameter"]
    H -->|"retry 1 time if unbound\nparameter placeholder detected"| G
    H --> I["execute_sql\n(SET TRANSACTION READ ONLY\nSET LOCAL ROLE restricted_runtime_reader\nPostgreSQL RLS enforced)"]
    I --> J[validate_sql_result]
    J --> K[emit_sql_result]
```

---

## 8. `final_answer_composer`

Assembles the final user-facing answer from validated, permission-safe evidence only. The LLM at this stage is bounded — it can only use the validated evidence passed to it; it cannot access raw data, raw SQL, or restricted content.

```mermaid
flowchart TD
    A[final_answer_intake] --> B[read_user_question]
    B --> C[read_final_answer_context_from_adapter]
    C --> D["build_final_answer_llm_payload\n(Build bounded LLM prompt)"]
    D --> E[call_final_answer_llm]
    E --> F[log_final_answer_llm_response]
    F --> G[parse_final_answer_llm_json]
    G --> H[attach_public_citations]
    H --> I[emit_final_answer]
```

---

## Boundary Summary

| Workflow | What it owns | What it must NOT do |
|---|---|---|
| **Main Graph** | Routing, state passing, dispatch | Build SQL context, retrieve data, evaluate evidence |
| **get_user_permission_schema** | Identity resolution, permission map | Allow downstream to re-resolve permissions; downstream must read from state only |
| **tool_selection_planner** | Route-level tool selection — decide which workflow handles the request | Check permission, decide SQL vs RAG, build context, inspect resource lists |
| **rag/sql Tool** | Multi-step obligation planning, child dispatch, result bundling | Re-resolve permission, compose final answer |
| **RAG Subgraph** | Permission-filtered document retrieval | Write final answer, access non-permitted sources |
| **SQL Subgraph** | Permission-filtered SQL generation, validation, execution | Execute without AST validation, bypass RLS |
| **final_answer_composer** | Final answer writing from validated evidence | Access raw data, unvalidated chunks, restricted content |
