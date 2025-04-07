import logging

def parse_pi_json(data, config):
    """
    Parses the raw EVE PI JSON data structure into a more usable format.
    Assumes Schematic ID == Output Commodity ID.

    Args:
        data (dict): The raw dictionary loaded from the JSON file.
        config (Config): The loaded configuration object for resolving IDs.

    Returns:
        dict: A dictionary containing parsed pins, links, routes, unknowns,
              and metadata.
    """
    pins_data = data.get("P", [])
    links_data = data.get("L", [])
    routes_data = data.get("R", [])
    metadata = {
        "cmdctr": data.get("CmdCtrLv"),
        "diameter": data.get("Diam"),
        "comment": data.get("Cmt")
    }
    logging.info(f"Raw data contains {len(pins_data)} pins, {len(links_data)} links, {len(routes_data)} routes.")

    parsed_pins = []
    unknown_pin_types = set()
    unknown_commodities = set() # Will now include unknown schematic IDs
    pin_index_map = {} # Maps original 1-based index from JSON to 0-based index in parsed_pins

    logging.debug("--- Parsing Pins ---")
    for i, pin in enumerate(pins_data):
        original_index = i + 1 # 1-based index from JSON list order
        pin_type_id = pin.get("T")
        schematic_id = pin.get("S") # This is the ID we assume == Output Commodity ID
        lat = pin.get("La", 0.0)
        lon = pin.get("Lo", 0.0)
        logging.debug(f"Raw Pin {original_index}: Type={pin_type_id}, Schematic={schematic_id}, Lat={lat}, Lon={lon}")

        if pin_type_id is None:
            logging.warning(f"Pin {original_index} missing 'T' (type ID). Skipping.")
            continue

        category, planet = config.get_pin_type(pin_type_id)
        schematic_info = None # Will be populated if schematic_id is valid
        schematic_name = None

        if category == "Unknown":
            logging.debug(f"  Pin {original_index}: Unknown pin type ID {pin_type_id}")
            unknown_pin_types.add(pin_type_id)

        if schematic_id is not None:
            # Try to get schematic info (name) using the schematic_id from commodities config
            schematic_info = config.get_schematic(schematic_id) # Uses get_commodity internally
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
            "type_name": f"{category} ({planet})", # Resolved name
            "category": category,
            "schematic_id": schematic_id,
            # Store the retrieved name directly if available
            "schematic_name": schematic_name
        })

    logging.debug(f"--- Parsing Links ({len(links_data)} found) ---")
    parsed_links = []
    for i, link in enumerate(links_data):
        source_idx_1based = link.get("S")
        dest_idx_1based = link.get("D")
        level = link.get("Lv", 0)
        logging.debug(f"Raw Link {i+1}: S={source_idx_1based}, D={dest_idx_1based}, Lv={level}")

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
    # unknown_commodities set is already defined above and includes schematic IDs
    for i, route in enumerate(routes_data):
        logging.debug(f"Raw Route {i+1}: {route}") # Log raw route data
        path = route.get("P") # Path is no longer used directly, S/D are preferred
        source_idx_1based = route.get("S") # Use direct S if available
        dest_idx_1based = route.get("D")   # Use direct D if available
        commodity_id = route.get("Typ") # Use 'Typ' for route commodity ID
        quantity = route.get("Qty", 0) # Use 'Qty' for quantity

        # Fallback to path if S/D are missing (less common but possible)
        if source_idx_1based is None and isinstance(path, list) and len(path) > 0:
            source_idx_1based = path[0]
            logging.warning(f"Route {i+1}: Missing 'S', using first element of 'P' ({source_idx_1based}) as source.")
        if dest_idx_1based is None and isinstance(path, list) and len(path) > 1:
             # Use last element of path as destination if 'D' is missing
             dest_idx_1based = path[-1]
             logging.warning(f"Route {i+1}: Missing 'D', using last element of 'P' ({dest_idx_1based}) as destination.")


        # Validate essential route data
        if source_idx_1based is None or dest_idx_1based is None:
             logging.warning(f"Route {i + 1} is missing valid source or destination pin index. Skipping route. Data: {route}")
             continue
        if commodity_id is None:
            # Attempt inference based on source pin's schematic output if Typ is missing
            source_pin_0_idx = pin_index_map.get(source_idx_1based)
            if source_pin_0_idx is not None:
                source_pin_data = parsed_pins[source_pin_0_idx]
                inferred_commodity_id = source_pin_data.get("schematic_id")
                if inferred_commodity_id is not None:
                    commodity_id = inferred_commodity_id
                    logging.warning(f"Route {i + 1} is missing commodity type 'Typ'. Inferred commodity ID {commodity_id} from source pin {source_idx_1based}'s schematic.")
                else:
                    logging.warning(f"Route {i + 1} is missing commodity type 'Typ' and source pin {source_idx_1based} has no schematic_id. Skipping route.")
                    continue
            else:
                logging.warning(f"Route {i + 1} is missing commodity type 'Typ' and source pin {source_idx_1based} could not be found. Skipping route.")
                continue

        logging.debug(f"  Processing Route: Source={source_idx_1based}, Dest={dest_idx_1based}, Commodity={commodity_id}, Qty={quantity}")

        # Map to internal 0-based indices
        source_0_idx = pin_index_map.get(source_idx_1based)
        dest_0_idx = pin_index_map.get(dest_idx_1based)
        logging.debug(f"  Mapped 0-based indices: Source={source_0_idx}, Dest={dest_0_idx}")

        # Check if mapping was successful
        if source_0_idx is None or dest_0_idx is None:
            logging.warning(f"Route {i + 1} references invalid/skipped pin(s): S={source_idx_1based} -> {source_0_idx}, D={dest_idx_1based} -> {dest_0_idx}. Skipping route.")
            continue

        # Resolve commodity name
        commodity_name = config.get_commodity(commodity_id)
        logging.debug(f"  Commodity ID={commodity_id}, Resolved Name='{commodity_name}', Quantity={quantity}")
        if f"Unknown ({commodity_id})" in commodity_name:
            logging.debug(f"    -> Added commodity ID {commodity_id} to unknown set.")
            unknown_commodities.add(commodity_id)

        # Store parsed route information using internal 0-based indices
        parsed_route_entry = {
            "source": source_0_idx,
            "target": dest_0_idx,
            "commodity_id": commodity_id,
            "commodity_name": commodity_name, # Store resolved name
            "quantity": quantity
        }
        parsed_routes.append(parsed_route_entry)
        logging.debug(f"  Appended parsed route: {parsed_route_entry}")

    logging.info(f"Parsing complete. Found {len(parsed_pins)} valid pins, {len(parsed_links)} valid links, {len(parsed_routes)} valid routes.")
    if unknown_pin_types: logging.info(f"Unknown Pin Type IDs: {sorted(list(unknown_pin_types))}")
    # Removed logging for unknown_schematics
    if unknown_commodities: logging.info(f"Unknown Commodity IDs (incl. schematics): {sorted(list(unknown_commodities))}")

    return {
        "pins": parsed_pins,
        "links": parsed_links,
        "routes": parsed_routes,
        "unknowns": {
            "commodity": sorted(list(unknown_commodities)),
            "pin_type": sorted(list(unknown_pin_types)),
            # Removed "schematic" key from unknowns
        },
        **metadata
    }
