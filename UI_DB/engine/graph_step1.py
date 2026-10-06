# import json
# import psycopg2
# import os
# import re
# import sqlglot
# import sqlglot.expressions as exp
# from dotenv import load_dotenv
# from typing import TypedDict, List, Dict, Any
# from langgraph.graph import StateGraph, START, END

# # --- 1. Environment & DB Setup ---
# load_dotenv()
# DB_USER = os.getenv("DB_USER")
# DB_PASSWORD = os.getenv("DB_PASSWORD")
# DB_HOST = os.getenv("DB_HOST") 
# DB_PORT = os.getenv("DB_PORT", "5432")
# DB_DATABASE = os.getenv("DB_DATABASE", "postgres")
# DB_SCHEMA = os.getenv("DB_SCHEMA", "stage_da2_dataset1")

# class DroppedMeasureError(Exception):
#     pass

# def get_db_connection():
#     return psycopg2.connect(
#         dbname=DB_DATABASE, user=DB_USER, password=DB_PASSWORD,
#         host=DB_HOST, port=DB_PORT, options=f'-c search_path={DB_SCHEMA}' 
#     )

# class QueryState(TypedDict):
#     payload: Dict[str, Any] 
#     valid_tables: List[str]
#     is_total_query: bool
#     dimension_columns: List[str]
#     join_clauses: List[str]
#     resolved_measures_sql: List[str]  
#     unresolved_measures: List[str]    
#     formula_definitions: Dict[str, Dict[str, Any]] 

# # --- 3. Shared Helpers ---
# def extract_joined_tables(join_clauses: list, primary_fact: str) -> list:
#     tables = [primary_fact] if primary_fact else []
#     for join_str in join_clauses:
#         parts = join_str.split(" ")
#         try:
#             idx = parts.index("JOIN")
#             tables.append(parts[idx + 1])
#         except ValueError:
#             pass
#     return list(set(tables))

# def extract_dependencies_ast(formula_string: str) -> list:
#     dependencies = []
#     try:
#         tree = sqlglot.parse_one(formula_string, read="postgres")
#         for column in tree.find_all(exp.Column):
#             col_name = column.name.lower().replace('"', '')
#             table_alias = column.table.lower() if column.table else None
#             full_dep = f"{table_alias}.{col_name}" if table_alias else col_name
#             if full_dep not in dependencies:
#                 dependencies.append(full_dep)
#     except Exception as e:
#         print(f"   [AST ERROR] Failed parsing {formula_string}: {e}. Using regex fallback.")
#         words = re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)?\b', formula_string)
#         ignore = {'sum', 'avg', 'min', 'max', 'count', 'case', 'when', 'then', 'else', 'end', 'coalesce', 'nullif', 'cast', 'int', 'decimal', 'and', 'or', 'is', 'not', 'null', 'to_char', 'date', 'over', 'partition', 'by', 'lead', 'lag', 'first_value'}
#         for w in words:
#             w_clean = w.lower()
#             if w_clean not in ignore and w_clean not in dependencies and not w_clean.isdigit():
#                 dependencies.append(w_clean)
#     return dependencies

# def check_column_has_data_fq(cur, fq_column_name: str) -> bool:
#     """Verifies that a specific column in a specific table actually contains non-null data."""
#     if "." not in fq_column_name: return False
#     table_name, col_name = fq_column_name.split(".", 1)
#     try:
#         cur.execute(f"SELECT 1 FROM {table_name} WHERE {col_name} IS NOT NULL LIMIT 1;")
#         return cur.fetchone() is not None
#     except psycopg2.Error:
#         cur.connection.rollback()
#         return False

# def test_join_path(cur, target_table: str, test_key: str) -> bool:
#     """
#     Runs a lightweight diagnostic query to ensure the target table is actually populated 
#     with the key we intend to join on. 
#     This avoids the INNER JOIN edge case where orphaned fact rows cause false negatives.
#     """
#     try:
#         cur.execute("SET statement_timeout = '2000';")
        
#         # Simply verify the bridge/desc table has actual data for this key
#         query = f"SELECT 1 FROM {target_table} WHERE {test_key} IS NOT NULL LIMIT 1;"
#         cur.execute(query)
#         has_data = cur.fetchone() is not None
        
#         cur.execute("SET statement_timeout = '0';")
#         return has_data
        
#     except psycopg2.errors.QueryCanceled:
#         cur.connection.rollback()
#         cur.execute("SET statement_timeout = '0';")
#         return False
        
#     except psycopg2.Error:
#         cur.connection.rollback()
#         try:
#             cur.execute("SET statement_timeout = '0';")
#         except:
#             pass
#         return False

# def test_full_join_path(cur, base_table: str, target_table: str, join_condition: str) -> bool:
#     """
#     Used specifically for cross-joining fact tables, where checking a single key isn't enough.
#     """
#     try:
#         cur.execute("SET statement_timeout = '2000';")
#         query = f"SELECT 1 FROM {base_table} INNER JOIN {target_table} ON {join_condition} LIMIT 1;"
#         cur.execute(query)
#         has_data = cur.fetchone() is not None
#         cur.execute("SET statement_timeout = '0';")
#         return has_data
#     except psycopg2.Error:
#         cur.connection.rollback()
#         try:
#             cur.execute("SET statement_timeout = '0';")
#         except:
#             pass
#         return False

# def run_diagnostics(cur, missing_term: str) -> list:
#     clean_term = re.sub(r'^(sum|avg|max|min|count)_', '', missing_term)
#     if "." in clean_term: clean_term = clean_term.split(".")[1]
    
#     parts = [p for p in clean_term.split('_') if len(p) > 2]
#     suggestions = set()
#     for part in parts:
#         search_pattern = f"%{part}%"
#         cur.execute("SELECT measure_aggregation_column_name FROM measure_aggregations WHERE measure_aggregation_column_name ILIKE %s LIMIT 5", (search_pattern,))
#         for row in cur.fetchall(): suggestions.add(row[0])
#         cur.execute("SELECT measure_column_name FROM measures WHERE measure_column_name ILIKE %s LIMIT 5", (search_pattern,))
#         for row in cur.fetchall(): suggestions.add(row[0])
#         cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema = %s AND column_name ILIKE %s LIMIT 5", (DB_SCHEMA, search_pattern))
#         for row in cur.fetchall(): suggestions.add(row[0])
#     return sorted(list(suggestions))

# def validate_and_enforce_data(cur, original_measure: str, phys_col: str, depth: int, payload_tables: list, active_joins: list) -> str:
#     """
#     STRICT DATA VALIDATION (MODIFIED): 
#     Checks for NULLs. If a column is 100% NULL but exists in the schema, 
#     issues a warning and proceeds to allow the user to force it.
#     """
#     indent = "    " * depth
#     col_name = phys_col.split(".", 1)[1] if "." in phys_col else phys_col
        
#     cur.execute("""
#         SELECT table_name FROM information_schema.columns 
#         WHERE table_schema = %s AND column_name = %s
#     """, (DB_SCHEMA, col_name))
    
#     all_tables = [row[0] for row in cur.fetchall()]
    
#     # Filter only tables that ACTUALLY have data for this column
#     populated_tables = []
#     for t in all_tables:
#         if check_column_has_data_fq(cur, f"{t}.{col_name}"):
#             populated_tables.append(t)
            
#     # Sort to prioritize active joins and payload tables
#     priority_order = (active_joins or []) + payload_tables + ["fact_data", "fact_override", "alert_fact"]
#     populated_tables.sort(key=lambda x: priority_order.index(x) if x in priority_order else 999)

#     if len(populated_tables) == 1:
#         return f"{populated_tables[0]}.{col_name}"
        
#     elif len(populated_tables) > 1:
#         print(f"\n{indent}  [AMBIGUITY] Column '{col_name}' contains valid data in MULTIPLE tables.")
#         for i, tbl in enumerate(populated_tables, 1):
#             note = " (Prioritized/Currently Joined)" if tbl in priority_order else ""
#             print(f"{indent}      {i}. {tbl}{note}")
            
#         while True:
#             choice = input(f"{indent}  > Select correct table number (1-{len(populated_tables)}): ").strip()
#             if choice.isdigit() and 1 <= int(choice) <= len(populated_tables):
#                 return f"{populated_tables[int(choice)-1]}.{col_name}"
                
