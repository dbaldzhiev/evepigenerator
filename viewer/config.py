import json
import os
import shutil
import datetime
import logging

class Config:
    DEFAULT_LABEL_SETTINGS = {
        "show_pin_name": True,
        "show_pin_id": True,
        "show_schematic_name": True,
        "show_schematic_id": False,
    }

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

        # Ensure ui_settings and label_display exist, using defaults if necessary
        ui_settings = self.data.setdefault("ui_settings", {})
        label_settings = ui_settings.setdefault("label_display", {})
        for key, default_value in self.DEFAULT_LABEL_SETTINGS.items():
            label_settings.setdefault(key, default_value)
        logging.debug(f"Initialized/Loaded label settings: {label_settings}")

        # --- Migration (Keep as is) ---
        if "schematics" in self.data:
            logging.warning(f"Found legacy 'schematics' section in {self.path}. Migrating to 'commodities'.")
            migrated_count = 0
            schematics_to_migrate = self.data.get("schematics", {})
            commodities = self.data.setdefault("commodities", {})
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
        type_id_str = str(type_id) if type_id is not None else "Unknown"
        meta = self.data.get("pin_types", {}).get(type_id_str)
        if meta:
            return meta.get("category", "Unknown"), meta.get("planet", "Unknown")
        return "Unknown", "Unknown"

    # --- NEW Helper Function ---
    def get_pin_type_id_by_category(self, category_name, planet_name="Generic"):
        """
        Finds the first pin type ID matching a category and optionally a planet.
        Tries specific planet first, then 'Generic', then 'Unknown'.

        Args:
            category_name (str): The category to search for (e.g., "Basic Industrial Facility").
            planet_name (str): The desired planet name (e.g., "Barren"). Defaults to "Generic".

        Returns:
            int: The pin type ID, or None if not found.
        """
        pin_types = self.data.get("pin_types", {})
        found_id = None

        # Prioritize specific planet match
        if planet_name != "Generic" and planet_name != "Unknown":
            for type_id_str, meta in pin_types.items():
                if meta.get("category") == category_name and meta.get("planet") == planet_name:
                    logging.debug(f"Found pin ID {type_id_str} for category '{category_name}' on planet '{planet_name}'")
                    return int(type_id_str)

        # Fallback to Generic planet match
        for type_id_str, meta in pin_types.items():
             if meta.get("category") == category_name and meta.get("planet", "Generic") == "Generic":
                 logging.debug(f"Found pin ID {type_id_str} for category '{category_name}' on planet 'Generic'")
                 return int(type_id_str)

        # Fallback to Unknown planet match (less ideal)
        for type_id_str, meta in pin_types.items():
             if meta.get("category") == category_name and meta.get("planet", "Unknown") == "Unknown":
                 logging.warning(f"Using pin ID {type_id_str} for category '{category_name}' with planet 'Unknown' as fallback.")
                 return int(type_id_str)

        logging.error(f"Could not find any pin type ID for category '{category_name}' matching planet '{planet_name}' or fallbacks.")
        return None
    # --- END NEW ---

    def get_commodity(self, commodity_id):
        """Gets the name for a commodity ID."""
        commodity_id_str = str(commodity_id) if commodity_id is not None else "Unknown"
        return self.data.get("commodities", {}).get(commodity_id_str, f"Unknown ({commodity_id_str})")

    def get_schematic(self, schematic_id):
        """Retrieves schematic name by looking up the ID in commodities."""
        name = self.get_commodity(schematic_id)
        if f"Unknown ({schematic_id})" in name:
             return None
        return {"name": name}

    def get_planet_name(self, planet_id):
        """Looks up the planet name from its ID."""
        lookup_id = str(planet_id) if planet_id is not None else "0"
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

    def get_label_settings(self):
        """Returns the current label display settings dictionary."""
        settings = self.data.get("ui_settings", {}).get("label_display", {})
        return {key: settings.get(key, default_value)
                for key, default_value in self.DEFAULT_LABEL_SETTINGS.items()}

    def save_label_settings(self, settings_dict):
        """Updates the label display settings within the config data structure."""
        if not isinstance(settings_dict, dict):
            logging.error(f"Attempted to save invalid label settings (not a dict): {settings_dict}")
            return False
        ui_settings = self.data.setdefault("ui_settings", {})
        valid_settings = {}
        for key, default_value in self.DEFAULT_LABEL_SETTINGS.items():
            valid_settings[key] = bool(settings_dict.get(key, default_value))
        ui_settings["label_display"] = valid_settings
        logging.info(f"Updating label settings in config data: {valid_settings}")
        return True

    def save(self):
        """Saves the current configuration data to the file, creating a backup first."""
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
                self.data.setdefault("commodities", {})
                self.data.setdefault("pin_types", {})
                self.data.setdefault("planet_types", {})
                ui_settings = self.data.setdefault("ui_settings", {})
                ui_settings.setdefault("label_display", self.DEFAULT_LABEL_SETTINGS)
                json.dump(self.data, f, indent=2, sort_keys=True)
            logging.info(f"Configuration saved successfully to {self.path}")
        except Exception as e:
             logging.error(f"Failed to save configuration to {self.path}: {e}")
             raise

