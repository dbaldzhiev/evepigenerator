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
            # Initialize with defaults if file not found? Or raise? Let's raise for now.
            raise
        except json.JSONDecodeError as e:
            logging.error(f"Error decoding JSON from {path}: {e}")
            raise

        # Ensure ui_settings and label_display exist, using defaults if necessary
        ui_settings = self.data.setdefault("ui_settings", {})
        label_settings = ui_settings.setdefault("label_display", {})
        # Populate missing default keys without overwriting existing ones
        for key, default_value in self.DEFAULT_LABEL_SETTINGS.items():
            label_settings.setdefault(key, default_value)
        logging.debug(f"Initialized/Loaded label settings: {label_settings}")


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
        type_id_str = str(type_id) if type_id is not None else "Unknown"
        meta = self.data.get("pin_types", {}).get(type_id_str)
        if meta:
            return meta.get("category", "Unknown"), meta.get("planet", "Unknown")
        return "Unknown", "Unknown"

    def get_commodity(self, commodity_id):
        """Gets the name for a commodity ID."""
        commodity_id_str = str(commodity_id) if commodity_id is not None else "Unknown"
        return self.data.get("commodities", {}).get(commodity_id_str, f"Unknown ({commodity_id_str})")

    def get_schematic(self, schematic_id):
        """
        Retrieves schematic info (name) by looking up the schematic_id in the
        commodities map. Returns a dict or None.
        """
        name = self.get_commodity(schematic_id)
        if f"Unknown ({schematic_id})" in name:
             return None
        return {"name": name}

    def get_planet_name(self, planet_id):
        """Looks up the planet name from its ID in the config."""
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

    # --- Label Settings Methods ---
    def get_label_settings(self):
        """Returns the current label display settings dictionary."""
        # Ensure defaults are loaded if keys are missing (should be handled by __init__)
        settings = self.data.get("ui_settings", {}).get("label_display", {})
        # Make sure all default keys are present in the returned dict
        return {key: settings.get(key, default_value)
                for key, default_value in self.DEFAULT_LABEL_SETTINGS.items()}

    # --- NEW: Method to update label settings in the config data ---
    def save_label_settings(self, settings_dict):
        """
        Updates the label display settings within the config data structure.
        Does NOT save to file; call self.save() externally for that.

        Args:
            settings_dict (dict): A dictionary containing the label settings
                                  (e.g., {'show_pin_name': True, ...}).

        Returns:
            bool: True if settings were updated successfully, False otherwise.
        """
        if not isinstance(settings_dict, dict):
            logging.error(f"Attempted to save invalid label settings (not a dict): {settings_dict}")
            return False

        # Ensure the ui_settings section exists
        ui_settings = self.data.setdefault("ui_settings", {})

        # Validate keys against defaults before saving, only keep known keys
        valid_settings = {}
        for key, default_value in self.DEFAULT_LABEL_SETTINGS.items():
            # Use the value from settings_dict if present, otherwise keep default
            # Ensure the value is a boolean
            valid_settings[key] = bool(settings_dict.get(key, default_value))

        # Update the label_display section
        ui_settings["label_display"] = valid_settings
        logging.info(f"Updating label settings in config data (will be saved on next Config.save()): {valid_settings}")
        # The actual saving to file happens when self.save() is called externally
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
                # Ensure top-level keys exist even if empty
                self.data.setdefault("commodities", {})
                self.data.setdefault("pin_types", {})
                self.data.setdefault("planet_types", {})
                # Ensure ui_settings and label_display exist before saving
                ui_settings = self.data.setdefault("ui_settings", {})
                ui_settings.setdefault("label_display", self.DEFAULT_LABEL_SETTINGS)

                json.dump(self.data, f, indent=2, sort_keys=True)
            logging.info(f"Configuration saved successfully to {self.path}")
        except Exception as e:
             logging.error(f"Failed to save configuration to {self.path}: {e}")
             raise # Re-raise the exception so the caller knows saving failed
