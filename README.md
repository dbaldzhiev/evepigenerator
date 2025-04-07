# EVE PI Viewer

A desktop application for visualizing EVE Online Planetary Interaction (PI) colony layouts exported as JSON templates.

This tool helps players understand the structure, connections, and material flow within their PI setups by providing a graphical representation based on the exported JSON data.

## Features

*   **Load PI Templates:** Load `.json` files exported directly from the EVE Online client.
*   **Visual Layout:** Displays pins (structures), links (connections), and routes (material flow) on a 2D plot using Matplotlib.
*   **ID Resolution:** Maps internal EVE Type IDs (for pins, commodities, schematics) to human-readable names using a configurable `config.json` file.
*   **Unknown ID Handling:** Prompts the user to identify unknown IDs encountered in a template and automatically updates the `config.json`.
*   **Template Management:** Load and manage saved templates from a local `templates/` directory.
*   **Interactive Plot:**
    *   Zoom and pan the layout view.
    *   Click on routes (curved arrows) to view detailed information (source, destination, commodity, quantity) in the Info Panel.
    *   Toggle route visibility.
*   **Clear Information Display:** Shows pin types, installed schematics (if any), and route details.
*   **Logging:** Records application events and potential errors to `pi_viewer.log` for debugging.

## Screenshots

*(Add screenshots of the application interface here if possible)*

*   *Main window showing a loaded PI layout.*
*   *Info panel displaying route details after clicking a route.*
*   *ID Editor window prompting for unknown pin types.*

## Requirements

*   **Python:** Version 3.6 or higher recommended.
*   **Tkinter:** Usually included with standard Python installations. If not, you may need to install it separately (e.g., `sudo apt-get install python3-tk` on Debian/Ubuntu, `brew install python-tk` on macOS).
*   **Matplotlib:** For plotting the layout (`pip install matplotlib`).

## Installation

1.  **Clone or Download:** Get the project files:
    ```bash
    git clone <your-repository-url>
    cd eve-pi-viewer