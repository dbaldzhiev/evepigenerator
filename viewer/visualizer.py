import tkinter as tk
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyArrowPatch
from matplotlib.lines import Line2D
import matplotlib.path as mpath
import logging
import math

# --- Define Pin Styles ---
CATEGORY_STYLES = {
    "Extractor": {"color": "#cc2e70", "marker": "X", "size": 12, "zorder": 6},
    "Launchpad": {"color": "#00ff4c", "marker": "^", "size": 12, "zorder": 6},
    "Basic Industrial Facility": {"color": "#f1c40f", "marker": "s", "size": 12, "zorder": 6},
    "Advanced Industrial Facility": {"color": "#e67e22", "marker": "p", "size": 12, "zorder": 6},
    "High-Tech Industrial Facility": {"color": "#e74c3c", "marker": "h", "size": 12, "zorder": 6},
    "Storage Facility": {"color": "#25a6af", "marker": "o", "size": 12, "zorder": 6},
    "Command Center": {"color": "#9b59b6", "marker": "*", "size": 12, "zorder": 6},
    "Unknown": {"color": "#34495e", "marker": "o", "size": 12, "zorder": 6}
}
DEFAULT_STYLE = CATEGORY_STYLES["Unknown"]

# --- Define Colors and Styles ---
ROUTE_COLOR = "#3498db"            # Blue for routes
ROUTE_HIGHLIGHT_COLOR = "#2980b9"    # Darker blue for selected route
ROUTE_PIN_HIGHLIGHT_COLOR = "#f39c12" # Orange for routes connected to selected pin
LINK_COLOR = "#95a5a6"             # Gray for links (less prominent)
PIN_HIGHLIGHT_BORDER_COLOR = "#e74c3c" # Red border for selected pin
PIN_LABEL_BG_COLOR = 'white'
PIN_LABEL_ALPHA = 0.85

# Adjusted for thinner lines and smaller arrowheads
ARROW_STYLE = "Simple,tail_width=0.3,head_width=1.5,head_length=3"
ROUTE_LINE_WIDTH = 0.125
ROUTE_MUTATION_SCALE = 2
LINK_LINE_WIDTH_BASE = 0.5
PIN_PICKER_RADIUS = 5 # Radius in points for clicking on pins/routes

def _get_pin_style(pin_category):
    """Gets the marker style dictionary for a given pin category."""
    # Use startswith for robustness against planet names like "Basic (Barren)"
    for key, style in CATEGORY_STYLES.items():
        if pin_category.startswith(key):
            return style
    return DEFAULT_STYLE # Fallback

def _format_pin_display_name(pin_data):
    """Creates a user-friendly display name for a pin."""
    category = pin_data.get('category', 'Unknown')
    type_id = pin_data.get('type_id', 'N/A')
    type_name = pin_data.get('type_name', 'Unknown Type') # Already formatted Category (Planet)
    original_index = pin_data.get('original_index', '?')

    if category == 'Unknown':
        # If category is Unknown, show the ID clearly
        name = f"Unknown Type ({type_id}) (#{original_index})"
    else:
        # Otherwise, use the resolved type_name
        name = f"{type_name} (#{original_index})"

    # Add schematic info if present
    schematic_name = pin_data.get("schematic_name")
    schematic_id = pin_data.get("schematic_id")
    if schematic_name:
        name += f"\n  ({schematic_name})"
    elif schematic_id is not None: # Only show if ID exists but name is unknown
        name += f"\n  (Unknown Sch: {schematic_id})"

    return name