#     elif all_tables:
#         # ADDED BLOCK: The column structurally exists, but is 100% NULL.
#         all_tables.sort(key=lambda x: priority_order.index(x) if x in priority_order else 999)
#         print(f"\n{indent}  [WARNING] Column '{col_name}' exists in the schema but is 100% NULL.")
        
#         if len(all_tables) == 1:
#             print(f"{indent}  Auto-forcing use of {all_tables[0]}.{col_name}")
#             return f"{all_tables[0]}.{col_name}"
#         else:
#             print(f"{indent}  Please select which empty table to force:")
#             for i, tbl in enumerate(all_tables, 1):
#                 note = " (Prioritized/Currently Joined)" if tbl in priority_order else ""
#                 print(f"{indent}      {i}. {tbl}{note}")
                
#             while True:
#                 choice = input(f"{indent}  > Select table number to force (1-{len(all_tables)}): ").strip()
#                 if choice.isdigit() and 1 <= int(choice) <= len(all_tables):
#                     return f"{all_tables[int(choice)-1]}.{col_name}"
                    
#     else:
#         # The column does NOT exist in the database at all
#         print(f"\n{indent}  [CRITICAL ERROR] '{col_name}' does not exist in ANY table.")
#         print(f"{indent}  Running diagnostics for alternative columns...")
#         suggestions = run_diagnostics(cur, phys_col)
        
#         if suggestions:
#             print(f"{indent}  Found {len(suggestions)} potential matches:")
#             for i, s in enumerate(suggestions, 1): print(f"{indent}      {i}. {s}")
        
#         while True:
#             choice = input(f"{indent}  > Type 1-{len(suggestions)} for suggestion, manual text, or 'drop': ").strip()
#             if choice.lower() == 'drop': 
#                 raise DroppedMeasureError(f"User dropped measure due to blank dependency: '{original_measure}'")
#             elif choice.isdigit() and 1 <= int(choice) <= len(suggestions):
#                 return resolve_measure(cur, suggestions[int(choice)-1], depth, payload_tables, active_joins)
#             elif choice:
#                 return resolve_measure(cur, choice, depth, payload_tables, active_joins)


# def handle_ambiguous_alias(cur, dep_with_alias: str, indent: str, active_joins: list) -> str:
#     table_alias, col_name = dep_with_alias.split(".", 1)
#     if table_alias in active_joins: return dep_with_alias
        
#     print(f"\n{indent}  [GHOST ALIAS DETECTED] Formula hardcodes alias '{table_alias}' for column '{col_name}'.")
#     return validate_and_enforce_data(cur, col_name, col_name, len(indent)//4, [], active_joins)

# def resolve_measure(cur, measure_name: str, depth: int, payload_tables: list, active_joins: list) -> str:
#     indent = "    " * depth
#     print(f"{indent}-> Resolving: {measure_name}")
    
#     if "." in measure_name:
#         table_prefix, base_col = measure_name.split(".", 1)
#         if table_prefix not in active_joins:
#             return handle_ambiguous_alias(cur, measure_name, indent, active_joins)
    
#     cur.execute("""
#         SELECT measure_aggregation_id, measure_aggregation_type, measure_id, measure_formula 
#         FROM measure_aggregations WHERE measure_aggregation_column_name = %s
#     """, (measure_name,))
#     row = cur.fetchone()
    
#     if not row:
#         match = re.match(r'^(sum|avg|max|min|count)_(.*)$', measure_name, re.IGNORECASE)
#         if match:
#             agg_func = match.group(1).upper()
#             phys_col = match.group(2).lower() 
#             print(f"{indent}   [BASE FALLBACK] Expanding inline aggregate '{measure_name}' -> {agg_func}({phys_col})")
#             fq_col = validate_and_enforce_data(cur, measure_name, phys_col, depth, payload_tables, active_joins)
#             return f"{agg_func}({fq_col})"
#         else:
#             print(f"{indent}   [BASE] '{measure_name}' not in metadata. Checking schema fallback...")
#             return validate_and_enforce_data(cur, measure_name, measure_name, depth, payload_tables, active_joins)

#     ma_id, agg_type, measure_id, formula = row
#     agg_type = agg_type.upper() if agg_type else "UNKNOWN"
    
#     if agg_type in ['FORMULA', 'BASE_FORMULA']:
#         cur.execute("""
#             SELECT ma.measure_aggregation_column_name 
#             FROM measure_aggregation_dependencies mad
#             JOIN measure_aggregations ma ON mad.source_measure_aggregation_id = ma.measure_aggregation_id
#             WHERE mad.target_measure_aggregation_id = %s
#         """, (ma_id,))
#         db_deps = [r[0].lower() for r in cur.fetchall() if r[0]] 
#         ast_deps = extract_dependencies_ast(formula)
        
#         combined_deps = list(set(db_deps + ast_deps))
#         working_formula = formula
        
#         for dep in combined_deps:
#             resolved_dep = resolve_measure(cur, dep, depth + 1, payload_tables, active_joins)
#             pattern = re.compile(rf'(?:\b[a-zA-Z_0-9]+\.)?\b{re.escape(dep)}\b', re.IGNORECASE)
#             working_formula = pattern.sub(resolved_dep, working_formula)
            
#         return f"({working_formula})"
        
#     elif agg_type in ['SUM', 'MAX', 'MIN', 'AVG', 'COUNT']:
#         phys_col = measure_name
#         if measure_id:
#             cur.execute("SELECT measure_column_name FROM measures WHERE measure_id = %s", (measure_id,))
#             res = cur.fetchone()
#             if res and res[0]: phys_col = res[0]
            
#         valid_phys_col = validate_and_enforce_data(cur, measure_name, phys_col, depth, payload_tables, active_joins)
#         return f"{agg_type}({valid_phys_col})"
        
#     elif agg_type == 'BASE_ONLY':
#         phys_col = measure_name
#         if measure_id:
#             cur.execute("SELECT measure_column_name FROM measures WHERE measure_id = %s", (measure_id,))
#             res = cur.fetchone()
#             if res and res[0]: phys_col = res[0]
            
#         return validate_and_enforce_data(cur, measure_name, phys_col, depth, payload_tables, active_joins)
        
#     return measure_name

# # --- 4. LangGraph Node Functions ---
# def identify_and_validate_tables(state: QueryState) -> QueryState:
#     print("\n--- NODE 1: Identifying & Validating Tables ---")
#     payload = state.get("payload", {})
#     valid_tables = []
    
#     try:
#         variables = payload.get("variables") or {}
#         query_block = variables.get("query") or {}
#         datatable_list = query_block.get("datatable") or []
        
#         if not datatable_list: 
#             print("-> Note: Empty datatable. Likely a pure dimension query.")
#             return {"valid_tables": []}
            
#         conn = get_db_connection()
#         cur = conn.cursor()
        
#         def validate_table(table_name):
#             safe_name = table_name.replace('"', '').replace("'", "")
#             try:
#                 cur.execute(f"SELECT 1 FROM {safe_name} LIMIT 1;")
#                 if cur.fetchone() is not None: return safe_name
#                 return None
#             except psycopg2.Error:
#                 conn.rollback()
#                 return None

#         for table in datatable_list:
#             valid_name = validate_table(table)
#             if valid_name: valid_tables.append(valid_name)
                
#         if not valid_tables:
#             print("\n-> WARNING: All payload tables failed. Attempting Fallback...")
#             for table in ["fact_data", "fact_override", "alert_fact", "fact_static_measure_data"]:
#                 valid_name = validate_table(table)
#                 if valid_name:
#                     print(f"   [FALLBACK SUCCESS] Using {valid_name}")
#                     valid_tables.append(valid_name)
                    
#         cur.close()
#         conn.close()
        
#         if not valid_tables: raise ValueError("CRITICAL: Both payload tables AND fallback tables failed validation.")
#         return {"valid_tables": valid_tables}
#     except Exception as e:
#         print(f"Fatal Error in identify_and_validate_tables: {e}")
#         raise


# def get_data_driven_join_keys(cur, table1, table2, common_keys):
#     """
#     APPROACH B: Iteratively tests join conditions against actual database rows.
#     Drops keys that cause the join to fail (like user_id mismatch).
#     """
#     valid_keys = []
    
#     for key in common_keys:
#         test_keys = valid_keys + [key]
#         conditions = " AND ".join([f"{table1}.{k} = {table2}.{k}" for k in test_keys])
        
#         # Test if an INNER JOIN with this key returns at least one row
#         query = f"SELECT 1 FROM {table1} INNER JOIN {table2} ON {conditions} LIMIT 1;"
        
