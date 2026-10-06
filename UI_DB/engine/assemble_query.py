import json
import sqlglot
from sqlglot.errors import ParseError
import os
import re

def assemble_final_query(state: dict) -> dict:
    print("\n--- NODE 5: Assembling and Validating Final SQL Query ---")
    
    # 1. Extract State Data
    payload = state.get("payload", {})
    query_block = payload.get("variables", {}).get("query", {})
    
    valid_tables = state.get("valid_tables", [])
    if not valid_tables:
        raise ValueError("Cannot assemble query: No valid tables found.")
    base_table = valid_tables[0]
    
    dimension_columns = state.get("dimension_columns", [])
    resolved_measures = state.get("resolved_measures_sql", [])
    join_clauses = state.get("join_clauses", [])
    is_total_query = state.get("is_total_query", False)
    
    # --- FIX 1: Extract Active Tables to prevent orphaned prefixes ---
    active_tables = [base_table]
    for j in join_clauses:
        parts = j.split()
        if "JOIN" in parts:
            idx = parts.index("JOIN")
            if idx + 1 < len(parts):
                active_tables.append(parts[idx + 1].strip())
                
    # --- FIX 2: Sanitize Orphaned Tables in SELECT Measures ---
    cleaned_measures = []
    for m in resolved_measures:
        prefixes = set(re.findall(r'\b([a-zA-Z_0-9]+)\.', m))
        for prefix in prefixes:
            if prefix not in active_tables:
                # Replace unjoined table prefix with the valid base_table
                m = re.sub(rf'\b{prefix}\.', f"{base_table}.", m)
        cleaned_measures.append(m)
    resolved_measures = cleaned_measures
    
    # 2. Build SELECT Clause
    select_items = dimension_columns + resolved_measures
    if not select_items:
        select_items = ["*"] 
    
    select_sql = "SELECT \n    " + ",\n    ".join(select_items)
    print("   [x] SELECT clause assembled")
    
    # 3. Build FROM Clause
    from_sql = f"\nFROM {base_table}"
    print("   [x] FROM clause assembled")
    
    # 4. Build JOIN Clauses
    join_sql = ""
    if join_clauses:
        join_sql = "\n" + "\n".join(join_clauses)
        print(f"   [x] JOIN clauses assembled ({len(join_clauses)} joins)")
        
    # 5. Build WHERE Clause
    where_sql = ""
    where_conditions = []
    
    scope_block = query_block.get("scope") or {}
    filters = scope_block.get("dimensionFilters", [])
    
    for filter_group in filters:
        xref_family = filter_group.get("dimensionColumnName", "")
        for and_cond in filter_group.get("and", []):
            dim_level = and_cond.get("dimensionLevelColumnName")
            operator = and_cond.get("cmpOperator", "").upper()
            values = and_cond.get("values", [])
            
            if not dim_level or not values:
                continue
                
            # --- FIX 3: Safe WHERE Clause Targeting ---
            expected_xref = f"{xref_family}_dim_xref"
            expected_desc = f"{dim_level}_dim_desc"
            
            # Smart Routing: Only use xref/desc prefixes IF they are actually joined.
            # Otherwise, default to the base_table because Step 1 used the Fast Path.
            if expected_xref in active_tables:
                col_fq = f"{expected_xref}.{dim_level}_id"
            elif expected_desc in active_tables:
                col_fq = f"{expected_desc}.{dim_level}_id"
            else:
                col_fq = f"{base_table}.{dim_level}_id"
            
            if operator == "IN":
                val_str = ", ".join([f"'{v}'" for v in values])
                where_conditions.append(f"{col_fq} IN ({val_str})")
            elif operator in ["EQUALS", "="]:
                where_conditions.append(f"{col_fq} = '{values[0]}'")
            
    if where_conditions:
        where_sql = "\nWHERE " + " AND ".join(where_conditions)
        print("   [x] WHERE clause assembled")
        
    # 6. Build GROUP BY Clause
    groupby_sql = ""
    if not is_total_query and dimension_columns:
        groupby_sql = "\nGROUP BY \n    " + ",\n    ".join(dimension_columns)
        print("   [x] GROUP BY clause assembled")
        
    # 7. Build ORDER BY Clause
    order_sql = ""
    sort_block = query_block.get("sort") or {}
    
    # --- FIX 4: Protect Measures from _name/_id injection ---
    measure_aliases = []
    for m in resolved_measures:
        if " AS " in m.upper():
            alias = m.upper().split(" AS ")[-1].strip().lower()
            measure_aliases.append(alias)
            
    if sort_block and isinstance(sort_block, dict):
        entries = sort_block.get("entries", [])
        order_clauses = []
        for entry in entries:
            col_name = entry.get("columnName")
            direction = entry.get("direction", "ASC")
            if col_name:
                # If it's a measure, do NOT append _name or _id
                if col_name.lower() in measure_aliases:
                    order_clauses.append(f"{col_name} {direction}")
                else:
                    col_type = entry.get("columnType", "")
                    if col_type == "NAME":
                        order_clauses.append(f"{col_name}_name {direction}")
                    else:
                        order_clauses.append(f"{col_name}_id {direction}")
                        
        if order_clauses:
            order_sql = "\nORDER BY " + ", ".join(order_clauses)
            print("   [x] ORDER BY clause assembled")

    # 8. Build LIMIT / OFFSET Clause
    limit_sql = ""
    limit_val = query_block.get("first")
    offset_val = query_block.get("after")
    
    if limit_val is not None:
        limit_sql += f"\nLIMIT {limit_val}"
    if offset_val is not None:
        try:
            offset_int = int(offset_val)
            limit_sql += f"\nOFFSET {offset_int}"
        except ValueError:
            pass
    print("   [x] LIMIT/OFFSET clause assembled")

    # 9. Concatenate Final Raw SQL
    raw_sql = select_sql + from_sql + join_sql + where_sql + groupby_sql + order_sql + limit_sql
    
    # 10. Step-wise Syntax Validation
    print("\n   => Validating Query Syntax via AST...")
    try:
        parsed_ast = sqlglot.parse_one(raw_sql, read="postgres")
        final_safe_sql = parsed_ast.sql(dialect="postgres", pretty=True)
        print("   [SUCCESS] Query is structurally valid PostgreSQL!")
        
    except ParseError as e:
        print("\n   [CRITICAL SYNTAX ERROR] The assembled query has invalid syntax.")
        print(f"   Details: {e.errors}")
        print("\n   --- RAW DUMP THAT CAUSED ERROR ---")
        print(raw_sql)
        raise ValueError("Query compilation failed at syntax validation phase.") from e

    state["final_sql"] = final_safe_sql
    return state

