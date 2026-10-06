import streamlit as st
import os
import glob
import sys
import subprocess
import json
import pandas as pd

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="QA Automation Command Center",
    page_icon=":material/analytics:",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- CORPORATE CSS ---
st.markdown("""
    <style>
    .block-container { padding-top: 2rem; max-width: 95%; }
    h1, h2, h3 { font-family: 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; letter-spacing: -0.5px; }
    .module-header { font-size: 1.5rem; font-weight: 600; margin-bottom: 0.5rem; display: flex; align-items: center; gap: 10px; }
    .module-desc { font-size: 1rem; opacity: 0.7; margin-bottom: 2rem; }
    .stButton>button { border-radius: 4px; height: 2.8rem; font-weight: 600; transition: all 0.2s; }
    .stTabs [data-baseweb="tab-list"] { gap: 8px; }
    .stTabs [data-baseweb="tab"] { padding-top: 10px; padding-bottom: 10px; padding-left: 20px; padding-right: 20px; border-radius: 4px 4px 0 0; }
    .bug-card { background-color: rgba(239, 68, 68, 0.1); border-left: 4px solid #ef4444; padding: 20px; margin-bottom: 20px; border-radius: 4px; }
    </style>
""", unsafe_allow_html=True)

# --- STATE MANAGEMENT ---
if "app_state" not in st.session_state:
    st.session_state.app_state = "DOMAIN_SELECTION"
if "workspace" not in st.session_state:
    st.session_state.workspace = None
if "domain" not in st.session_state:
    st.session_state.domain = "UI"  # Default to UI

# --- HELPER FUNCTIONS ---
def get_base_dir():
    return "UI_DB" if st.session_state.domain == "UI-DB" else "UI"

def get_workspaces():
    base_dir = os.path.join(get_base_dir(), "workspaces")
    if not os.path.exists(base_dir): 
        os.makedirs(base_dir, exist_ok=True)
        return []
    return [d for d in os.listdir(base_dir) if os.path.isdir(os.path.join(base_dir, d))]

def get_files(workspace, pattern):
    if not workspace: return []
    path = os.path.join(get_base_dir(), "workspaces", workspace, pattern)
    files = [os.path.basename(f) for f in glob.glob(path)]
    return sorted(list(set(files)))

def spawn_terminal(script_path, env_vars, is_pytest=False):
    """Spawns a native Windows terminal safely passing env vars without shell string injection."""
    if sys.platform != "win32":
        st.error("Execution is currently optimized for Windows environments.")
        return
    custom_env = os.environ.copy()
    for k, v in env_vars.items():
        if v is not None:
            custom_env[k] = str(v).strip()
    if is_pytest:
        cmd = f'cmd /k "{script_path}"'
    else:
        cmd = f'cmd /k "python {script_path}"'
        
    subprocess.Popen(cmd, env=custom_env, creationflags=subprocess.CREATE_NEW_CONSOLE)
    st.toast("Module execution spawned in terminal.", icon="✅")

# ==========================================
# SCREEN 1: DOMAIN SELECTION
# ==========================================
def render_domain_selection():
    st.title("Enterprise QA Orchestrator")
    st.markdown("<p class='module-desc'>Select the target automation domain to proceed.</p>", unsafe_allow_html=True)
    st.divider()
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        if st.button("UI Automation Suite", icon=":material/desktop_windows:", type="primary", use_container_width=True):
            st.session_state.domain = "UI"
            st.session_state.app_state = "WORKSPACE_SELECTION"
            st.rerun()
            
        st.write("")
        if st.button("UI-DB Automation Suite", icon=":material/database:", type="primary", use_container_width=True):
            st.session_state.domain = "UI-DB"
            st.session_state.app_state = "WORKSPACE_SELECTION"
            st.rerun()

