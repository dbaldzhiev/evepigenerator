import tkinter as tk
from tkinter import ttk, messagebox

def resolve_unknown_ids(unknowns, id_type, known_options, config, update_callback):
    if not unknowns:
        return

    root = tk.Toplevel()
    root.title(f"Resolve Unknown {id_type.replace('_', ' ').capitalize()} IDs")
    root.geometry("450x400") # Adjust size as needed
    root.grab_set() # Make window modal

    main_frame = tk.Frame(root, padx=10, pady=10)
    main_frame.pack(fill="both", expand=True)

    tk.Label(main_frame, text=f"Found {len(unknowns)} unknown {id_type.replace('_', ' ').lower()}(s). Please provide names/types:", justify=tk.LEFT).pack(pady=(0, 10), anchor="w")

    entries = []
    for uid in unknowns:
        frame = tk.Frame(main_frame)
        frame.pack(pady=3, fill="x")

        label = tk.Label(frame, text=f"ID {uid}:", width=10, anchor="w")
        label.pack(side="left", padx=(0, 5))

        if id_type == "schematic":
            # Use Entry for schematic names
            entry = tk.Entry(frame, width=35)
            entry.insert(0, "Enter Schematic Name")
            entry.pack(side="left", fill="x", expand=True)
            entries.append((uid, entry, "entry")) # Store type
        else:
            # Use Combobox for commodities and pin_types
            # Ensure known_options contains unique, sorted strings
            unique_options = sorted(list(set(map(str, known_options))))
            combo = ttk.Combobox(frame, values=unique_options, width=33)
            combo.set("Select or type...")
            combo.pack(side="left", fill="x", expand=True)
            entries.append((uid, combo, "combo")) # Store type

    def apply():
        resolved_count = 0
        for uid, widget, widget_type in entries:
            if widget_type == "combo":
                selection = widget.get()
                if selection and selection != "Select or type...":
                    if id_type == "commodity":
                        config.add_commodity(uid, selection)
                        resolved_count += 1
                    elif id_type == "pin_type":
                        # Assuming selection is the category name
                        config.add_pin_type(uid, category=selection, planet="Unknown") # Default planet
                        resolved_count += 1
            elif widget_type == "entry":
                name = widget.get()
                if name and name != "Enter Schematic Name":
                    if id_type == "schematic":
                        config.add_schematic(uid, name) # Add schematic requires name only initially
                        resolved_count += 1

        if resolved_count > 0:
            try:
                config.save()
                messagebox.showinfo("Saved", f"{resolved_count} unknown ID(s) resolved and configuration saved.", parent=root)
                update_callback() # Trigger the refresh in the main app
            except Exception as e:
                 messagebox.showerror("Error", f"Failed to save configuration: {e}", parent=root)
        else:
             messagebox.showwarning("No Changes", "No valid selections or entries were made.", parent=root)

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