def render_matplotlib_plot(parsed, config, container_frame, info_panel=None, show_routes=True):
    """Renders the PI layout plot with interactive elements."""
    for widget in container_frame.winfo_children():
        widget.destroy()

    if not parsed or not parsed.get("pins"):
        tk.Label(container_frame, text="No data to display.", bg=container_frame.cget('bg')).pack(expand=True)
        if info_panel:
            _reset_info_panel(info_panel)
        return

    fig, ax = plt.subplots(figsize=(10, 7), facecolor=container_frame.cget('bg'))
    ax.set_facecolor('#ffffff')  # White background for plot area

    pins_by_index = {pin['index']: pin for pin in parsed["pins"]}
    pin_artists = {} # Store matplotlib artists {pin_index: Line2D}
    route_patches = [] # Store route FancyArrowPatch objects

    # --- State Tracking ---
    selected_pin_artist = None
    selected_route_patch = None
    highlighted_route_patches = [] # Routes highlighted due to pin selection

    # --- Plot Pins ---
    logging.debug("Plotting pins...")
    for pin in parsed["pins"]:
        x, y = pin["lon"], pin["lat"]
        category = pin.get("category", "Unknown")
        style = _get_pin_style(category)

        # Create the pin marker (plot point)
        # Use picker=PIN_PICKER_RADIUS to make it clickable
        pin_artist, = ax.plot(x, y, marker=style["marker"], color=style["color"],
                              markersize=style["size"], linestyle='None',
                              zorder=style["zorder"], picker=PIN_PICKER_RADIUS, gid=pin['index']) # Store pin index in gid

        pin_artist.pin_data = pin # Attach pin data to the artist
        pin_artists[pin['index']] = pin_artist

        # Add pin label text
        label_text = _format_pin_display_name(pin).split('\n')[0] # Show only first line initially
        ax.text(x, y + 0.0015, label_text, ha='center', va='bottom', fontsize=7,
                bbox=dict(facecolor=PIN_LABEL_BG_COLOR, edgecolor='none', alpha=PIN_LABEL_ALPHA, pad=0.3),
                zorder=style["zorder"] + 1) # Label above pin

    # --- Plot Links ---
    logging.debug("Plotting links...")
    for link in parsed.get("links", []):
        try:
            src = pins_by_index[link["source"]]
            dst = pins_by_index[link["target"]]
            link_lw = max(0.5, link.get("level", 1) * LINK_LINE_WIDTH_BASE)
            ax.plot([src["lon"], dst["lon"]], [src["lat"], dst["lat"]],
                    color=LINK_COLOR, linewidth=link_lw,
                    linestyle='--', zorder=1) # Links behind pins/routes
        except KeyError as e:
            logging.warning(f"Skipping link due to missing pin index: {e}. Link data: {link}")

    # --- Plot Routes with Curved Arrows ---
    logging.debug("Plotting routes...")
    routes_data = parsed.get('routes', [])
    for i, route in enumerate(routes_data):
        try:
            src_idx = route["source"]
            dst_idx = route["target"]
            src = pins_by_index[src_idx]
            dst = pins_by_index[dst_idx]
            src_coords = (src["lon"], src["lat"])
            dst_coords = (dst["lon"], dst["lat"])

            # --- Calculate Curve Control Point ---
            dx = dst_coords[0] - src_coords[0]
            dy = dst_coords[1] - src_coords[1]
            dist = math.hypot(dx, dy)
            if dist < 1e-6: # Avoid division by zero for overlapping pins
                logging.warning(f"Skipping route #{i} between pin {src_idx} and {dst_idx} due to zero distance.")
                continue

            # Normal vector to the line segment
            norm_x = -dy / dist
            norm_y = dx / dist

            # Base curvature + variation to separate parallel routes
            base_offset_scale = dist * 0.1
            offset_variation = (i % 7) * 0.03 # Cycle through 7 offsets
            offset_direction = 1 if (i // 7) % 2 == 0 else -1 # Alternate direction
            offset_scale = base_offset_scale * (1 + offset_variation) * offset_direction

            # Quadratic Bezier control point
            ctrl_x = (src_coords[0] + dst_coords[0]) / 2 + norm_x * offset_scale
            ctrl_y = (src_coords[1] + dst_coords[1]) / 2 + norm_y * offset_scale

            # --- Create Path and Patch ---
            Path = mpath.Path
            path_data = [
                (Path.MOVETO, src_coords),
                (Path.CURVE3, (ctrl_x, ctrl_y)), # Single control point
                (Path.LINETO, dst_coords)         # End point
            ]
            codes, verts = zip(*path_data)
            path = Path(verts, codes)

            patch = FancyArrowPatch(path=path, arrowstyle=ARROW_STYLE, mutation_scale=ROUTE_MUTATION_SCALE,
                                    edgecolor=ROUTE_COLOR, facecolor=ROUTE_COLOR,
                                    lw=ROUTE_LINE_WIDTH,
                                    alpha=0.7, zorder=2, # Routes above links, below pins
                                    shrinkA=2, shrinkB=2, # Shrink ends slightly
                                    picker=PIN_PICKER_RADIUS) # Make routes clickable

            # Store data and original style on the patch
            patch.route_data = route
            patch.original_lw = ROUTE_LINE_WIDTH
            patch.original_edgecolor = ROUTE_COLOR
            patch.original_facecolor = ROUTE_COLOR
            patch.original_zorder = 2
            patch.set_visible(show_routes) # Set initial visibility
            ax.add_patch(patch)
            route_patches.append(patch)

        except KeyError as e:
            logging.warning(f"Skipping route due to missing pin index: {e}. Route data: {route}")
        except Exception as e:
            logging.error(f"Error drawing route #{i} between pin {src_idx} and {dst_idx}: {e}", exc_info=True)

    # --- Plot Setup ---
    ax.set_aspect('equal', adjustable='box')
    ax.invert_yaxis()
    # ax.invert_xaxis() # Usually not needed for lat/lon? Test this.
    ax.axis('off')

    # --- Add Title/Subtitle ---
    title_parts = []
    if parsed.get("planet_name"):
        title_parts.append(f"Planet: {parsed['planet_name']}")
    if parsed.get("cmdctr"):
        title_parts.append(f"CC Lvl: {parsed['cmdctr']}")
    # if parsed.get("diameter"): # Diameter often not useful?
    #     title_parts.append(f"Diameter: {parsed['diameter']}")
    main_title = " | ".join(title_parts)
    sub_title = parsed.get("comment", "")

    ax.set_title(main_title, fontsize=12, pad=20)
    if sub_title:
        plt.suptitle(sub_title, fontsize=9, y=0.98)

    # --- Embed in Tkinter ---
    canvas = FigureCanvasTkAgg(fig, master=container_frame)
    canvas_widget = canvas.get_tk_widget()
    canvas_widget.pack(fill=tk.BOTH, expand=True)

    toolbar_frame = tk.Frame(container_frame, bg=container_frame.cget('bg'))
    toolbar_frame.pack(fill=tk.X, side=tk.BOTTOM)
    toolbar = NavigationToolbar2Tk(canvas, toolbar_frame)
    toolbar.update()

    # --- Interaction Logic ---

    def _reset_highlights():
        """Resets all highlights (pin and routes)."""
        nonlocal selected_pin_artist, selected_route_patch, highlighted_route_patches

        # Reset previously selected pin
        if selected_pin_artist:
            selected_pin_artist.set_markeredgewidth(0) # Remove border
            selected_pin_artist = None

        # Reset previously selected route
        if selected_route_patch:
            patch = selected_route_patch
            patch.set(lw=patch.original_lw, edgecolor=patch.original_edgecolor,
                      facecolor=patch.original_facecolor, zorder=patch.original_zorder)
            selected_route_patch = None

        # Reset routes highlighted by pin selection
        for patch in highlighted_route_patches:
             # Check if it wasn't also the directly selected route
            if patch != selected_route_patch:
                patch.set(lw=patch.original_lw, edgecolor=patch.original_edgecolor,
                          facecolor=patch.original_facecolor, zorder=patch.original_zorder)
        highlighted_route_patches = []

    def _highlight_pin(pin_artist):
        """Highlights the selected pin and its connected routes."""
        nonlocal selected_pin_artist, highlighted_route_patches
        _reset_highlights() # Clear previous selections first

        selected_pin_artist = pin_artist
        pin_data = pin_artist.pin_data
        pin_index = pin_data['index']

        # Style the selected pin (e.g., add a border)
        pin_artist.set_markeredgewidth(1.5)
        pin_artist.set_markeredgecolor(PIN_HIGHLIGHT_BORDER_COLOR)
        pin_artist.set_zorder(10) # Bring pin to front

        # Find and highlight connected routes
        highlighted_route_patches = []
        for patch in route_patches:
            if not patch.get_visible(): continue # Skip hidden routes
            route_data = patch.route_data
            if route_data['source'] == pin_index or route_data['target'] == pin_index:
                patch.set(lw=patch.original_lw * 1.8, edgecolor=ROUTE_PIN_HIGHLIGHT_COLOR,
                          facecolor=ROUTE_PIN_HIGHLIGHT_COLOR, zorder=3) # Highlight connected routes
                highlighted_route_patches.append(patch)

        if info_panel:
            _update_info_panel_for_pin(info_panel, pin_data)

    def _highlight_route(route_patch):
        """Highlights the selected route."""
        nonlocal selected_route_patch
        _reset_highlights() # Clear previous selections first

        selected_route_patch = route_patch
        route_data = route_patch.route_data

        # Style the selected route
        route_patch.set(lw=route_patch.original_lw * 2.5, edgecolor=ROUTE_HIGHLIGHT_COLOR,
                        facecolor=ROUTE_HIGHLIGHT_COLOR, zorder=10) # Bring route to front

        if info_panel:
            _update_info_panel_for_route(info_panel, route_data, pins_by_index)


    def on_pick(event):
        """Handles clicks on pins or routes."""
        # Ignore if navigation toolbar is active
        if toolbar.mode != '':
            return

        artist = event.artist
        logging.debug(f"Pick event on: {type(artist)}")

        if isinstance(artist, Line2D) and hasattr(artist, 'pin_data'):
            # Clicked on a Pin
            logging.info(f"Pin clicked: Index {artist.pin_data['index']}")
            _highlight_pin(artist)
        elif isinstance(artist, FancyArrowPatch) and hasattr(artist, 'route_data'):
            # Clicked on a Route
            logging.info(f"Route clicked: {artist.route_data['commodity_name']} from {artist.route_data['source']} to {artist.route_data['target']}")
            _highlight_route(artist)
        else:
            # Clicked on something else or empty space
            logging.debug("Clicked on non-interactive element or background.")
            _reset_highlights()
            if info_panel:
                _reset_info_panel(info_panel)

        canvas.draw_idle() # Redraw the canvas to show changes

    # Connect the pick event handler
    fig.canvas.mpl_connect('pick_event', on_pick)

    # --- Info Panel Setup ---
    def _clear_info_panel_content(panel):
        """Clears all widgets except the title widget from the info panel."""
        title_widget = None
        for widget in panel.winfo_children():
            is_title = isinstance(widget, tk.Label) and widget.cget('font').endswith("bold") and widget.cget('text') == "Info Panel"
            if is_title:
                title_widget = widget
            else:
                widget.destroy()
        return title_widget

    def _reset_info_panel(panel):
        """Resets the info panel to its default state."""
        title_widget = _clear_info_panel_content(panel)
        if not title_widget: # Should not happen if panel setup correctly
             tk.Label(panel, text="Info Panel", font=("Segoe UI", 12, "bold"),
                      bg=panel.cget('bg')).pack(pady=(10, 5), anchor='nw', padx=10)

        default_info = tk.Label(panel, text="Click on a pin (marker) or a route (curved arrow) to see details here.",
                                bg=panel.cget('bg'), justify=tk.LEFT, wraplength=230)
        default_info.pack(pady=5, padx=10, anchor="nw")

    def _update_info_panel_for_pin(panel, pin_data):
        """Updates the info panel with details of the selected pin."""
        title_widget = _clear_info_panel_content(panel)
        if not title_widget: return

        bg_color = panel.cget('bg')
        pin_name_full = _format_pin_display_name(pin_data) # Get multi-line name

        tk.Label(panel, text="Selected Pin", font=("Segoe UI", 11, "bold"),
                 bg=bg_color).pack(pady=(0, 5), anchor='nw', padx=10)
        tk.Label(panel, text=pin_name_full, bg=bg_color, justify=tk.LEFT,
                 anchor='w', wraplength=230).pack(fill='x', padx=10)
        tk.Label(panel, text=f"Coordinates: ({pin_data['lat']:.4f}, {pin_data['lon']:.4f})",
                 bg=bg_color, justify=tk.LEFT, anchor='w').pack(fill='x', padx=10)

        # Add more details if needed (e.g., list connected routes?)

    def _update_info_panel_for_route(panel, route_data, pins_lookup):
        """Updates the info panel with details of the selected route."""
        title_widget = _clear_info_panel_content(panel)
        if not title_widget: return

        bg_color = panel.cget('bg')
        try:
            source_pin = pins_lookup[route_data['source']]
            target_pin = pins_lookup[route_data['target']]

            source_name = _format_pin_display_name(source_pin)
            target_name = _format_pin_display_name(target_pin)
            # Commodity name already includes ID if unknown from parser
            commodity_name = route_data.get('commodity_name', f"Unknown ({route_data.get('commodity_id', 'N/A')})")
            quantity = route_data.get('quantity', 0)

            tk.Label(panel, text="Selected Route", font=("Segoe UI", 11, "bold"),
                     bg=bg_color).pack(pady=(0, 5), anchor='nw', padx=10)
            tk.Label(panel, text=f"From:", bg=bg_color, justify=tk.LEFT,
                     anchor='w').pack(fill='x', padx=10)
            tk.Label(panel, text=source_name, bg=bg_color, justify=tk.LEFT,
                     anchor='w', wraplength=230, padx=20).pack(fill='x', padx=10) # Indent pin details

            tk.Label(panel, text=f"To:", bg=bg_color, justify=tk.LEFT,
                     anchor='w').pack(fill='x', padx=10, pady=(5,0))
            tk.Label(panel, text=target_name, bg=bg_color, justify=tk.LEFT,
                     anchor='w', wraplength=230, padx=20).pack(fill='x', padx=10) # Indent pin details

            tk.Label(panel, text=f"Commodity: {commodity_name}", bg=bg_color, justify=tk.LEFT,
                     anchor='w', wraplength=230).pack(fill='x', padx=10, pady=(5,0))
            tk.Label(panel, text=f"Quantity: {quantity:,}", bg=bg_color,
                     justify=tk.LEFT, anchor='w').pack(fill='x', padx=10)

        except KeyError as e:
            logging.error(f"Info panel (route) update failed: Missing key {e}. Route: {route_data}")
            tk.Label(panel, text="Error displaying route details.\nMissing pin data.", fg="red",
                     bg=bg_color, justify=tk.LEFT).pack(pady=5, padx=10, anchor="nw")
        except Exception as e:
            logging.exception("Unexpected error updating info panel for route")
            tk.Label(panel, text="Error displaying route details.", fg="red",
                     bg=bg_color).pack(pady=5, padx=10, anchor="nw")

    # Initialize info panel
    if info_panel:
        _reset_info_panel(info_panel)

    canvas.draw() # Initial draw
