# Mera Hisaab — Google ADK Shopkeeper Assistant Agent

An intelligent, multi-tenant AI assistant powered by **Google ADK (Agent Development Kit)** and **Gemini 2.5 Flash** that enables shopkeepers to interact with their **Mera Hisaab** store in natural language (Hindi, Hinglish, English) with full CRUD capabilities.

---

## Architecture & Core Principles

```
  ┌────────────────────────────────────────────────────────┐
  │                 Shopkeeper / User                      │
  │     (Hindi / Hinglish / English Natural Language)      │
  └───────────────────────────┬────────────────────────────┘
                              │
                              ▼
  ┌────────────────────────────────────────────────────────┐
  │           Mera Hisaab ADK Agent Runtime                │
  │           (mera_hisaab_agent/ — Isolated)              │
  │                                                        │
  │  • mh_agent.config      (Validated environment config) │
  │  • mh_agent.context     (Multi-tenant & user security) │
  │  • mh_agent.callbacks   (Rule F confirmation guardrail)│
  │  • mh_agent.tools       (19 Read & Write Tools)        │
  │  • mh_agent.repository  (Strictly tenant-scoped reads) │
  │  • mh_agent.actions     (Service-only write dispatch)  │
  └───────────────────────────┬────────────────────────────┘
                              │ Service Calls Only
                              │ (NO direct DB writes)
                              ▼
  ┌────────────────────────────────────────────────────────┐
  │         Shared Django Service Layer (services.py)       │
  │  • sales.services.create_sale                          │
  │  • sales.services.void_sale                            │
  │  • customers.services.record_charge / record_payment   │
  │  • customers.services.create_customer / update...      │
  │  • products.services.create_product / update...        │
  │  • inventory.services.record_transaction               │
  └───────────────────────────┬────────────────────────────┘
                              │ Atomic Transactions & Row Locks
                              ▼
  ┌────────────────────────────────────────────────────────┐
  │          PostgreSQL / SQLite Database                  │
  └────────────────────────────────────────────────────────┘
```

1. **Strict Decoupling**: The agent resides in a completely separate folder (`mera_hisaab_agent/`) with its own virtual environment (`mera_hisaab_agent/venv`). The Django project operates 100% independently whether the agent exists or not.
2. **Single Authoritative Service Layer**: The agent **never** writes directly to the database (no `.save()`, `.create()`, `.update()`, `.delete()`, raw SQL). All data changes flow through the exact same `services.py` layer that the web app uses.
3. **Multi-Tenant Scoping**: All database reads and writes are strictly scoped to the tenant business (`.for_business(business)`) derived from `BUSINESS_ID`.
4. **Real Actor Permissions**: Every action runs as a verified user (`AGENT_ACTOR_USER_ID`) with active `BusinessMembership` capabilities checked (`can_access_pos`, `can_manage_inventory`, `can_manage_customers`, `can_view_reports`).
5. **Two-Step Confirmation on Writes (Rule Set F)**: Every mutating tool requires `confirm: bool = False`. If unconfirmed, the agent provides a human-readable summary. A `before_tool_callback` guardrail blocks any unconfirmed write execution.

---

## Directory Structure

```
mera_hisaab_agent/
├── mh_agent/
│   ├── __init__.py         # Exports root_agent
│   ├── agent.py            # root_agent = Agent(...) definition
│   ├── config.py           # Validated environment loader (Zero hardcoding)
│   ├── django_setup.py     # Standalone Django bootstrap (Lazy import)
│   ├── context.py          # Tenant & actor resolution + permission checks
│   ├── repository.py       # Read-only queries (Tenant-scoped)
│   ├── actions.py          # Service-only write operations
│   ├── tools.py            # 19 ADK Tool functions (confirm: bool pattern)
│   └── callbacks.py        # before_tool_callback confirmation guardrail
├── test_agent.py           # Comprehensive E2E test suite
├── .env.example            # Sample configuration template
├── .gitignore              # Ignores .env and venv
├── requirements.txt        # google-adk, python-dotenv
└── README.md
```

