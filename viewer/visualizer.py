import tkinter as tk
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyArrowPatch
from matplotlib.lines import Line2D
import matplotlib.path as mpath
import logging
import math
from collections import defaultdict

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

def _format_pin_display_name(pin_data, include_index=True):
    """
    Creates a user-friendly display name for a pin.
    Args:
        pin_data (dict): The pin data dictionary.
        include_index (bool): Whether to include the original index in the name.
    """
    category = pin_data.get('category', 'Unknown')
    type_id = pin_data.get('type_id', 'N/A')
    type_name = pin_data.get('type_name', 'Unknown Type') # Already formatted Category (Planet)
    original_index = pin_data.get('original_index', '?')

    if category == 'Unknown':
        # If category is Unknown, show the ID clearly
        name = f"Unknown Type ({type_id})"
    else:
        # Otherwise, use the resolved type_name
        name = f"{type_name}"

    if include_index:
        name += f" (#{original_index})"

    # Add schematic info if present
    schematic_name = pin_data.get("schematic_name")
    schematic_id = pin_data.get("schematic_id")
    if schematic_name:
        name += f"\n  ({schematic_name})"
    elif schematic_id is not None: # Only show if ID exists but name is unknown
        name += f"\n  (Unknown Sch: {schematic_id})"

    return name