#         try:
#             cur.execute(query)
#             if cur.fetchone():  # If a row is returned, the key is mathematically valid!
#                 valid_keys.append(key)
#         except Exception:
#             cur.execute("ROLLBACK;") # Catch any syntax errors to keep the cursor alive
            
#     # CRITICAL FALLBACK: If tables currently have NO overlapping data (Empty Trap),
#     # fallback to the safest known core grain to prevent query failure.
#     if not valid_keys:
#         print(f"    [WARNING] Data-driven test found NO valid keys (override table may be empty). Using safe fallback.")
#         safe_fallback = {'time_id', 'product_id', 'location_id'}
#         return [k for k in common_keys if k in safe_fallback]
        
#     return valid_keys




# def resolve_dimensions(state: QueryState) -> QueryState:
#     print("\n--- NODE 2: Resolving Dimensions (Schema & Diagnostic Driven) ---")
#     payload = state.get("payload") or {}
#     valid_tables = state.get("valid_tables", [])
    
#     primary_fact_table = valid_tables[0] if valid_tables else ""
#     variables = payload.get("variables") or {}
#     query_block = variables.get("query") or {}
    
#     dimension_levels = query_block.get("dimensionLevels")
#     if isinstance(dimension_levels, str): dimension_levels = [dimension_levels]
#     dimension_levels = dimension_levels or []
    
#     scope_block = query_block.get("scope") or {}
#     filters = scope_block.get("dimensionFilters") or []
    
#     dimension_columns = []
#     join_clauses = []
    
#     if not primary_fact_table:
#         return {"is_total_query": False, "dimension_columns": dimension_columns, "join_clauses": []}
    
#     conn = get_db_connection()
#     cur = conn.cursor()
    
#     # 1. Cross join valid fact tables dynamically
#     if len(valid_tables) > 1:
#         for secondary_table in valid_tables[1:]:
#             cur.execute("""
#                 SELECT column_name FROM information_schema.columns 
#                 WHERE table_schema = %s AND table_name = %s AND column_name LIKE '%%_id'
#                 INTERSECT
#                 SELECT column_name FROM information_schema.columns 
#                 WHERE table_schema = %s AND table_name = %s AND column_name LIKE '%%_id'
#             """, (DB_SCHEMA, primary_fact_table, DB_SCHEMA, secondary_table))
            
#             raw_common_keys = [row[0] for row in cur.fetchall()]
#             print(f"    [DIAGNOSTIC] Inferring true dimensions for {primary_fact_table} <-> {secondary_table}...")
#             common_keys = get_data_driven_join_keys(cur, primary_fact_table, secondary_table, raw_common_keys)
#             # ------------------------
            
#             if common_keys:
#                 join_conditions = " AND ".join([f"{primary_fact_table}.{key} = {secondary_table}.{key}" for key in common_keys])

#             if common_keys:
#                 join_conditions = " AND ".join([f"{primary_fact_table}.{key} = {secondary_table}.{key}" for key in common_keys])
                
#                 # Test the path, but optionally force it if it's a declared payload table
#                 if test_full_join_path(cur, primary_fact_table, secondary_table, join_conditions):
#                     join_clauses.append(f"LEFT JOIN {secondary_table} ON {join_conditions}")
#                 elif secondary_table in payload.get("variables", {}).get("query", {}).get("datatable", []):
#                     print(f"    [WARNING] Forced join on {secondary_table} even though test failed.")
#                     join_clauses.append(f"LEFT JOIN {secondary_table} ON {join_conditions}")

#     required_dimensions = {}
#     if not dimension_levels and not filters:
#         cur.close()
#         conn.close()
#         return {"is_total_query": True, "dimension_columns": [], "join_clauses": join_clauses}
        
#     for dim in dimension_levels: required_dimensions[dim] = {"xref_family": None, "is_select": True}
#     for filter_group in filters:
#         xref_family = filter_group.get("dimensionColumnName")
#         for and_cond in filter_group.get("and", []):
#             dim_level = and_cond.get("dimensionLevelColumnName") 
#             if dim_level:
#                 if dim_level in required_dimensions: required_dimensions[dim_level]["xref_family"] = xref_family
#                 else: required_dimensions[dim_level] = {"xref_family": xref_family, "is_select": False}

#     for dim_level, rules in required_dimensions.items():
#         desc_table = f"{dim_level}_dim_desc"
#         target_id_col = f"{dim_level}_id"
#         xref_family = rules["xref_family"]
        
#         if rules["is_select"]: 
#             dimension_columns.extend([f"{desc_table}.{dim_level}_id", f"{desc_table}.{dim_level}_name"])
            
#         # Fast Path: Does the fact table already hold this dimension directly with non-null data?
#         # Fast Path: Does the fact table hold this dimension directly with VALID relational data?
#         cur.execute("SELECT 1 FROM information_schema.columns WHERE table_schema = %s AND table_name = %s AND column_name = %s", (DB_SCHEMA, primary_fact_table, target_id_col))
        
#         if cur.fetchone():
#             print(f"    [DIAGNOSTIC] Fact table contains '{target_id_col}'. Testing relational integrity for Fast Path...")
#             join_condition = f"{primary_fact_table}.{target_id_col} = {desc_table}.{target_id_col}"
            
#             # Use test_full_join_path to prove the fact column legitimately maps to the dimension table
#             if test_full_join_path(cur, primary_fact_table, desc_table, join_condition):
#                 print(f"    [DIAGNOSTIC SUCCESS] '{target_id_col}' is a valid denormalized column! Using Fast Path.")
#                 if rules["is_select"]:
#                     join_clauses.append(f"LEFT JOIN {desc_table} ON {join_condition}")
#                 continue
#             else:
#                 print(f"    [DIAGNOSTIC FAILED] '{target_id_col}' contains orphaned/ghost data. Falling back to XREF bridge routing.")

#         # --- STRUCTURAL DIAGNOSTIC XREF RESOLUTION ---
#         if xref_family:
#             cur.execute("""
#                 SELECT table_name FROM information_schema.tables 
#                 WHERE table_schema = %s AND table_name LIKE %s AND table_name LIKE '%%_xref'
#             """, (DB_SCHEMA, f"%{xref_family}%"))
#         else:
#             cur.execute("""
#                 SELECT table_name FROM information_schema.columns 
#                 WHERE table_schema = %s AND column_name = %s AND table_name LIKE '%%_xref'
#             """, (DB_SCHEMA, target_id_col))
        
#         xref_candidates = [row[0] for row in cur.fetchall()]
#         selected_xref = None
#         join_key = None
        
#         for xref in xref_candidates:
#             # Find intersecting keys
#             cur.execute("""
#                 SELECT column_name FROM information_schema.columns WHERE table_schema = %s AND table_name = %s AND column_name LIKE '%%_id'
#                 INTERSECT
#                 SELECT column_name FROM information_schema.columns WHERE table_schema = %s AND table_name = %s AND column_name LIKE '%%_id'
#             """, (DB_SCHEMA, primary_fact_table, DB_SCHEMA, xref))
            
#             keys = [row[0] for row in cur.fetchall()]
#             if not keys: continue
            
#             # Prioritize the family key, fallback to the first shared key
#             test_key = f"{xref_family}_id" if xref_family and f"{xref_family}_id" in keys else keys[0]
            
#             # --- UPDATED DIAGNOSTIC CHECK ---
#             print(f"    [DIAGNOSTIC] Testing bridge table '{xref}' for key '{test_key}'...")
#             if test_join_path(cur, xref, test_key):
#                 print(f"    [DIAGNOSTIC SUCCESS] {xref} is populated and valid!")
#                 selected_xref = xref
#                 join_key = test_key
#                 break # Stop searching, we found the right table
#             else:
#                 print(f"    [DIAGNOSTIC FAILED] {xref} has no valid '{test_key}' data. Skipping.")

#         # Apply the validated bridge
#         if selected_xref and join_key:
#             join_clauses.append(f"LEFT JOIN {selected_xref} ON {primary_fact_table}.{join_key} = {selected_xref}.{join_key}")
            
#             # Now, test if the description table is also populated before joining it
#             if rules["is_select"]:
#                 print(f"    [DIAGNOSTIC] Testing description table: {desc_table}...")
#                 if test_join_path(cur, desc_table, target_id_col):
#                     join_clauses.append(f"LEFT JOIN {desc_table} ON {selected_xref}.{target_id_col} = {desc_table}.{target_id_col}")
#                 else:
#                     print(f"    [WARNING] {desc_table} is empty. Skipping join to prevent 0-row result.")
                    
