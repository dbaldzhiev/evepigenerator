import logging

def parse_pi_json(data, config):
    """
    Parses the raw EVE PI JSON data structure into a more usable format.

    Args:
        data (dict): The raw dictionary loaded from the JSON file.
        config (Config): The loaded configuration object for resolving IDs.

    Returns:
        dict: A dictionary containing parsed pins, links, routes, unknowns,
              planet ID, planet name, and metadata. Returns None on critical failure.
    """
    if not isinstance(data, dict):
        logging.error("Invalid input data: Expected a dictionary.")
        return None

    pins_data = data.get("P", [])
    links_data = data.get("L", [])
    routes_data = data.get("R", [])
    planet_id = data.get("Pln")
    planet_name = config.get_planet_name(planet_id) # Resolve planet name using config
    metadata = {
        "cmdctr": data.get("CmdCtrLv"),
        "diameter": data.get("Diam"),
        "comment": data.get("Cmt")
    }
    logging.info(f"Raw data: {len(pins_data)} pins, {len(links_data)} links, {len(routes_data)} routes. Planet ID: {planet_id} (Name: {planet_name})")

    if not isinstance(pins_data, list):
        logging.error("Invalid 'P' (pins) data: Expected a list.")
        pins_data = [] # Attempt to continue with empty list
    if not isinstance(links_data, list):
        logging.error("Invalid 'L' (links) data: Expected a list.")
        links_data = []
    if not isinstance(routes_data, list):
        logging.error("Invalid 'R' (routes) data: Expected a list.")
        routes_data = []

    parsed_pins = []
    unknown_pin_types = set()
    unknown_commodities = set() # Includes unknown schematic IDs and route commodity IDs
    pin_index_map = {} # Maps original 1-based index from JSON to 0-based index in parsed_pins

    logging.debug("--- Parsing Pins ---")
    for i, pin_raw in enumerate(pins_data):
        original_index = i + 1 # 1-based index from JSON list order

        if not isinstance(pin_raw, dict):
            logging.warning(f"Pin {original_index}: Invalid data format (expected dict, got {type(pin_raw)}). Skipping.")
            continue

        pin_type_id = pin_raw.get("T")
        schematic_id = pin_raw.get("S") # Assumed == Output Commodity ID for factories
        lat = pin_raw.get("La", 0.0)
        lon = pin_raw.get("Lo", 0.0)
        logging.debug(f"Raw Pin {original_index}: Type={pin_type_id}, Schematic={schematic_id}, Lat={lat}, Lon={lon}")

        if pin_type_id is None:
            logging.warning(f"Pin {original_index} missing 'T' (type ID). Treating as Unknown.")
            # Don't skip, just mark as unknown type
            pin_type_id = f"Missing_{original_index}" # Create a placeholder ID

        # Get category and associated planet name *from config*
        category, planet_name_from_config = config.get_pin_type(pin_type_id)
        schematic_name = None

        if category == "Unknown":
            logging.debug(f"  Pin {original_index}: Unknown pin type ID '{pin_type_id}'")
            unknown_pin_types.add(pin_type_id) # Add the actual ID found (or placeholder)

        if schematic_id is not None:
            # Try to get schematic info (name) using the schematic_id from commodities config
            # This uses get_commodity internally
            schematic_info = config.get_schematic(schematic_id)
            if schematic_info:
                schematic_name = schematic_info.get("name")
                logging.debug(f"  Pin {original_index}: Found schematic/commodity name '{schematic_name}' for ID {schematic_id}")
            else:
                # If schematic_info is None, the commodity name is unknown
                logging.debug(f"  Pin {original_index}: Unknown schematic/commodity ID {schematic_id}")
                unknown_commodities.add(schematic_id) # Add to unknown commodities

        # The 0-based index for our internal list
        current_list_index = len(parsed_pins)
        pin_index_map[original_index] = current_list_index
        logging.debug(f"  Mapping original index {original_index} to internal index {current_list_index}")

        parsed_pins.append({
            "index": current_list_index, # Internal 0-based index
            "original_index": original_index, # Original 1-based index for display/reference
            "lat": lat,
            "lon": lon,
            "type_id": pin_type_id,
            # Use the category and planet name resolved from config for display
            "type_name": f"{category} ({planet_name_from_config})", # Formatted name
            "category": category, # Just the category for styling/logic
            "schematic_id": schematic_id,
            "schematic_name": schematic_name # Store the retrieved name directly if available
        })

    logging.debug(f"--- Parsing Links ({len(links_data)} found) ---")
    parsed_links = []
    for i, link_raw in enumerate(links_data):
        if not isinstance(link_raw, dict):
            logging.warning(f"Link {i+1}: Invalid data format (expected dict, got {type(link_raw)}). Skipping.")
            continue

        source_idx_1based = link_raw.get("S")
        dest_idx_1based = link_raw.get("D")
        level = link_raw.get("Lv", 0)
        logging.debug(f"Raw Link {i+1}: S={source_idx_1based}, D={dest_idx_1based}, Lv={level}")

        if source_idx_1based is None or dest_idx_1based is None:
             logging.warning(f"Link {i + 1} missing 'S' or 'D' pin index. Skipping link. Data: {link_raw}")
             continue

        source_0_idx = pin_index_map.get(source_idx_1based)
        dest_0_idx = pin_index_map.get(dest_idx_1based)
        logging.debug(f"  Mapped indices: Source={source_0_idx}, Dest={dest_0_idx}")

        if source_0_idx is None or dest_0_idx is None:
            logging.warning(f"Link {i + 1} references invalid/skipped pin(s): S={source_idx_1based} -> {source_0_idx}, D={dest_idx_1based} -> {dest_0_idx}. Skipping link.")
            continue

        parsed_links.append({
            "source": source_0_idx, # Internal 0-based index
            "target": dest_0_idx, # Internal 0-based index
            "level": level
        })

    logging.debug(f"--- Parsing Routes ({len(routes_data)} found) ---")
    parsed_routes = []
    for i, route_raw in enumerate(routes_data):
        if not isinstance(route_raw, dict):
            logging.warning(f"Route {i+1}: Invalid data format (expected dict, got {type(route_raw)}). Skipping.")
            continue

        logging.debug(f"Raw Route {i+1}: {route_raw}") # Log raw route data
        path = route_raw.get("P") # Path is less reliable, prefer S/D
        source_idx_1based = route_raw.get("S") # Use direct S if available
        dest_idx_1based = route_raw.get("D")   # Use direct D if available
        # --- FIX: Use "T" instead of "Typ" for commodity ID ---
        commodity_id = route_raw.get("T") # Use 'T' for route commodity ID
        # --- END FIX ---
        quantity = route_raw.get("Qty", 0) # Use 'Qty' for quantity

        # --- Source/Destination Pin Index Resolution ---
        # Prefer S/D, fallback to P only if necessary and P is valid
        if source_idx_1based is None:
            if isinstance(path, list) and len(path) > 0:
                source_idx_1based = path[0]
                logging.debug(f"Route {i+1}: Missing 'S', using first element of 'P' ({source_idx_1based}) as source.") # Changed to debug
            else:
                logging.error(f"Route {i + 1}: Critical - Missing source pin index ('S' and invalid/missing 'P'). Skipping route. Data: {route_raw}")
                continue # Cannot proceed without a source

        if dest_idx_1based is None:
            if isinstance(path, list) and len(path) > 1:
                 dest_idx_1based = path[-1]
                 logging.debug(f"Route {i+1}: Missing 'D', using last element of 'P' ({dest_idx_1based}) as destination.") # Changed to debug
            else:
                 logging.error(f"Route {i + 1}: Critical - Missing destination pin index ('D' and invalid/missing 'P'). Skipping route. Data: {route_raw}")
                 continue # Cannot proceed without a destination

        # --- Commodity ID Resolution ---
        if commodity_id is None:
            # Attempt inference based on source pin's schematic output if 'T' is missing
            logging.warning(f"Route {i + 1}: Missing commodity type 'T'. Attempting inference from source pin {source_idx_1based}.")
            source_pin_0_idx = pin_index_map.get(source_idx_1based)
            if source_pin_0_idx is not None and source_pin_0_idx < len(parsed_pins):
                source_pin_data = parsed_pins[source_pin_0_idx]
                inferred_commodity_id = source_pin_data.get("schematic_id")
                if inferred_commodity_id is not None:
                    commodity_id = inferred_commodity_id
                    logging.info(f"Route {i + 1}: Successfully inferred commodity ID {commodity_id} from source pin {source_idx_1based}'s schematic.") # Changed to info
                else:
                    # Source pin exists but has no schematic_id (e.g., extractor, storage)
                    logging.warning(f"Route {i + 1}: Missing commodity type 'T'. Source pin {source_idx_1based} ({source_pin_data.get('category')}) has no schematic_id. Cannot infer type. Skipping route.")
                    continue
            else:
                # Source pin index itself is invalid (shouldn't happen if S/D checks passed, but safety)
                logging.warning(f"Route {i + 1}: Missing commodity type 'T' and source pin {source_idx_1based} could not be found in parsed pins. Skipping route.")
                continue
        # else: # Commodity ID was present in the raw data ('T' key)
        #     logging.debug(f"Route {i+1}: Found commodity ID {commodity_id} directly from 'T' key.")

        logging.debug(f"  Processing Route: SourceIdx={source_idx_1based}, DestIdx={dest_idx_1based}, CommodityID={commodity_id}, Qty={quantity}")

        # --- Map to internal 0-based indices ---
        source_0_idx = pin_index_map.get(source_idx_1based)
        dest_0_idx = pin_index_map.get(dest_idx_1based)
        logging.debug(f"  Mapped 0-based indices: Source={source_0_idx}, Dest={dest_0_idx}")

        # Check if mapping was successful (pins might have been skipped earlier)
        if source_0_idx is None or dest_0_idx is None:
            logging.warning(f"Route {i + 1} references invalid/skipped pin(s): S={source_idx_1based} -> {source_0_idx}, D={dest_idx_1based} -> {dest_0_idx}. Skipping route.")
            continue

        # --- Resolve commodity name ---
        commodity_name = config.get_commodity(commodity_id)
        logging.debug(f"  Commodity ID={commodity_id}, Resolved Name='{commodity_name}', Quantity={quantity}")
        if f"Unknown ({commodity_id})" in commodity_name:
            logging.debug(f"    -> Added commodity ID {commodity_id} to unknown set.")
            unknown_commodities.add(commodity_id)

        # --- Store parsed route information ---
        parsed_route_entry = {
            "source": source_0_idx,       # Internal 0-based index
            "target": dest_0_idx,       # Internal 0-based index
            "commodity_id": commodity_id,
            "commodity_name": commodity_name, # Store resolved name (includes 'Unknown (id)' if needed)
            "quantity": quantity
        }
        parsed_routes.append(parsed_route_entry)
        logging.debug(f"  Appended parsed route: {parsed_route_entry}")

    # --- Final Summary ---
    logging.info(f"Parsing complete. Found {len(parsed_pins)} valid pins, {len(parsed_links)} valid links, {len(parsed_routes)} valid routes.")
    # Convert sets to sorted lists for consistent output/handling
    final_unknown_commodities = sorted(list(unknown_commodities))
    final_unknown_pin_types = sorted(list(unknown_pin_types))

    if final_unknown_pin_types: logging.info(f"Unknown Pin Type IDs: {final_unknown_pin_types}")
    if final_unknown_commodities: logging.info(f"Unknown Commodity IDs (incl. schematics/routes): {final_unknown_commodities}")

    return {
        "pins": parsed_pins,
        "links": parsed_links,
        "routes": parsed_routes,
        "planet_id": planet_id,
        "planet_name": planet_name, # Include resolved planet name
        "unknowns": {
            "commodity": final_unknown_commodities,
            "pin_type": final_unknown_pin_types,
        },
        **metadata # Add other metadata like cmdctr, diameter, comment
    }
