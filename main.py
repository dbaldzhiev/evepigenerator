import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog, scrolledtext
from viewer.config import Config
from viewer.parser import parse_pi_json
from viewer.visualizer import render_matplotlib_plot
from viewer.id_editor import resolve_unknown_ids
# Import new generator function and loader
from viewer.generator import generate_pi_layout, load_production_data
import os
import json
import logging
import pyperclip # For copy to clipboard

# --- Configuration ---
CONFIG_PATH = "viewer/assets/config.json"
TEMPLATE_DIR = "templates"
LOG_FILE = "pi_viewer.log"
CSV_DIR = "docs" # Directory for P1-P4 CSVs

# --- Logging Setup ---
logging.basicConfig(filename=LOG_FILE, level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - [%(module)s:%(lineno)d] - %(message)s')

# --- Generator Dialog Class ---
class GeneratorDialog(tk.Toplevel):
    def __init__(self, parent, config, app_instance):
        super().__init__(parent)
        self.config = config
        self.app_instance = app_instance # To call process_json_string
        self.production_data = None # Loaded later
        self.title("PI Layout Generator (Fixed Layout)")
        self.geometry("600x550") # Adjusted size
        self.resizable(False, False)
        self.grab_set() # Make modal

        # --- Load Production Data ---
        self.production_data = load_production_data(self.config, CSV_DIR)
        if not self.production_data:
             messagebox.showerror("Generator Error",
                                  f"Failed to load production data from CSVs in '{CSV_DIR}'.\n"
                                  "Generator cannot function without it. Check logs.", parent=parent)
             self.destroy() # Close dialog if data loading fails
             return

        # --- Data for Comboboxes ---
        self.storage_types = self._get_pin_types_by_category(["Storage Facility"])
        self.launchpad_types = self._get_pin_types_by_category(["Launchpad"])
        self.commodities = self._get_commodities() # All commodities for input validation

        # --- UI Elements ---
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill="both", expand=True)

        # --- Input Frame ---
        input_frame = ttk.LabelFrame(main_frame, text="Parameters", padding="10")
        input_frame.pack(fill="x", pady=(0, 10))
        # ***** TYPO FIX HERE *****
        input_frame.columnconfigure(1, weight=1) # Make entry/combobox expand

        # Storage Type
        ttk.Label(input_frame, text="Storage Type:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.storage_type_var = tk.StringVar()
        self.storage_type_combo = ttk.Combobox(input_frame, textvariable=self.storage_type_var,
                                                values=list(self.storage_types.keys()), state="readonly")
        if self.storage_types:
             self.storage_type_var.set(list(self.storage_types.keys())[0])
        self.storage_type_combo.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

        # Launchpad Type
        ttk.Label(input_frame, text="Launchpad Type:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.launchpad_type_var = tk.StringVar()
        self.launchpad_type_combo = ttk.Combobox(input_frame, textvariable=self.launchpad_type_var,
                                                values=list(self.launchpad_types.keys()), state="readonly")
        if self.launchpad_types:
             self.launchpad_type_var.set(list(self.launchpad_types.keys())[0])
        self.launchpad_type_combo.grid(row=1, column=1, padx=5, pady=5, sticky="ew")

        # Schematic Counts Input
        ttk.Label(input_frame, text="Schematics (Name: Count):").grid(row=2, column=0, padx=5, pady=5, sticky="nw")
        self.schematics_text = scrolledtext.ScrolledText(input_frame, wrap=tk.WORD, height=7, width=40)
        self.schematics_text.grid(row=2, column=1, padx=5, pady=5, sticky="ew")
        self.schematics_text.bind("<FocusIn>", self.clear_placeholder)
        self.schematics_text.bind("<FocusOut>", self.add_placeholder)
        self.placeholder_active = True
        self.add_placeholder(None)

        # --- Output Frame ---
        output_frame = ttk.LabelFrame(main_frame, text="Generated JSON", padding="10")
        output_frame.pack(fill="both", expand=True, pady=(0, 10))

        self.output_text = scrolledtext.ScrolledText(output_frame, wrap=tk.WORD, height=10, state=tk.DISABLED)
        self.output_text.pack(fill="both", expand=True)

        # --- Button Frame ---
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill="x")

        self.generate_button = ttk.Button(button_frame, text="Generate", command=self.do_generate)
        self.generate_button.pack(side="left", padx=(0, 5))

        self.copy_button = ttk.Button(button_frame, text="Copy to Clipboard", command=self.copy_to_clipboard, state=tk.DISABLED)
        self.copy_button.pack(side="left", padx=5)

        self.load_button = ttk.Button(button_frame, text="Load in Viewer", command=self.load_in_viewer, state=tk.DISABLED)
        self.load_button.pack(side="left", padx=5)

        self.cancel_button = ttk.Button(button_frame, text="Close", command=self.destroy)
        self.cancel_button.pack(side="right")

        self.protocol("WM_DELETE_WINDOW", self.destroy)

    # --- Placeholder Logic (Keep as is) ---
    def clear_placeholder(self, event):
        if self.placeholder_active:
            self.schematics_text.delete("1.0", tk.END)
            self.schematics_text.config(fg='black')
            self.placeholder_active = False

    def add_placeholder(self, event):
        if not self.schematics_text.get("1.0", tk.END).strip():
            self.schematics_text.insert("1.0", "Enter schematics, one per line:\nCommodity Name: Count\n\nExample:\nBiofuels: 4\nBacteria: 8")
            self.schematics_text.config(fg='grey')
            self.placeholder_active = True

    # --- Helper Methods (Keep as is) ---
    def _get_pin_types_by_category(self, categories):
        types = {}
        all_pin_types = self.config.data.get("pin_types", {})
        for pin_id, data in all_pin_types.items():
            category = data.get("category")
            planet = data.get("planet", "Unknown")
            if category in categories:
                name = f"{category} ({planet})" if planet != "Unknown" else category
                if name in types: name = f"{name} (ID: {pin_id})"
                types[name] = int(pin_id)
        return dict(sorted(types.items()))

    def _get_commodities(self):
        commodities = {name: int(id_str) for id_str, name in self.config.data.get("commodities", {}).items()}
        return dict(sorted(commodities.items()))

    def _find_name_by_id(self, data_dict, target_id):
        for name, id_val in data_dict.items():
            if id_val == target_id: return name
        return None

    # --- Main Generation Logic (Keep as is) ---
    def do_generate(self):
        if not self.production_data:
             messagebox.showerror("Error", "Production data not loaded. Cannot generate.", parent=self)
             return
        try:
            storage_name = self.storage_type_var.get()
            launchpad_name = self.launchpad_type_var.get()
            if not all([storage_name, launchpad_name]):
                messagebox.showerror("Error", "Please make selections for Storage and Launchpad types.", parent=self)
                return
            storage_id = self.storage_types.get(storage_name)
            launchpad_id = self.launchpad_types.get(launchpad_name)
            if not all([storage_id, launchpad_id]):
                 messagebox.showerror("Error", "Could not find ID for selected pin type(s). Check config.", parent=self)
                 logging.error(f"Pin ID lookup failed: S:{storage_id}, L:{launchpad_id}")
                 return

            schematic_counts = {}
            raw_schematics_text = self.schematics_text.get("1.0", tk.END).strip()
            if self.placeholder_active or not raw_schematics_text:
                 messagebox.showerror("Input Error", "Please enter the required schematics and their counts.", parent=self)
                 return
            lines = raw_schematics_text.split('\n')
            valid_input_found = False
            for i, line in enumerate(lines):
                line = line.strip()
                if not line or ':' not in line: continue
                parts = line.split(':', 1)
                name = parts[0].strip()
                count_str = parts[1].strip()
                if not name: continue
                if name not in self.commodities:
                     messagebox.showerror("Input Error", f"Unknown commodity name on line {i+1}: '{name}'\nPlease use exact names from the config.", parent=self)
                     return
                try:
                    count = int(count_str)
                    if count <= 0: raise ValueError("Count must be positive.")
                except ValueError:
                     messagebox.showerror("Input Error", f"Invalid count on line {i+1} for '{name}': '{count_str}'\nPlease enter a positive whole number.", parent=self)
                     return
                schematic_counts[name] = schematic_counts.get(name, 0) + count
                valid_input_found = True
            if not valid_input_found:
                 messagebox.showerror("Input Error", "No valid 'Commodity Name: Count' entries found.", parent=self)
                 return

            generated_json = generate_pi_layout(
                schematic_counts=schematic_counts,
                storage_type_id=storage_id,
                launchpad_type_id=launchpad_id,
                config=self.config,
                production_data=self.production_data
            )

            self.output_text.config(state=tk.NORMAL)
            self.output_text.delete("1.0", tk.END)
            if generated_json:
                self.output_text.insert("1.0", generated_json)
                self.copy_button.config(state=tk.NORMAL)
                self.load_button.config(state=tk.NORMAL)
                logging.info("JSON generated successfully.")
            else:
                self.output_text.insert("1.0", "Error generating JSON. Check logs for details.")
                self.copy_button.config(state=tk.DISABLED)
                self.load_button.config(state=tk.DISABLED)
            self.output_text.config(state=tk.DISABLED)
        except Exception as e:
            messagebox.showerror("Generation Error", f"An unexpected error occurred: {e}", parent=self)
            logging.exception("Error during JSON generation process.")
            self.output_text.config(state=tk.NORMAL)
            self.output_text.delete("1.0", tk.END)
            self.output_text.insert("1.0", f"Unexpected Error: {e}")
            self.output_text.config(state=tk.DISABLED)
            self.copy_button.config(state=tk.DISABLED)
            self.load_button.config(state=tk.DISABLED)

    # --- copy_to_clipboard and load_in_viewer (Keep as is) ---
    def copy_to_clipboard(self):
        json_string = self.output_text.get("1.0", tk.END).strip()
        if json_string and not json_string.startswith("Error"):
            try:
                pyperclip.copy(json_string)
                logging.info("Generated JSON copied to clipboard.")
            except Exception as e:
                messagebox.showerror("Clipboard Error", f"Could not copy to clipboard:\n{e}", parent=self)
                logging.error(f"Failed to copy to clipboard: {e}")
        else:
            messagebox.showwarning("Nothing to Copy", "No valid JSON generated yet.", parent=self)

    def load_in_viewer(self):
        json_string = self.output_text.get("1.0", tk.END).strip()
        if json_string and not json_string.startswith("Error"):
            logging.info("Loading generated JSON into viewer.")
            self.app_instance.process_json_string(json_string)
            self.destroy()
        else:
            messagebox.showwarning("Nothing to Load", "No valid JSON generated yet.", parent=self)


# --- PI Viewer App Class (Ensure this is complete) ---
class PIViewerApp(tk.Tk):
    # ... (Include the full, complete PIViewerApp class from the previous step) ...
    def __init__(self):
        super().__init__()
        self.title("EVE PI Viewer")
        self.geometry("1200x800")
        self.configure(bg="#f0f0f0")
        self.last_parsed = None
        self.current_file_path = None
        self.config_data = None
        self.show_routes_var = tk.BooleanVar(value=True)
        self.show_labels_var = tk.BooleanVar(value=True)
        self.current_canvas = None
        self.current_label_artists = []
        self.template_files = []
        try:
            self.config_data = Config(CONFIG_PATH)
            logging.info(f"Configuration loaded successfully from {CONFIG_PATH}")
            initial_label_settings = self.config_data.get_label_settings()
            self.label_settings_vars = {key: tk.BooleanVar(value=value) for key, value in initial_label_settings.items()}
            logging.info(f"Initial label display settings loaded: {initial_label_settings}")
        except FileNotFoundError:
            messagebox.showerror("Error", f"Configuration file not found: {CONFIG_PATH}")
            logging.error(f"Configuration file not found: {CONFIG_PATH}")
            self.destroy(); return
        except json.JSONDecodeError as e:
            messagebox.showerror("Error", f"Error decoding configuration file: {CONFIG_PATH}\n{e}")
            logging.error(f"Error decoding configuration file: {CONFIG_PATH} - {e}")
            self.destroy(); return
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load configuration: {e}")
            logging.exception("Configuration loading error")
            self.destroy(); return
        self.build_ui()
        self.update_template_list()
        self.update_status("Application ready. Load a PI JSON file, paste JSON, or select a template.")

    def build_ui(self):
        menubar = tk.Menu(self)
        self.config(menu=menubar)
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Load File...", command=self.load_file_from_dialog)
        file_menu.add_command(label="Paste JSON...", command=self.paste_json_from_dialog)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.quit)
        settings_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Settings", menu=settings_menu)
        settings_menu.add_command(label="Label Display...", command=self.open_label_settings_dialog)
        generator_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Generator", menu=generator_menu)
        generator_menu.add_command(label="Generate Layout...", command=self.open_generator_dialog)
        sidebar = tk.Frame(self, width=250, bg="#2c3e50")
        sidebar.pack(side="left", fill="y", padx=(0, 1), pady=0)
        sidebar.pack_propagate(False)
        main_area = tk.Frame(self, bg="#f0f0f0")
        main_area.pack(side="right", fill="both", expand=True)
        self.plot_frame = tk.Frame(main_area, bg="#ffffff")
        self.plot_frame.pack(side="left", fill="both", expand=True, padx=5, pady=5)
        self.info_panel = tk.Frame(main_area, width=250, bg="#eeeeee", relief=tk.SUNKEN, borderwidth=1)
        self.info_panel.pack(side="right", fill="y", padx=(0, 5), pady=5)
        self.info_panel.pack_propagate(False)
        toggle_frame = tk.Frame(sidebar, bg="#2c3e50")
        toggle_frame.pack(pady=(10, 10), padx=10, fill='x')
        route_toggle = tk.Checkbutton(toggle_frame, text="Show Routes", variable=self.show_routes_var, command=self.toggle_routes, bg="#2c3e50", fg="white", selectcolor="#34495e", activebackground="#2c3e50", activeforeground="white", font=("Segoe UI", 10), anchor='w')
        route_toggle.pack(side=tk.TOP, fill='x')
        label_toggle = tk.Checkbutton(toggle_frame, text="Show Labels", variable=self.show_labels_var, command=self.toggle_labels, bg="#2c3e50", fg="white", selectcolor="#34495e", activebackground="#2c3e50", activeforeground="white", font=("Segoe UI", 10), anchor='w')
        label_toggle.pack(side=tk.TOP, fill='x')
        template_label = tk.Label(sidebar, text="Templates", bg="#2c3e50", fg="white", font=("Segoe UI", 12, "bold"))
        template_label.pack(pady=(5, 5))
        self.listbox = tk.Listbox(sidebar, bg="#34495e", fg="white", font=("Segoe UI", 10), activestyle="none", selectbackground="#1abc9c", relief=tk.FLAT, borderwidth=0, highlightthickness=0)
        self.listbox.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.listbox.bind("<<ListboxSelect>>", self.on_template_select)
        self._setup_info_panel_default()
        self.status_bar = tk.Label(self, text="Status: Initializing...", bd=1, relief=tk.SUNKEN, anchor=tk.W, bg="#dddddd")
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    def _setup_info_panel_default(self):
        for widget in self.info_panel.winfo_children(): widget.destroy()
        info_title = tk.Label(self.info_panel, text="Info Panel", bg="#eeeeee", font=("Segoe UI", 12, "bold"))
        info_title.pack(pady=(10, 5), anchor='nw', padx=10)
        self.info_content_label = tk.Label(self.info_panel, text="Load a PI JSON file, paste JSON, or select a template.\n\nClick on a pin (marker) or a route (curved arrow) in the plot to see details here.", bg="#eeeeee", justify=tk.LEFT, wraplength=230)
        self.info_content_label.pack(pady=5, padx=10, anchor="nw")

    def update_status(self, message):
        self.status_bar.config(text=f"Status: {message}")
        logging.info(f"Status Update: {message}")
        self.update_idletasks()

    def update_template_list(self):
        self.listbox.delete(0, tk.END)
        self.template_files = []
        try:
            if not os.path.exists(TEMPLATE_DIR):
                os.makedirs(TEMPLATE_DIR)
                logging.warning(f"Template directory '{TEMPLATE_DIR}' not found, created.")
                self.update_status(f"Template directory '{TEMPLATE_DIR}' created. No templates found.")
            else:
                self.template_files = sorted([f for f in os.listdir(TEMPLATE_DIR) if f.endswith(".json")])
            if not self.template_files:
                 self.listbox.insert(tk.END, "(No templates found)")
                 self.listbox.config(state=tk.DISABLED)
            else:
                 self.listbox.config(state=tk.NORMAL)
                 for file in self.template_files: self.listbox.insert(tk.END, os.path.basename(file))
        except Exception as e:
            messagebox.showerror("Error", f"Error reading template directory '{TEMPLATE_DIR}': {e}")
            logging.exception("Error reading template directory")
            self.update_status(f"Error reading templates: {e}")
            self.listbox.insert(tk.END, "(Error reading templates)")
            self.listbox.config(state=tk.DISABLED)

    def load_file_from_dialog(self):
        path = filedialog.askopenfilename(title="Select EVE PI JSON File", filetypes=[("JSON files", "*.json"), ("All files", "*.*")])
        if path:
            logging.info(f"File selected from dialog: {path}")
            self.current_file_path = path
            self.listbox.selection_clear(0, tk.END)
            self.process_file(path)
        else: logging.info("File dialog cancelled.")

    def paste_json_from_dialog(self):
        dialog = tk.Toplevel(self); dialog.title("Paste PI JSON Data"); dialog.geometry("500x400"); dialog.grab_set()
        ttk.Label(dialog, text="Paste the exported PI JSON string below:").pack(pady=(10, 5), padx=10, anchor='w')
        text_area = scrolledtext.ScrolledText(dialog, wrap=tk.WORD, height=15, width=60)
        text_area.pack(pady=5, padx=10, fill="both", expand=True); text_area.focus_set()
        button_frame = ttk.Frame(dialog); button_frame.pack(pady=10, fill='x', padx=10)
        result = {"json_string": None}
        def on_ok():
            json_string = text_area.get("1.0", tk.END).strip()
            if not json_string: messagebox.showwarning("Empty Input", "Please paste the JSON data.", parent=dialog); return
            result["json_string"] = json_string; dialog.destroy()
        def on_cancel(): dialog.destroy()
        ok_button = ttk.Button(button_frame, text="Process", command=on_ok, style='Accent.TButton'); ok_button.pack(side="right", padx=(5, 0))
        cancel_button = ttk.Button(button_frame, text="Cancel", command=on_cancel); cancel_button.pack(side="right")
        style = ttk.Style(self)
        try: style.configure('Accent.TButton', foreground='white', background='#1abc9c')
        except tk.TclError: logging.warning("Could not apply 'Accent.TButton' style.")
        dialog.wait_window()
        if result["json_string"]:
            logging.info("JSON string received from paste dialog.")
            self.listbox.selection_clear(0, tk.END); self.current_file_path = None
            self.process_json_string(result["json_string"])
        else: logging.info("Paste JSON dialog cancelled or no input provided.")

    def on_template_select(self, event):
        if event.widget != self.listbox: return
        selection = self.listbox.curselection()
        if not selection: return
        if self.listbox.cget('state') == tk.DISABLED or self.listbox.get(selection[0]).startswith("("): return
        try:
            index = selection[0]
            if index not in self.listbox.curselection(): logging.warning("on_template_select fired for an index no longer selected. Ignoring."); return
            if hasattr(self, 'template_files') and index < len(self.template_files):
                 filename = self.template_files[index]; path = os.path.join(TEMPLATE_DIR, filename)
            else:
                 filename_from_listbox = self.listbox.get(index); path = os.path.join(TEMPLATE_DIR, filename_from_listbox)
                 logging.warning(f"Reconstructing template path from listbox text: {path}")
            if path == self.current_file_path and self.last_parsed:
                logging.info(f"Template {os.path.basename(path)} corresponds to the currently loaded file. Skipping re-process.")
                self.listbox.selection_set(index); return
            self.current_file_path = path
            logging.info(f"Processing template selection: {os.path.basename(path)} ({path})")
            self.process_file(path)
        except IndexError:
            logging.warning("Listbox selection index out of range."); self.update_status("Error selecting template. Please try again."); self.update_template_list()
        except Exception as e:
            messagebox.showerror("Error", f"Error processing template selection: {e}"); logging.exception("Error processing template selection"); self.update_status(f"Error processing template: {e}")

    def process_file(self, path):
        file_basename = os.path.basename(path)
        logging.info(f"--- Starting process_file for: {file_basename} ---")
        self.update_status(f"Loading PI data from: {file_basename}..."); self.current_file_path = path
        raw_data = None
        try:
            with open(path, 'r') as f: raw_data = json.load(f)
            logging.info(f"Successfully read JSON data from {path}")
        except FileNotFoundError: messagebox.showerror("Error", f"File not found: {path}"); self.update_status(f"Error: File not found {file_basename}"); logging.error(f"File not found: {path}"); self.clear_plot_and_state(); return
        except json.JSONDecodeError as e: messagebox.showerror("Error", f"Invalid JSON format in {file_basename}:\n{e}"); self.update_status(f"Error: Invalid JSON in {file_basename}"); logging.error(f"Invalid JSON in {path}: {e}"); self.clear_plot_and_state(); return
        except Exception as e: messagebox.showerror("Error", f"Failed to read file {file_basename}: {e}"); self.update_status(f"Error: Failed to read {file_basename}"); logging.exception(f"Error reading file {path}"); self.clear_plot_and_state(); return
        if raw_data is not None: self._process_raw_data(raw_data, f"file '{file_basename}'")

    def process_json_string(self, json_string):
        logging.info("--- Starting process_json_string ---")
        self.update_status("Loading PI data from generated/pasted JSON..."); self.current_file_path = None
        raw_data = None
        try:
            raw_data = json.loads(json_string)
            logging.info("Successfully parsed JSON string.")
        except json.JSONDecodeError as e: messagebox.showerror("Error", f"Invalid JSON format in provided data:\n{e}"); self.update_status("Error: Invalid JSON in provided data"); logging.error(f"Invalid JSON in provided string: {e}"); self.clear_plot_and_state(); return
        except Exception as e: messagebox.showerror("Error", f"Failed to process provided data: {e}"); self.update_status("Error: Failed to process provided data"); logging.exception("Error processing provided JSON string"); self.clear_plot_and_state(); return
        if raw_data is not None: self._process_raw_data(raw_data, "provided JSON data")
        else: logging.error("process_json_string: raw_data is None after JSON parsing attempt."); self.clear_plot_and_state()

    def _process_raw_data(self, raw_data, source_description):
        logging.info(f"Processing raw data from {source_description}")
        self.update_status(f"Parsing data from {source_description}...")
        try:
            if not self.config_data: logging.error("Config not loaded."); raise ValueError("Config not loaded.")
            self._last_raw_data_processed = raw_data # Store for re-parse
            parsed = parse_pi_json(raw_data, self.config_data)
            if parsed is None: raise ValueError("Parsing failed critically (check logs).")
            self.last_parsed = parsed
            logging.info(f"Successfully parsed data from {source_description}")
        except Exception as e: messagebox.showerror("Error", f"Failed to parse data from {source_description}: {e}"); self.update_status(f"Error: Failed parsing {source_description}"); logging.exception(f"Error parsing data from {source_description}"); self.clear_plot_and_state(); return
        logging.info("Calling refresh_plot (initial render before potential ID resolution).")
        self.refresh_plot()
        unknowns = parsed.get("unknowns", {}); unknown_commodities = list(unknowns.get("commodity", [])); unknown_pin_types = list(unknowns.get("pin_type", [])); current_planet_id = parsed.get("planet_id")
        logging.info(f"Planet ID from JSON parser: {current_planet_id}")
        resolution_needed = False
        if unknown_commodities:
            resolution_needed = True; logging.info(f"Resolving unknown commodities: {unknown_commodities}")
            known_commodity_values = list(self.config_data.data.get("commodities", {}).values())
            resolve_unknown_ids(unknown_commodities, "commodity", known_commodity_values, self.config_data, self.refresh_plot_after_resolve, None)
        if unknown_pin_types and not unknown_commodities:
            resolution_needed = True; logging.info(f"Resolving unknown pin types: {unknown_pin_types}")
            pin_type_values = self.config_data.data.get("pin_types", {}).values()
            known_categories = list(set(["Extractor", "Launchpad", "Basic Industrial Facility", "Advanced Industrial Facility", "High-Tech Industrial Facility", "Storage Facility", "Command Center"] + [v.get('category', 'Unknown') for v in pin_type_values]))
            resolve_unknown_ids(unknown_pin_types, "pin_type", known_categories, self.config_data, self.refresh_plot_after_resolve, current_planet_id)
        elif unknown_pin_types and unknown_commodities: logging.info("Unknown pin types also found, handled after commodity resolution.")
        if resolution_needed and not unknown_commodities and not unknown_pin_types: pass
        elif resolution_needed: self.update_status(f"Plot rendered. Resolve unknown IDs for {source_description}."); logging.info(f"Unknown IDs found for {source_description}. Resolution dialogs triggered.")
        else: self.update_status(f"Plot rendered successfully for {source_description}."); logging.info(f"Plot rendered successfully for {source_description} (no unknown IDs found).")
        logging.info(f"--- Finished processing data from {source_description} ---")

    def refresh_plot_after_resolve(self):
        self.update_status("IDs resolved. Re-parsing and refreshing plot..."); logging.info("--- Starting refresh_plot_after_resolve ---")
        raw_data_to_reparse = None; source_description = "unknown source"
        if self.current_file_path and os.path.exists(self.current_file_path):
            source_description = f"file '{os.path.basename(self.current_file_path)}'"; logging.info(f"Re-processing {source_description}")
            try:
                with open(self.current_file_path, 'r') as f: raw_data_to_reparse = json.load(f)
            except Exception as e: messagebox.showerror("Error", f"Failed to re-read file {source_description} after ID resolution: {e}"); self.update_status(f"Error: Failed re-reading {source_description}"); logging.exception(f"Error re-reading file {self.current_file_path} after ID resolution"); self.clear_plot_and_state(); return
        elif hasattr(self, '_last_raw_data_processed') and self._last_raw_data_processed:
             source_description = "provided JSON data"; logging.info(f"Re-processing {source_description} using stored raw data."); raw_data_to_reparse = self._last_raw_data_processed
        else: errmsg = "Cannot refresh: Missing original data source after ID resolution."; self.update_status(errmsg); logging.warning(errmsg); self.clear_plot_and_state(); return
        if raw_data_to_reparse:
            try:
                logging.info("Re-parsing data with updated config...")
                self._process_raw_data(raw_data_to_reparse, source_description + " (re-parse)")
            except Exception as e: messagebox.showerror("Error", f"Failed to re-process data after ID resolution: {e}"); self.update_status(f"Error: Failed re-processing {source_description}"); logging.exception(f"Error re-processing data from {source_description} after ID resolution"); self.clear_plot_and_state()
        logging.info("--- Finished refresh_plot_after_resolve ---")

    def refresh_plot(self):
        logging.debug("--- Starting refresh_plot ---")
        if self.last_parsed:
            logging.info("Rendering plot based on self.last_parsed data.")
            try:
                show_routes_state = self.show_routes_var.get(); show_labels_state = self.show_labels_var.get()
                current_label_settings = {key: var.get() for key, var in self.label_settings_vars.items()}
                logging.debug(f"Calling render_matplotlib_plot with show_routes={show_routes_state}, show_labels={show_labels_state}, label_settings={current_label_settings}.")
                canvas, label_artists = render_matplotlib_plot(self.last_parsed, self.config_data, self.plot_frame, self.info_panel, show_routes=show_routes_state, show_labels=show_labels_state, label_settings=current_label_settings)
                self.current_canvas = canvas; self.current_label_artists = label_artists if label_artists else []
                logging.debug("render_matplotlib_plot finished.")
            except Exception as e: messagebox.showerror("Error", f"Failed to render plot: {e}"); self.update_status("Error: Failed to render plot."); logging.exception("Plot rendering error"); self.clear_plot_display()
        else: self.update_status("No data available to render plot."); logging.warning("refresh_plot called without valid self.last_parsed data."); self.clear_plot_display()
        logging.debug("--- Finished refresh_plot ---")

    def clear_plot_display(self):
        logging.info("Clearing plot area display and resetting info panel.")
        for widget in self.plot_frame.winfo_children(): widget.destroy()
        tk.Label(self.plot_frame, text="Load a file, paste JSON, or select a template.", bg="#ffffff").pack(expand=True)
        self._setup_info_panel_default(); self.current_canvas = None; self.current_label_artists = []

    def clear_plot_and_state(self):
        logging.info("Clearing plot, resetting info panel, and clearing parsed state.")
        self.last_parsed = None; self.current_file_path = None
        if hasattr(self, '_last_raw_data_processed'): del self._last_raw_data_processed
        self.clear_plot_display()

    def toggle_routes(self):
        route_state = self.show_routes_var.get(); state_text = 'shown' if route_state else 'hidden'
        logging.info(f"Route visibility toggled to: {route_state}. Refreshing plot.")
        self.update_status(f"Routes {state_text}. Refreshing plot...")
        if self.last_parsed: self.refresh_plot(); self.update_status(f"Plot refreshed. Routes are {state_text}.")
        else: logging.warning("Toggle routes called but no data loaded."); self.update_status("Load data to toggle route visibility.")

    def toggle_labels(self):
        label_state = self.show_labels_var.get(); state_text = 'shown' if label_state else 'hidden'
        logging.info(f"Label visibility toggled to: {label_state}")
        if self.current_canvas and self.current_label_artists:
            self.update_status(f"Labels {state_text}. Updating display...")
            try:
                for label in self.current_label_artists: label.set_visible(label_state)
                self.current_canvas.draw_idle(); self.update_status(f"Plot updated. Labels are {state_text}.")
            except Exception as e: logging.exception("Error toggling label visibility"); self.update_status(f"Error updating labels to {state_text}. Re-rendering..."); self.refresh_plot()
        elif self.last_parsed: logging.warning("Toggle labels called, data exists but no canvas/artists. Full refresh."); self.update_status(f"Labels {state_text}. Refreshing plot..."); self.refresh_plot(); self.update_status(f"Plot refreshed. Labels are {state_text}.")
        else: logging.warning("Toggle labels called but no data loaded."); self.update_status("Load data to toggle label visibility.")

    def open_label_settings_dialog(self):
        dialog = tk.Toplevel(self); dialog.title("Pin Label Display Settings"); dialog.geometry("350x280"); dialog.resizable(False, False); dialog.grab_set()
        temp_vars = {key: tk.BooleanVar(value=var.get()) for key, var in self.label_settings_vars.items()}
        main_frame = tk.Frame(dialog, padx=15, pady=15); main_frame.pack(fill="both", expand=True)
        tk.Label(main_frame, text="Show in Pin Labels:", font=("Segoe UI", 10, "bold")).pack(anchor='w', pady=(0, 10))
        tk.Checkbutton(main_frame, text="Pin Name (Category)", variable=temp_vars["show_pin_name"], anchor='w').pack(fill='x')
        tk.Checkbutton(main_frame, text="Pin Type ID", variable=temp_vars["show_pin_id"], anchor='w').pack(fill='x')
        tk.Checkbutton(main_frame, text="Schematic Name", variable=temp_vars["show_schematic_name"], anchor='w').pack(fill='x')
        tk.Checkbutton(main_frame, text="Schematic ID", variable=temp_vars["show_schematic_id"], anchor='w').pack(fill='x')
        button_frame = tk.Frame(main_frame); button_frame.pack(side=tk.BOTTOM, fill="x", pady=(20, 0)); button_frame.column_configure(0, weight=1)
        def apply_changes():
            logging.info("Applying label settings changes.")
            for key, temp_var in temp_vars.items(): self.label_settings_vars[key].set(temp_var.get())
            if self.last_parsed: self.refresh_plot(); self.update_status("Label display settings applied.")
            else: self.update_status("Label display settings updated (no plot to refresh).")
        def save_and_apply():
            apply_changes(); logging.info("Saving label settings as default.")
            current_settings = {key: var.get() for key, var in self.label_settings_vars.items()}
            try:
                if self.config_data.save_label_settings(current_settings):
                    self.config_data.save(); self.update_status("Label display settings saved as default.")
                    messagebox.showinfo("Settings Saved", "Label display settings saved as default.", parent=dialog)
                else: messagebox.showerror("Error", "Failed to prepare settings for saving.", parent=dialog); logging.error("save_label_settings returned False.")
            except Exception as e: messagebox.showerror("Error", f"Failed to save settings to config file:\n{e}", parent=dialog); logging.exception("Failed to save label settings to config file.")
            dialog.destroy()
        def cancel(): logging.debug("Label settings dialog cancelled."); dialog.destroy()
        cancel_btn = tk.Button(button_frame, text="Cancel", command=cancel, width=10); cancel_btn.pack(side=tk.RIGHT, padx=(5, 0))
        apply_btn = tk.Button(button_frame, text="Apply", command=lambda: [apply_changes(), dialog.destroy()], width=10); apply_btn.pack(side=tk.RIGHT, padx=(5,0))
        save_btn = tk.Button(button_frame, text="Save as Default", command=save_and_apply, width=15); save_btn.pack(side=tk.RIGHT)
        dialog.protocol("WM_DELETE_WINDOW", cancel); dialog.wait_window()

    def open_generator_dialog(self):
        if not self.config_data: messagebox.showerror("Error", "Configuration not loaded. Cannot open generator."); return
        dialog = GeneratorDialog(self, self.config_data, self)


# --- Main execution block ---
if __name__ == "__main__":
    try: import pyperclip
    except ImportError: logging.warning("pyperclip module not found. 'Copy to Clipboard' will not work."); print("Optional: pip install pyperclip")
    if not os.path.isdir(CSV_DIR): logging.error(f"CSV directory '{CSV_DIR}' not found."); print(f"ERROR: Directory '{CSV_DIR}' not found. Generator will not function.")
    logging.info("--- Starting PI Viewer Application ---")
    app = PIViewerApp()
    app.mainloop()
    logging.info("--- PI Viewer Application finished ---")

