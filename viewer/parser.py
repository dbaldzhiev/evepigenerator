import logging

def parse_pi_json(data, config):
    """
    Parses the raw EVE PI JSON data structure into a more usable format.

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
    unknown_schematics = set()
    pin_index_map = {} # Maps original 1-based index from JSON to 0-based index in parsed_pins

    logging.debug("--- Parsing Pins ---")
    for i, pin in enumerate(pins_data):
        original_index = i + 1 # 1-based index from JSON list order
        pin_type_id = pin.get("T")
        schematic_id = pin.get("S")
        lat = pin.get("La", 0.0)
        lon = pin.get("Lo", 0.0)
        logging.debug(f"Raw Pin {original_index}: Type={pin_type_id}, Schematic={schematic_id}, Lat={lat}, Lon={lon}")

        if pin_type_id is None:
            logging.warning(f"Pin {original_index} missing 'T' (type ID). Skipping.")
            continue

        category, planet = config.get_pin_type(pin_type_id)
        schematic_info = config.get_schematic(schematic_id) if schematic_id is not None else None

        if category == "Unknown":
            logging.debug(f"  Pin {original_index}: Unknown pin type ID {pin_type_id}")
            unknown_pin_types.add(pin_type_id)
        if schematic_id is not None and schematic_info is None:
            logging.debug(f"  Pin {original_index}: Unknown schematic ID {schematic_id}")
            unknown_schematics.add(schematic_id)

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
            "schematic": schematic_info # Resolved schematic details or None
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
    unknown_commodities = set()
    for i, route in enumerate(routes_data):
        logging.debug(f"Raw Route {i+1}: {route}") # Log raw route data
        path = route.get("P")
        commodity_id = route.get("T")
        quantity = route.get("Q", 0)

        # Validate essential route data
        if not isinstance(path, list) or len(path) < 2:
            logging.warning(f"Route {i + 1} has invalid 'P' path (must be list with >= 2 elements): {path}. Skipping route.")
            continue
        if commodity_id is None:
            logging.warning(f"Route {i + 1} is missing commodity type 'T'. Skipping route.")
            continue

        # Extract source and destination from the path list (1-based indices)
        source_idx_1based = path[0]
        dest_idx_1based = path[-1]
        logging.debug(f"  Extracted 1-based indices from path {path}: Source={source_idx_1based}, Dest={dest_idx_1based}")

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
        if "Unknown" in commodity_name:
            logging.debug(f"    -> Added commodity ID {commodity_id} to unknown set.")
            unknown_commodities.add(commodity_id)

        # Store parsed route information using internal 0-based indices
        parsed_route_entry = {
            "source": source_0_idx,
            "target": dest_0_idx,
            "commodity_id": commodity_id,
            "commodity_name": commodity_name,
            "quantity": quantity
        }
        parsed_routes.append(parsed_route_entry)
        logging.debug(f"  Appended parsed route: {parsed_route_entry}")

    logging.info(f"Parsing complete. Found {len(parsed_pins)} valid pins, {len(parsed_links)} valid links, {len(parsed_routes)} valid routes.")
    if unknown_pin_types: logging.info(f"Unknown Pin Type IDs: {sorted(list(unknown_pin_types))}")
    if unknown_schematics: logging.info(f"Unknown Schematic IDs: {sorted(list(unknown_schematics))}")
    if unknown_commodities: logging.info(f"Unknown Commodity IDs: {sorted(list(unknown_commodities))}")

    return {
        "pins": parsed_pins,
        "links": parsed_links,
        "routes": parsed_routes,
        "unknowns": {
            "commodity": sorted(list(unknown_commodities)),
            "pin_type": sorted(list(unknown_pin_types)),
            "schematic": sorted(list(unknown_schematics))
        },
        **metadata
    }
