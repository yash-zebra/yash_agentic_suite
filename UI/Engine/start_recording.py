import os
import time

try:
    import pyperclip
except ImportError:
    print("❌ Missing 'pyperclip' library. Please run: pip install pyperclip")
    exit(1)

from playwright.sync_api import sync_playwright

# The Javascript to inject the Floating Dual-Widget (Bookmark + Assertion)
WIDGET_JS = """
(() => {
    function injectWidget() {
        if (document.getElementById('agent-recorder-widget')) return;
        if (!document.body) return; 
        
        const widget = document.createElement('div');
        widget.id = 'agent-recorder-widget';
        widget.style.cssText = 'position:fixed; bottom:20px; left:20px; z-index:2147483647; background-color:#1e293b; padding:12px 16px; border-radius:8px; box-shadow:0 10px 25px rgba(0,0,0,0.5); font-family:sans-serif; border:1px solid #475569; display:flex; flex-direction:column; gap:12px; min-width:350px;';
        
        // --- Drag Handle ---
        const dragHandle = document.createElement('div');
        dragHandle.innerHTML = '⋮⋮ DRAG TO MOVE ⋮⋮';
        dragHandle.style.cssText = 'background:#0f172a; margin:-12px -16px 0px -16px; padding:5px; text-align:center; font-size:10px; color:#94a3b8; cursor:move; border-radius:8px 8px 0 0; user-select:none;';
        widget.appendChild(dragHandle);

        // --- Row 1: Section Bookmark ---
        const row1 = document.createElement('div');
        row1.style.cssText = 'display:flex; gap:10px; align-items:center;';
        row1.innerHTML = `
            <span style="color:#f8fafc; font-size:14px; font-weight:bold; width:80px;">🔖 Section:</span>
            <input id="agent-bookmark-text" type="text" placeholder="e.g. Global Filters" style="flex-grow:1; padding:6px; border-radius:4px; border:1px solid #94a3b8; background:#f1f5f9; color:black;">
            <button id="agent-bookmark-btn" style="padding:6px 12px; background:#10b981; color:white; border:none; border-radius:4px; cursor:pointer; font-weight:bold; width:120px;">Add Section</button>
        `;
        widget.appendChild(row1);

        // --- Row 2: Human Assertion ---
        const row2 = document.createElement('div');
        row2.style.cssText = 'display:flex; gap:10px; align-items:center;';
        row2.innerHTML = `
            <span style="color:#f8fafc; font-size:14px; font-weight:bold; width:80px;">🧠 Assertion:</span>
            <input id="agent-assertion-text" type="text" placeholder="e.g. Grid has no 0 values" style="flex-grow:1; padding:6px; border-radius:4px; border:1px solid #94a3b8; background:#f1f5f9; color:black;">
            <button id="agent-assertion-btn" style="padding:6px 12px; background:#3b82f6; color:white; border:none; border-radius:4px; cursor:pointer; font-weight:bold; width:120px;">Save Assertion</button>
        `;
        widget.appendChild(row2);
        document.body.appendChild(widget);

        // --- Button Logics ---
        const sectionBtn = document.getElementById('agent-bookmark-btn');
        const sectionInput = document.getElementById('agent-bookmark-text');
        sectionBtn.onclick = () => {
            const orig = sectionBtn.innerText;
            sectionBtn.innerText = 'Saved!'; sectionBtn.style.backgroundColor = '#059669';
            setTimeout(() => { sectionBtn.innerText = orig; sectionBtn.style.backgroundColor = '#10b981'; sectionInput.value = ''; }, 1000);
        };

        const assertBtn = document.getElementById('agent-assertion-btn');
        const assertInput = document.getElementById('agent-assertion-text');
        assertBtn.onclick = () => {
            const orig = assertBtn.innerText;
            assertBtn.innerText = 'Saved!'; assertBtn.style.backgroundColor = '#1d4ed8';
            setTimeout(() => { assertBtn.innerText = orig; assertBtn.style.backgroundColor = '#3b82f6'; assertInput.value = ''; }, 1000);
        };

        // --- Drag Logic ---
        let startX, startY, initialLeft, initialTop;
        dragHandle.onmousedown = (e) => {
            e.preventDefault();
            startX = e.clientX; startY = e.clientY;
            const rect = widget.getBoundingClientRect();
            widget.style.left = rect.left + 'px'; widget.style.top = rect.top + 'px';
            widget.style.right = 'auto'; widget.style.bottom = 'auto'; widget.style.transform = 'none';
            initialLeft = rect.left; initialTop = rect.top;
            document.onmousemove = (me) => {
                widget.style.left = (initialLeft + me.clientX - startX) + 'px';
                widget.style.top = (initialTop + me.clientY - startY) + 'px';
            };
            document.onmouseup = () => { document.onmousemove = null; document.onmouseup = null; };
        };
    }
    
    // Attempt injection on load and repeatedly to survive Angular routing/MFA
    document.addEventListener('DOMContentLoaded', injectWidget);
    setInterval(injectWidget, 2000);
})();
"""

