import json
import math
import logging
import os
import csv
from tkinter import messagebox # Import messagebox for error popups

# --- Constants ---
DEFAULT_PLANET_ID = 2016
DEFAULT_CMD_CTR_LVL = 5
DEFAULT_LINK_LEVEL = 5
DEFAULT_ROUTE_QTY = 3000

TIER_TO_FACTORY_CATEGORY = {
    1: "Basic Industrial Facility",
    2: "Advanced Industrial Facility",
    3: "Advanced Industrial Facility",
    4: "High-Tech Industrial Facility"
}

# --- Fixed Layout Coordinates ---
ST_X, ST_Y = 0.0, 0.0
LP_X, LP_Y = 0.0, 0.08
ROW_V_SPACING = 0.06
COL_H_SPACING = 0.06
SIDE_OFFSET = 0.05
NUM_ROWS = 3
NUM_COLS_LEFT = 4
NUM_COLS_RIGHT = 3
TOTAL_FACTORY_SLOTS = NUM_ROWS * (NUM_COLS_LEFT + NUM_COLS_RIGHT) # 3 * 7 = 21

# Factory Positions (List of (x, y) tuples) - Rounded
FACTORY_SLOTS_BY_ROW = [[] for _ in range(NUM_ROWS)] # Store slots as [[row0_slots], [row1_slots], ...]
_factory_y_coords = [round(ST_Y + ROW_V_SPACING, 2), round(ST_Y, 2), round(ST_Y - ROW_V_SPACING, 2)] # Top, Middle, Bottom rows
_factory_x_coords_left = [round(ST_X - SIDE_OFFSET - i * COL_H_SPACING, 2) for i in range(NUM_COLS_LEFT)] # L4, L3, L2, L1
_factory_x_coords_right = [round(ST_X + SIDE_OFFSET + i * COL_H_SPACING, 2) for i in range(NUM_COLS_RIGHT)] # R1, R2, R3

# Populate FACTORY_SLOTS_BY_ROW
for r, y in enumerate(_factory_y_coords):
    # Left side (L1, L2, L3, L4) - Closest to center first in list
    for x in reversed(_factory_x_coords_left):
        FACTORY_SLOTS_BY_ROW[r].append((x, y))
    # Right side (R1, R2, R3) - Closest to center first in list
    for x in _factory_x_coords_right:
        FACTORY_SLOTS_BY_ROW[r].append((x, y))

# --- Production Data Loading (Keep as is) ---
def load_production_data(config, csv_dir="docs"):
    production_data = {}
    commodity_name_to_id = {name: int(id_str) for id_str, name in config.data.get("commodities", {}).items()}
    def get_id(name):
        comm_id = commodity_name_to_id.get(name)
        if comm_id is None: logging.warning(f"Prod data load: Commodity '{name}' not found.")
        return comm_id
    files_to_process = {"P1.csv": (1, 1), "P2.csv": (2, 2), "P3.csv": (3, 3), "P4.csv": (3, 4)}
    logging.info(f"Loading production data from CSVs in '{csv_dir}'...")
    has_errors = False
    for filename, (num_inputs, output_tier) in files_to_process.items():
        filepath = os.path.join(csv_dir, filename)
        try:
            with open(filepath, 'r', newline='') as f:
                reader = csv.reader(f, delimiter=';'); next(reader) # Skip header
                logging.debug(f"  Processing {filename} (Inputs: {num_inputs}, Tier: P{output_tier})")
                for i, row in enumerate(reader):
                    if not row or len(row) < num_inputs + 1: logging.warning(f"    Skip row {i+2} in {filename}: Insufficient columns"); continue
                    output_name = row[num_inputs].strip(); input_names = [n.strip() for n in row[:num_inputs] if n.strip()]
                    output_id = get_id(output_name)
                    if output_id is None: has_errors = True; continue
                    input_ids = []; valid_inputs = True
                    for name in input_names:
                        input_id = get_id(name)
                        if input_id is None: has_errors = True; valid_inputs = False; break
                        input_ids.append(input_id)
                    if valid_inputs:
                        if output_id in production_data: logging.warning(f"    Duplicate output ID {output_id} ('{output_name}'). Overwriting.")
                        production_data[output_id] = {'inputs': input_ids, 'tier': output_tier}
                        logging.debug(f"    Mapped: {output_name}({output_id}) [T{output_tier}] -> {[n for n in input_names]}({input_ids})")
                    else: logging.warning(f"    Skip entry for '{output_name}' due to missing input ID(s).")
        except FileNotFoundError: logging.error(f"Prod data load: File not found: {filepath}"); has_errors = True
        except Exception as e: logging.error(f"Prod data load: Error reading {filepath}: {e}"); has_errors = True
    if not production_data: logging.error("Prod data load: No valid data loaded."); return None
    if has_errors: logging.warning("Prod data load: Completed with errors/warnings.")
    logging.info(f"Production data loaded. {len(production_data)} recipes found.")
    return production_data

