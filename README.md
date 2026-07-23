# Company Intelligent — Enterprise AI Operator for RAG & SQL

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)

> **GitHub Topics:** `rag` `sql` `enterprise` `llm` `langgraph` `ai-agent` `permission` `fastapi` `postgresql` `openwebui`

> **A secure, deterministic, and permission-enforced AI backend for enterprise internal data.**  
> Built for business use — where getting the answer wrong is worse than not answering at all.

---

## What Is This?

**Company Intelligent** is a complete AI operator system designed specifically for **enterprise internal use**. It allows employees to ask natural-language questions about company data — structured databases, internal documents, policy files — and receive accurate, auditable, permission-enforced answers.

It is not a chatbot. It is not a personal assistant. It is a governed backend system that sits between your users and your data, enforcing who can see what, at every step of the pipeline.

The system is designed to be deployed on your own infrastructure. For ease of evaluation, the default user interface is [Open WebUI](https://github.com/open-webui/open-webui), but the AI agent backend can be integrated into any platform via its API.

---

## Why Is This Different?

The most important difference between this system and other open-source RAG or SQL agent frameworks is simple:

**Everyone else's RAG and SQL systems are built for personal use. They do not seriously address user permission.**

In most frameworks, the LLM is simply told via a system prompt: *"only show the user data they are allowed to see."* That is not enterprise-grade security. A creative question can bypass it. A hallucination can leak it. A free-form agent loop can expose it.

This system is built from the ground up on the opposite assumption: **the LLM is never trusted with access control decisions.**

---

## 🔐 Selling Point 1 — Multi-Layer Permission Enforcement

Enterprise AI's first concern must always be **who is allowed to see what**. This system enforces that with multiple independent layers, so that no single failure can cause a data leak.

**Layer 1 — Identity Resolution**  
Before any tool is selected or any data is touched, the backend resolves the authenticated user's identity and constructs a `user_permission_schema` — a validated, server-side object mapping exactly which folders and data sources this specific user may access, based on their Share Drive permissions.

**Layer 2 — Permission-Filtered Context Construction**  
When the SQL or RAG workflow runs, it does not operate on the full database or document store. It first narrows the available context to only the sources permitted by `user_permission_schema`. The LLM only ever sees data it is allowed to see.

**Layer 3 — PostgreSQL Row-Level Security (RLS)**  
Even after application-level filtering, the database enforces Row-Level Security. SQL queries are executed under a restricted role (`restricted_runtime_reader`) with `SET TRANSACTION READ ONLY` and per-user RLS policy scopes applied at the database level. This is a second, independent enforcement line — even if application filtering has a bug, the database will not return restricted rows.

**Layer 4 — Output Validation Before Final Answer**  
Before any response reaches the user, the system validates that no restricted source content, raw SQL, internal permission metadata, denied resource data, or unvalidated chunks appear in the public output.

The result: a user who does not have access to a folder or a table cannot extract that information from this system — not through clever prompting, not through edge cases, not through LLM hallucination.

---

## 🎯 Selling Point 2 — Minimising LLM Involvement to Minimise Hallucination

In enterprise business use, an incorrect answer is often more damaging than no answer. This system is designed around one principle: **use deterministic code wherever possible; invoke the LLM only where human language understanding is genuinely required.**

Concretely, the system:

- **Uses hard-coded routing logic** wherever the decision is deterministic. If identity resolution fails, the system routes to deny immediately — no LLM involved.
- **Uses AST-based SQL validation** (via [SQLGlot](https://github.com/tobymao/sqlglot)) to verify that generated SQL is read-only, in-scope, and safe — rather than asking the LLM to judge its own output.
- **Uses exact SQL results for all numeric answers.** Totals, counts, rankings, revenue figures, and percentages must come from SQL — the LLM is explicitly forbidden from performing arithmetic or estimating numbers from document text.
- **Validates all child workflow outputs** before they reach the final answer composer. The composer only receives pre-validated, permission-safe evidence. The LLM at the composition stage is bounded — it can only write based on what the system hands it.

The LLM is used for what it is genuinely good at: understanding natural language, selecting the right workflow, decomposing questions into SQL and RAG obligations, generating candidate SQL from a filtered schema, planning document retrieval, and writing readable final answers from validated evidence. Everything else is code.

---

## 💼 Selling Point 3 — Fully Generic Design & Bring Your Own Data (BYOD)

One of the most important design principles of this system — and one of the hardest to maintain during development — is that **every part of the system is generic**. There is no hardcoded company name, no hardcoded folder path, no hardcoded table structure, no hardcoded user assumption anywhere in the business logic.

Every design decision, every change, every new feature had to be validated against one question: *"Will this work for any company's data, or only for our demo data?"* That constraint forced a much higher standard of architecture throughout the entire codebase.

The result is that swapping in your own company data requires no code changes whatsoever.

### Demo Share Drive Structure

The `demo_share_drive` folder is located in the **root of the project directory** (the same level as `docker-compose.yml` and `README.md`). This path is already pre-configured in `.env.example` as `HOST_SHARE_DRIVE_PATH=./demo_share_drive`.

The included demo uses the following structure — **do not add, delete, or rename any subfolders**:

```
demo_share_drive/
├── Employee Guidelines/     # Policy documents (PDF)
├── File Server/             # Structured business data (CSV, XLSX)
├── Finance/                 # Financial records (XLSX)
└── HR/                      # HR records and employee CVs (XLSX, PDF)
```

### BYOD Procedure

1. **Replace the files** inside each subfolder with your own company data (PDF, DOCX, XLSX, CSV). Keep the subfolder structure intact.
2. **Rebuild the dataset:**
   ```bash
   .\rebuild-dataset.bat
   ```
   The system will automatically parse your files, extract structured data, build the source catalog, infer approved join relationships, and populate the database. No code changes required.
3. **Restart the system:**
   ```bash
   .\start-demo.bat
   ```

The permission schema applies to your data automatically based on the folder structure and user access configuration.

---

## 🧠 Selling Point 4 — Synthesising the Best Ideas from the Field

This system is not built in isolation. It synthesises proven concepts from leading open-source RAG and SQL agent research, and re-implements them inside a permission-enforced, fail-closed enterprise boundary.

**On the RAG side:**
- Ingestion and retrieval are fully separated. Chunks carry source, section, and metadata for precise permission filtering.
- Hybrid retrieval combines semantic and keyword matching. The RAG node returns structured evidence, never a final answer.
- Multi-step mixed reasoning: a single user request can trigger a SQL step to retrieve exact figures, followed by a RAG step to retrieve the policy context explaining those figures — inspired by LlamaIndex's SQL + Vector concept.

**On the SQL side:**
- Schema alone is not enough. SQL generation is informed by a semantic context layer: table profiles, column profiles, approved join policies, and business metric definitions — dramatically reducing hallucinated table and column references. (Inspired by WrenAI and Vanna AI.)
- SQL is validated by AST parsing (SQLGlot), not regex or LLM self-review, catching unsafe operations and out-of-scope relations deterministically.
- SQL generation and SQL execution are strictly separated. The LLM generates a candidate; a deterministic validator approves it; the database executes it under RLS.

The key correction applied throughout: every borrowed concept has been re-implemented inside a permission-enforced, fail-closed boundary. None of the original frameworks were designed for enterprise access control.

---

## 🔌 Selling Point 5 — Deployable as an AI Agent into Any Platform

This is not just an Open WebUI demo. The core orchestrator is a **standalone FastAPI backend** that exposes a clean HTTP endpoint.

- Any platform that can make an HTTP POST request can integrate with it.
- Open WebUI is the default evaluation interface — clone and run, and it works immediately.
- The same agent can be placed behind a Slack bot, a Microsoft Teams integration, an internal web portal, or any enterprise platform.

The Open WebUI tool (`company_intelligent`) is a thin transport layer. The intelligence, the permission enforcement, and the data access all live in the backend — independently of the UI.

---

## 🏗️ Built for Real Deployment — Not Just a Demo

This system is designed to be cloned onto a real company server with minimal adaptation. Every key integration point is explicitly abstracted as a replaceable connection, not hardcoded to the demo environment.

### Data Source Connection

The system includes a dedicated data source adapter layer. The demo version reads from a local `demo_share_drive` folder. For real deployment, replace the adapter connection to point at your company's actual data source — SharePoint, OneDrive, a local file server, a NAS, or any network-mounted storage — and the entire system works without any other code changes.

### User Identity & Permission Connection

The demo resolves user identity directly from the Open WebUI session. For real deployment, replace the identity adapter to connect to your company's existing identity provider — Active Directory, SharePoint, a NAS user directory, or any other authentication source. The permission enforcement logic downstream does not change.

### Tool-Agnostic Final Answer Composition

The `final_answer_composer` is a dedicated node in the **main graph** (not inside any tool workflow) for a deliberate reason: different tool workflows produce different output structures. By placing the composer at the top level, the system can accept validated results from any tool — the RAG/SQL tool today, a mailbox reader tomorrow, a calendar agent the day after — and always convert them into a consistent, readable natural-language response. Adding a new tool does not require touching the answer composition logic.

### Forward-Compatible Tool Routing

The `tool_selection_planner` is a standalone LangGraph subgraph that selects which tool workflow handles each request. In the current demo, only one tool (`sql_rag`) exists, so it always routes there. But the architecture is already prepared: **adding a new tool workflow requires only registering a new tool capability card and implementing the workflow** — the main graph and the planner require no changes.

### The Core Philosophy

Most open-source AI agents are built to make a demo work. This system is built to make a real deployment work. The difference is that every integration point is an explicit, replaceable seam — not a hardcoded assumption. Taking this system from Docker demo to a real company server is a matter of configuration, not reengineering.

---

## Architecture Overview

The system is composed of 8 interconnected workflows. Each workflow owns a strict boundary.

For the full detailed architecture with all internal node flows, see **[ARCHITECTURE.md](./ARCHITECTURE.md)**.

High-level request flow:

```
Open WebUI
    │  POST /openwebui/ask
    ▼
orchestrator-api (FastAPI)
    │
    ├─ request_intake
    ├─ get_user_permission_schema   ← Multi-layer identity + permission enforcement
    ├─ tool_selection_planner       ← LLM selects route-level workflow
    │                                 (designed for multi-tool future expansion)
    ├─ tool_dispatch
    │     └─ sql_rag_agent (rag/sql tool workflow)
    │           ├─ runtime_obligation_planner   ← LLM decomposes request into steps
    │           ├─ multi_step_runtime_executor  ← Deterministic step scheduling
    │           ├─ perform_rag_sql              ← Dispatch to RAG or SQL child
    │           ├─ normalizer_transformer       ← Validate & normalise child output
    │           └─ final_result_bundle          ← Assemble validated evidence
    └─ final_answer_composer   ← LLM writes answer from validated evidence only
```

The main graph is strictly a router. It does not build SQL context, perform retrieval, or evaluate evidence. Every layer has an explicit boundary.

---

## Quickstart

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running.
- An API key for your preferred LLM provider. The system supports **any OpenAI-compatible LLM API** — configure your provider URL, model name, and API key in `.env`.

### First-Time Setup

```bash
# 1. Clone the repository
git clone https://github.com/gordochan9/company-intelligent.git
cd company-intelligent

# 2. Create your .env file from the example
copy .env.example .env

# 3. Open .env and fill in the required values:
#    DEEPSEEK_API_KEY     → Your LLM API key
#    DEEPSEEK_BASE_URL    → Your LLM provider's OpenAI-compatible endpoint
#    LLM_MODEL            → Your model name
#    POSTGRES_PASSWORD    → Any secure local password
#    OPENWEBUI_WEBUI_SECRET_KEY  → Any random secret string
#    OPENWEBUI_SHARED_SECRET     → Any random secret string
#    HOST_SHARE_DRIVE_PATH       → Absolute path to your demo_share_drive folder
#                                  e.g. C:\Users\YourName\company-intelligent\demo_share_drive

# 4. Start the system
.\start-demo.bat
```

On first run, the system will start PostgreSQL, the Orchestrator API, and Open WebUI via Docker Compose, and automatically bootstrap the demo environment.

Open your browser and go to: **http://localhost:8002**

### Demo Accounts

Two accounts are pre-created automatically during first-time setup:

| Account | Email | Password | Group | Share Drive Access |
|---|---|---|---|---|
| Demo Admin | `admin@demo.com` | `admin` | `operations_admin` | ✅ Employee Guidelines / ✅ File Server / ✅ Finance / ✅ HR |
| Demo User | `user@demo.com` | `user` | `standard_employee` | ✅ Employee Guidelines / ✅ File Server / ❌ Finance / ❌ HR |

> 💡 **Testing the permission system:** Log in as `user@demo.com` and ask about salary records, financial figures, or HR data. The system will deny access or return no results — not because the LLM was told to, but because the data is filtered out at the backend before the LLM ever sees it. Then log in as `admin@demo.com` and ask the same question.

### Subsequent Runs

```bash
.\start-demo.bat
```

### To Stop

```bash
.\stop-project-3.0-demo.bat
```

---

## Built With

| Technology | Role |
|---|---|
| [LangGraph](https://github.com/langchain-ai/langgraph) | All graph and subgraph orchestration |
| [FastAPI](https://fastapi.tiangolo.com/) + [Uvicorn](https://www.uvicorn.org/) | Orchestrator API runtime |
| [Open WebUI](https://github.com/open-webui/open-webui) | User interface and AI agent host |
| [PostgreSQL](https://www.postgresql.org/) + [pgvector](https://github.com/pgvector/pgvector) | Runtime database, Row-Level Security, structured data, vector storage, audit log |
| [psycopg](https://www.psycopg.org/) | PostgreSQL driver |
| [SQLGlot](https://github.com/tobymao/sqlglot) | SQL AST parsing and deterministic validation |
| [Pydantic](https://docs.pydantic.dev/) | Schema contracts and validation |
| [pypdf](https://github.com/py-pdf/pypdf) | PDF text extraction |
| [python-docx](https://python-docx.readthedocs.io/) | DOCX document extraction |
| [openpyxl](https://openpyxl.readthedocs.io/) | XLSX structured data import |
| Any OpenAI-compatible LLM API | LLM provider — configurable via `.env` |

---

## Contributing & Forking

This project is highly opinionated by design — the architectural boundaries exist to maintain enterprise-grade security and deterministic behaviour. PRs are welcomed but may not be merged if they risk architectural drift.

You are absolutely encouraged to **fork this repository** and adapt it freely for your own use. That is what the MIT licence is for.

---

## About the Author

Built by **Gordon Chan** — a solo developer, entirely from scratch.

I am currently based in **Toronto** and actively looking for opportunities in **AI engineering, backend development, and enterprise AI implementation**.

This project is my most honest demonstration of what I can design and build end-to-end — not by asking an AI to generate a system, but by understanding the actual production requirements of enterprise security, data governance, and deterministic execution, and building to meet them.

If your company is exploring AI adoption — whether building an internal knowledge assistant, a governed data query system, or a custom AI operator — **I would genuinely welcome an interview opportunity.**

📧 [gordochan9@gmail.com](mailto:gordochan9@gmail.com)  
💼 [LinkedIn — Kwun Tat Gordon Chan](https://www.linkedin.com/in/kwun-tat-gordon-chan-616930244/)

---

## License

Released under the **MIT License**. See [`LICENSE`](./LICENSE) for full details.

You are completely free to use, modify, fork, and deploy this system — including in commercial production environments.
