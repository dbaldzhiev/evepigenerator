import json
import os
import shutil
import datetime
import logging

class Config:
    def __init__(self, path):
        self.path = path
        try:
            with open(path, 'r') as f:
                self.data = json.load(f)
        except FileNotFoundError:
            logging.error(f"Configuration file not found at {path}")
            raise
        except json.JSONDecodeError as e:
            logging.error(f"Error decoding JSON from {path}: {e}")
            raise

        # --- One-time Migration from separate 'schematics' to 'commodities' ---
        if "schematics" in self.data:
            logging.warning(f"Found legacy 'schematics' section in {self.path}. Migrating to 'commodities'.")
            migrated_count = 0
            schematics_to_migrate = self.data.get("schematics", {})
            commodities = self.data.setdefault("commodities", {}) # Ensure commodities exists

            for sch_id_str, sch_data in schematics_to_migrate.items():
                name = sch_data.get("name")
                if name:
                    if sch_id_str not in commodities or commodities[sch_id_str] != name:
                        logging.info(f"  Migrating Schematic ID {sch_id_str} ('{name}') to commodities.")
                        commodities[sch_id_str] = name
                        migrated_count += 1
                    else:
                         logging.debug(f"  Schematic ID {sch_id_str} ('{name}') already exists correctly in commodities. Skipping migration for this ID.")
                else:
                    logging.warning(f"  Skipping migration for Schematic ID {sch_id_str}: missing 'name'.")

            del self.data["schematics"]
            logging.info(f"Removed legacy 'schematics' section. Migrated {migrated_count} new/updated entries to 'commodities'.")
            try:
                self.save()
                logging.info("Configuration saved automatically after migration.")
            except Exception as e:
                logging.error(f"Failed to save configuration automatically after migration: {e}")
        # --- End Migration ---


    def get_pin_type(self, type_id):
        """Gets the category and planet name for a pin type ID."""
        # Ensure type_id is treated as string for lookup
        type_id_str = str(type_id) if type_id is not None else "Unknown"
        meta = self.data.get("pin_types", {}).get(type_id_str)
        if meta:
            return meta.get("category", "Unknown"), meta.get("planet", "Unknown")
        return "Unknown", "Unknown"

    def get_commodity(self, commodity_id):
        """Gets the name for a commodity ID."""
        # Ensure commodity_id is treated as string for lookup
        commodity_id_str = str(commodity_id) if commodity_id is not None else "Unknown"
        return self.data.get("commodities", {}).get(commodity_id_str, f"Unknown ({commodity_id_str})")

    # get_schematic is essentially identical to get_commodity now.
    # We can keep it for backward compatibility within the parser or remove it
    # and update the parser to use get_commodity directly. Let's keep it for now
    # but acknowledge it's just a wrapper.
    def get_schematic(self, schematic_id):
        """
        Retrieves schematic info (name) by looking up the schematic_id in the
        commodities map. Returns a dict or None.
        """
        name = self.get_commodity(schematic_id)
        if f"Unknown ({schematic_id})" in name:
             return None # Return None if the commodity name is unknown
        return {"name": name} # Return in a dict structure

    def get_planet_name(self, planet_id):
        """Looks up the planet name from its ID in the config."""
        # Use 0 as a fallback ID if planet_id is None or invalid
        lookup_id = str(planet_id) if planet_id is not None else "0"
        # Provide a more descriptive unknown if the ID itself was None/invalid
        default_name = "Unknown Planet (ID Missing)" if planet_id is None else f"Unknown Planet (ID: {lookup_id})"
        return self.data.get("planet_types", {}).get(lookup_id, default_name)

    def add_commodity(self, id, name):
        """Adds or updates a commodity ID and name."""
        commodities = self.data.setdefault("commodities", {})
        commodities[str(id)] = name
        logging.info(f"Added/Updated commodity: ID={id}, Name='{name}'")

    def add_pin_type(self, id, category, planet="Generic"):
        """Adds or updates a pin type ID with category and planet."""
        pin_types = self.data.setdefault("pin_types", {})
        pin_types[str(id)] = { "category": category, "planet": planet }
        logging.info(f"Added/Updated pin type: ID={id}, Category='{category}', Planet='{planet}'")

    def save(self):
        """Saves the current configuration data to the file, creating a backup first."""
        # Backup before writing
        backup_dir = os.path.join(os.path.dirname(self.path), "backup")
        os.makedirs(backup_dir, exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = os.path.join(backup_dir, f"config_backup_{timestamp}.json")

        if os.path.exists(self.path):
             try:
                 shutil.copy2(self.path, backup_file)
                 logging.info(f"Configuration backup created at {backup_file}")
             except Exception as e:
                 logging.error(f"Failed to create configuration backup: {e}")
        else:
             logging.warning(f"Original config file {self.path} not found. Skipping backup.")

        try:
            with open(self.path, 'w') as f:
                # Ensure top-level keys exist even if empty
                self.data.setdefault("commodities", {})
                self.data.setdefault("pin_types", {})
                self.data.setdefault("planet_types", {})
                json.dump(self.data, f, indent=2, sort_keys=True) # Sort keys for consistency
            logging.info(f"Configuration saved successfully to {self.path}")
        except Exception as e:
             logging.error(f"Failed to save configuration to {self.path}: {e}")
             raise # Re-raise so the caller knows saving failed