#     cur.close()
#     conn.close()
#         # Use dict.fromkeys() to remove duplicates but KEEP the original order
#     return {
#         "is_total_query": False, 
#         "dimension_columns": list(dict.fromkeys(dimension_columns)), 
#         "join_clauses": list(dict.fromkeys(join_clauses))
#     }

# def resolve_measures_simple(state: QueryState) -> QueryState:
#     print("\n--- NODE 3: Measure Resolution (Simple & Base) ---")
#     payload = state.get("payload", {})
#     valid_tables = state.get("valid_tables", [])
    
#     aggregated_measures = payload.get("variables", {}).get("query", {}).get("aggregatedMeasures", [])
#     resolved_measures_sql = []
#     unresolved_measures = []
    
#     if not aggregated_measures: return {"resolved_measures_sql": [], "unresolved_measures": []}
    
#     active_joins = extract_joined_tables(state.get("join_clauses", []), valid_tables[0] if valid_tables else None)
#     is_grouped = not state.get("is_total_query") and len(state.get("dimension_columns", [])) > 0
    
#     conn = get_db_connection()
#     cur = conn.cursor()
            
#     for measure in aggregated_measures:
#         measure = measure.strip()
#         if not measure: continue
            
#         print(f"\nProcessing: {measure}")
#         cur.execute("SELECT measure_aggregation_type, measure_id FROM measure_aggregations WHERE measure_aggregation_column_name = %s", (measure,))
#         meta_row = cur.fetchone()
        
#         if not meta_row:
#             print(f"   [WARNING] '{measure}' not found in metadata. Checking physical schema.")
#             try:
#                 valid_col = validate_and_enforce_data(cur, measure, measure, 0, valid_tables, active_joins)
#                 if is_grouped:
#                     agg_wrapper = "MAX({}::text)" if "comment" in measure.lower() or "name" in measure.lower() else "MAX({}::numeric)"
#                     valid_col = agg_wrapper.format(valid_col)
#                 resolved_measures_sql.append(f"{valid_col} AS {measure}")
#             except DroppedMeasureError:
#                 unresolved_measures.append(measure)
#             continue
            
#         agg_type, m_id = meta_row
#         agg_type = agg_type.upper() if agg_type else ""
#         print(f"   [METADATA] Found Type: {agg_type}")
        
#         if agg_type == 'BASE_ONLY':
#             cur.execute("SELECT measure_column_name FROM measures WHERE measure_id = %s", (m_id,))
#             res = cur.fetchone()
#             phys_col = res[0] if res else measure
#             try:
#                 valid_col = validate_and_enforce_data(cur, measure, phys_col, 0, valid_tables, active_joins)
#                 if is_grouped:
#                     agg_wrapper = "MAX({}::text)" if "comment" in measure.lower() or "name" in measure.lower() else "MAX({}::numeric)"
#                     valid_col = agg_wrapper.format(valid_col)
#                 resolved_measures_sql.append(f"{valid_col} AS {measure}")
#             except DroppedMeasureError:
#                 unresolved_measures.append(measure)
                
#         elif agg_type in ['SUM', 'MAX', 'MIN', 'AVG', 'COUNT']:
#             cur.execute("SELECT measure_column_name FROM measures WHERE measure_id = %s", (m_id,))
#             res = cur.fetchone()
#             phys_col = res[0] if res else measure
#             try:
#                 valid_col = validate_and_enforce_data(cur, measure, phys_col, 0, valid_tables, active_joins)
#                 resolved_measures_sql.append(f"{agg_type}({valid_col}) AS {measure}")
#             except DroppedMeasureError:
#                 unresolved_measures.append(measure)
                
#         elif 'FORMULA' in agg_type:
#             print(f"   [DEFERRED] Queuing complex formula for Node 4.")
#             unresolved_measures.append(measure)
            
#     cur.close()
#     conn.close()
#     return {"resolved_measures_sql": resolved_measures_sql, "unresolved_measures": unresolved_measures}

# def validate_resolved_measures(state: QueryState) -> QueryState:
#     return state 

# def resolve_complex_formulas(state: QueryState) -> QueryState:
#     print("\n--- NODE 4: Complex Formula Resolution ---")
#     unresolved_measures = state.get("unresolved_measures", [])
#     resolved_measures_sql = list(state.get("resolved_measures_sql", []))
#     payload_tables = state.get("payload", {}).get("variables", {}).get("query", {}).get("datatable", [])
    
#     valid_tables = state.get("valid_tables", [])
#     primary_fact = valid_tables[0] if valid_tables else None
#     active_joins = extract_joined_tables(state.get("join_clauses", []), primary_fact)
    
#     conn = get_db_connection()
#     cur = conn.cursor()
    
#     for measure in unresolved_measures:
#         try:
#             print(f"\n=========================================\nAnalyzing Complex Measure: {measure}\n=========================================")
#             final_sql = resolve_measure(cur, measure, 0, payload_tables, active_joins)
#             final_sql_line = f"{final_sql} AS {measure}"
#             resolved_measures_sql.append(final_sql_line)
#             print(f"\n   [SUCCESS] Compiled Formula: {final_sql_line}")
#         except DroppedMeasureError as e:
#             print(f"   [WARNING] Skipping '{measure}': {e}")
            
#     cur.close()
#     conn.close()
#     return {"resolved_measures_sql": resolved_measures_sql, "unresolved_measures": []}

# # --- 5. Graph Construction & Execution ---
# workflow = StateGraph(QueryState)

# workflow.add_node("identify_and_validate_tables", identify_and_validate_tables)
# workflow.add_node("resolve_dimensions", resolve_dimensions)
# workflow.add_node("resolve_measures_simple", resolve_measures_simple)
# workflow.add_node("validate_resolved_measures", validate_resolved_measures)
# workflow.add_node("resolve_complex_formulas", resolve_complex_formulas) 

# workflow.add_edge(START, "identify_and_validate_tables")
# workflow.add_edge("identify_and_validate_tables", "resolve_dimensions")
# workflow.add_edge("resolve_dimensions", "resolve_measures_simple")
# workflow.add_edge("resolve_measures_simple", "validate_resolved_measures")
# workflow.add_edge("validate_resolved_measures", "resolve_complex_formulas") 
# workflow.add_edge("resolve_complex_formulas", END)                          

# app = workflow.compile()

# if __name__ == "__main__":
#     try:
#         with open('payload.json', 'r') as f:
#             graphql_payload = json.load(f)
#     except FileNotFoundError:
#         exit(1)
        
#     initial_state = {
#         "payload": graphql_payload, "valid_tables": [], "is_total_query": False,
#         "dimension_columns": [], "join_clauses": [], "resolved_measures_sql": [],
#         "unresolved_measures": [], "formula_definitions": {}
#     }
    
#     final_state = app.invoke(initial_state)
#     print("\n=========================================")
#     print("--- Final State Summary ---")
#     print(f"Valid Fact Tables: {final_state.get('valid_tables')}")
#     print(f"Is Total Query:    {final_state.get('is_total_query')}")
#     print(f"Dimension Columns: {len(final_state.get('dimension_columns'))} cols")
#     print(f"Joins Generated:   {len(final_state.get('join_clauses'))}")
#     print(f"Resolved Measures: {len(final_state.get('resolved_measures_sql'))}")
#     print("=========================================")
    
#     output_filename = "state_checkpoint.json"
#     try:
#         with open(output_filename, 'w') as f:
#             json.dump(final_state, f, indent=4)
#         print(f"\n[SUCCESS] Entire workflow state saved to '{output_filename}'")
#     except Exception as e:
#         print(f"\n[ERROR] Failed to save state to '{output_filename}': {e}")


































import json
import psycopg2
import os
import re
import sqlglot
import sqlglot.expressions as exp
from dotenv import load_dotenv
from typing import TypedDict, List, Dict, Any
from langgraph.graph import StateGraph, START, END

# --- 1. Environment & DB Setup ---
load_dotenv()
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_DATABASE = os.getenv("DB_DATABASE", "postgres")
DB_SCHEMA = os.getenv("DB_SCHEMA", "stage_da2_dataset1")

class DroppedMeasureError(Exception):
    pass

