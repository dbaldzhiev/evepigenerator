import tkinter as tk
from tkinter import ttk, messagebox
import logging # Added

# --- Updated function signature ---
def resolve_unknown_ids(unknown_ids, id_type, known_options, config, update_callback, planet_id=None):
    """
    Opens a dialog to resolve unknown IDs (commodities or pin types).

    Args:
        unknown_ids (list): List of unknown IDs (integers or strings).
        id_type (str): Type of ID being resolved ('commodity' or 'pin_type').
        known_options (list): List of known names/categories for suggestions.
        config (Config): The configuration object to update.
        update_callback (callable): Function to call after successful save.
        planet_id (int, optional): The planet ID from the current JSON, used for pin types. Defaults to None.
    """
    if not unknown_ids:
        return

    root = tk.Toplevel()
    root.title(f"Resolve Unknown {id_type.replace('_', ' ').capitalize()} IDs")
    root.geometry("450x400") # Adjust size as needed
    root.grab_set() # Make window modal

    main_frame = tk.Frame(root, padx=10, pady=10)
    main_frame.pack(fill="both", expand=True)

    tk.Label(main_frame, text=f"Found {len(unknown_ids)} unknown {id_type.replace('_', ' ').lower()}(s). Please provide names/types:", justify=tk.LEFT).pack(pady=(0, 10), anchor="w")

    entries = []
    for uid in unknown_ids:
        frame = tk.Frame(main_frame)
        frame.pack(pady=3, fill="x")

        label = tk.Label(frame, text=f"ID {uid}:", width=10, anchor="w")
        label.pack(side="left", padx=(0, 5))

        # Use Combobox for both commodities and pin_types
        # Schematic IDs will be resolved as commodities now.
        if id_type == "commodity":
            # Provide existing commodity names as suggestions
            unique_options = sorted(list(set(map(str, config.data.get("commodities", {}).values()))))
            combo = ttk.Combobox(frame, values=unique_options, width=33)
            combo.set("Select or type name...") # Changed default text
            combo.pack(side="left", fill="x", expand=True)
            entries.append((uid, combo, "combo")) # Store type
        elif id_type == "pin_type":
             # Ensure known_options contains unique, sorted strings
            unique_options = sorted(list(set(map(str, known_options))))
            combo = ttk.Combobox(frame, values=unique_options, width=33)
            combo.set("Select or type category...") # Changed default text
            combo.pack(side="left", fill="x", expand=True)
            entries.append((uid, combo, "combo")) # Store type
        # Removed the 'entry' type for schematics

    def apply():
        resolved_count = 0
        ids_to_resolve = [] # Store tuples (id, value)

        for uid, widget, widget_type in entries:
            # Only handle combo boxes now
            if widget_type == "combo":
                selection = widget.get()
                # Check if selection is meaningful
                if selection and not selection.startswith("Select or type"):
                    ids_to_resolve.append((uid, selection))

        if not ids_to_resolve:
             messagebox.showwarning("No Changes", "No valid selections or entries were made.", parent=root)
             root.destroy()
             return

        # --- Get Planet Name if resolving pin types ---
        resolved_planet_name = "Unknown" # Default
        if id_type == "pin_type":
            # Look up the planet name using the provided planet_id
            resolved_planet_name = config.get_planet_name(planet_id)
            logging.info(f"Using planet name '{resolved_planet_name}' for new pin types (resolved from ID: {planet_id})")
        # --- End Get Planet Name ---


        # Apply changes to config object
        for uid, selection in ids_to_resolve:
             if id_type == "commodity":
                 logging.info(f"Adding/Updating commodity: ID={uid}, Name='{selection}'")
                 config.add_commodity(uid, selection)
                 resolved_count += 1
             elif id_type == "pin_type":
                 # Assuming selection is the category name
                 # --- Use the resolved planet name ---
                 logging.info(f"Adding/Updating pin type: ID={uid}, Category='{selection}', Planet='{resolved_planet_name}'")
                 # Pass the resolved planet name to add_pin_type
                 config.add_pin_type(uid, category=selection, planet=resolved_planet_name)
                 resolved_count += 1

        if resolved_count > 0:
            try:
                config.save() # Save the updated config object
                messagebox.showinfo("Saved", f"{resolved_count} unknown ID(s) resolved and configuration saved.", parent=root)
                if update_callback:
                    update_callback() # Trigger the refresh in the main app
            except Exception as e:
                 messagebox.showerror("Error", f"Failed to save configuration: {e}", parent=root)
                 logging.error(f"Failed to save configuration after resolving IDs: {e}")
        else:
             # This case should ideally not be reached due to the check above, but kept as safety
             messagebox.showwarning("No Changes Applied", "No valid selections resulted in configuration changes.", parent=root)


        root.destroy()

    def cancel():
        root.destroy()

    button_frame = tk.Frame(main_frame)
    button_frame.pack(pady=(15, 0), fill="x")

    apply_btn = tk.Button(button_frame, text="Apply and Save", command=apply, bg="#1abc9c", fg="white", relief=tk.FLAT)
    apply_btn.pack(side="right", padx=(5, 0))

    cancel_btn = tk.Button(button_frame, text="Cancel", command=cancel, bg="#bdc3c7", fg="white", relief=tk.FLAT)
    cancel_btn.pack(side="right")

    root.wait_window() # Wait until the window is closed
