# 🤖 Enterprise QA Orchestrator & Agentic Test Suite

Welcome to the **Enterprise QA Orchestrator**, a state-of-the-art, dual-domain framework powered by LangGraph, Computer Vision, AST parsing, and Large Language Models. 

This repository contains two distinct autonomous suites:
1. **UI Automation Suite:** An end-to-end framework that records human UI interactions, injects dynamic stability fallbacks, captures visual intent, and uses an Epistemic QA Agent to verify Virtual DOM (V-DOM) and pixel-level changes.
2. **UI-DB Validation Suite:** A deterministic pipeline that reverses GraphQL payloads into AST-validated PostgreSQL queries via Data-Driven diagnostics and intelligent join mapping.

---

## 📑 Table of Contents
1. [Prerequisites & Setup](#prerequisites--setup)
2. [Project Architecture](#project-architecture)
3. [Dashboard UI Walkthrough](#dashboard-ui-walkthrough)
    * [UI Automation Suite](#ui-automation-suite)
    * [UI-DB Automation Suite](#ui-db-automation-suite)
4. [CLI Execution Guide](#cli-execution-guide)

---

## ⚙️ Prerequisites & Setup

### 1. Install Dependencies
Ensure you have Python installed - Version 3.13.14 and Pip package installer - 26.1.2. Run the following command to install all required libraries:
```bash
pip install streamlit playwright pandas openpyxl opencv-python numpy pyyaml langchain-openai langgraph python-dotenv sqlglot pyperclip Pillow psycopg2-binary
```
Or
```bash
pip install -r requirements.txt
```


### 2. Install Playwright Browsers
```bash
playwright install
```


### 3. Environment Variables (`.env`)
Create a `.env` file in the root directory (`R_CPY`) and populate it with your Azure OpenAI and Database credentials:
```env
# Azure OpenAI Credentials
AZURE_API_KEY=your_api_key_here
AZURE_ENDPOINT=https://your-endpoint.openai.azure.com/
AZURE_API_VERSION=2024-06-01
AZURE_DEPLOYMENT_NAME=gpt-4o

# Database Credentials (For UI-DB Suite)
DB_USER=your_db_user
DB_PASSWORD=your_db_password
DB_HOST=your_db_host
DB_PORT=5432
DB_DATABASE=postgres
DB_SCHEMA=stage_da2_dataset1
```

---

## 🏗️ Project Architecture

```text
agentic-test-suite/
│
├── orchestrator.py                <-- Streamlit Command Center (Main Entry Point)
├── .env                           <-- Credentials
│
├── UI/                            <-- 🖥️ UI Automation Domain
│   ├── Engine/
│   │   ├── start_recording.py     # Captures Playwright flow & URL stamps
│   │   ├── 1_preprocessor.py      # Extracts human assertions & builds YAML KB
│   │   ├── 2_build_mechanical.py  # Compiles AST-safe hardened Pytest runner
│   │   └── vdom_agent_copy2.py    # LangGraph Agent, CV Diff Engine, Excel reporting
│   └── workspaces/                <-- UI Project Sandboxes
│       └── Example_Project/
│
└── UI_DB/                         <-- 🗄️ UI-DB Validation Domain
    ├── engine/
    │   ├── graph_step1.py         # DB Diagnostic & Schema Inference Agent
    │   └── assemble_query.py      # AST-Validated SQL Compiler
    └── workspaces/                <-- UI-DB Project Sandboxes
        └── Example_Project/
```

---

## 🖥️ Dashboard UI Walkthrough

The easiest and most powerful way to use this framework is through the Streamlit Web Dashboard. 

**To launch the dashboard, run:**
```bash
streamlit run orchestrator.py
```
*The dashboard will automatically open in your default web browser.*

### Domain 1: UI Automation Suite
Select **UI Automation Suite** from the domain menu. Create a new workspace (e.g., `Demand_Analysis`) and navigate through the 5 horizontal tabs:

* **Tab 1: Record**
  * Enter a URL and filename, then click "Launch Recorder". 
  * Playwright will open. Authenticate (MFA), start the recorder, and use the injected floating widget to save **Sections** and **Human Assertions**. 
  * *Critical:* Click "Copy" in the Playwright inspector before closing the browser.
* **Tab 2: Preprocess**
  * Select your recorded `raw_*.py` script and click Execute. The engine will extract your URL stamp, map your assertions, and generate a `cleaned_*.py` script and a `workflow_kb.yaml`.
* **Tab 3: Compile**
  * Select your sanitized script and YAML. The compiler will inject a 6-tier autonomous fallback system, CV screenshot anchors, and dynamic locators to generate an `execute_mechanical_*.py` Pytest file.
* **Tab 4: Execute / Regression**
  * Run the mechanical Pytest script. This physically navigates the application, capturing Before, Intent (Crosshair), and After visual DOM states.
* **Tab 5: QA Agent**
  * Run the Epistemic QA Agent. The UI will stream execution logs live.
  * The agent generates OpenCV diffs (red bounding boxes) and evaluates visual state changes against business logic.
  * *Result:* Visual bug cards will appear directly in the UI, and a highly formatted Excel report will be available for download.

### Domain 2: UI-DB Automation Suite
Select **UI-DB Automation Suite** from the domain menu. Create a workspace and navigate through the 3 tabs:

* **Tab 1: Input Payload**
  * Paste your raw GraphQL JSON payload captured from the browser network tab. Assign it a Query Name and click Save.
* **Tab 2: Diagnostic Agent**
  * Select your saved payload. The LangGraph agent interrogates the PostgreSQL database, validates tables, resolves dimension mappings, drops empty fact tables, and generates a data-driven `_state_checkpoint.json`.
* **Tab 3: SQL Assembly Agent**
  * Select the checkpoint. The compiler will safely inject WHERE conditions, dynamic joins, and measure wrappers, verifying the syntax via `sqlglot` AST parsing.
  * *Result:* The final, executable PostgreSQL query is displayed directly on the screen and saved to the workspace.

---

## 💻 CLI Execution Guide

If you prefer to bypass the UI entirely or wish to integrate these steps into a CI/CD pipeline, you can run the scripts natively using Windows CLI commands.

*Note: The scripts are built to consume environment variables. When chaining commands in Windows (`&`), ensure there are **no trailing spaces** before the ampersand.*

### UI Automation CLI Commands

**1. Record a Script**
```cmd
set AUTO_WORKSPACE=UI\workspaces\MyProject& set AUTO_URL=https://stage.bbu.esp.antuit.ai& set AUTO_FILENAME=raw_flow.py& python UI\Engine\start_recording.py
```

**2. Preprocess Data & Build Knowledge Base**
```cmd
set AUTO_WORKSPACE=UI\workspaces\MyProject& set AUTO_SCRIPT=raw_flow.py& python UI\Engine\1_preprocessor.py
```

**3. Compile Mechanical Runner**
```cmd
set AUTO_WORKSPACE=UI\workspaces\MyProject& set AUTO_SCRIPT=cleaned_raw_flow.py& set AUTO_KB=raw_flow_KB.yaml& python UI\Engine\2_build_mechanical.py
```

**4. Execute Pytest Runner**
```cmd
cd UI\workspaces\MyProject
pytest execute_mechanical_raw_flow.py -s --headed
cd ..\..\..
```

**5. Run the Epistemic QA Agent**
```cmd
set AUTO_WORKSPACE=UI\workspaces\MyProject& set AUTO_KB=raw_flow_KB.yaml& python UI\Engine\vdom_agent_copy2.py
```

---

### UI-DB Automation CLI Commands

*(Assuming your `payload.json` is already saved in `UI_DB\workspaces\MyProject`)*

**1. Run Diagnostic Agent**
```cmd
set AUTO_WORKSPACE=UI_DB\workspaces\MyProject& set AUTO_QUERY_NAME=payload& python UI_DB\engine\graph_step1.py
```

**2. Run SQL Assembly Agent**
```cmd
set AUTO_WORKSPACE=UI_DB\workspaces\MyProject& set AUTO_QUERY_NAME=payload& python UI_DB\engine\assemble_query.py
```
`
