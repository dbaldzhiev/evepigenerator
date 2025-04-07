import json
import os
import shutil
import datetime
import logging # Added for migration logging

class Config:
    def __init__(self, path):
        self.path = path
        try:
            with open(path, 'r') as f:
                self.data = json.load(f)
        except FileNotFoundError:
            # Re-raise or handle as appropriate for the application startup
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
                    # Check if ID exists in commodities or if name differs
                    if sch_id_str not in commodities or commodities[sch_id_str] != name:
                        logging.info(f"  Migrating Schematic ID {sch_id_str} ('{name}') to commodities.")
                        commodities[sch_id_str] = name
                        migrated_count += 1
                    else:
                         logging.debug(f"  Schematic ID {sch_id_str} ('{name}') already exists correctly in commodities. Skipping migration for this ID.")
                else:
                    logging.warning(f"  Skipping migration for Schematic ID {sch_id_str}: missing 'name'.")

            # Remove the old schematics section after migration attempt
            del self.data["schematics"]
            logging.info(f"Removed legacy 'schematics' section. Migrated {migrated_count} new/updated entries to 'commodities'.")
            # Optionally save immediately after migration
            try:
                self.save()
                logging.info("Configuration saved automatically after migration.")
            except Exception as e:
                logging.error(f"Failed to save configuration automatically after migration: {e}")
        # --- End Migration ---


    def get_pin_type(self, type_id):
        meta = self.data.get("pin_types", {}).get(str(type_id)) # Added default {}
        if meta:
            return meta.get("category", "Unknown"), meta.get("planet", "Unknown")
        return "Unknown", "Unknown"

    def get_commodity(self, commodity_id):
        # Ensure commodity_id is treated as string for lookup
        return self.data.get("commodities", {}).get(str(commodity_id), f"Unknown ({commodity_id})") # Added default {}

    def get_schematic(self, schematic_id):
        """
        Retrieves schematic info (currently just the name) by looking up
        the schematic_id in the commodities map, assuming SchematicID == OutputCommodityID.
        """
        name = self.get_commodity(schematic_id)
        if f"Unknown ({schematic_id})" in name:
             return None # Return None if the commodity name is unknown
        return {"name": name} # Return in a dict structure for potential future expansion

    # --- New Method ---
    def get_planet_name(self, planet_id):
        """Looks up the planet name from its ID in the config."""
        # Use 0 as a fallback ID if planet_id is None or invalid
        lookup_id = str(planet_id) if planet_id is not None else "0"
        return self.data.get("planet_types", {}).get(lookup_id, "Unknown")
    # --- End New Method ---

    def add_commodity(self, id, name):
        commodities = self.data.setdefault("commodities", {})
        commodities[str(id)] = name

    def add_pin_type(self, id, category, planet="Generic"):
        pin_types = self.data.setdefault("pin_types", {})
        pin_types[str(id)] = { "category": category, "planet": planet }

    # Removed add_schematic method

    def save(self):
        # Backup before writing
        backup_dir = os.path.join(os.path.dirname(self.path), "backup")
        os.makedirs(backup_dir, exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = os.path.join(backup_dir, f"config_backup_{timestamp}.json")

        # Ensure the file exists before trying to copy
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
                # Ensure 'commodities', 'pin_types', and 'planet_types' keys exist even if empty
                self.data.setdefault("commodities", {})
                self.data.setdefault("pin_types", {})
                self.data.setdefault("planet_types", {}) # Ensure planet_types exists
                json.dump(self.data, f, indent=2, sort_keys=True) # Sort keys for consistency
            logging.info(f"Configuration saved successfully to {self.path}")
        except Exception as e:
             logging.error(f"Failed to save configuration to {self.path}: {e}")
             # Re-raise the exception so the caller knows saving failed
             raise