def render_matplotlib_plot(parsed, config, container_frame, info_panel=None, show_routes=True, show_labels=True):
    """
    Renders the PI layout plot with interactive elements.

    Returns:
        tuple: (canvas, label_artists) or (None, None) on failure.
               canvas is the FigureCanvasTkAgg object.
               label_artists is a list of matplotlib Text objects for pin labels.
    """
    for widget in container_frame.winfo_children():
        widget.destroy()

    if not parsed or not parsed.get("pins"):
        tk.Label(container_frame, text="No data to display.", bg=container_frame.cget('bg')).pack(expand=True)
        if info_panel:
            _reset_info_panel(info_panel)
        return None, None

    fig, ax = plt.subplots(figsize=(10, 7), facecolor=container_frame.cget('bg'))
    ax.set_facecolor('#ffffff')  # White background for plot area

    pins_by_index = {pin['index']: pin for pin in parsed["pins"]}
    pin_artists = {} # Store matplotlib artists {pin_index: Line2D}
    route_patches = [] # Store route FancyArrowPatch objects (one per merged group)
    label_artists = [] # Store matplotlib Text objects for labels

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
        pin_artist, = ax.plot(x, y, marker=style["marker"], color=style["color"],
                              markersize=style["size"], linestyle='None',
                              zorder=style["zorder"], picker=PIN_PICKER_RADIUS, gid=pin['index']) # Store pin index in gid

        pin_artist.pin_data = pin # Attach pin data to the artist
        pin_artists[pin['index']] = pin_artist

        # Add pin label text (without index for plot display)
        label_text = _format_pin_display_name(pin, include_index=False).split('\n')[0] # Show only first line initially
        label_artist = ax.text(x, y + 0.003, label_text, ha='center', va='bottom', fontsize=7,
                               bbox=dict(facecolor=PIN_LABEL_BG_COLOR, edgecolor='none', alpha=PIN_LABEL_ALPHA, pad=0.3),
                               zorder=style["zorder"] + 1, # Label above pin
                               visible=show_labels) # Set initial visibility
        label_artists.append(label_artist)

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

    # --- Group and Plot Routes ---
    logging.debug("Grouping and plotting routes...")
    routes_data = parsed.get('routes', [])
    # Group routes by the pair of connected pins (order doesn't matter)
    grouped_routes = defaultdict(list)
    for route in routes_data:
        try:
            src_idx = route["source"]
            dst_idx = route["target"]
            # Ensure pins exist before grouping
            if src_idx in pins_by_index and dst_idx in pins_by_index:
                key = tuple(sorted((src_idx, dst_idx))) # Unique key for the pin pair
                grouped_routes[key].append(route)
            else:
                 logging.warning(f"Skipping route due to missing pin index in pins_by_index. Route data: {route}")
        except KeyError as e:
            logging.warning(f"Skipping route during grouping due to missing key: {e}. Route data: {route}")

    route_group_counter = 0 # To vary curve offset
    for pin_pair_key, routes_in_group in grouped_routes.items():
        if not routes_in_group: continue # Should not happen with defaultdict, but safety first

        # Use the first route in the group to determine path geometry
        # (All routes in the group share the same start/end pins)
        first_route = routes_in_group[0]
        try:
            src_idx = first_route["source"]
            dst_idx = first_route["target"]
            src = pins_by_index[src_idx]
            dst = pins_by_index[dst_idx]
            src_coords = (src["lon"], src["lat"])
            dst_coords = (dst["lon"], dst["lat"])

            # --- Calculate Curve Control Point ---
            dx = dst_coords[0] - src_coords[0]
            dy = dst_coords[1] - src_coords[1]
            dist = math.hypot(dx, dy)
            if dist < 1e-6: # Avoid division by zero for overlapping pins
                logging.warning(f"Skipping route group between pin {src_idx} and {dst_idx} due to zero distance.")
                continue

            # Normal vector to the line segment
            norm_x = -dy / dist
            norm_y = dx / dist

            # Base curvature + slight variation to separate parallel *groups* of routes
            # (Individual routes within the group are now merged visually)
            base_offset_scale = dist * 0.1
            # Use a simpler offset scheme now that we group
            offset_variation = (route_group_counter % 5) * 0.05 # Cycle through 5 offsets for different pin pairs
            offset_direction = 1 if (route_group_counter // 5) % 2 == 0 else -1 # Alternate direction
            offset_scale = base_offset_scale * (1 + offset_variation) * offset_direction

            route_group_counter += 1 # Increment for next group

            # Quadratic Bezier control point
            ctrl_x = (src_coords[0] + dst_coords[0]) / 2 + norm_x * offset_scale
            ctrl_y = (src_coords[1] + dst_coords[1]) / 2 + norm_y * offset_scale

            # --- Create Path and Patch ---
            Path = mpath.Path
            # Determine arrow direction based on the *first* route in the list
            # (This is arbitrary if routes go both ways, but consistent)
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

            # Store the *list* of route data and original style on the patch
            patch.route_data_list = routes_in_group # Store the whole list
            patch.original_lw = ROUTE_LINE_WIDTH
            patch.original_edgecolor = ROUTE_COLOR
            patch.original_facecolor = ROUTE_COLOR
            patch.original_zorder = 2
            patch.set_visible(show_routes) # Set initial visibility
            ax.add_patch(patch)
            route_patches.append(patch) # Add the single patch representing the group

        except KeyError as e:
            logging.warning(f"Skipping route group due to missing pin index: {e}. First route data: {first_route}")
        except Exception as e:
            logging.error(f"Error drawing route group between pins {pin_pair_key}: {e}", exc_info=True)


    # --- Plot Setup ---
    ax.set_aspect('equal', adjustable='box')
    ax.invert_yaxis()
    # ax.invert_xaxis() # Usually not needed for lat/lon
    ax.axis('off')

    # --- Add Title/Subtitle ---
    title_parts = []
    if parsed.get("planet_name"):
        title_parts.append(f"Planet: {parsed['planet_name']}")
    if parsed.get("cmdctr"):
        title_parts.append(f"CC Lvl: {parsed['cmdctr']}")
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
    # The NavigationToolbar2Tk provides zoom/pan controls
    toolbar = NavigationToolbar2Tk(canvas, toolbar_frame)
    toolbar.update()

    # --- Interaction Logic ---

    def _reset_highlights():
        """Resets all highlights (pin and routes)."""
        nonlocal selected_pin_artist, selected_route_patch, highlighted_route_patches

        # Reset previously selected pin
        if selected_pin_artist:
            selected_pin_artist.set_markeredgewidth(0) # Remove border
            selected_pin_artist.set_zorder(_get_pin_style(selected_pin_artist.pin_data.get("category", "Unknown"))["zorder"]) # Reset zorder
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
        # Reset info panel if nothing is selected
        if info_panel:
             _reset_info_panel(info_panel)


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

        # Find and highlight connected routes (using the grouped patches)
        highlighted_route_patches = []
        connected_routes_data = [] # For info panel

        for patch in route_patches:
            if not patch.get_visible(): continue # Skip hidden routes
            # Check if the selected pin is part of this route group's pair
            route_list = patch.route_data_list
            if not route_list: continue
            # Check source/target of the first route (representative of the pair)
            first_route_in_group = route_list[0]
            if first_route_in_group['source'] == pin_index or first_route_in_group['target'] == pin_index:
                patch.set(lw=patch.original_lw * 1.8, edgecolor=ROUTE_PIN_HIGHLIGHT_COLOR,
                          facecolor=ROUTE_PIN_HIGHLIGHT_COLOR, zorder=3) # Highlight connected routes
                highlighted_route_patches.append(patch)
                connected_routes_data.extend(route_list) # Add all routes in the group

        if info_panel:
            # Pass all routes (not just groups) connected to this pin
            all_routes = parsed.get('routes', [])
            _update_info_panel_for_pin(info_panel, pin_data, all_routes, pins_by_index)

    def _highlight_route(route_patch):
        """Highlights the selected route group."""
        nonlocal selected_route_patch
        _reset_highlights() # Clear previous selections first

        selected_route_patch = route_patch
        route_data_list = route_patch.route_data_list # Get the list of routes

        # Style the selected route group arrow
        route_patch.set(lw=route_patch.original_lw * 2.5, edgecolor=ROUTE_HIGHLIGHT_COLOR,
                        facecolor=ROUTE_HIGHLIGHT_COLOR, zorder=10) # Bring route to front

        if info_panel:
            # Pass the list of routes to the info panel function
            _update_info_panel_for_route(info_panel, route_data_list, pins_by_index)


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
        elif isinstance(artist, FancyArrowPatch) and hasattr(artist, 'route_data_list'):
            # Clicked on a Route (group)
            route_list = artist.route_data_list
            logging.info(f"Route group clicked: Representing {len(route_list)} route(s) between pins {tuple(sorted((route_list[0]['source'], route_list[0]['target'])))}")
            _highlight_route(artist)
        else:
            # Clicked on something else or empty space
            logging.debug("Clicked on non-interactive element or background.")
            _reset_highlights()
            # Info panel reset is handled within _reset_highlights

        canvas.draw_idle() # Redraw the canvas to show changes

    # Connect the pick event handler
    fig.canvas.mpl_connect('pick_event', on_pick)
    # Connect button press event to handle background clicks for deselection
    def on_button_press(event):
         # Check if the click was outside any axes (likely background)
         # and not on an interactive artist (picker should handle artists)
         if event.inaxes is None and toolbar.mode == '':
             logging.debug("Background click detected.")
             _reset_highlights()
             canvas.draw_idle()

    fig.canvas.mpl_connect('button_press_event', on_button_press)


    # --- Info Panel Setup ---
    def _clear_info_panel_content(panel):
        """Clears all widgets except the title widget from the info panel."""
        title_widget = None
        for widget in panel.winfo_children():
            is_title = isinstance(widget, tk.Label) and widget.cget('font').endswith("bold") # Simpler check
            if is_title and widget.cget('text') == "Info Panel": # Check text too
                title_widget = widget
            else:
                widget.destroy()
        # If title wasn't found (e.g., after error), recreate it
        if not title_widget and panel.winfo_children(): # Check if panel has children before adding
             title_widget = tk.Label(panel, text="Info Panel", font=("Segoe UI", 12, "bold"),
                                     bg=panel.cget('bg'))
             title_widget.pack(pady=(10, 5), anchor='nw', padx=10)
        elif not panel.winfo_children(): # Panel was empty
             title_widget = tk.Label(panel, text="Info Panel", font=("Segoe UI", 12, "bold"),
                                     bg=panel.cget('bg'))
             title_widget.pack(pady=(10, 5), anchor='nw', padx=10)

        return title_widget

    def _reset_info_panel(panel):
        """Resets the info panel to its default state."""
        title_widget = _clear_info_panel_content(panel)
        # title_widget should always be valid now

        default_info = tk.Label(panel, text="Click on a pin (marker) or a route (curved arrow) to see details here.",
                                bg=panel.cget('bg'), justify=tk.LEFT, wraplength=230)
        default_info.pack(pady=5, padx=10, anchor="nw")

    def _update_info_panel_for_pin(panel, pin_data, all_routes, pins_lookup):
        """Updates the info panel with details of the selected pin and its routes."""
        title_widget = _clear_info_panel_content(panel)
        if not title_widget: return

        bg_color = panel.cget('bg')
        pin_index = pin_data['index']
        # Get multi-line name including index for info panel
        pin_name_full = _format_pin_display_name(pin_data, include_index=True)

        tk.Label(panel, text="Selected Pin", font=("Segoe UI", 11, "bold"),
                 bg=bg_color).pack(pady=(0, 5), anchor='nw', padx=10)
        tk.Label(panel, text=pin_name_full, bg=bg_color, justify=tk.LEFT,
                 anchor='w', wraplength=230).pack(fill='x', padx=10)
        tk.Label(panel, text=f"Coordinates: ({pin_data['lat']:.4f}, {pin_data['lon']:.4f})",
                 bg=bg_color, justify=tk.LEFT, anchor='w').pack(fill='x', padx=10, pady=(0, 10))

        # --- Display Incoming/Outgoing Routes ---
        incoming_routes = []
        outgoing_routes = []
        for route in all_routes:
            if route['target'] == pin_index:
                incoming_routes.append(route)
            elif route['source'] == pin_index:
                outgoing_routes.append(route)

        if incoming_routes:
            tk.Label(panel, text="Incoming Routes:", font=("Segoe UI", 10, "bold"),
                     bg=bg_color, anchor='w').pack(fill='x', padx=10, pady=(5, 2))
            for route in incoming_routes:
                 try:
                     source_pin = pins_lookup[route['source']]
                     source_name_short = _format_pin_display_name(source_pin, include_index=False).split('\n')[0]
                     commodity = route.get('commodity_name', f"Unknown ({route.get('commodity_id')})")
                     qty = route.get('quantity', 0)
                     route_text = f"  • From {source_name_short}: {qty:,} x {commodity}"
                     tk.Label(panel, text=route_text, bg=bg_color, justify=tk.LEFT,
                              anchor='w', wraplength=230).pack(fill='x', padx=15) # Indent route details
                 except KeyError:
                     tk.Label(panel, text=f"  • From Pin #{route['source']} (Error): Data missing", bg=bg_color, fg="red", justify=tk.LEFT, anchor='w').pack(fill='x', padx=15)


        if outgoing_routes:
            tk.Label(panel, text="Outgoing Routes:", font=("Segoe UI", 10, "bold"),
                     bg=bg_color, anchor='w').pack(fill='x', padx=10, pady=(5, 2))
            for route in outgoing_routes:
                 try:
                     target_pin = pins_lookup[route['target']]
                     target_name_short = _format_pin_display_name(target_pin, include_index=False).split('\n')[0]
                     commodity = route.get('commodity_name', f"Unknown ({route.get('commodity_id')})")
                     qty = route.get('quantity', 0)
                     route_text = f"  • To {target_name_short}: {qty:,} x {commodity}"
                     tk.Label(panel, text=route_text, bg=bg_color, justify=tk.LEFT,
                              anchor='w', wraplength=230).pack(fill='x', padx=15) # Indent route details
                 except KeyError:
                     tk.Label(panel, text=f"  • To Pin #{route['target']} (Error): Data missing", bg=bg_color, fg="red", justify=tk.LEFT, anchor='w').pack(fill='x', padx=15)

        if not incoming_routes and not outgoing_routes:
             tk.Label(panel, text="No routes connected.", bg=bg_color, justify=tk.LEFT,
                      anchor='w', font=("Segoe UI", 9, "italic")).pack(fill='x', padx=10, pady=(5,0))


    def _update_info_panel_for_route(panel, route_data_list, pins_lookup):
        """Updates the info panel with details of the selected route group."""
        title_widget = _clear_info_panel_content(panel)
        if not title_widget: return
        if not route_data_list: # Should not happen if called correctly
            _reset_info_panel(panel)
            return

        bg_color = panel.cget('bg')

        # Use the first route to get pin indices (they are the same for the group)
        first_route = route_data_list[0]
        pin1_idx = first_route['source']
        pin2_idx = first_route['target']

        try:
            pin1 = pins_lookup[pin1_idx]
            pin2 = pins_lookup[pin2_idx]
            pin1_name = _format_pin_display_name(pin1, include_index=True) # Full name for panel
            pin2_name = _format_pin_display_name(pin2, include_index=True) # Full name for panel

            tk.Label(panel, text=f"Selected Route Group ({len(route_data_list)} routes)", font=("Segoe UI", 11, "bold"),
                     bg=bg_color).pack(pady=(0, 5), anchor='nw', padx=10)

            tk.Label(panel, text=f"Between Pin:", bg=bg_color, justify=tk.LEFT,
                     anchor='w').pack(fill='x', padx=10)
            tk.Label(panel, text=pin1_name, bg=bg_color, justify=tk.LEFT,
                     anchor='w', wraplength=230, padx=20).pack(fill='x', padx=10) # Indent pin details

            tk.Label(panel, text=f"And Pin:", bg=bg_color, justify=tk.LEFT,
                     anchor='w').pack(fill='x', padx=10, pady=(5,0))
            tk.Label(panel, text=pin2_name, bg=bg_color, justify=tk.LEFT,
                     anchor='w', wraplength=230, padx=20).pack(fill='x', padx=10) # Indent pin details

            # Aggregate commodities and quantities
            commodities_summary = defaultdict(lambda: {'qty': 0, 'directions': set()})
            for route in route_data_list:
                comm_id = route.get('commodity_id')
                comm_name = route.get('commodity_name', f"Unknown ({comm_id})")
                qty = route.get('quantity', 0)
                direction = f"{route['source']} -> {route['target']}" # Indicate direction based on original indices
                commodities_summary[comm_name]['qty'] += qty
                commodities_summary[comm_name]['directions'].add(direction)

            tk.Label(panel, text="Transported Commodities:", font=("Segoe UI", 10, "bold"),
                     bg=bg_color, anchor='w').pack(fill='x', padx=10, pady=(10, 2))

            if commodities_summary:
                for comm_name, data in commodities_summary.items():
                    # Show directionality if routes go both ways for the same commodity
                    # Note: Uses original pin indices for direction display
                    direction_str = f" ({', '.join(sorted(list(data['directions'])))})" if len(data['directions']) > 1 else ""
                    summary_text = f"  • {comm_name}: {data['qty']:,}{direction_str}"
                    tk.Label(panel, text=summary_text, bg=bg_color, justify=tk.LEFT,
                             anchor='w', wraplength=230).pack(fill='x', padx=15)
            else:
                tk.Label(panel, text="  (No commodity data)", bg=bg_color, justify=tk.LEFT,
                         anchor='w', font=("Segoe UI", 9, "italic")).pack(fill='x', padx=15)


        except KeyError as e:
            logging.error(f"Info panel (route group) update failed: Missing key {e}. Route list: {route_data_list}")
            tk.Label(panel, text="Error displaying route details.\nMissing pin data.", fg="red",
                     bg=bg_color, justify=tk.LEFT).pack(pady=5, padx=10, anchor="nw")
        except Exception as e:
            logging.exception("Unexpected error updating info panel for route group")
            tk.Label(panel, text="Error displaying route details.", fg="red",
                     bg=bg_color).pack(pady=5, padx=10, anchor="nw")

    # Initialize info panel
    if info_panel:
        _reset_info_panel(info_panel)

    canvas.draw() # Initial draw

    return canvas, label_artists # Return canvas and labels for external control
