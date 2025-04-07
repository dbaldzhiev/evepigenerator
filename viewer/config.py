import json
import os
import shutil
import datetime

class Config:
    def __init__(self, path):
        self.path = path
        with open(path, 'r') as f:
            self.data = json.load(f)

    def get_pin_type(self, type_id):
        meta = self.data["pin_types"].get(str(type_id))
        if meta:
            return meta.get("category", "Unknown"), meta.get("planet", "Unknown")
        return "Unknown", "Unknown"

    def get_commodity(self, commodity_id):
        return self.data["commodities"].get(str(commodity_id), f"Unknown ({commodity_id})")

    def get_schematic(self, schematic_id):
        return self.data["schematics"].get(str(schematic_id), None)

    def add_commodity(self, id, name):
        self.data["commodities"][str(id)] = name

    def add_pin_type(self, id, category, planet="Generic"):
        self.data["pin_types"][str(id)] = { "category": category, "planet": planet }

    def add_schematic(self, id, name):
        self.data["schematics"][str(id)] = { "name": name, "inputs": [], "output": int(id) }

    def save(self):
        # Backup before writing
        backup_dir = os.path.join(os.path.dirname(self.path), "backup")
        os.makedirs(backup_dir, exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = os.path.join(backup_dir, f"config_backup_{timestamp}.json")
        shutil.copy2(self.path, backup_file)

        with open(self.path, 'w') as f:
            json.dump(self.data, f, indent=2)