if __name__ == "__main__":
    print("\n" + "="*70)
    print("🛠️ UI-DB STEP 2: SQL ASSEMBLY AGENT")
    print("="*70)

    # 🔴 SILENTLY CONSUME AND STRIP UI ENVIRONMENT VARIABLES
    workspace = os.getenv("AUTO_WORKSPACE")
    if workspace: workspace = workspace.strip()
    if not workspace:
        workspace = input("Enter Workspace Directory (e.g. UI_DB/workspaces/EBW):\n> ").strip()

    if workspace and not os.path.exists(workspace):
        print(f"\n❌ Error: Workspace '{workspace}' does not exist.")
        exit(1)

    query_name = os.getenv("AUTO_QUERY_NAME")
    if query_name: query_name = query_name.strip()
    if not query_name:
        query_name = input("Enter Query Name (e.g. payload):\n> ").strip()

    if query_name.endswith(".json"):
        query_name = query_name[:-5]
    if query_name.endswith("_state_checkpoint"):
        query_name = query_name.replace("_state_checkpoint", "")

    # Define explicit project paths
    input_filename = os.path.join(workspace, f"{query_name}_state_checkpoint.json")
    output_filename = os.path.join(workspace, f"final_{query_name}.sql")

    if not os.path.exists(input_filename):
        print(f"\n❌ Error: Checkpoint file '{input_filename}' not found.")
        print("Make sure you run Step 1 (graph_step1.py) first!")
        exit(1)

    print(f"📂 Workspace: {workspace}")
    print(f"📄 Target Checkpoint: {os.path.basename(input_filename)}")
    print(f"🎯 Output SQL File: {os.path.basename(output_filename)}\n")

    try:
        with open(input_filename, 'r', encoding='utf-8') as f:
            checkpoint_state = json.load(f)
            
        final_state = assemble_final_query(checkpoint_state)
        
        print("\n=========================================")
        print("FINAL COMPILED SQL:")
        print("=========================================")
        print(final_state["final_sql"])
        
        # 🔴 SAVE THE SQL QUERY TO THE SPECIFIC WORKSPACE FOLDER
        with open(output_filename, 'w', encoding='utf-8') as f:
            f.write(final_state["final_sql"])
            
        print(f"\n✅ Assembly Complete! SQL saved to: {output_filename}\n")
        
    except Exception as e:
        print(f"\n❌ [ERROR] Failed to assemble or save query: {e}")