# ==========================================
# SCREEN 2: WORKSPACE SELECTION
# ==========================================
def render_workspace_selection():
    domain_label = "UI-DB" if st.session_state.domain == "UI-DB" else "UI"
    st.title(f"{domain_label} Workspace Configuration")
    st.markdown("<p class='module-desc'>Select an existing project namespace or initialize a new one.</p>", unsafe_allow_html=True)
    st.divider()
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("### :material/folder: Existing Workspaces")
        workspaces = get_workspaces()
        if workspaces:
            selected_ws = st.selectbox("Select Project Namespace", workspaces, label_visibility="collapsed")
            if st.button("Load Workspace", icon=":material/login:", type="primary", use_container_width=True):
                st.session_state.workspace = selected_ws
                st.session_state.app_state = "WORKFLOW"
                st.rerun()
        else:
            st.info("No existing workspaces detected.")
            
        st.write("")
        st.markdown("### :material/create_new_folder: Initialize New Workspace")
        new_ws = st.text_input("Project Namespace", placeholder="e.g., Zebra_Demand_Analysis", label_visibility="collapsed")
        
        if st.button("Create & Continue", icon=":material/add_circle:", use_container_width=True):
            clean_ws = new_ws.strip().replace(" ", "_")
            if clean_ws:
                os.makedirs(os.path.join(get_base_dir(), "workspaces", clean_ws), exist_ok=True)
                st.session_state.workspace = clean_ws
                st.session_state.app_state = "WORKFLOW"
                st.rerun()
            else:
                st.error("Namespace is required.")
                
        st.write("")
        if st.button("Back to Domains", icon=":material/arrow_back:", use_container_width=True):
            st.session_state.app_state = "DOMAIN_SELECTION"
            st.rerun()