def get_db_connection():
    return psycopg2.connect(
        dbname=DB_DATABASE, user=DB_USER, password=DB_PASSWORD,
        host=DB_HOST, port=DB_PORT, options=f'-c search_path={DB_SCHEMA}'
    )

class QueryState(TypedDict):
    payload: Dict[str, Any]
    valid_tables: List[str]
    is_total_query: bool
    is_dim_query: bool  # <--- NEW: Flags pure dimension queries
    dimension_columns: List[str]
    join_clauses: List[str]
    resolved_measures_sql: List[str]  
    unresolved_measures: List[str]    
    formula_definitions: Dict[str, Dict[str, Any]]

# --- 3. Shared Helpers ---
def extract_joined_tables(join_clauses: list, primary_fact: str) -> list:
    tables = [primary_fact] if primary_fact else []
    for join_str in join_clauses:
        parts = join_str.split(" ")
        try:
            idx = parts.index("JOIN")
            tables.append(parts[idx + 1])
        except ValueError:
            pass
    return list(set(tables))

def extract_dependencies_ast(formula_string: str) -> list:
    dependencies = []
    try:
        tree = sqlglot.parse_one(formula_string, read="postgres")
        for column in tree.find_all(exp.Column):
            col_name = column.name.lower().replace('"', '')
            table_alias = column.table.lower() if column.table else None
            full_dep = f"{table_alias}.{col_name}" if table_alias else col_name
            if full_dep not in dependencies:
                dependencies.append(full_dep)
    except Exception as e:
        print(f"   [AST ERROR] Failed parsing {formula_string}: {e}. Using regex fallback.")
        words = re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)?\b', formula_string)
        ignore = {'sum', 'avg', 'min', 'max', 'count', 'case', 'when', 'then', 'else', 'end', 'coalesce', 'nullif', 'cast', 'int', 'decimal', 'and', 'or', 'is', 'not', 'null', 'to_char', 'date', 'over', 'partition', 'by', 'lead', 'lag', 'first_value'}
        for w in words:
            w_clean = w.lower()
            if w_clean not in ignore and w_clean not in dependencies and not w_clean.isdigit():
                dependencies.append(w_clean)
    return dependencies

def check_column_has_data_fq(cur, fq_column_name: str) -> bool:
    """Verifies that a specific column in a specific table actually contains non-null data."""
    if "." not in fq_column_name: return False
    table_name, col_name = fq_column_name.split(".", 1)
    try:
        cur.execute(f"SELECT 1 FROM {table_name} WHERE {col_name} IS NOT NULL LIMIT 1;")
        return cur.fetchone() is not None
    except psycopg2.Error:
        cur.connection.rollback()
        return False

def test_join_path(cur, target_table: str, test_key: str) -> bool:
    try:
        cur.execute("SET statement_timeout = '2000';")
        query = f"SELECT 1 FROM {target_table} WHERE {test_key} IS NOT NULL LIMIT 1;"
        cur.execute(query)
        has_data = cur.fetchone() is not None
        cur.execute("SET statement_timeout = '0';")
        return has_data
    except psycopg2.errors.QueryCanceled:
        cur.connection.rollback()
        cur.execute("SET statement_timeout = '0';")
        return False
    except psycopg2.Error:
        cur.connection.rollback()
        try:
            cur.execute("SET statement_timeout = '0';")
        except:
            pass
        return False

def test_full_join_path(cur, base_table: str, target_table: str, join_condition: str) -> bool:
    try:
        cur.execute("SET statement_timeout = '2000';")
        query = f"SELECT 1 FROM {base_table} INNER JOIN {target_table} ON {join_condition} LIMIT 1;"
        cur.execute(query)
        has_data = cur.fetchone() is not None
        cur.execute("SET statement_timeout = '0';")
        return has_data
    except psycopg2.Error:
        cur.connection.rollback()
        try:
            cur.execute("SET statement_timeout = '0';")
        except:
            pass
        return False

def run_diagnostics(cur, missing_term: str) -> list:
    clean_term = re.sub(r'^(sum|avg|max|min|count)_', '', missing_term)
    if "." in clean_term: clean_term = clean_term.split(".")[1]
    
    parts = [p for p in clean_term.split('_') if len(p) > 2]
    suggestions = set()
    for part in parts:
        search_pattern = f"%{part}%"
        cur.execute("SELECT measure_aggregation_column_name FROM measure_aggregations WHERE measure_aggregation_column_name ILIKE %s LIMIT 5", (search_pattern,))
        for row in cur.fetchall(): suggestions.add(row[0])
        cur.execute("SELECT measure_column_name FROM measures WHERE measure_column_name ILIKE %s LIMIT 5", (search_pattern,))
        for row in cur.fetchall(): suggestions.add(row[0])
        cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema = %s AND column_name ILIKE %s LIMIT 5", (DB_SCHEMA, search_pattern))
        for row in cur.fetchall(): suggestions.add(row[0])
    return sorted(list(suggestions))

def validate_and_enforce_data(cur, original_measure: str, phys_col: str, depth: int, payload_tables: list, active_joins: list) -> str:
    indent = "    " * depth
    col_name = phys_col.split(".", 1)[1] if "." in phys_col else phys_col
    col_name = col_name.lower()
        
    cur.execute("""
        SELECT table_name FROM information_schema.columns 
        WHERE table_schema = %s AND column_name = %s
    """, (DB_SCHEMA, col_name))
    
    all_tables = [row[0] for row in cur.fetchall()]
    
    populated_tables = []
    for t in all_tables:
        if check_column_has_data_fq(cur, f"{t}.{col_name}"):
            populated_tables.append(t)
            
    priority_order = (active_joins or []) + payload_tables + ["fact_data", "fact_override", "alert_fact"]
    populated_tables.sort(key=lambda x: priority_order.index(x) if x in priority_order else 999)

    if len(populated_tables) == 1:
        return f"{populated_tables[0]}.{col_name}"
        
    elif len(populated_tables) > 1:
        print(f"\n{indent}  [AMBIGUITY] Column '{col_name}' contains valid data in MULTIPLE tables.")
        for i, tbl in enumerate(populated_tables, 1):
            note = " (Prioritized/Currently Joined)" if tbl in priority_order else ""
            print(f"{indent}      {i}. {tbl}{note}")
            
        while True:
            choice = input(f"{indent}  > Select correct table number (1-{len(populated_tables)}): ").strip()
            if choice.isdigit() and 1 <= int(choice) <= len(populated_tables):
                return f"{populated_tables[int(choice)-1]}.{col_name}"
                
    elif all_tables:
        all_tables.sort(key=lambda x: priority_order.index(x) if x in priority_order else 999)
        print(f"\n{indent}  [WARNING] Column '{col_name}' exists in the schema but is 100% NULL.")
        
        if len(all_tables) == 1:
            print(f"{indent}  Auto-forcing use of {all_tables[0]}.{col_name}")
            return f"{all_tables[0]}.{col_name}"
        else:
            print(f"{indent}  Please select which empty table to force:")
            for i, tbl in enumerate(all_tables, 1):
                note = " (Prioritized/Currently Joined)" if tbl in priority_order else ""
                print(f"{indent}      {i}. {tbl}{note}")
                
            while True:
                choice = input(f"{indent}  > Select table number to force (1-{len(all_tables)}): ").strip()
                if choice.isdigit() and 1 <= int(choice) <= len(all_tables):
                    return f"{all_tables[int(choice)-1]}.{col_name}"
                    
    else:
        print(f"\n{indent}  [CRITICAL ERROR] '{col_name}' does not exist in ANY table.")
        print(f"{indent}  Running diagnostics for alternative columns...")
        suggestions = run_diagnostics(cur, phys_col)
        
        if suggestions:
            print(f"{indent}  Found {len(suggestions)} potential matches:")
            for i, s in enumerate(suggestions, 1): print(f"{indent}      {i}. {s}")
        
        while True:
            choice = input(f"{indent}  > Type 1-{len(suggestions)} for suggestion, manual text, or 'drop': ").strip()
            if choice.lower() == 'drop':
                raise DroppedMeasureError(f"User dropped measure due to blank dependency: '{original_measure}'")
            elif choice.isdigit() and 1 <= int(choice) <= len(suggestions):
                return resolve_measure(cur, suggestions[int(choice)-1], depth, payload_tables, active_joins)
            elif choice:
                return resolve_measure(cur, choice, depth, payload_tables, active_joins)