---

## Configuration (`.env`)

Create `mera_hisaab_agent/.env`:

```env
# Google Gemini API key (Required)
GOOGLE_API_KEY=your_gemini_api_key_here

# Gemini Model (Default: gemini-2.5-flash)
GEMINI_MODEL=gemini-2.5-flash

# Path to the Django project root directory (Required)
MERA_HISAAB_PATH=c:/Users/Kanishak/Desktop/mera_hisaab

# Django settings module (Default: config.settings.dev)
DJANGO_SETTINGS_MODULE=config.settings.dev

# Shop / Business ID to scope queries and writes (Required)
BUSINESS_ID=3

# Actor User ID in the business (Required)
AGENT_ACTOR_USER_ID=7
```

---

## Running the Agent

### 1. Run the Automated E2E Test Suite
Verifies all 6 layers (Config, Setup, Context, Read Tools, Guardrails, Confirmed Writes, Soft-deletes, Void Sale):

```powershell
.\mera_hisaab_agent\venv\Scripts\python.exe mera_hisaab_agent\test_agent.py
```

### 2. Start the ADK Web UI
Launch the interactive web interface:

```powershell
.\mera_hisaab_agent\venv\Scripts\python.exe -m google.adk.cli web mera_hisaab_agent
```
Then open `http://127.0.0.1:8000` in your browser.

### 3. Run via ADK CLI Interactive Terminal

```powershell
.\mera_hisaab_agent\venv\Scripts\python.exe -m google.adk.cli run mera_hisaab_agent
```

---

## Example Natural Language Interactions

### Read Queries (No confirmation needed)

- **Sales Summary:**
  > **Shopkeeper:** *"Aaj ki bikri ka summary batao"*
  > **Agent:** Calls `get_sales_summary_tool(period='today')` and responds with total revenue, cash received, and credit created in ₹.

- **Low Stock Alerts:**
  > **Shopkeeper:** *"Kaunsa maal khatam hone wala hai?"*
  > **Agent:** Calls `list_low_stock_products_tool()` and highlights products below minimum stock level.

- **Udhaar Khata Inspection:**
  > **Shopkeeper:** *"Ramesh Verma ka kitna udhaar baki hai?"*
  > **Agent:** Calls `get_customer_detail_tool()` and displays their pending balance along with a 1-click WhatsApp payment reminder link.

---

### Write Operations (Two-step confirmation required)

- **Recording Udhaar Payment (Jama):**
  > **Shopkeeper:** *"Ramesh Verma ne 500 rupaye cash diye hain, jama kar do"*
  > **Agent:** *"Aap Ramesh Verma ke account mein ₹500 cash jama karne ke liye keh rahe hain. Kya main isko record kar doon?"*
  > **Shopkeeper:** *"Haan kar do"*
  > **Agent:** Calls `record_customer_payment_tool(confirm=True)`: *"Theek hai, Ramesh Verma ke account mein ₹500 cash jama ho gaye hain. Ab unka naya balance ₹3315.40 hai."*

- **POS Sale (Bikri):**
  > **Shopkeeper:** *"Sunita Sharma ko 2 packet Amul Butter becha, 50 rupaye cash mila baki udhaar"*
  > **Agent:** Summarizes total bill, cash received, and remaining credit, then asks for confirmation before recording.

- **Adding a New Product:**
  > **Shopkeeper:** *"Naya item add karo: Good Day Biscuit, selling price 20, purchase price 15, opening stock 40 pack"*
  > **Agent:** Summarizes details and records product with opening stock ledger entry only after approval.

- **Voiding a Bill (Radd):**
  > **Shopkeeper:** *"Bill SGS--2026-000005 cancel kar do"*
  > **Agent:** Summarizes that voiding will reverse inventory to stock, refund cash payments, and reverse customer udhaar atomically, requesting confirmation before proceeding.