def main():
    print("\n" + "="*70)
    print("🛠️  RECORDING SETUP")
    print("="*70)
    
    # 🔴 SILENTLY CONSUME UI ENVIRONMENT VARIABLES
    workspace = os.getenv("AUTO_WORKSPACE")
    if workspace is None:
        workspace = input("Enter Workspace Directory (e.g. workspaces/Zebra/)\n(Press [ENTER] for current dir):\n> ").strip()
        
    if workspace and not os.path.exists(workspace):
        os.makedirs(workspace, exist_ok=True)
        print(f"📁 Created workspace: {workspace}")

    target_url = os.getenv("AUTO_URL")
    if not target_url:
        default_url = "https://stage.bbu.esp.antuit.ai/dp/demand-planning/executive-dashboard?workbookId=4&tabIndex=1"
        target_url = input(f"Enter target URL\n(Press [ENTER] for default: {default_url}):\n> ").strip() or default_url

    output_file = os.getenv("AUTO_FILENAME")
    if not output_file:
        default_output = "raw_codegen.py"
        output_file = input(f"\nEnter output filename\n(Press [ENTER] for default: {default_output}):\n> ").strip() or default_output
        
    if not output_file.endswith(".py"):
        output_file += ".py"

    output_path = os.path.join(workspace, output_file) if workspace else output_file

    print("\n" + "="*70)
    print("🎥 AGENT RECORDER LAUNCHING...")
    print("1. Playwright will open. Turn 'Record' OFF in the Inspector.")
    print("2. Pass your MFA securely.")
    print("3. Turn 'Record' ON and begin your flow.")
    print("4. Use the floating widget to mark Sections AND record Assertions.")
    print("\n⚠️ CRITICAL LAST STEP:")
    print("When you are finished, click the 'Copy' icon at the top right of")
    print(f"the Playwright Inspector code window, and THEN close the browser.")
    print("="*70 + "\n")
    
    # Clear clipboard before starting
    pyperclip.copy("")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(viewport={'width': 1280, 'height': 800})
        
        # Inject the widget across all pages and MFA redirects
        context.add_init_script(WIDGET_JS)
        
        page = context.new_page()
        page.goto(target_url, timeout=0)
        
        # Halts script, opens Inspector, allows user to record
        page.pause()
        browser.close()
        
    # --- THE AUTO-SAVE BRIDGE ---
    print("\n[Recorder] Browser closed. Checking clipboard for code...")
    time.sleep(1) # Give OS a moment to ensure clipboard is updated
    
    clipboard_content = pyperclip.paste()
    
    # Validate that they actually copied the Playwright code
    if "from playwright.sync_api" in clipboard_content or "page." in clipboard_content:
        with open(output_path, "w", encoding="utf-8") as f:
            # 🔴 STAMP THE TARGET URL INTO THE SCRIPT FOR THE PREPROCESSOR
            f.write(f"# RECORDED_URL: {target_url}\n")
            f.write(clipboard_content)
        print(f"✅ Success! Your recorded session has been auto-saved to: {output_path}")
    else:
        print("❌ Error: No Playwright code found in clipboard.")
        print("Did you forget to click 'Copy' in the Inspector before closing?")

if __name__ == "__main__":
    main()