# ==========================================
# SCREEN 3A: UI WORKFLOW PIPELINE
# ==========================================
def render_ui_workflow():
    ws = st.session_state.workspace
    
    colA, colB, colC = st.columns([2.5, 1, 1])
    with colA:
        st.title(f"UI Project: {ws}")
        st.markdown("<p class='module-desc'>Select a module below to execute individual scripts or run regression tests.</p>", unsafe_allow_html=True)
    with colB:
        st.write(""); st.write("")
        if st.button("↻ Refresh Files", use_container_width=True): st.rerun()
    with colC:
        st.write(""); st.write("")
        if st.button("Switch Workspace", icon=":material/swap_horiz:", use_container_width=True):
            st.session_state.workspace = None
            st.session_state.app_state = "WORKSPACE_SELECTION"
            st.rerun()

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        ":material/videocam: 1. Record", 
        ":material/cleaning_services: 2. Preprocess", 
        ":material/build: 3. Compile", 
        ":material/play_circle: 4. Execute / Regression", 
        ":material/psychology: 5. QA Agent"
    ])

    # --- TAB 1: RECORD ---
    with tab1:
        st.markdown("<div class='module-header'>Recorder Module</div>", unsafe_allow_html=True)
        st.markdown("<p class='module-desc'>Launch the Inspector to manually navigate the application and capture human assertions.</p>", unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        with c1: rec_url = st.text_input("Target URL (Optional)", placeholder="https://stage.bbu.esp...")
        with c2: rec_filename = st.text_input("Output Script Name", value="raw_codegen.py")
        if st.button("Launch Recorder Environment", icon=":material/videocam:", type="primary"):
            env = {"AUTO_WORKSPACE": os.path.join("UI", "workspaces", ws), "AUTO_URL": rec_url.strip() if rec_url else "", "AUTO_FILENAME": rec_filename.strip().replace(" ", "_") if rec_filename else "raw_codegen.py"}
            spawn_terminal("UI/Engine/start_recording.py", env)

    # --- TAB 2: PREPROCESS ---
    with tab2:
        st.markdown("<div class='module-header'>Data Structuring Module</div>", unsafe_allow_html=True)
        st.markdown("<p class='module-desc'>Parse the raw code to extract human assertions and initialize the Knowledge Base.</p>", unsafe_allow_html=True)
        all_py_files = get_files(ws, "*.py")
        raw_scripts = [f for f in all_py_files if not f.startswith("cleaned_") and not f.startswith("execute_")]
        if raw_scripts:
            selected_raw = st.selectbox("Raw Target Script", raw_scripts)
            if st.button("Execute Preprocessor", icon=":material/cleaning_services:", type="primary"):
                env = {"AUTO_WORKSPACE": os.path.join("UI", "workspaces", ws), "AUTO_SCRIPT": selected_raw}
                spawn_terminal("UI/Engine/1_preprocessor.py", env)
        else:
            st.warning("No raw scripts detected in this workspace.", icon=":material/warning:")

    # --- TAB 3: COMPILE ---
    with tab3:
        st.markdown("<div class='module-header'>Compiler Module</div>", unsafe_allow_html=True)
        st.markdown("<p class='module-desc'>Inject autonomous fallbacks, dynamic locators, and CV screenshot anchors.</p>", unsafe_allow_html=True)
        clean_scripts = get_files(ws, "cleaned_*.py")
        kbs = list(dict.fromkeys(get_files(ws, "*_KB.yaml") + get_files(ws, "workflow_kb.yaml")))
        if clean_scripts and kbs:
            c1, c2 = st.columns(2)
            with c1: selected_clean = st.selectbox("Sanitized Script", clean_scripts)
            with c2: selected_kb_build = st.selectbox("Target Knowledge Base", kbs)
            if st.button("Compile Executable", icon=":material/build:", type="primary"):
                env = {"AUTO_WORKSPACE": os.path.join("UI", "workspaces", ws), "AUTO_SCRIPT": selected_clean, "AUTO_KB": selected_kb_build}
                spawn_terminal("UI/Engine/2_build_mechanical.py", env)
        else: st.warning("Missing required artifacts (Cleaned Scripts or YAML KBs).", icon=":material/warning:")

    # --- TAB 4: EXECUTE / REGRESSION ---
    with tab4:
        st.markdown("<div class='module-header'>Execution & Regression Module</div>", unsafe_allow_html=True)
        st.markdown("<p class='module-desc'>Select an executable to run independently. Ideal for generating new visual diffs.</p>", unsafe_allow_html=True)
        mech_scripts = get_files(ws, "execute_mechanical_*.py")
        if mech_scripts:
            selected_mech = st.selectbox("Target Executable", mech_scripts)
            if st.button("Initiate Execution", icon=":material/play_circle:", type="primary"):
                ws_path = os.path.join("UI", "workspaces", ws).replace("/", "\\")
                cmd = f"cd {ws_path} & pytest {selected_mech} -s --headed"
                spawn_terminal(cmd, {}, is_pytest=True)
        else: st.warning("No compiled executables found in this workspace.", icon=":material/warning:")

    # --- TAB 5: QA AGENT ---
    with tab5:
        st.markdown("<div class='module-header'>Epistemic QA Agent</div>", unsafe_allow_html=True)
        st.markdown("<p class='module-desc'>Trigger LangGraph to evaluate CV diffs and trace the Virtual DOM. <b>Logs stream live.</b></p>", unsafe_allow_html=True)
        kbs_vdom = list(dict.fromkeys(get_files(ws, "*_KB.yaml") + get_files(ws, "workflow_kb.yaml")))
        if kbs_vdom:
            selected_kb_vdom = st.selectbox("Populated Knowledge Base", kbs_vdom)
            if st.button("Initialize Epistemic QA Agent", icon=":material/psychology:", type="primary"):
                st.divider()
                st.markdown("### 📡 Live Execution Logs")
                log_container = st.empty()
                env = os.environ.copy()
                env["AUTO_WORKSPACE"] = os.path.join("UI", "workspaces", ws)
                env["AUTO_KB"] = selected_kb_vdom
                env["AUTO_TRIAGE"] = "true" 
                env["PYTHONIOENCODING"] = "utf-8"
                cmd = [sys.executable, "-u", "UI/Engine/vdom_agent_copy2.py"]
                process = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", bufsize=1)
                
                log_lines = []
                for line in iter(process.stdout.readline, ''):
                    log_lines.append(line)
                    log_container.code("".join(log_lines[-25:]), language="log")
                process.wait()
                
                log_container.empty()
                with st.expander("Show Full Execution Logs", expanded=False):
                    st.code("".join(log_lines), language="log")
                
                st.divider()
                report_dir = os.path.join("UI", "outputs", ws, "Naive_Agent_Reports")
                json_path = os.path.join(report_dir, "latest_run.json")
                if os.path.exists(json_path):
                    with open(json_path, "r", encoding="utf-8") as f:
                        run_data = json.load(f)
                    if run_data.get("total_bugs", 0) > 0:
                        st.error(f"🚨 {run_data['total_bugs']} Bugs Detected During Execution!", icon=":material/gpp_bad:")
                        st.markdown("### Visual Failure Analysis")
                        for bug in run_data["details"]:
                            if bug["Pass/Fail"] == "FAIL":
                                st.markdown(f"<div class='bug-card'>", unsafe_allow_html=True)
                                st.markdown(f"**Test Chunk ID:** `{bug['Test Scenario']}`")
                                st.markdown(f"**Expected:**\n{bug['Expected Result']}")
                                st.markdown(f"**Observed Error:**\n{bug['Observed Result']}")
                                img_cols = st.columns(3)
                                if bug.get("Before Image") and os.path.exists(bug["Before Image"]):
                                    img_cols[0].image(bug["Before Image"], caption="Before Action")
                                if bug.get("Intent Image") and os.path.exists(bug["Intent Image"]):
                                    img_cols[1].image(bug["Intent Image"], caption="Target Element")
                                if bug.get("After Image") and os.path.exists(bug["After Image"]):
                                    img_cols[2].image(bug["After Image"], caption="Resulting Failure State")
                                st.markdown("</div>", unsafe_allow_html=True)
                    else:
                        st.success("✅ No bugs detected! All V-DOM verifications passed.", icon=":material/gpp_good:")
                
                st.divider()
                st.markdown("### 📊 Report Preview & Download")
                if os.path.exists(report_dir):
                    reports = glob.glob(os.path.join(report_dir, "*.xlsx"))
                    if reports:
                        latest_report = max(reports, key=os.path.getctime)
                        try:
                            df = pd.read_excel(latest_report, engine='openpyxl')
                            st.dataframe(df, use_container_width=True)
                            st.markdown("#### 🖼️ Visual Step Preview")
                            if os.path.exists(json_path):
                                with open(json_path, "r", encoding="utf-8") as f:
                                    preview_data = json.load(f)
                                for item in preview_data.get("details", []):
                                    icon = "✅" if item["Pass/Fail"] == "PASS" else "❌"
                                    with st.expander(f"{icon} {item['Test Scenario']} ({item['Pass/Fail']})"):
                                        c1, c2 = st.columns(2)
                                        c1.markdown(f"**Expected:**\n{item['Expected Result']}")
                                        c2.markdown(f"**Observed:**\n{item['Observed Result']}")
                                        img_cols = st.columns(3)
                                        if item.get("Before Image") and os.path.exists(item["Before Image"]):
                                            img_cols[0].image(item["Before Image"], caption="Before Action")
                                        if item.get("Intent Image") and os.path.exists(item["Intent Image"]):
                                            img_cols[1].image(item["Intent Image"], caption="Target Element")
                                        if item.get("After Image") and os.path.exists(item["After Image"]):
                                            img_cols[2].image(item["After Image"], caption="Resulting State")
                        except Exception as e:
                            st.error(f"Failed to load preview: {e}")
                        st.write("")
                        with open(latest_report, "rb") as f:
                            st.download_button("Download Formatted Excel Report", data=f, file_name=os.path.basename(latest_report), mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", icon=":material/download:", type="primary")
        else:
            st.warning("No Knowledge Base found in this workspace.", icon=":material/warning:")


# ==========================================
# SCREEN 3B: UI-DB WORKFLOW PIPELINE
# ==========================================
def render_uidb_workflow():
    ws = st.session_state.workspace
    
    colA, colB, colC = st.columns([2.5, 1, 1])
    with colA:
        st.title(f"UI-DB Project: {ws}")
        st.markdown("<p class='module-desc'>Data Warehouse & GraphQL Validation Pipeline.</p>", unsafe_allow_html=True)
    with colB:
        st.write(""); st.write("")
        if st.button("↻ Refresh Files", use_container_width=True): st.rerun()
    with colC:
        st.write(""); st.write("")
        if st.button("Switch Workspace", icon=":material/swap_horiz:", use_container_width=True):
            st.session_state.workspace = None
            st.session_state.app_state = "WORKSPACE_SELECTION"
            st.rerun()

    tab1, tab2, tab3 = st.tabs([
        ":material/data_object: 1. Input Payload", 
        ":material/troubleshoot: 2. Diagnostic Agent", 
        ":material/terminal: 3. SQL Assembly Agent"
    ])

    # --- TAB 1: INPUT PAYLOAD ---
    with tab1:
        st.markdown("<div class='module-header'>Payload Ingestion</div>", unsafe_allow_html=True)
        st.markdown("<p class='module-desc'>Paste the raw GraphQL payload JSON captured from the application.</p>", unsafe_allow_html=True)
        
        q_name = st.text_input("Query Name", value="payload")
        payload_data = st.text_area("GraphQL JSON", height=300, placeholder='{\n  "operationName": "fetch_weekly_summary",\n  "variables": { ... }\n}')
        
        if st.button("Save Payload", type="primary", icon=":material/save:"):
            if q_name and payload_data:
                try:
                    parsed = json.loads(payload_data)
                    out_path = os.path.join("UI_DB", "workspaces", ws, f"{q_name.strip()}.json")
                    with open(out_path, "w", encoding="utf-8") as f:
                        json.dump(parsed, f, indent=4)
                    st.success(f"✅ Payload saved successfully to {out_path}!")
                except json.JSONDecodeError:
                    st.error("❌ Invalid JSON. Please check the payload format.")
            else:
                st.error("Query Name and Payload are required.")

    # --- TAB 2: DIAGNOSTIC AGENT ---
    with tab2:
        st.markdown("<div class='module-header'>Diagnostic Agent (Step 1)</div>", unsafe_allow_html=True)
        st.markdown("<p class='module-desc'>Identify valid tables, resolve dimensions, and diagnose true join paths directly against the Data Warehouse.</p>", unsafe_allow_html=True)
        
        all_json = get_files(ws, "*.json")
        raw_payloads = [f for f in all_json if not f.endswith("_state_checkpoint.json")]
        
        if raw_payloads:
            sel_payload = st.selectbox("Target Payload", raw_payloads)
            if st.button("Execute Diagnostic Agent", type="primary", icon=":material/troubleshoot:"):
                env = {
                    "AUTO_WORKSPACE": os.path.join("UI_DB", "workspaces", ws),
                    "AUTO_QUERY_NAME": sel_payload.replace(".json", "")
                }
                spawn_terminal("UI_DB/engine/graph_step1.py", env)
        else:
            st.warning("No JSON payloads found. Please save one in Tab 1.", icon=":material/warning:")

    # --- TAB 3: SQL ASSEMBLY AGENT ---
    with tab3:
        st.markdown("<div class='module-header'>SQL Assembly Agent (Step 2)</div>", unsafe_allow_html=True)
        st.markdown("<p class='module-desc'>Translate deterministic diagnostic checkpoints into safely compiled, AST-validated SQL queries.</p>", unsafe_allow_html=True)
        
        checkpoints = get_files(ws, "*_state_checkpoint.json")
        if checkpoints:
            sel_chk = st.selectbox("Target Checkpoint", checkpoints)
            if st.button("Compile Final SQL", type="primary", icon=":material/terminal:"):
                env = {
                    "AUTO_WORKSPACE": os.path.join("UI_DB", "workspaces", ws),
                    "AUTO_QUERY_NAME": sel_chk.replace("_state_checkpoint.json", "")
                }
                spawn_terminal("UI_DB/engine/assemble_query.py", env)
            
            # 🔴 Provide a Live Preview of the SQL if it exists!
            qname = sel_chk.replace("_state_checkpoint.json", "")
            sql_path = os.path.join("UI_DB", "workspaces", ws, f"final_{qname}.sql")
            if os.path.exists(sql_path):
                st.divider()
                st.markdown(f"### 📝 Compiled SQL Preview: `final_{qname}.sql`")
                with open(sql_path, "r", encoding="utf-8") as f:
                    st.code(f.read(), language="sql")
        else:
            st.warning("No state checkpoints found. Please run the Diagnostic Agent in Step 1.", icon=":material/warning:")


# ==========================================
# APP ROUTER
# ==========================================
if st.session_state.app_state == "DOMAIN_SELECTION":
    render_domain_selection()
elif st.session_state.app_state == "WORKSPACE_SELECTION":
    render_workspace_selection()
elif st.session_state.app_state == "WORKFLOW":
    if st.session_state.domain == "UI":
        render_ui_workflow()
    else:
        render_uidb_workflow()
