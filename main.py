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
# Use INFO level by default, change to DEBUG for more verbose route parsing logs
logging.basicConfig(filename=LOG_FILE, level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - [%(module)s:%(lineno)d] - %(message)s')

class PIViewerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("EVE PI Viewer")
        self.geometry("1200x800") # Increased size slightly
        self.configure(bg="#f0f0f0")

        self.last_parsed = None
        self.current_file_path = None
        self.config_data = None # Initialize

        try:
            self.config_data = Config(CONFIG_PATH)
            logging.info(f"Configuration loaded successfully from {CONFIG_PATH}")
        except FileNotFoundError:
            messagebox.showerror("Error", f"Configuration file not found: {CONFIG_PATH}")
            logging.error(f"Configuration file not found: {CONFIG_PATH}")
            self.destroy()
            return
        except json.JSONDecodeError as e:
            messagebox.showerror("Error", f"Error decoding configuration file: {CONFIG_PATH} - {e}")
            logging.error(f"Error decoding configuration file: {CONFIG_PATH} - {e}")
            self.destroy()
            return
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load configuration: {e}")
            logging.exception("Configuration loading error")
            self.destroy()
            return

        self.build_ui()
        self.update_template_list()
        self.update_status("Application ready. Load a PI JSON file or select a template.")

    def build_ui(self):
        # --- Main Panes ---
        # Sidebar (Left)
        sidebar = tk.Frame(self, width=250, bg="#2c3e50")
        sidebar.pack(side="left", fill="y", padx=(0, 1), pady=0)
        sidebar.pack_propagate(False) # Prevent sidebar from shrinking

        # Main Area (Center/Right) - will contain plot and info
        main_area = tk.Frame(self, bg="#f0f0f0")
        main_area.pack(side="right", fill="both", expand=True)

        # Plot Frame (within main_area, takes most space)
        self.plot_frame = tk.Frame(main_area, bg="#ffffff") # White background for plot area
        self.plot_frame.pack(side="left", fill="both", expand=True)

        # Info Panel (within main_area, right side)
        self.info_panel = tk.Frame(main_area, width=250, bg="#eeeeee", relief=tk.SUNKEN, borderwidth=1)
        self.info_panel.pack(side="right", fill="y", padx=(0, 5), pady=5)
        self.info_panel.pack_propagate(False) # Prevent info panel from shrinking

        # --- Sidebar Widgets ---
        load_button = tk.Button(sidebar, text="Load File...", command=self.load_file_from_dialog, bg="#1abc9c", fg="white", relief=tk.FLAT, font=("Segoe UI", 10))
        load_button.pack(pady=10, padx=10, fill="x")

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

    def _clear_info_panel(self):
        """Clears the info panel except for the title."""
        for widget in self.info_panel.winfo_children():
            # Keep the title label
            is_title = isinstance(widget, tk.Label) and widget.cget('font').endswith("bold")
            if not is_title:
                widget.destroy()

    def _setup_info_panel_default(self):
        """Sets up the default content of the info panel."""
        for widget in self.info_panel.winfo_children():
            widget.destroy() # Clear everything first
        info_title = tk.Label(self.info_panel, text="Info Panel", bg="#eeeeee", font=("Segoe UI", 12, "bold"))
        info_title.pack(pady=(10, 5), anchor='nw', padx=10) # Anchor top-left
        self.info_content_label = tk.Label(self.info_panel, text="Load a PI JSON file or select a template from the list.\n\nClick on a route (orange line) in the plot to see detailed route information here.", bg="#eeeeee", justify=tk.LEFT, wraplength=230)
        self.info_content_label.pack(pady=5, padx=10, anchor="nw")


    def update_status(self, message):
        self.status_bar.config(text=f"Status: {message}")
        logging.info(f"Status Update: {message}")
        self.update_idletasks() # Force UI update

    def update_template_list(self):
        self.listbox.delete(0, tk.END) # Clear existing list
        try:
            if not os.path.exists(TEMPLATE_DIR):
                os.makedirs(TEMPLATE_DIR)
                logging.warning(f"Template directory '{TEMPLATE_DIR}' not found, created.")
                self.update_status(f"Template directory '{TEMPLATE_DIR}' created. No templates found yet.")
                self.template_files = []
            else:
                self.template_files = sorted([f for f in os.listdir(TEMPLATE_DIR) if f.endswith(".json")])

            if not self.template_files:
                 self.listbox.insert(tk.END, "(No templates found)")
                 self.listbox.config(state=tk.DISABLED)
            else:
                 self.listbox.config(state=tk.NORMAL)
                 for file in self.template_files:
                    self.listbox.insert(tk.END, file)

        except Exception as e:
            messagebox.showerror("Error", f"Error reading template directory '{TEMPLATE_DIR}': {e}")
            logging.exception("Error reading template directory")
            self.update_status(f"Error reading templates: {e}")
            self.listbox.insert(tk.END, "(Error reading templates)")
            self.listbox.config(state=tk.DISABLED)


    def load_file_from_dialog(self):
        path = filedialog.askopenfilename(
            title="Select EVE PI JSON File",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        if path:
            logging.info(f"File selected from dialog: {path}") # LOGGING
            self.current_file_path = path
            logging.info("Clearing listbox selection.") # LOGGING
            self.listbox.selection_clear(0, tk.END) # Clear template selection
            logging.info(f"Calling process_file for: {path}") # LOGGING
            self.process_file(path)
        else:
            logging.info("File dialog cancelled.") # LOGGING

    def on_template_select(self, event):
        # Check if the listbox is the source of the event
        if event.widget != self.listbox:
            logging.debug("Ignoring ListboxSelect event not from self.listbox")
            return

        selection = self.listbox.curselection()
        if not selection:
            logging.debug("Ignoring ListboxSelect event with no selection.")
            return

        # Prevent processing if the listbox is disabled or showing placeholder text
        if self.listbox.cget('state') == tk.DISABLED or self.listbox.get(selection[0]).startswith("("):
            logging.debug("Ignoring ListboxSelect event on disabled or placeholder item.")
            return

        try:
            index = selection[0]
            # Double check if this index is still actually selected
            # Prevents potential race condition if selection cleared rapidly
            if index not in self.listbox.curselection():
                 logging.warning("on_template_select fired for an index that is no longer selected. Ignoring.")
                 return

            filename = self.template_files[index] # Use stored list
            path = os.path.join(TEMPLATE_DIR, filename)

            # Avoid reprocessing the exact same file if already loaded
            # Check path AND if last_parsed exists (meaning a successful parse happened)
            if path == self.current_file_path and self.last_parsed:
                logging.info(f"Template {filename} corresponds to the currently loaded file. Skipping re-process.")
                # Ensure the selection visually remains
                self.listbox.selection_set(index)
                return

            self.current_file_path = path
            logging.info(f"Processing template selection: {filename} ({path})") # LOGGING
            self.process_file(path)
        except IndexError:
            # This can happen if template_files list changes between selection and processing
            logging.warning("Listbox selection index out of range, likely due to template list update race condition.")
            self.update_status("Error selecting template. Please try again.")
            self.update_template_list() # Refresh listbox content might help
        except Exception as e:
            messagebox.showerror("Error", f"Error processing template selection: {e}")
            logging.exception("Error processing template selection")
            self.update_status(f"Error processing template: {e}")


    def process_file(self, path):
        logging.info(f"--- Starting process_file ---")
        logging.info(f"  Target path: {path}")
        logging.info(f"  Current self.current_file_path: {self.current_file_path}") # Log internal state
        # Ensure the internal state matches the path we intend to process
        if path != self.current_file_path:
             logging.warning(f"Mismatch: process_file called with '{os.path.basename(path)}' but self.current_file_path is '{os.path.basename(self.current_file_path)}'. Updating self.current_file_path.")
             self.current_file_path = path # Ensure consistency

        self.update_status(f"Loading PI data from: {os.path.basename(path)}...")
        try:
            with open(path, 'r') as f:
                data = json.load(f)
            logging.info(f"Successfully read JSON data from {path}")
        except FileNotFoundError:
            messagebox.showerror("Error", f"File not found: {path}")
            self.update_status(f"Error: File not found {os.path.basename(path)}")
            logging.error(f"File not found: {path}")
            self.clear_plot()
            return
        except json.JSONDecodeError as e:
            messagebox.showerror("Error", f"Invalid JSON format in {os.path.basename(path)}: {e}")
            self.update_status(f"Error: Invalid JSON in {os.path.basename(path)}")
            logging.error(f"Invalid JSON in {path}: {e}")
            self.clear_plot()
            return
        except Exception as e:
            messagebox.showerror("Error", f"Failed to read file {os.path.basename(path)}: {e}")
            self.update_status(f"Error: Failed to read {os.path.basename(path)}")
            logging.exception(f"Error reading file {path}")
            self.clear_plot()
            return

        self.update_status(f"Parsing data from {os.path.basename(path)}...")
        try:
            # Ensure config is loaded
            if not self.config_data:
                 logging.error("Configuration data is not loaded during process_file.")
                 raise ValueError("Configuration data is not loaded.")
            parsed = parse_pi_json(data, self.config_data)
            self.last_parsed = parsed # Store parsed data immediately
            logging.info(f"Successfully parsed data for {os.path.basename(path)}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to parse data from {os.path.basename(path)}: {e}")
            self.update_status(f"Error: Failed parsing {os.path.basename(path)}")
            logging.exception(f"Error parsing file {path}")
            self.clear_plot()
            return

        # --- Render Plot FIRST ---
        # Render the plot even if there are unknowns. They will show as "Unknown".
        logging.info("Calling refresh_plot (initial render before potential ID resolution).")
        self.refresh_plot()

        # --- Check for and Resolve Unknowns AFTER rendering initial plot ---
        # Create copies of unknown lists as they might be modified indirectly by callbacks
        unknown_commodities = list(parsed["unknowns"]["commodity"])
        unknown_pin_types = list(parsed["unknowns"]["pin_type"])
        unknown_schematics = list(parsed["unknowns"]["schematic"])

        # Flag to track if any resolution dialogs were shown
        resolution_needed = False

        if unknown_commodities:
            resolution_needed = True
            logging.info(f"Resolving unknown commodities: {unknown_commodities}")
            resolve_unknown_ids(
                unknown_commodities,
                "commodity",
                list(self.config_data.data["commodities"].values()), # Pass known names
                self.config_data,
                self.refresh_plot_after_resolve # Use specific callback
            )
        if unknown_pin_types:
            resolution_needed = True
            logging.info(f"Resolving unknown pin types: {unknown_pin_types}")
            resolve_unknown_ids(
                unknown_pin_types,
                "pin_type",
                # Provide standard categories + existing categories from config
                list(set(["Extractor", "Launchpad", "Basic Industrial Facility", "Advanced Industrial Facility", "High-Tech Industrial Facility", "Storage Facility", "Command Center"] + [v.get('category', 'Unknown') for v in self.config_data.data["pin_types"].values()])),
                self.config_data,
                self.refresh_plot_after_resolve
            )
        if unknown_schematics:
             resolution_needed = True
             logging.info(f"Resolving unknown schematics: {unknown_schematics}")
             resolve_unknown_ids(
                unknown_schematics,
                "schematic",
                [], # No predefined list for schematics, handled by entry field
                self.config_data,
                self.refresh_plot_after_resolve
            )

        if resolution_needed:
            self.update_status(f"Plot rendered with potential unknown IDs. Please resolve them for {os.path.basename(path)}.")
            logging.info(f"Unknown IDs found for {os.path.basename(path)}. Resolution dialogs triggered.")
        else:
            # If no resolution was needed, the initial render was final for this load
            self.update_status(f"Plot rendered successfully for {os.path.basename(path)}.")
            logging.info(f"Plot rendered successfully for {os.path.basename(path)} (no unknown IDs found).")
        logging.info(f"--- Finished process_file for {os.path.basename(path)} ---")


    def refresh_plot_after_resolve(self):
        """Callback specifically for after ID resolution. Re-parses and re-renders."""
        self.update_status("IDs resolved. Re-parsing and refreshing plot...")
        logging.info("--- Starting refresh_plot_after_resolve ---")
        if self.current_file_path and self.config_data:
            logging.info(f"Re-processing file: {self.current_file_path}")
            # Re-parse the *original* data with the *updated* config
            try:
                with open(self.current_file_path, 'r') as f:
                    data = json.load(f)
                logging.info("Re-parsing data with updated config...")
                # Re-parse using the potentially updated config
                self.last_parsed = parse_pi_json(data, self.config_data)
                logging.info("Re-parsing complete. Calling refresh_plot.")
                # Now refresh the plot with the newly parsed data
                self.refresh_plot()
                self.update_status(f"Plot refreshed with resolved IDs for {os.path.basename(self.current_file_path)}.")
                logging.info(f"Plot refreshed successfully after ID resolution for {os.path.basename(self.current_file_path)}.")
            except Exception as e:
                 messagebox.showerror("Error", f"Failed to re-process file after ID resolution: {e}")
                 self.update_status(f"Error: Failed re-processing {os.path.basename(self.current_file_path)}")
                 logging.exception(f"Error re-processing file {self.current_file_path} after ID resolution")
                 self.clear_plot()
        else:
            errmsg = "Cannot refresh: Missing file path or config data after ID resolution."
            self.update_status(errmsg)
            logging.warning(errmsg)
            self.clear_plot()
        logging.info("--- Finished refresh_plot_after_resolve ---")


    def refresh_plot(self):
        """Renders the plot based on self.last_parsed."""
        logging.debug("--- Starting refresh_plot ---")
        if hasattr(self, "last_parsed") and self.last_parsed:
            logging.info("Rendering plot based on self.last_parsed data.")
            try:
                # Clear previous plot
                logging.debug("Clearing previous plot widgets.")
                for widget in self.plot_frame.winfo_children():
                    widget.destroy()

                # Reset info panel to default state before rendering
                logging.debug("Resetting info panel to default.")
                self._setup_info_panel_default()

                # Render the plot, passing the info_panel for updates
                logging.debug("Calling render_matplotlib_plot.")
                render_matplotlib_plot(self.last_parsed, self.config_data, self.plot_frame, self.info_panel)
                logging.debug("render_matplotlib_plot finished.")
                # Status update handled by calling function (process_file or refresh_plot_after_resolve)
            except Exception as e:
                messagebox.showerror("Error", f"Failed to render plot: {e}")
                self.update_status("Error: Failed to render plot.")
                logging.exception("Plot rendering error")
                self.clear_plot() # Attempt to clear frame on error
        else:
            # This case should ideally not be hit if called correctly, but good failsafe
            self.update_status("No data available to render plot.")
            logging.warning("refresh_plot called without valid self.last_parsed data.")
            self.clear_plot()
        logging.debug("--- Finished refresh_plot ---")

    def clear_plot(self):
        """Clears the plot area and resets info panel."""
        logging.info("Clearing plot area and resetting info panel.")
        for widget in self.plot_frame.winfo_children():
            widget.destroy()
        # Display a message in the plot area
        tk.Label(self.plot_frame, text="No plot data loaded or error during rendering.", bg="#ffffff").pack(expand=True)

        # Reset info panel to its default state
        self._setup_info_panel_default()


if __name__ == "__main__":
    logging.info("Starting PI Viewer Application.")
    app = PIViewerApp()
    app.mainloop()
    logging.info("PI Viewer Application finished.")