def handle_ambiguous_alias(cur, dep_with_alias: str, indent: str, active_joins: list) -> str:
    table_alias, col_name = dep_with_alias.split(".", 1)
    if table_alias in active_joins: return dep_with_alias
    print(f"\n{indent}  [GHOST ALIAS DETECTED] Formula hardcodes alias '{table_alias}' for column '{col_name}'.")
    return validate_and_enforce_data(cur, col_name, col_name, len(indent)//4, [], active_joins)

def resolve_measure(cur, measure_name: str, depth: int, payload_tables: list, active_joins: list) -> str:
    indent = "    " * depth
    print(f"{indent}-> Resolving: {measure_name}")
    
    if "." in measure_name:
        table_prefix, base_col = measure_name.split(".", 1)
        if table_prefix not in active_joins:
            return handle_ambiguous_alias(cur, measure_name, indent, active_joins)
    
    cur.execute("""
        SELECT measure_aggregation_id, measure_aggregation_type, measure_id, measure_formula
        FROM measure_aggregations WHERE measure_aggregation_column_name ILIKE %s
    """, (measure_name,))
    row = cur.fetchone()
    
    if not row:
        match = re.match(r'^(sum|avg|max|min|count)_(.*)$', measure_name, re.IGNORECASE)
        if match:
            agg_func = match.group(1).upper()
            phys_col = match.group(2).lower()
            print(f"{indent}   [BASE FALLBACK] Expanding inline aggregate '{measure_name}' -> {agg_func}({phys_col})")
            fq_col = validate_and_enforce_data(cur, measure_name, phys_col, depth, payload_tables, active_joins)
            return f"{agg_func}({fq_col})"
        else:
            print(f"{indent}   [BASE] '{measure_name}' not in metadata. Checking schema fallback...")
            return validate_and_enforce_data(cur, measure_name, measure_name, depth, payload_tables, active_joins)

    ma_id, agg_type, measure_id, formula = row
    agg_type = agg_type.upper() if agg_type else "UNKNOWN"
    
    if agg_type in ['FORMULA', 'BASE_FORMULA']:
        cur.execute("""
            SELECT ma.measure_aggregation_column_name
            FROM measure_aggregation_dependencies mad
            JOIN measure_aggregations ma ON mad.source_measure_aggregation_id = ma.measure_aggregation_id
            WHERE mad.target_measure_aggregation_id = %s
        """, (ma_id,))
        db_deps = [r[0].lower() for r in cur.fetchall() if r[0]]
        ast_deps = extract_dependencies_ast(formula)
        
        combined_deps = list(set(db_deps + ast_deps))
        working_formula = formula
        
        for dep in combined_deps:
            resolved_dep = resolve_measure(cur, dep, depth + 1, payload_tables, active_joins)
            pattern = re.compile(rf'(?:\b[a-zA-Z_0-9]+\.)?\b{re.escape(dep)}\b', re.IGNORECASE)
            working_formula = pattern.sub(resolved_dep, working_formula)
            
        return f"({working_formula})"
        
    elif agg_type in ['SUM', 'MAX', 'MIN', 'AVG', 'COUNT']:
        phys_col = measure_name
        if measure_id:
            cur.execute("SELECT measure_column_name FROM measures WHERE measure_id = %s", (measure_id,))
            res = cur.fetchone()
            if res and res[0]: phys_col = res[0]
            
        valid_phys_col = validate_and_enforce_data(cur, measure_name, phys_col, depth, payload_tables, active_joins)
        return f"{agg_type}({valid_phys_col})"
        
    elif agg_type == 'BASE_ONLY':
        phys_col = measure_name
        if measure_id:
            cur.execute("SELECT measure_column_name FROM measures WHERE measure_id = %s", (measure_id,))
            res = cur.fetchone()
            if res and res[0]: phys_col = res[0]
            
        return validate_and_enforce_data(cur, measure_name, phys_col, depth, payload_tables, active_joins)
        
    return measure_name

def get_data_driven_join_keys(cur, table1, table2, common_keys):
    valid_keys = []
    for key in common_keys:
        test_keys = valid_keys + [key]
        conditions = " AND ".join([f"{table1}.{k} = {table2}.{k}" for k in test_keys])
        query = f"SELECT 1 FROM {table1} INNER JOIN {table2} ON {conditions} LIMIT 1;"
        try:
            cur.execute(query)
            if cur.fetchone():
                valid_keys.append(key)
        except Exception:
            cur.execute("ROLLBACK;")
            
    if not valid_keys:
        print(f"    [WARNING] Data-driven test found NO valid keys (override table may be empty). Using safe fallback.")
        safe_fallback = {'time_id', 'product_id', 'location_id'}
        return [k for k in common_keys if k in safe_fallback]
        
    return valid_keys

# --- 4. LangGraph Node Functions ---
def identify_and_validate_tables(state: QueryState) -> QueryState:
    print("\n--- NODE 1: Identifying & Validating Tables ---")
    payload = state.get("payload", {})
    valid_tables = []
    
    try:
        variables = payload.get("variables") or {}
        query_block = variables.get("query") or {}
        datatable_list = query_block.get("datatable") or []
        if isinstance(datatable_list, str):
            datatable_list = [datatable_list] if datatable_list else []
            
        # --- NEW: DETECT DIMENSION QUERIES (Filter Dropdowns) ---
        is_dim_query = "daDimMembersQuery" in payload.get("query", "") or not datatable_list
        
        if is_dim_query:
            print("   [INFO] Detected Dimension Member Query. Bypassing Fact validation.")
            dim_levels = query_block.get("dimensionLevels")
            dim = dim_levels[0] if isinstance(dim_levels, list) else dim_levels
            
            base_table = f"{dim}_dim_desc" if dim else ""
            
            # Verify the description table actually exists in the schema
            conn = get_db_connection()
            cur = conn.cursor()
            try:
                cur.execute(f"SELECT 1 FROM {base_table} LIMIT 1;")
                if cur.fetchone(): valid_tables = [base_table]
            except Exception:
                pass
            finally:
                conn.rollback()
                cur.close()
                conn.close()
                
            if valid_tables:
                return {"valid_tables": valid_tables, "is_dim_query": True}
            else:
                raise ValueError(f"Dimension desc table '{base_table}' not found for query.")
        # --------------------------------------------------------

        conn = get_db_connection()
        cur = conn.cursor()
        
        def validate_table(table_name):
            safe_name = table_name.replace('"', '').replace("'", "")
            try:
                cur.execute(f"SELECT 1 FROM {safe_name} LIMIT 1;")
                if cur.fetchone() is not None: return safe_name
                return None
            except psycopg2.Error:
                conn.rollback()
                return None

        for table in datatable_list:
            valid_name = validate_table(table)
            if valid_name: valid_tables.append(valid_name)
                
        if not valid_tables:
            print("\n-> WARNING: All payload tables failed. Attempting Fallback...")
            for table in ["fact_data", "fact_override", "alert_fact", "fact_static_measure_data"]:
                valid_name = validate_table(table)
                if valid_name:
                    print(f"   [FALLBACK SUCCESS] Using {valid_name}")
                    valid_tables.append(valid_name)
                    
        cur.close()
        conn.close()
        
        if not valid_tables: raise ValueError("CRITICAL: Both payload tables AND fallback tables failed validation.")
        return {"valid_tables": valid_tables, "is_dim_query": False}
    except Exception as e:
        print(f"Fatal Error in identify_and_validate_tables: {e}")
        raise

def resolve_dimensions(state: QueryState) -> QueryState:
    print("\n--- NODE 2: Resolving Dimensions (Schema & Diagnostic Driven) ---")
    
    # --- NEW: SHORT-CIRCUIT FOR DIMENSION QUERIES ---
    # --- UPDATED: SHORT-CIRCUIT FOR DIMENSION QUERIES WITH CROSS-FILTERING ---
    if state.get("is_dim_query"):
        payload = state.get("payload", {})
        variables = payload.get("variables", {}).get("query", {})
        
        dim_levels = variables.get("dimensionLevels")
        dim = dim_levels[0] if isinstance(dim_levels, list) else dim_levels
        
        join_clauses = []
        
        if dim:
            desc_table = f"{dim}_dim_desc"
            
            # Check for cross-hierarchy filters in the scope
            scope_block = variables.get("scope") or {}
            filters = scope_block.get("dimensionFilters") or []
            
            for filter_group in filters:
                xref_family = filter_group.get("dimensionColumnName")
                if xref_family:
                    xref_table = f"{xref_family}_dim_xref"
                    # Create the join from the description table back to the bridge table
                    join_condition = f"{desc_table}.{dim}_id = {xref_table}.{dim}_id"
                    join_clauses.append(f"LEFT JOIN {xref_table} ON {join_condition}")
            
            # Return the deduplicated join clauses
            return {
                "is_total_query": False,
                "dimension_columns": [f"{desc_table}.{dim}_id", f"{desc_table}.{dim}_name"],
                "join_clauses": list(dict.fromkeys(join_clauses))
            }
            
        return {"is_total_query": False, "dimension_columns": [], "join_clauses": []}
    # ------------------------------------------------
    
    payload = state.get("payload") or {}
    valid_tables = state.get("valid_tables", [])
    primary_fact_table = valid_tables[0] if valid_tables else ""
    variables = payload.get("variables") or {}
    query_block = variables.get("query") or {}
    
    dimension_levels = query_block.get("dimensionLevels")
    if isinstance(dimension_levels, str): dimension_levels = [dimension_levels]
    dimension_levels = dimension_levels or []
    
    scope_block = query_block.get("scope") or {}
    filters = scope_block.get("dimensionFilters") or []
    
    dimension_columns = []
    join_clauses = []
    
    if not primary_fact_table:
        return {"is_total_query": False, "dimension_columns": dimension_columns, "join_clauses": []}
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    if len(valid_tables) > 1:
        for secondary_table in valid_tables[1:]:
            cur.execute("""
                SELECT column_name FROM information_schema.columns
                WHERE table_schema = %s AND table_name = %s AND column_name LIKE '%%_id'
                INTERSECT
                SELECT column_name FROM information_schema.columns
                WHERE table_schema = %s AND table_name = %s AND column_name LIKE '%%_id'
            """, (DB_SCHEMA, primary_fact_table, DB_SCHEMA, secondary_table))
            
            raw_common_keys = [row[0] for row in cur.fetchall()]
            print(f"    [DIAGNOSTIC] Inferring true dimensions for {primary_fact_table} <-> {secondary_table}...")
            common_keys = get_data_driven_join_keys(cur, primary_fact_table, secondary_table, raw_common_keys)
            
            if common_keys:
                join_conditions = " AND ".join([f"{primary_fact_table}.{key} = {secondary_table}.{key}" for key in common_keys])
                if test_full_join_path(cur, primary_fact_table, secondary_table, join_conditions):
                    join_clauses.append(f"LEFT JOIN {secondary_table} ON {join_conditions}")
                elif secondary_table in payload.get("variables", {}).get("query", {}).get("datatable", []):
                    print(f"    [WARNING] Forced join on {secondary_table} even though test failed.")
                    join_clauses.append(f"LEFT JOIN {secondary_table} ON {join_conditions}")

    required_dimensions = {}
    if not dimension_levels and not filters:
        cur.close()
        conn.close()
        return {"is_total_query": True, "dimension_columns": [], "join_clauses": join_clauses}
        
    for dim in dimension_levels: required_dimensions[dim] = {"xref_family": None, "is_select": True}
    for filter_group in filters:
        xref_family = filter_group.get("dimensionColumnName")
        for and_cond in filter_group.get("and", []):
            dim_level = and_cond.get("dimensionLevelColumnName")
            if dim_level:
                if dim_level in required_dimensions: required_dimensions[dim_level]["xref_family"] = xref_family
                else: required_dimensions[dim_level] = {"xref_family": xref_family, "is_select": False}

    for dim_level, rules in required_dimensions.items():
        desc_table = f"{dim_level}_dim_desc"
        target_id_col = f"{dim_level}_id"
        xref_family = rules["xref_family"]
        
        if rules["is_select"]:
            dimension_columns.extend([f"{desc_table}.{dim_level}_id", f"{desc_table}.{dim_level}_name"])
            
        cur.execute("SELECT 1 FROM information_schema.columns WHERE table_schema = %s AND table_name = %s AND column_name = %s", (DB_SCHEMA, primary_fact_table, target_id_col))
        
        if cur.fetchone():
            print(f"    [DIAGNOSTIC] Fact table contains '{target_id_col}'. Testing relational integrity for Fast Path...")
            join_condition = f"{primary_fact_table}.{target_id_col} = {desc_table}.{target_id_col}"
            
            if test_full_join_path(cur, primary_fact_table, desc_table, join_condition):
                print(f"    [DIAGNOSTIC SUCCESS] '{target_id_col}' is a valid denormalized column! Using Fast Path.")
                if rules["is_select"]:
                    join_clauses.append(f"LEFT JOIN {desc_table} ON {join_condition}")
                continue
            else:
                print(f"    [DIAGNOSTIC FAILED] '{target_id_col}' contains orphaned/ghost data. Falling back to XREF bridge routing.")

        if xref_family:
            cur.execute("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = %s AND table_name LIKE %s AND table_name LIKE '%%_xref'
            """, (DB_SCHEMA, f"%{xref_family}%"))
        else:
            cur.execute("""
                SELECT table_name FROM information_schema.columns
                WHERE table_schema = %s AND column_name = %s AND table_name LIKE '%%_xref'
            """, (DB_SCHEMA, target_id_col))
        
        xref_candidates = [row[0] for row in cur.fetchall()]
        selected_xref = None
        join_key = None
        
        for xref in xref_candidates:
            cur.execute("""
                SELECT column_name FROM information_schema.columns WHERE table_schema = %s AND table_name = %s AND column_name LIKE '%%_id'
                INTERSECT
                SELECT column_name FROM information_schema.columns WHERE table_schema = %s AND table_name = %s AND column_name LIKE '%%_id'
            """, (DB_SCHEMA, primary_fact_table, DB_SCHEMA, xref))
            
            keys = [row[0] for row in cur.fetchall()]
            if not keys: continue
            
            test_key = f"{xref_family}_id" if xref_family and f"{xref_family}_id" in keys else keys[0]
            
            print(f"    [DIAGNOSTIC] Testing bridge table '{xref}' for key '{test_key}'...")
            if test_join_path(cur, xref, test_key):
                print(f"    [DIAGNOSTIC SUCCESS] {xref} is populated and valid!")
                selected_xref = xref
                join_key = test_key
                break
            else:
                print(f"    [DIAGNOSTIC FAILED] {xref} has no valid '{test_key}' data. Skipping.")

        if selected_xref and join_key:
            join_clauses.append(f"LEFT JOIN {selected_xref} ON {primary_fact_table}.{join_key} = {selected_xref}.{join_key}")
            if rules["is_select"]:
                print(f"    [DIAGNOSTIC] Testing description table: {desc_table}...")
                if test_join_path(cur, desc_table, target_id_col):
                    join_clauses.append(f"LEFT JOIN {desc_table} ON {selected_xref}.{target_id_col} = {desc_table}.{target_id_col}")
                else:
                    print(f"    [WARNING] {desc_table} is empty. Skipping join to prevent 0-row result.")
                    
    cur.close()
    conn.close()
    
    return {
        "is_total_query": False,
        "dimension_columns": list(dict.fromkeys(dimension_columns)),
        "join_clauses": list(dict.fromkeys(join_clauses))
    }

def resolve_measures_simple(state: QueryState) -> QueryState:
    print("\n--- NODE 3: Measure Resolution (Simple & Base) ---")
    
    # --- NEW: SHORT-CIRCUIT FOR DIMENSION QUERIES ---
    if state.get("is_dim_query"):
        return {"resolved_measures_sql": [], "unresolved_measures": []}
    # ------------------------------------------------
    
    payload = state.get("payload", {})
    valid_tables = state.get("valid_tables", [])
    
    aggregated_measures = payload.get("variables", {}).get("query", {}).get("aggregatedMeasures", [])
    resolved_measures_sql = []
    unresolved_measures = []
    
    if not aggregated_measures: return {"resolved_measures_sql": [], "unresolved_measures": []}
    
    active_joins = extract_joined_tables(state.get("join_clauses", []), valid_tables[0] if valid_tables else None)
    is_grouped = not state.get("is_total_query") and len(state.get("dimension_columns", [])) > 0
    
    conn = get_db_connection()
    cur = conn.cursor()

    # Helper to prevent nesting aggregates like MAX(SUM(...))
    def is_already_aggregated(col_str):
        return any(agg in col_str.upper() for agg in ['SUM(', 'MAX(', 'MIN(', 'AVG(', 'COUNT('])
            
    for measure in aggregated_measures:
        measure = measure.strip()
        if not measure: continue
            
        print(f"\nProcessing: {measure}")
        cur.execute("SELECT measure_aggregation_type, measure_id FROM measure_aggregations WHERE measure_aggregation_column_name ILIKE %s", (measure,))
        meta_row = cur.fetchone()
        
        if not meta_row:
            print(f"   [WARNING] '{measure}' not found in metadata. Checking physical schema.")
            try:
                valid_col = validate_and_enforce_data(cur, measure, measure, 0, valid_tables, active_joins)
                # 🔴 FIX: Only wrap in MAX if it doesn't already have an aggregate function!
                if is_grouped and not is_already_aggregated(valid_col):
                    agg_wrapper = "MAX({}::text)" if "comment" in measure.lower() or "name" in measure.lower() else "MAX({}::numeric)"
                    valid_col = agg_wrapper.format(valid_col)
                resolved_measures_sql.append(f"{valid_col} AS {measure}")
            except DroppedMeasureError:
                unresolved_measures.append(measure)
            continue
            
        agg_type, m_id = meta_row
        agg_type = agg_type.upper() if agg_type else ""
        print(f"   [METADATA] Found Type: {agg_type}")
        
        if agg_type == 'BASE_ONLY':
            cur.execute("SELECT measure_column_name FROM measures WHERE measure_id = %s", (m_id,))
            res = cur.fetchone()
            phys_col = res[0] if res else measure
            try:
                valid_col = validate_and_enforce_data(cur, measure, phys_col, 0, valid_tables, active_joins)
                # 🔴 FIX: Only wrap in MAX if it doesn't already have an aggregate function!
                if is_grouped and not is_already_aggregated(valid_col):
                    agg_wrapper = "MAX({}::text)" if "comment" in measure.lower() or "name" in measure.lower() else "MAX({}::numeric)"
                    valid_col = agg_wrapper.format(valid_col)
                resolved_measures_sql.append(f"{valid_col} AS {measure}")
            except DroppedMeasureError:
                unresolved_measures.append(measure)
                
        elif agg_type in ['SUM', 'MAX', 'MIN', 'AVG', 'COUNT']:
            cur.execute("SELECT measure_column_name FROM measures WHERE measure_id = %s", (m_id,))
            res = cur.fetchone()
            phys_col = res[0] if res else measure
            try:
                valid_col = validate_and_enforce_data(cur, measure, phys_col, 0, valid_tables, active_joins)
                resolved_measures_sql.append(f"{agg_type}({valid_col}) AS {measure}")
            except DroppedMeasureError:
                unresolved_measures.append(measure)
                
        elif 'FORMULA' in agg_type:
            print(f"   [DEFERRED] Queuing complex formula for Node 4.")
            unresolved_measures.append(measure)
            
    cur.close()
    conn.close()
    return {"resolved_measures_sql": resolved_measures_sql, "unresolved_measures": unresolved_measures}


def validate_resolved_measures(state: QueryState) -> QueryState:
    return state

def resolve_complex_formulas(state: QueryState) -> QueryState:
    print("\n--- NODE 4: Complex Formula Resolution ---")
    
    # --- NEW: SHORT-CIRCUIT FOR DIMENSION QUERIES ---
    if state.get("is_dim_query"):
        return {"resolved_measures_sql": [], "unresolved_measures": []}
    # ------------------------------------------------
    
    unresolved_measures = state.get("unresolved_measures", [])
    resolved_measures_sql = list(state.get("resolved_measures_sql", []))
    payload_tables = state.get("payload", {}).get("variables", {}).get("query", {}).get("datatable", [])
    
    valid_tables = state.get("valid_tables", [])
    primary_fact = valid_tables[0] if valid_tables else None
    active_joins = extract_joined_tables(state.get("join_clauses", []), primary_fact)
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    for measure in unresolved_measures:
        try:
            print(f"\n=========================================\nAnalyzing Complex Measure: {measure}\n=========================================")
            final_sql = resolve_measure(cur, measure, 0, payload_tables, active_joins)
            final_sql_line = f"{final_sql} AS {measure}"
            resolved_measures_sql.append(final_sql_line)
            print(f"\n   [SUCCESS] Compiled Formula: {final_sql_line}")
        except DroppedMeasureError as e:
            print(f"   [WARNING] Skipping '{measure}': {e}")
            
    cur.close()
    conn.close()
    return {"resolved_measures_sql": resolved_measures_sql, "unresolved_measures": []}

# --- 5. Graph Construction & Execution ---
workflow = StateGraph(QueryState)

workflow.add_node("identify_and_validate_tables", identify_and_validate_tables)
workflow.add_node("resolve_dimensions", resolve_dimensions)
workflow.add_node("resolve_measures_simple", resolve_measures_simple)
workflow.add_node("validate_resolved_measures", validate_resolved_measures)
workflow.add_node("resolve_complex_formulas", resolve_complex_formulas)

workflow.add_edge(START, "identify_and_validate_tables")
workflow.add_edge("identify_and_validate_tables", "resolve_dimensions")
workflow.add_edge("resolve_dimensions", "resolve_measures_simple")
workflow.add_edge("resolve_measures_simple", "validate_resolved_measures")
workflow.add_edge("validate_resolved_measures", "resolve_complex_formulas")
workflow.add_edge("resolve_complex_formulas", END)                          

app = workflow.compile()

if __name__ == "__main__":
    import os
    import json
    
    print("\n" + "="*70)
    print("🔍 UI-DB STEP 1: DIAGNOSTIC AGENT")
    print("="*70)

    # 🔴 SILENTLY CONSUME AND STRIP UI ENVIRONMENT VARIABLES
    workspace = os.getenv("AUTO_WORKSPACE")
    if workspace: workspace = workspace.strip()
    if not workspace:
        workspace = input("Enter Workspace Directory (e.g. UI_DB/workspaces/EBW):\n> ").strip()

    if workspace and not os.path.exists(workspace):
        os.makedirs(workspace, exist_ok=True)

    query_name = os.getenv("AUTO_QUERY_NAME")
    if query_name: query_name = query_name.strip()
    if not query_name:
        query_name = input("Enter Query Name (e.g. payload):\n> ").strip()

    # Clean up query name just in case the user typed .json
    if query_name.endswith(".json"):
        query_name = query_name[:-5]
    if query_name.endswith("_state_checkpoint"):
        query_name = query_name.replace("_state_checkpoint", "")

    # Define explicit project paths
    input_filename = os.path.join(workspace, f"{query_name}.json")
    output_filename = os.path.join(workspace, f"{query_name}_state_checkpoint.json")

    if not os.path.exists(input_filename):
        print(f"\n❌ Error: '{input_filename}' not found.")
        exit(1)

    print(f"📂 Workspace: {workspace}")
    print(f"📄 Target Payload: {query_name}.json")
    print(f"🎯 Output Checkpoint: {os.path.basename(output_filename)}\n")

    # Read the payload
    with open(input_filename, 'r', encoding='utf-8') as f:
        graphql_payload = json.load(f)
        
    initial_state = {
        "payload": graphql_payload,
        "valid_tables": [],
        "is_total_query": False,
        "is_dim_query": False,
        "dimension_columns": [],
        "join_clauses": [],
        "resolved_measures_sql": [],
        "unresolved_measures": [],
        "formula_definitions": {}
    }
    
    final_state = app.invoke(initial_state)
    
    print("\n=========================================")
    print("--- Final State Summary ---")
    print(f"Valid Fact Tables: {final_state.get('valid_tables')}")
    print(f"Is Total Query:    {final_state.get('is_total_query')}")
    print(f"Is Dim Query:      {final_state.get('is_dim_query')}")
    print(f"Dimension Columns: {len(final_state.get('dimension_columns'))} cols")
    print(f"Joins Generated:   {len(final_state.get('join_clauses'))}")
    print(f"Resolved Measures: {len(final_state.get('resolved_measures_sql'))}")
    print("=========================================")

    # 🔴 SAVE THE CHECKPOINT TO THE SPECIFIC WORKSPACE FOLDER
    try:
        with open(output_filename, "w", encoding="utf-8") as f:
            json.dump(final_state, f, indent=4)
        print(f"\n✅ Diagnostics Complete! Checkpoint saved to: {output_filename}\n")
    except Exception as e:
        print(f"\n[ERROR] Failed to save state to '{output_filename}': {e}")