# --- Revised Generator Function ---
def generate_pi_layout(schematic_counts, storage_type_id, launchpad_type_id, config, production_data):
    logging.info(f"Generating fixed layout (Row Chain -> ST -> LP) for: {schematic_counts}")
    if not production_data: logging.error("Gen failed: Production data missing."); return None
    if not all([storage_type_id, launchpad_type_id]): logging.error("Gen failed: Missing ST/LP type ID."); return None

    pins = []
    links = []
    routes = []
    pin_index_counter = 0
    factory_assignments = {} # Map 0-based factory index -> output_schematic_id
    factory_indices_by_row = [[] for _ in range(NUM_ROWS)] # Store 0-based indices [[row0_indices], [row1_indices], ...]

    # --- Determine Planet and Get Factory Type IDs ---
    planet_id = DEFAULT_PLANET_ID; planet_name = "Unknown"
    for pin_id in [storage_type_id, launchpad_type_id]:
         _, p_name = config.get_pin_type(pin_id)
         if p_name != "Unknown" and p_name != "Generic":
              planet_name = p_name
              planet_types_rev = {v: k for k, v in config.data.get("planet_types", {}).items()}
              found_id = planet_types_rev.get(planet_name)
              if found_id: planet_id = int(found_id); logging.info(f"Inferred Planet ID {planet_id} ('{planet_name}') from pin {pin_id}."); break
    if planet_name == "Unknown": logging.warning(f"Could not infer planet type. Using default Planet ID: {planet_id}")

    factory_type_ids = {cat: config.get_pin_type_id_by_category(cat, planet_name) for tier, cat in TIER_TO_FACTORY_CATEGORY.items()}
    if None in factory_type_ids.values():
        missing_cats = [cat for cat, type_id in factory_type_ids.items() if type_id is None]
        logging.error(f"Gen failed: Config missing factory categories {missing_cats} for planet '{planet_name}'.")
        messagebox.showerror("Config Error", f"Missing factory definitions in config for planet '{planet_name}'.\nNeeded: {', '.join(missing_cats)}")
        return None
    logging.info(f"Using Factory Type IDs for Planet '{planet_name}': {factory_type_ids}")

    # --- 1. Create Core Pins (Storage, Launchpad) ---
    pins.append({"T": storage_type_id, "La": round(ST_Y, 2), "Lo": round(ST_X, 2)})
    storage_index_0based = pin_index_counter; pin_index_counter += 1
    logging.debug(f"  Added Storage Pin: Index={storage_index_0based}, Pos=({round(ST_Y, 2)}, {round(ST_X, 2)})")
    pins.append({"T": launchpad_type_id, "La": round(LP_Y, 2), "Lo": round(LP_X, 2)})
    launchpad_index_0based = pin_index_counter; pin_index_counter += 1
    logging.debug(f"  Added Launchpad Pin: Index={launchpad_index_0based}, Pos=({round(LP_Y, 2)}, {round(LP_X, 2)})")

    # --- 2. Create Factory Pins ---
    total_factories_requested = sum(schematic_counts.values())
    if total_factories_requested > TOTAL_FACTORY_SLOTS:
        logging.error(f"Gen failed: Requested {total_factories_requested} factories > {TOTAL_FACTORY_SLOTS} slots.")
        messagebox.showerror("Input Error", f"Too many factories requested ({total_factories_requested}). Max: {TOTAL_FACTORY_SLOTS}.")
        return None

    commodity_name_to_id = {name: int(id_str) for id_str, name in config.data.get("commodities", {}).items()}
    factory_slot_counter = 0

    # Assign schematics to slots row by row
    schematic_list_flat = []
    for name, count in schematic_counts.items():
        schematic_list_flat.extend([name] * count)

    for r in range(NUM_ROWS):
        for c in range(len(FACTORY_SLOTS_BY_ROW[r])):
            if factory_slot_counter >= len(schematic_list_flat):
                # No more schematics requested, stop adding factories
                break

            schematic_name = schematic_list_flat[factory_slot_counter]
            schematic_id = commodity_name_to_id.get(schematic_name) # Should exist due to UI validation
            recipe_info = production_data.get(schematic_id)
            if recipe_info is None:
                 logging.error(f"Gen failed: Schematic '{schematic_name}' is not producible factory output.")
                 messagebox.showerror("Input Error", f"Cannot generate factory for '{schematic_name}'.\nCheck P1-P4 CSV files.")
                 return None

            schematic_tier = recipe_info['tier']
            factory_category = TIER_TO_FACTORY_CATEGORY.get(schematic_tier)
            current_factory_type_id = factory_type_ids.get(factory_category) # Should exist due to check above

            factory_x, factory_y = FACTORY_SLOTS_BY_ROW[r][c]

            pins.append({
                "T": current_factory_type_id,
                "S": schematic_id,
                "La": factory_y, # Already rounded
                "Lo": factory_x  # Already rounded
            })
            factory_index_0based = pin_index_counter
            factory_indices_by_row[r].append(factory_index_0based) # Add index to the correct row list
            factory_assignments[factory_index_0based] = schematic_id
            pin_index_counter += 1
            factory_slot_counter += 1
            logging.debug(f"  Added Factory Pin: Row={r}, Col={c}, Index={factory_index_0based}, Type={factory_category}({current_factory_type_id}), Output={schematic_name}({schematic_id}), Pos=({factory_y}, {factory_x})")
        if factory_slot_counter >= len(schematic_list_flat):
             break # Stop outer loop if all schematics assigned


    # --- 3. Create Links (NEW STRUCTURE) ---
    storage_1_idx = storage_index_0based + 1
    launchpad_1_idx = launchpad_index_0based + 1

    for r in range(NUM_ROWS):
        row_indices = factory_indices_by_row[r]
        if not row_indices: continue # Skip if row is empty

        # Link factories within the row sequentially (o-o-o...)
        for i in range(len(row_indices) - 1):
            source_1_idx = row_indices[i] + 1
            dest_1_idx = row_indices[i+1] + 1
            links.append({"S": source_1_idx, "D": dest_1_idx, "Lv": DEFAULT_LINK_LEVEL})
            logging.debug(f"  Added Intra-Row Link: Row={r}, {source_1_idx} -> {dest_1_idx}")

        # Link the first factory in the row (closest to center) to Storage
        first_factory_1_idx = row_indices[0] + 1
        links.append({"S": first_factory_1_idx, "D": storage_1_idx, "Lv": DEFAULT_LINK_LEVEL})
        logging.debug(f"  Added Row-to-Storage Link: Row={r}, Fac({first_factory_1_idx}) -> ST({storage_1_idx})")

    # Link Storage to Launchpad
    links.append({"S": storage_1_idx, "D": launchpad_1_idx, "Lv": DEFAULT_LINK_LEVEL})
    logging.debug(f"  Added Storage-to-Launchpad Link: ST({storage_1_idx}) -> LP({launchpad_1_idx})")


    # --- 4. Create Routes (ST->Fac->LP) ---
    # This logic remains the same, using the factory_assignments and production_data

    all_factory_indices = [idx for row in factory_indices_by_row for idx in row] # Flatten list for iteration
    for fac_0_idx in all_factory_indices:
        fac_1_idx = fac_0_idx + 1
        output_schematic_id = factory_assignments[fac_0_idx]
        recipe_info = production_data.get(output_schematic_id)

        # Output Route (Factory -> Launchpad)
        routes.append({
            "P": [fac_1_idx, launchpad_1_idx],
            "T": output_schematic_id,
            "Qty": DEFAULT_ROUTE_QTY
        })
        logging.debug(f"  Added Output Route: Fac({fac_1_idx}) -> LP({launchpad_1_idx}), Comm={output_schematic_id}, Qty={DEFAULT_ROUTE_QTY}")

        # Input Routes (Storage -> Factory)
        if recipe_info:
            input_commodity_ids = recipe_info.get('inputs', [])
            if not input_commodity_ids:
                logging.debug(f"    No input routes needed for factory {fac_1_idx} (Output: {output_schematic_id})")
            else:
                for input_comm_id in input_commodity_ids:
                    routes.append({
                        "P": [storage_1_idx, fac_1_idx],
                        "T": input_comm_id,
                        "Qty": DEFAULT_ROUTE_QTY
                    })
                    logging.debug(f"  Added Input Route: ST({storage_1_idx}) -> Fac({fac_1_idx}), Comm={input_comm_id}, Qty={DEFAULT_ROUTE_QTY}")
        else:
             logging.warning(f"    Could not find recipe info for factory {fac_1_idx} output {output_schematic_id}. Skipping input routes.")


    # --- 5. Assemble Final JSON Structure ---
    final_json_data = {
        "P": pins,
        "L": links,
        "R": routes,
        "Pln": planet_id,
        "CmdCtrLv": DEFAULT_CMD_CTR_LVL,
        "Diam": 100000, # Placeholder
        "Cmt": f"Generated: {factory_slot_counter} Factories (Row Chain->ST->LP)"
    }

    try:
        json_string = json.dumps(final_json_data, separators=(',', ':'))
        logging.info("Layout generation successful.")
        return json_string
    except Exception as e:
        logging.error(f"Error converting layout data to JSON: {e}")
        return None
