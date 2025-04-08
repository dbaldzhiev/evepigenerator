import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog, scrolledtext # Added scrolledtext
from viewer.config import Config
from viewer.parser import parse_pi_json
from viewer.visualizer import render_matplotlib_plot
from viewer.id_editor import resolve_unknown_ids
import os
import json
import logging

# --- Configuration ---
CONFIG_PATH = "viewer/assets/config.json"
TEMPLATE_DIR = "templates"
LOG_FILE = "pi_viewer.log"

# --- Logging Setup ---
logging.basicConfig(filename=LOG_FILE, level=logging.INFO, # Use INFO, DEBUG for detailed parsing/rendering
                    format='%(asctime)s - %(levelname)s - [%(module)s:%(lineno)d] - %(message)s')

class PIViewerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("EVE PI Viewer")
        self.geometry("1200x800")
        self.configure(bg="#f0f0f0")

        # --- Internal State ---
        self.last_parsed = None         # Stores the result from parse_pi_json
        self.current_file_path = None   # Path to the currently loaded JSON file
        self.config_data = None         # Holds the Config object
        self.show_routes_var = tk.BooleanVar(value=True) # Controls route visibility
        self.show_labels_var = tk.BooleanVar(value=True) # Controls label visibility (overall toggle)
        self.current_canvas = None      # Holds the current Matplotlib canvas object
        self.current_label_artists = [] # Holds the label artists for toggling

        # --- Load Configuration ---
        try:
            self.config_data = Config(CONFIG_PATH)
            logging.info(f"Configuration loaded successfully from {CONFIG_PATH}")
            # --- Load Label Settings ---
            initial_label_settings = self.config_data.get_label_settings()
            self.label_settings_vars = {
                key: tk.BooleanVar(value=value)
                for key, value in initial_label_settings.items()
            }
            logging.info(f"Initial label display settings loaded: {initial_label_settings}")

        except FileNotFoundError:
            messagebox.showerror("Error", f"Configuration file not found: {CONFIG_PATH}")
            logging.error(f"Configuration file not found: {CONFIG_PATH}")
            self.destroy()
            return
        except json.JSONDecodeError as e:
            messagebox.showerror("Error", f"Error decoding configuration file: {CONFIG_PATH}\n{e}")
            logging.error(f"Error decoding configuration file: {CONFIG_PATH} - {e}")
            self.destroy()
            return
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load configuration: {e}")
            logging.exception("Configuration loading error")
            self.destroy()
            return

        # --- Build UI ---
        self.build_ui()
        self.update_template_list()
        self.update_status("Application ready. Load a PI JSON file, paste JSON, or select a template.")

    def build_ui(self):
        # --- Menu Bar ---
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

        # --- Main Panes ---
        sidebar = tk.Frame(self, width=250, bg="#2c3e50")
        sidebar.pack(side="left", fill="y", padx=(0, 1), pady=0)
        sidebar.pack_propagate(False)

        main_area = tk.Frame(self, bg="#f0f0f0")
        main_area.pack(side="right", fill="both", expand=True)

        self.plot_frame = tk.Frame(main_area, bg="#ffffff") # White background for plot area
        self.plot_frame.pack(side="left", fill="both", expand=True, padx=5, pady=5)

        self.info_panel = tk.Frame(main_area, width=250, bg="#eeeeee", relief=tk.SUNKEN, borderwidth=1)
        self.info_panel.pack(side="right", fill="y", padx=(0, 5), pady=5)
        self.info_panel.pack_propagate(False)

        # --- Sidebar Widgets ---
        # Buttons moved to menu, keep toggles
        # load_button = tk.Button(sidebar, text="Load File...", command=self.load_file_from_dialog, bg="#1abc9c", fg="white", relief=tk.FLAT, font=("Segoe UI", 10))
        # load_button.pack(pady=(10, 5), padx=10, fill="x") # Adjusted padding
        # paste_button = tk.Button(sidebar, text="Paste JSON...", command=self.paste_json_from_dialog, bg="#3498db", fg="white", relief=tk.FLAT, font=("Segoe UI", 10))
        # paste_button.pack(pady=(0, 5), padx=10, fill="x") # Adjusted padding

        # --- Toggles Frame ---
        toggle_frame = tk.Frame(sidebar, bg="#2c3e50")
        toggle_frame.pack(pady=(10, 10), padx=10, fill='x') # Added top padding

        route_toggle = tk.Checkbutton(toggle_frame, text="Show Routes", variable=self.show_routes_var,
                                      command=self.toggle_routes, bg="#2c3e50", fg="white",
                                      selectcolor="#34495e", activebackground="#2c3e50",
                                      activeforeground="white", font=("Segoe UI", 10), anchor='w')
        route_toggle.pack(side=tk.TOP, fill='x')

        label_toggle = tk.Checkbutton(toggle_frame, text="Show Labels", variable=self.show_labels_var,
                                      command=self.toggle_labels, bg="#2c3e50", fg="white",
                                      selectcolor="#34495e", activebackground="#2c3e50",
                                      activeforeground="white", font=("Segoe UI", 10), anchor='w')
        label_toggle.pack(side=tk.TOP, fill='x')


        template_label = tk.Label(sidebar, text="Templates", bg="#2c3e50", fg="white", font=("Segoe UI", 12, "bold"))
        template_label.pack(pady=(5, 5))

        self.listbox = tk.Listbox(sidebar, bg="#34495e", fg="white", font=("Segoe UI", 10), activestyle="none", selectbackground="#1abc9c", relief=tk.FLAT, borderwidth=0, highlightthickness=0)
        self.listbox.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.listbox.bind("<<ListboxSelect>>", self.on_template_select)

        # --- Info Panel Initial Content ---
        self._setup_info_panel_default()

        # --- Status Bar ---
        self.status_bar = tk.Label(self, text="Status: Initializing...", bd=1, relief=tk.SUNKEN, anchor=tk.W, bg="#dddddd")
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    def _setup_info_panel_default(self):
        """Sets up the default content of the info panel."""
        for widget in self.info_panel.winfo_children():
            widget.destroy() # Clear everything first
        info_title = tk.Label(self.info_panel, text="Info Panel", bg="#eeeeee", font=("Segoe UI", 12, "bold"))
        info_title.pack(pady=(10, 5), anchor='nw', padx=10)
        self.info_content_label = tk.Label(self.info_panel,
                                           text="Load a PI JSON file, paste JSON, or select a template.\n\n"
                                                "Click on a pin (marker) or a route (curved arrow) "
                                                "in the plot to see details here.",
                                           bg="#eeeeee", justify=tk.LEFT, wraplength=230)
        self.info_content_label.pack(pady=5, padx=10, anchor="nw")

    def update_status(self, message):
        """Updates the status bar text and logs the message."""
        self.status_bar.config(text=f"Status: {message}")
        logging.info(f"Status Update: {message}")
        self.update_idletasks() # Force UI update

    def update_template_list(self):
        """Refreshes the listbox with JSON files from the template directory."""
        self.listbox.delete(0, tk.END)
        self.template_files = [] # Reset stored list
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
                 for file in self.template_files:
                    self.listbox.insert(tk.END, os.path.basename(file)) # Show only filename

        except Exception as e:
            messagebox.showerror("Error", f"Error reading template directory '{TEMPLATE_DIR}': {e}")
            logging.exception("Error reading template directory")
            self.update_status(f"Error reading templates: {e}")
            self.listbox.insert(tk.END, "(Error reading templates)")
            self.listbox.config(state=tk.DISABLED)

    def load_file_from_dialog(self):
        """Opens a file dialog to select a JSON file and processes it."""
        path = filedialog.askopenfilename(
            title="Select EVE PI JSON File",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        if path:
            logging.info(f"File selected from dialog: {path}")
            self.current_file_path = path
            self.listbox.selection_clear(0, tk.END) # Clear template selection
            self.process_file(path)
        else:
            logging.info("File dialog cancelled.")

    def paste_json_from_dialog(self):
        """Opens a dialog to paste JSON data and processes it."""
        dialog = tk.Toplevel(self)
        dialog.title("Paste PI JSON Data")
        dialog.geometry("500x400")
        dialog.grab_set() # Make modal

        tk.Label(dialog, text="Paste the exported PI JSON string below:").pack(pady=(10, 5), padx=10, anchor='w')

        text_area = scrolledtext.ScrolledText(dialog, wrap=tk.WORD, height=15, width=60)
        text_area.pack(pady=5, padx=10, fill="both", expand=True)
        text_area.focus_set()

        button_frame = tk.Frame(dialog)
        button_frame.pack(pady=10, fill='x', padx=10)

        result = {"json_string": None} # Dictionary to store result

        def on_ok():
            json_string = text_area.get("1.0", tk.END).strip()
            if not json_string:
                messagebox.showwarning("Empty Input", "Please paste the JSON data.", parent=dialog)
                return
            result["json_string"] = json_string
            dialog.destroy()

        def on_cancel():
            dialog.destroy()

        ok_button = tk.Button(button_frame, text="Process", command=on_ok, bg="#1abc9c", fg="white", relief=tk.FLAT)
        ok_button.pack(side="right", padx=(5, 0))

        cancel_button = tk.Button(button_frame, text="Cancel", command=on_cancel, bg="#bdc3c7", fg="white", relief=tk.FLAT)
        cancel_button.pack(side="right")

        dialog.wait_window() # Wait for dialog to close

        # Process the result after the dialog is closed
        if result["json_string"]:
            logging.info("JSON string received from paste dialog.")
            self.listbox.selection_clear(0, tk.END) # Clear template selection
            self.current_file_path = None # Pasted data doesn't have a file path
            self.process_json_string(result["json_string"])
        else:
            logging.info("Paste JSON dialog cancelled or no input provided.")


    def on_template_select(self, event):
        """Handles selection changes in the template listbox."""
        if event.widget != self.listbox: return # Ensure event is from the correct widget
        selection = self.listbox.curselection()
        if not selection: return # No item selected

        # Prevent processing if listbox is disabled or shows placeholder
        if self.listbox.cget('state') == tk.DISABLED or self.listbox.get(selection[0]).startswith("("):
            return

        try:
            index = selection[0]
            # Check if index is still selected (mitigates potential race condition)
            if index not in self.listbox.curselection():
                 logging.warning("on_template_select fired for an index no longer selected. Ignoring.")
                 return

            # Use the stored full path list if available, otherwise reconstruct
            if hasattr(self, 'template_files') and index < len(self.template_files):
                 filename = self.template_files[index]
                 path = os.path.join(TEMPLATE_DIR, filename)
            else:
                 # Fallback: reconstruct path from listbox text (less ideal)
                 filename_from_listbox = self.listbox.get(index)
                 path = os.path.join(TEMPLATE_DIR, filename_from_listbox)
                 logging.warning(f"Reconstructing template path from listbox text: {path}")


            # Avoid reprocessing the exact same file path if already loaded and parsed
            if path == self.current_file_path and self.last_parsed:
                logging.info(f"Template {os.path.basename(path)} corresponds to the currently loaded file. Skipping re-process.")
                # Ensure selection remains visually
                self.listbox.selection_set(index)
                return

            self.current_file_path = path
            logging.info(f"Processing template selection: {os.path.basename(path)} ({path})")
            self.process_file(path)
        except IndexError:
            logging.warning("Listbox selection index out of range, possibly due to list update race condition.")
            self.update_status("Error selecting template. Please try again.")
            self.update_template_list() # Refresh listbox
        except Exception as e:
            messagebox.showerror("Error", f"Error processing template selection: {e}")
            logging.exception("Error processing template selection")
            self.update_status(f"Error processing template: {e}")

    def process_file(self, path):
        """Loads, parses, and renders the PI data from the given file path."""
        file_basename = os.path.basename(path)
        logging.info(f"--- Starting process_file for: {file_basename} ---")
        self.update_status(f"Loading PI data from: {file_basename}...")
        self.current_file_path = path # Update current path state

        try:
            with open(path, 'r') as f:
                raw_data = json.load(f)
            logging.info(f"Successfully read JSON data from {path}")
        except FileNotFoundError:
            messagebox.showerror("Error", f"File not found: {path}")
            self.update_status(f"Error: File not found {file_basename}")
            logging.error(f"File not found: {path}")
            self.clear_plot_and_state()
            return
        except json.JSONDecodeError as e:
            messagebox.showerror("Error", f"Invalid JSON format in {file_basename}:\n{e}")
            self.update_status(f"Error: Invalid JSON in {file_basename}")
            logging.error(f"Invalid JSON in {path}: {e}")
            self.clear_plot_and_state()
            return
        except Exception as e:
            messagebox.showerror("Error", f"Failed to read file {file_basename}: {e}")
            self.update_status(f"Error: Failed to read {file_basename}")
            logging.exception(f"Error reading file {path}")
            self.clear_plot_and_state()
            return

        # --- Common Processing Logic ---
        self._process_raw_data(raw_data, f"file '{file_basename}'")

    def process_json_string(self, json_string):
        """Parses and renders PI data from a JSON string."""
        logging.info("--- Starting process_json_string ---")
        self.update_status("Loading PI data from pasted JSON...")
        self.current_file_path = None # No file path for pasted data

        try:
            raw_data = json.loads(json_string)
            logging.info("Successfully parsed JSON string.")
        except json.JSONDecodeError as e:
            messagebox.showerror("Error", f"Invalid JSON format in pasted data:\n{e}")
            self.update_status("Error: Invalid JSON in pasted data")
            logging.error(f"Invalid JSON in pasted string: {e}")
            self.clear_plot_and_state()
            return
        except Exception as e:
            messagebox.showerror("Error", f"Failed to process pasted data: {e}")
            self.update_status("Error: Failed to process pasted data")
            logging.exception("Error processing pasted JSON string")
            self.clear_plot_and_state()
            return

        # --- Common Processing Logic ---
        self._process_raw_data(raw_data, "pasted JSON")

    def _process_raw_data(self, raw_data, source_description):
        """Shared logic to parse data, render plot, and handle unknowns."""
        logging.info(f"Processing raw data from {source_description}")
        self.update_status(f"Parsing data from {source_description}...")
        try:
            if not self.config_data:
                 logging.error("Configuration data is not loaded during _process_raw_data.")
                 raise ValueError("Configuration data is not loaded.") # Should not happen

            parsed = parse_pi_json(raw_data, self.config_data)
            if parsed is None: # Parser can return None on critical failure
                 raise ValueError("Parsing failed critically (check logs).")

            self.last_parsed = parsed # Store parsed data
            logging.info(f"Successfully parsed data from {source_description}")

        except Exception as e:
            messagebox.showerror("Error", f"Failed to parse data from {source_description}: {e}")
            self.update_status(f"Error: Failed parsing {source_description}")
            logging.exception(f"Error parsing data from {source_description}")
            self.clear_plot_and_state()
            return

        # --- Render Plot FIRST ---
        logging.info("Calling refresh_plot (initial render before potential ID resolution).")
        self.refresh_plot() # This now uses self.last_parsed and current toggle states

        # --- Check for and Resolve Unknowns AFTER rendering initial plot ---
        # Ensure unknowns exist before accessing keys
        unknowns = parsed.get("unknowns", {})
        unknown_commodities = list(unknowns.get("commodity", []))
        unknown_pin_types = list(unknowns.get("pin_type", []))
        current_planet_id = parsed.get("planet_id") # Get planet_id from parser result
        logging.info(f"Planet ID from JSON parser: {current_planet_id}")

        resolution_needed = False
        # Check commodities first
        if unknown_commodities:
            resolution_needed = True
            logging.info(f"Resolving unknown commodities: {unknown_commodities}")
            # Ensure commodities key exists in config data before accessing values
            known_commodity_values = list(self.config_data.data.get("commodities", {}).values())
            resolve_unknown_ids(
                unknown_ids=unknown_commodities, id_type="commodity",
                known_options=known_commodity_values,
                config=self.config_data, update_callback=self.refresh_plot_after_resolve,
                planet_id=None # Not needed for commodities
            )
        # Check pin types only *after* commodities are potentially resolved (if needed)
        # Re-check unknowns in case config was updated but not re-parsed yet
        # (refresh_plot_after_resolve handles the re-parse)
        if unknown_pin_types and not unknown_commodities: # Only pop pin type dialog if no commodity dialog was shown
            resolution_needed = True
            logging.info(f"Resolving unknown pin types: {unknown_pin_types}")
            # Provide known categories + any existing from config as suggestions
            pin_type_values = self.config_data.data.get("pin_types", {}).values()
            known_categories = list(set(
                ["Extractor", "Launchpad", "Basic Industrial Facility", "Advanced Industrial Facility",
                 "High-Tech Industrial Facility", "Storage Facility", "Command Center"] +
                [v.get('category', 'Unknown') for v in pin_type_values]
            ))
            resolve_unknown_ids(
                unknown_ids=unknown_pin_types, id_type="pin_type",
                known_options=known_categories,
                config=self.config_data, update_callback=self.refresh_plot_after_resolve,
                planet_id=current_planet_id # Pass the planet ID
            )
        elif unknown_pin_types and unknown_commodities:
             logging.info("Unknown pin types also found, but will be handled after commodity resolution triggers a refresh.")
             # Don't trigger the pin_type dialog immediately, let the commodity resolution callback handle the refresh,
             # which will then re-evaluate unknowns.

        if resolution_needed and not unknown_commodities and not unknown_pin_types:
             # This case means resolution happened, but the refresh callback handles the status.
             pass
        elif resolution_needed:
            self.update_status(f"Plot rendered. Resolve unknown IDs for {source_description}.")
            logging.info(f"Unknown IDs found for {source_description}. Resolution dialogs triggered.")
        else:
            self.update_status(f"Plot rendered successfully for {source_description}.")
            logging.info(f"Plot rendered successfully for {source_description} (no unknown IDs found).")

        logging.info(f"--- Finished processing data from {source_description} ---")


    def refresh_plot_after_resolve(self):
        """Callback after ID resolution. Re-parses the current data (file or stored string) and re-renders."""
        self.update_status("IDs resolved. Re-parsing and refreshing plot...")
        logging.info("--- Starting refresh_plot_after_resolve ---")

        raw_data = None
        source_description = "unknown source"

        # Determine where the original data came from
        if self.current_file_path and os.path.exists(self.current_file_path):
            source_description = f"file '{os.path.basename(self.current_file_path)}'"
            logging.info(f"Re-processing {source_description}")
            try:
                with open(self.current_file_path, 'r') as f:
                    raw_data = json.load(f)
            except Exception as e:
                messagebox.showerror("Error", f"Failed to re-read file {source_description} after ID resolution: {e}")
                self.update_status(f"Error: Failed re-reading {source_description}")
                logging.exception(f"Error re-reading file {self.current_file_path} after ID resolution")
                self.clear_plot_and_state()
                return
        elif self.last_parsed: # If no file path, assume data came from paste
             # Limitation: Cannot reliably re-parse pasted data without storing the original string/dict.
             # We will re-process the *newly parsed* data after resolving IDs, which might miss some nuances
             # if the parser itself needs re-running on the *original* raw data.
             # For now, proceed by re-parsing the current self.last_parsed data to check for remaining unknowns
             # and then re-render. This is better than doing nothing.
             logging.warning("Re-processing pasted data after ID resolution. Re-parsing current structure, not original JSON.")
             source_description = "pasted JSON"
             # Re-parse the *existing parsed data* with the updated config to catch remaining unknowns
             # This isn't ideal but the best we can do without storing the original paste.
             try:
                 logging.info("Re-parsing existing parsed structure with updated config...")
                 re_parsed_check = parse_pi_json(self.last_parsed, self.config_data) # Use the current parsed data as input
                 if re_parsed_check is None:
                     raise ValueError("Re-parsing check failed critically after ID resolution.")
                 self.last_parsed = re_parsed_check # Update with potentially newly resolved names
                 logging.info("Re-parsing check complete.")
                 # Now check for remaining unknowns after this re-parse
                 unknowns = self.last_parsed.get("unknowns", {})
                 remaining_commodities = unknowns.get("commodity", [])
                 remaining_pin_types = unknowns.get("pin_type", [])

                 if remaining_commodities or remaining_pin_types:
                      logging.warning(f"Remaining unknowns after re-parse check: C={remaining_commodities}, P={remaining_pin_types}. Triggering resolution again.")
                      # Trigger the processing again to handle remaining unknowns
                      # This might lead to nested calls if not careful, but _process_raw_data handles sequential checks.
                      self._process_raw_data(self.last_parsed, source_description + " (re-check)") # Use the re-parsed data
                      return # Exit here, _process_raw_data will handle rendering/status
                 else:
                      # No remaining unknowns after re-parse check, just refresh the plot
                      logging.info("No remaining unknowns found after re-parse check. Refreshing plot.")
                      self.refresh_plot()
                      self.update_status(f"Plot refreshed with resolved IDs for {source_description}.")
                      logging.info(f"Plot refreshed successfully after ID resolution for {source_description}.")

             except Exception as e:
                 messagebox.showerror("Error", f"Failed to re-process pasted data after ID resolution: {e}")
                 self.update_status(f"Error: Failed re-processing {source_description}")
                 logging.exception(f"Error re-processing pasted data from {source_description} after ID resolution")
                 self.clear_plot_and_state()
             return # Exit after handling pasted data

        else: # No file path and no last_parsed data - should not happen if resolve was triggered
            errmsg = "Cannot refresh: Missing file path and parsed data after ID resolution."
            self.update_status(errmsg)
            logging.warning(errmsg)
            self.clear_plot_and_state()
            return

        # If we have raw_data (must be from file)
        if raw_data:
            try:
                logging.info("Re-parsing data with updated config...")
                parsed = parse_pi_json(raw_data, self.config_data) # Re-parse from original file data

                if parsed is None:
                    raise ValueError("Re-parsing failed critically after ID resolution.")

                self.last_parsed = parsed # Update parsed data

                logging.info("Re-parsing complete. Checking for remaining unknowns...")
                # Check for remaining unknowns *again* after re-parsing the original file data
                unknowns = self.last_parsed.get("unknowns", {})
                remaining_commodities = unknowns.get("commodity", [])
                remaining_pin_types = unknowns.get("pin_type", [])
                current_planet_id = self.last_parsed.get("planet_id")

                if remaining_commodities:
                    logging.info(f"Still unknown commodities after re-parse: {remaining_commodities}. Triggering resolution again.")
                    known_commodity_values = list(self.config_data.data.get("commodities", {}).values())
                    resolve_unknown_ids(remaining_commodities, "commodity", known_commodity_values, self.config_data, self.refresh_plot_after_resolve, None)
                    # Don't refresh plot yet, let the next callback handle it
                elif remaining_pin_types:
                     logging.info(f"Still unknown pin types after re-parse: {remaining_pin_types}. Triggering resolution again.")
                     pin_type_values = self.config_data.data.get("pin_types", {}).values()
                     known_categories = list(set(
                         ["Extractor", "Launchpad", "Basic Industrial Facility", "Advanced Industrial Facility",
                          "High-Tech Industrial Facility", "Storage Facility", "Command Center"] +
                         [v.get('category', 'Unknown') for v in pin_type_values]
                     ))
                     resolve_unknown_ids(remaining_pin_types, "pin_type", known_categories, self.config_data, self.refresh_plot_after_resolve, current_planet_id)
                     # Don't refresh plot yet
                else:
                     # No remaining unknowns, finally refresh the plot
                     logging.info("No remaining unknowns after re-parse. Calling refresh_plot.")
                     self.refresh_plot() # Re-render using the new self.last_parsed
                     self.update_status(f"Plot refreshed with resolved IDs for {source_description}.")
                     logging.info(f"Plot refreshed successfully after ID resolution for {source_description}.")

            except Exception as e:
                 messagebox.showerror("Error", f"Failed to re-process data after ID resolution: {e}")
                 self.update_status(f"Error: Failed re-processing {source_description}")
                 logging.exception(f"Error re-processing data from {source_description} after ID resolution")
                 self.clear_plot_and_state()
        # else: # Handled by the checks above

        logging.info("--- Finished refresh_plot_after_resolve ---")


    def refresh_plot(self):
        """Renders the plot based on self.last_parsed and current settings."""
        logging.debug("--- Starting refresh_plot ---")
        if self.last_parsed:
            logging.info("Rendering plot based on self.last_parsed data.")
            try:
                # Get current toggle states
                show_routes_state = self.show_routes_var.get()
                show_labels_state = self.show_labels_var.get()
                # Get current label content settings
                current_label_settings = {key: var.get() for key, var in self.label_settings_vars.items()}
                logging.debug(f"Calling render_matplotlib_plot with show_routes={show_routes_state}, show_labels={show_labels_state}, label_settings={current_label_settings}.")

                # Render the plot, passing toggle states and label settings
                canvas, label_artists = render_matplotlib_plot(
                    self.last_parsed, self.config_data, self.plot_frame,
                    self.info_panel, show_routes=show_routes_state,
                    show_labels=show_labels_state, label_settings=current_label_settings
                )
                # Store canvas and labels for toggling later
                self.current_canvas = canvas
                self.current_label_artists = label_artists if label_artists else []

                logging.debug("render_matplotlib_plot finished.")
                # Status is usually updated by the caller (_process_raw_data or refresh_plot_after_resolve)
            except Exception as e:
                messagebox.showerror("Error", f"Failed to render plot: {e}")
                self.update_status("Error: Failed to render plot.")
                logging.exception("Plot rendering error")
                self.clear_plot_display() # Clear display on error
        else:
            self.update_status("No data available to render plot.")
            logging.warning("refresh_plot called without valid self.last_parsed data.")
            self.clear_plot_display() # Clear display if no data
        logging.debug("--- Finished refresh_plot ---")

    def clear_plot_display(self):
        """Clears only the plot area and resets the info panel display."""
        logging.info("Clearing plot area display and resetting info panel.")
        for widget in self.plot_frame.winfo_children():
            widget.destroy()
        tk.Label(self.plot_frame, text="Load a file, paste JSON, or select a template.", bg="#ffffff").pack(expand=True) # Updated text
        self._setup_info_panel_default() # Reset info panel
        self.current_canvas = None
        self.current_label_artists = []

    def clear_plot_and_state(self):
        """Clears plot, resets info panel, and clears internal parsed data state."""
        logging.info("Clearing plot, resetting info panel, and clearing parsed state.")
        self.last_parsed = None
        self.current_file_path = None # Also clear current file path on critical errors
        self.clear_plot_display()
        # Optionally clear listbox selection?
        # self.listbox.selection_clear(0, tk.END)


    def toggle_routes(self):
        """Handles the 'Show Routes' checkbox toggle by re-rendering."""
        route_state = self.show_routes_var.get()
        state_text = 'shown' if route_state else 'hidden'
        logging.info(f"Route visibility toggled to: {route_state}. Refreshing plot.")
        self.update_status(f"Routes {state_text}. Refreshing plot...")

        # Re-render the plot with the new setting IF data exists
        if self.last_parsed:
            self.refresh_plot() # refresh_plot now reads the latest toggle states
            self.update_status(f"Plot refreshed. Routes are {state_text}.")
        else:
            logging.warning("Toggle routes called but no data loaded.")
            self.update_status("Load data to toggle route visibility.")

    def toggle_labels(self):
        """Handles the 'Show Labels' checkbox toggle (overall visibility)."""
        # This now only controls the *overall* visibility. Content is set via settings.
        label_state = self.show_labels_var.get()
        state_text = 'shown' if label_state else 'hidden'
        logging.info(f"Label visibility toggled to: {label_state}")

        if self.current_canvas and self.current_label_artists:
            self.update_status(f"Labels {state_text}. Updating display...")
            try:
                for label in self.current_label_artists:
                    label.set_visible(label_state)
                self.current_canvas.draw_idle() # Redraw efficiently
                self.update_status(f"Plot updated. Labels are {state_text}.")
            except Exception as e:
                 logging.exception("Error toggling label visibility")
                 self.update_status(f"Error updating labels to {state_text}. Re-rendering...")
                 # Fallback to full refresh on error
                 self.refresh_plot()

        elif self.last_parsed:
             # Data exists, but canvas/artists aren't stored (shouldn't happen often)
             # Do a full refresh
             logging.warning("Toggle labels called, data exists but no canvas/artists. Performing full refresh.")
             self.update_status(f"Labels {state_text}. Refreshing plot...")
             self.refresh_plot()
             self.update_status(f"Plot refreshed. Labels are {state_text}.")
        else:
             logging.warning("Toggle labels called but no data loaded.")
             self.update_status("Load data to toggle label visibility.")

    # --- Settings Dialog ---
    def open_label_settings_dialog(self):
        """Opens the dialog to configure pin label display."""
        dialog = tk.Toplevel(self)
        dialog.title("Pin Label Display Settings")
        dialog.geometry("350x250") # Adjusted size
        dialog.resizable(False, False)
        dialog.grab_set() # Make modal

        # Temporary variables for the dialog, initialized from app state
        temp_vars = {key: tk.BooleanVar(value=var.get()) for key, var in self.label_settings_vars.items()}

        main_frame = tk.Frame(dialog, padx=15, pady=15)
        main_frame.pack(fill="both", expand=True)

        tk.Label(main_frame, text="Show in Pin Labels:", font=("Segoe UI", 10, "bold")).pack(anchor='w', pady=(0, 10))

        # Create checkboxes linked to temp_vars
        tk.Checkbutton(main_frame, text="Pin Name (Category)", variable=temp_vars["show_pin_name"], anchor='w').pack(fill='x')
        tk.Checkbutton(main_frame, text="Pin Type ID", variable=temp_vars["show_pin_id"], anchor='w').pack(fill='x')
        tk.Checkbutton(main_frame, text="Schematic Name", variable=temp_vars["show_schematic_name"], anchor='w').pack(fill='x')
        tk.Checkbutton(main_frame, text="Schematic ID", variable=temp_vars["show_schematic_id"], anchor='w').pack(fill='x')

        # --- Button Frame ---
        button_frame = tk.Frame(main_frame)
        # Pack buttons to the bottom right
        button_frame.pack(side=tk.BOTTOM, fill="x", pady=(20, 0))
        button_frame.column_configure(0, weight=1) # Push buttons right

        def apply_changes():
            """Applies the temporary settings to the main app state and refreshes the plot."""
            logging.info("Applying label settings changes.")
            for key, temp_var in temp_vars.items():
                self.label_settings_vars[key].set(temp_var.get())
            self.refresh_plot() # Re-render with new label settings
            self.update_status("Label display settings applied.")

        def save_and_apply():
            """Applies changes and saves them as default to config."""
            apply_changes() # Apply first
            logging.info("Saving label settings as default.")
            current_settings = {key: var.get() for key, var in self.label_settings_vars.items()}
            try:
                if self.config_data.save_label_settings(current_settings):
                    self.config_data.save() # Persist changes to file
                    self.update_status("Label display settings saved as default.")
                    messagebox.showinfo("Settings Saved", "Label display settings saved as default.", parent=dialog)
                else:
                     messagebox.showerror("Error", "Failed to prepare settings for saving.", parent=dialog)
            except Exception as e:
                 messagebox.showerror("Error", f"Failed to save settings to configuration file:\n{e}", parent=dialog)
                 logging.exception("Failed to save label settings to config file.")
            dialog.destroy()


        def cancel():
            logging.debug("Label settings dialog cancelled.")
            dialog.destroy()

        # Buttons on the right side
        cancel_btn = tk.Button(button_frame, text="Cancel", command=cancel, width=10)
        cancel_btn.pack(side=tk.RIGHT, padx=(5, 0))

        apply_btn = tk.Button(button_frame, text="Apply", command=lambda: [apply_changes(), dialog.destroy()], width=10)
        apply_btn.pack(side=tk.RIGHT, padx=(5,0))

        save_btn = tk.Button(button_frame, text="Save as Default", command=save_and_apply, width=15)
        save_btn.pack(side=tk.RIGHT)


        dialog.protocol("WM_DELETE_WINDOW", cancel) # Handle closing window
        dialog.wait_window()


if __name__ == "__main__":
    logging.info("--- Starting PI Viewer Application ---")
    app = PIViewerApp()
    app.mainloop()
    logging.info("--- PI Viewer Application finished ---")
