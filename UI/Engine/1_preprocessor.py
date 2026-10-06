import os
import re
import yaml

def main():
    print("\n" + "="*70)
    print("🧹 PREPROCESSOR & KNOWLEDGE BASE BUILDER")
    print("="*70)
    
    # 🔴 SILENTLY CONSUME UI ENVIRONMENT VARIABLES
    workspace = os.getenv("AUTO_WORKSPACE")
    if workspace is None:
        workspace = input("Enter Workspace Directory (e.g. workspaces/Zebra/)\n(Press [ENTER] for current dir):\n> ").strip()
        
    if workspace and not os.path.exists(workspace):
        os.makedirs(workspace, exist_ok=True)
        print(f"📁 Created workspace: {workspace}")

    input_file = os.getenv("AUTO_SCRIPT")
    if not input_file:
        default_input = "raw_codegen.py"
        input_file = input(f"Enter the raw script to clean\n(Press [ENTER] for default: {default_input}):\n> ").strip() or default_input
        
    if not input_file.endswith(".py"): 
        input_file += ".py"
        
    input_path = os.path.join(workspace, input_file) if workspace else input_file
    
    if not os.path.exists(input_path):
        print(f"\n❌ Error: '{input_path}' not found.")
        return

    with open(input_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    # 🔴 AUTO-GENERATE KB AND SCRIPT NAMES
    base_name = os.path.basename(input_path).replace(".py", "")
    core_name = base_name[4:] if base_name.startswith("raw_") else base_name
    
    output_py_path = os.path.join(workspace, f"cleaned_{core_name}.py") if workspace else f"cleaned_{core_name}.py"
    output_yaml_path = os.path.join(workspace, f"{core_name}_KB.yaml") if workspace else f"{core_name}_KB.yaml"
    
    print(f"\n🔍 Processing '{input_path}'...")
    print(f"   -> Targeting Output: {output_py_path}")
    print(f"   -> Targeting KB: {output_yaml_path}")
    
    clean_code = []
    
    yaml_data = {
        "workflow_meta": {
            "name": f"{core_name} UI Workflow",
            "status": "PENDING_DISCOVERY"
        },
        "global_context": {
            "page_description": "To be populated by AI Scholar...",
            "known_quirks": ""
        },
        "sections": []
    }
    
    current_section = None
    section_counter = 0
    step_counter = 1
    last_step_ref = None
    
    fill_pattern = re.compile(r'\.fill\((["\'])(.*?)\1\)')
    action_pattern = re.compile(r'\.(click|fill|press|check|uncheck|hover|dblclick)\(')
    
    # 🔴 READ URL STAMP OR EXTRACT FROM CODE
    extracted_url = "https://stage.bbu.esp.antuit.ai/dp/demand-planning/executive-dashboard?workbookId=4&tabIndex=1"
    for l in lines:
        if "# RECORDED_URL:" in l:
            extracted_url = l.split("# RECORDED_URL:")[1].strip()
            break
        elif "page.goto(" in l:
            match = re.search(r'page\.goto\((["\'])(.*?)\1', l)
            if match:
                extracted_url = match.group(2)
                break

    for line in lines:
        stripped_line = line.strip()
        
        # Skip the URL stamp from being injected multiple times in the code
        if stripped_line.startswith("# RECORDED_URL:"):
            continue
            
        # ---------------------------------------------------------------------
        # INJECT MFA BLOCK
        # ---------------------------------------------------------------------
        if "def test_example(" in stripped_line:
            clean_code.append(line)
            clean_code.append('    # --- MFA & Login Wait Block ---\n')
            clean_code.append(f'    try: page.goto("{extracted_url}", timeout=0)\n    except: pass\n')
            clean_code.append('    print("\\n" + "="*60)\n')
            clean_code.append('    input("ACTION REQUIRED: Log in, pass MFA, then PRESS [ENTER]...\\n")\n')
            clean_code.append('    print("="*60 + "\\n")\n\n')
            continue
            
        # ---------------------------------------------------------------------
        # WIDGET DETECTION
        # ---------------------------------------------------------------------
        if "e.g. Global Filters" in stripped_line or "Add Section" in stripped_line:
            if ".fill(" in stripped_line:
                match = fill_pattern.search(stripped_line)
                if match:
                    section_name = match.group(2)
                    section_counter += 1
                    step_counter = 1 
                    
                    clean_code.append(f"\n    # {'='*60}\n")
                    clean_code.append(f"    # SECTION: {section_name}\n")
                    clean_code.append(f"    # {'='*60}\n")
                    
                    current_section = {
                        "section_name": section_name,
                        "section_goal": "",
                        "section_verification": {
                            "ai_understanding": "",
                            "human_assertions": []
                        },
                        "steps": []
                    }
                    yaml_data["sections"].append(current_section)
                    print(f"  📂 Created Section: '{section_name}'")
            continue 
            
        if "e.g. Grid has no 0 values" in stripped_line or "Save Assertion" in stripped_line:
            if ".fill(" in stripped_line:
                match = fill_pattern.search(stripped_line)
                if match:
                    assertion_text = match.group(2)
                    if last_step_ref is not None:
                        if 'human_assertions' not in last_step_ref:
                            last_step_ref['human_assertions'] = []
                        last_step_ref['human_assertions'].append(assertion_text)
                        print(f"    🧠 Attached Assertion to Step {last_step_ref['step_id']}: '{assertion_text[:40]}...'")
                    else:
                        print("    ⚠️ Warning: Assertion found before any action was taken. Ignored.")
            continue 
            
        # ---------------------------------------------------------------------
        # MECHANICAL CODE
        # ---------------------------------------------------------------------
        clean_code.append(line)
        if "page." in stripped_line and action_pattern.search(stripped_line):
            
            if current_section is None:
                section_counter += 1
                current_section = {
                    "section_name": "Default Initialization",
                    "section_goal": "",
                    "section_verification": {"ai_understanding": "", "human_assertions": []},
                    "steps": []
                }
                yaml_data["sections"].append(current_section)
                clean_code.insert(-1, f"\n    # {'='*60}\n    # SECTION: Default Initialization\n    # {'='*60}\n")
                print("  📂 Created Section: 'Default Initialization' (Auto-detected)")
            
            action_match = action_pattern.search(stripped_line)
            action_type = action_match.group(1)
            step_id = f"{section_counter}_{step_counter}"
            
            step_data = {
                "step_id": step_id,
                "raw_code": stripped_line,
                "action": action_type,
                "execution_mode": "FAST_PASS", 
                "milestone_classification": "UNCLASSIFIED",
                "ai_understanding": "",
                "baseline_images": {
                    "before": f"baselines/step_{step_id}_before.png",
                    "intent": f"baselines/step_{step_id}_intent.png",
                    "after": f"baselines/step_{step_id}_after.png"
                }
            }
            current_section["steps"].append(step_data)
            
            last_step_ref = step_data 
            step_counter += 1
            
    with open(output_py_path, "w", encoding="utf-8") as f:
        f.writelines(clean_code)
        
    with open(output_yaml_path, "w", encoding="utf-8") as f:
        yaml.dump(yaml_data, f, default_flow_style=False, sort_keys=False)
        
    print("\n✅ Pre-Processing Complete!")
    print(f"  -> Cleaned script saved to: {output_py_path}")
    print(f"  -> Knowledge Base saved to: {output_yaml_path}\n")

if __name__ == "__main__":
    main()
