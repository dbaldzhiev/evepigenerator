import tkinter as tk
from tkinter import ttk, filedialog, messagebox
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

        # --- Load Configuration ---
        try:
            self.config_data = Config(CONFIG_PATH)
            logging.info(f"Configuration loaded successfully from {CONFIG_PATH}")
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
        self.update_status("Application ready. Load a PI JSON file or select a template.")

    def build_ui(self):
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
        load_button = tk.Button(sidebar, text="Load File...", command=self.load_file_from_dialog, bg="#1abc9c", fg="white", relief=tk.FLAT, font=("Segoe UI", 10))
        load_button.pack(pady=10, padx=10, fill="x")

        route_toggle = tk.Checkbutton(sidebar, text="Show Routes", variable=self.show_routes_var,
                                      command=self.toggle_routes, bg="#2c3e50", fg="white",
                                      selectcolor="#34495e", activebackground="#2c3e50",
                                      activeforeground="white", font=("Segoe UI", 10), anchor='w')
        route_toggle.pack(pady=(0, 10), padx=10, fill='x')

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
        # --- Updated default text ---
        self.info_content_label = tk.Label(self.info_panel,
                                           text="Load a PI JSON file or select a template.\n\n"
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

        self.update_status(f"Parsing data from {file_basename}...")
        try:
            if not self.config_data:
                 logging.error("Configuration data is not loaded during process_file.")
                 raise ValueError("Configuration data is not loaded.") # Should not happen

            parsed = parse_pi_json(raw_data, self.config_data)
            if parsed is None: # Parser can return None on critical failure
                 raise ValueError("Parsing failed critically (check logs).")

            self.last_parsed = parsed # Store parsed data
            logging.info(f"Successfully parsed data for {file_basename}")

        except Exception as e:
            messagebox.showerror("Error", f"Failed to parse data from {file_basename}: {e}")
            self.update_status(f"Error: Failed parsing {file_basename}")
            logging.exception(f"Error parsing file {path}")
            self.clear_plot_and_state()
            return

        # --- Render Plot FIRST ---
        # Render the plot even if there are unknowns. They will show as "Unknown".
        logging.info("Calling refresh_plot (initial render before potential ID resolution).")
        self.refresh_plot() # This now uses self.last_parsed

        # --- Check for and Resolve Unknowns AFTER rendering initial plot ---
        unknown_commodities = list(parsed["unknowns"]["commodity"])
        unknown_pin_types = list(parsed["unknowns"]["pin_type"])
        current_planet_id = parsed.get("planet_id") # Get planet_id from parser result
        logging.info(f"Planet ID from JSON parser: {current_planet_id}")

        resolution_needed = False
        if unknown_commodities:
            resolution_needed = True
            logging.info(f"Resolving unknown commodities: {unknown_commodities}")
            resolve_unknown_ids(
                unknown_ids=unknown_commodities, id_type="commodity",
                known_options=list(self.config_data.data.get("commodities", {}).values()),
                config=self.config_data, update_callback=self.refresh_plot_after_resolve,
                planet_id=None # Not needed for commodities
            )
        if unknown_pin_types:
            resolution_needed = True
            logging.info(f"Resolving unknown pin types: {unknown_pin_types}")
            # Provide known categories + any existing from config as suggestions
            known_categories = list(set(
                ["Extractor", "Launchpad", "Basic Industrial Facility", "Advanced Industrial Facility",
                 "High-Tech Industrial Facility", "Storage Facility", "Command Center"] +
                [v.get('category', 'Unknown') for v in self.config_data.data.get("pin_types", {}).values()]
            ))
            resolve_unknown_ids(
                unknown_ids=unknown_pin_types, id_type="pin_type",
                known_options=known_categories,
                config=self.config_data, update_callback=self.refresh_plot_after_resolve,
                planet_id=current_planet_id # Pass the planet ID
            )

        if resolution_needed:
            self.update_status(f"Plot rendered. Resolve unknown IDs for {file_basename}.")
            logging.info(f"Unknown IDs found for {file_basename}. Resolution dialogs triggered.")
        else:
            self.update_status(f"Plot rendered successfully for {file_basename}.")
            logging.info(f"Plot rendered successfully for {file_basename} (no unknown IDs found).")

        logging.info(f"--- Finished process_file for {file_basename} ---")

    def refresh_plot_after_resolve(self):
        """Callback after ID resolution. Re-parses the current file and re-renders."""
        self.update_status("IDs resolved. Re-parsing and refreshing plot...")
        logging.info("--- Starting refresh_plot_after_resolve ---")
        if self.current_file_path and self.config_data and os.path.exists(self.current_file_path):
            file_basename = os.path.basename(self.current_file_path)
            logging.info(f"Re-processing file: {file_basename}")
            try:
                # Re-read and re-parse the *original* data with the *updated* config
                with open(self.current_file_path, 'r') as f:
                    raw_data = json.load(f)
                logging.info("Re-parsing data with updated config...")
                self.last_parsed = parse_pi_json(raw_data, self.config_data) # Update parsed data

                if self.last_parsed is None:
                    raise ValueError("Re-parsing failed critically after ID resolution.")

                logging.info("Re-parsing complete. Calling refresh_plot.")
                self.refresh_plot() # Re-render using the new self.last_parsed
                self.update_status(f"Plot refreshed with resolved IDs for {file_basename}.")
                logging.info(f"Plot refreshed successfully after ID resolution for {file_basename}.")
            except Exception as e:
                 messagebox.showerror("Error", f"Failed to re-process file after ID resolution: {e}")
                 self.update_status(f"Error: Failed re-processing {file_basename}")
                 logging.exception(f"Error re-processing file {self.current_file_path} after ID resolution")
                 self.clear_plot_and_state()
        else:
            errmsg = "Cannot refresh: Missing or invalid file path, or config data after ID resolution."
            self.update_status(errmsg)
            logging.warning(errmsg)
            self.clear_plot_and_state()
        logging.info("--- Finished refresh_plot_after_resolve ---")

    def refresh_plot(self):
        """Renders the plot based on self.last_parsed and current settings."""
        logging.debug("--- Starting refresh_plot ---")
        if self.last_parsed:
            logging.info("Rendering plot based on self.last_parsed data.")
            try:
                # Clear previous plot widgets (render function does this now)
                # logging.debug("Clearing previous plot widgets.")
                # for widget in self.plot_frame.winfo_children():
                #     widget.destroy()

                # Reset info panel handled within render function now
                # logging.debug("Resetting info panel to default.")
                # self._setup_info_panel_default()

                # Render the plot, passing the info_panel and route visibility state
                show_routes_state = self.show_routes_var.get()
                logging.debug(f"Calling render_matplotlib_plot with show_routes={show_routes_state}.")
                render_matplotlib_plot(self.last_parsed, self.config_data, self.plot_frame,
                                       self.info_panel, show_routes=show_routes_state)
                logging.debug("render_matplotlib_plot finished.")
                # Status is usually updated by the caller (process_file, refresh_plot_after_resolve, toggle_routes)
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
        tk.Label(self.plot_frame, text="Load a file or select a template.", bg="#ffffff").pack(expand=True)
        self._setup_info_panel_default() # Reset info panel

    def clear_plot_and_state(self):
        """Clears plot, resets info panel, and clears internal parsed data state."""
        logging.info("Clearing plot, resetting info panel, and clearing parsed state.")
        self.last_parsed = None
        self.current_file_path = None # Also clear current file path on critical errors
        self.clear_plot_display()
        # Optionally clear listbox selection?
        # self.listbox.selection_clear(0, tk.END)


    def toggle_routes(self):
        """Handles the 'Show Routes' checkbox toggle."""
        route_state = self.show_routes_var.get()
        state_text = 'shown' if route_state else 'hidden'
        logging.info(f"Route visibility toggled to: {route_state}")
        self.update_status(f"Routes {state_text}. Refreshing plot...")

        # Re-render the plot with the new setting IF data exists
        if self.last_parsed:
            self.refresh_plot()
            self.update_status(f"Plot refreshed. Routes are {state_text}.")
        else:
            logging.warning("Toggle routes called but no data loaded.")
            self.update_status("Load data to toggle route visibility.")


if __name__ == "__main__":
    logging.info("--- Starting PI Viewer Application ---")
    app = PIViewerApp()
    app.mainloop()
    logging.info("--- PI Viewer Application finished ---")

