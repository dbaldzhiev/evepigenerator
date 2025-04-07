import tkinter as tk
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyArrowPatch
import matplotlib.path as mpath
import logging
import math

# --- Define Pin Styles ---
CATEGORY_STYLES = {
    "Extractor": {"color": "#cc2e70", "marker": "X", "size": 12},  # Dark Pink X
    "Launchpad": {"color": "#00ff4c", "marker": "^", "size": 12},    # Bright Green Triangle Up
    "Basic Industrial Facility": {"color": "#f1c40f", "marker": "s", "size": 12},  # Yellow Square
    "Advanced Industrial Facility": {"color": "#e67e22", "marker": "p", "size": 12},  # Orange Pentagon
    "High-Tech Industrial Facility": {"color": "#e74c3c", "marker": "h", "size": 12},  # Red Hexagon
    "Storage Facility": {"color": "#25a6af", "marker": "o", "size": 12},  # Cyan Circle
    "Command Center": {"color": "#9b59b6", "marker": "*", "size": 12},  # Purple Star
    "Unknown": {"color": "#34495e", "marker": "o", "size": 12}           # Dark Gray
}

# --- Updated Colors ---
ROUTE_COLOR = "#3498db"            # Blue for routes
ROUTE_HIGHLIGHT_COLOR = "#2980b9"    # Darker blue for selected route
LINK_COLOR = "#e74c3c"             # Red for links
# --- End Updated Colors ---

# Adjusted for thinner lines and smaller arrowheads
ARROW_STYLE = "Simple,tail_width=0.3,head_width=1.5,head_length=3" # Thinner tail, smaller head
ROUTE_LINE_WIDTH = 0.125 # Thinner base line width
ROUTE_MUTATION_SCALE = 2 # Smaller arrowhead scale

def _get_pin_style(pin_category):
    """Gets the marker style dictionary for a given pin category."""
    # Use startswith for more robustness against planet names in category string
    if pin_category.startswith("Basic Industrial Facility"):
        return CATEGORY_STYLES["Basic Industrial Facility"]
    if pin_category.startswith("Advanced Industrial Facility"):
        return CATEGORY_STYLES["Advanced Industrial Facility"]
    if pin_category.startswith("High-Tech Industrial Facility"):
        return CATEGORY_STYLES["High-Tech Industrial Facility"]
    if pin_category.startswith("Storage Facility"):
        return CATEGORY_STYLES["Storage Facility"]
    if pin_category.startswith("Launchpad"):
        return CATEGORY_STYLES["Launchpad"]
    if pin_category.startswith("Extractor"):
        return CATEGORY_STYLES["Extractor"]
    if pin_category.startswith("Command Center"):
        return CATEGORY_STYLES["Command Center"]
    return CATEGORY_STYLES.get(pin_category, CATEGORY_STYLES["Unknown"]) # Fallback

def render_matplotlib_plot(parsed, config, container_frame, info_panel=None, show_routes=True):
    """Renders the PI layout plot.

    Args:
        parsed (dict): Parsed data from parse_pi_json.
        config (Config): Configuration object.
        container_frame (tk.Frame): The Tkinter frame to embed the plot in.
        info_panel (tk.Frame, optional): The frame for displaying route info. Defaults to None.
        show_routes (bool, optional): Whether to display route lines. Defaults to True.
    """
    for widget in container_frame.winfo_children():
        widget.destroy()

    if not parsed or not parsed.get("pins"):
        tk.Label(container_frame, text="No data to display.", bg=container_frame.cget('bg')).pack(expand=True)
        if info_panel:
            _reset_info_panel(info_panel) # Reset info panel even if no plot
        return

    fig, ax = plt.subplots(figsize=(10, 7), facecolor=container_frame.cget('bg'))
    ax.set_facecolor('#ffffff')  # White background for plot area

    pins_by_index = {pin['index']: pin for pin in parsed["pins"]}

    # --- Plot Pins ---
    for pin in parsed["pins"]:
        x, y = pin["lon"], pin["lat"]
        category = pin.get("category", "Unknown") # Use resolved category for styling
        style = _get_pin_style(category) # Style based on category

        ax.plot(x, y, marker=style["marker"], color=style["color"],
                markersize=style["size"], linestyle='None', zorder=5)

        # Build label text
        label_lines = []
        # --- MODIFICATION START: Display ID if pin type is unknown ---
        if category == "Unknown":
            # If category is Unknown, show the ID
            label_lines.append(f"Unknown Type ({pin.get('type_id', 'N/A')})")
        else:
            # Otherwise, use the resolved type_name (Category (Planet))
            pin_display_name = pin.get("type_name", "Unknown") # Already formatted by parser
            label_lines.append(f"{pin_display_name}")
        # --- MODIFICATION END ---

        # Check for schematic name directly from parsed pin data
        schematic_name = pin.get("schematic_name")
        schematic_id = pin.get("schematic_id")

        # --- MODIFICATION START: Display ID if schematic name is unknown ---
        if schematic_name:
            # Use the resolved name if available
            label_lines.append(f"({schematic_name})")
        elif schematic_id is not None:
            # If name wasn't resolved but ID exists, show unknown ID
            label_lines.append(f"(Unknown Sch: {schematic_id})")
        # --- MODIFICATION END ---

        label_text = "\n".join(label_lines)
        ax.text(x, y+0.0015, label_text, ha='center', va='top', fontsize=7,
                bbox=dict(facecolor='white', edgecolor='none', alpha=0.85, pad=0.3), zorder=6)

    # --- Plot Links ---
    for link in parsed.get("links", []):
        try:
            src = pins_by_index[link["source"]]
            dst = pins_by_index[link["target"]]
            ax.plot([src["lon"], dst["lon"]], [src["lat"], dst["lat"]],
                    color=LINK_COLOR, linewidth=max(0.5, link.get("level", 1) * 0.5),
                    linestyle='--', zorder=1)
        except KeyError as e:
            logging.warning(f"Skipping link due to missing pin index: {e}. Link data: {link}")

    # --- Plot Routes with Curved Arrows ---
    route_patches = []
    routes_data = parsed.get('routes', [])
    for i, route in enumerate(routes_data):
        try:
            src_idx = route["source"]
            dst_idx = route["target"]
            src = pins_by_index[src_idx]
            dst = pins_by_index[dst_idx]
            src_coords = (src["lon"], src["lat"])
            dst_coords = (dst["lon"], dst["lat"])

            mid_x = (src_coords[0] + dst_coords[0]) / 2
            mid_y = (src_coords[1] + dst_coords[1]) / 2
            dx = dst_coords[0] - src_coords[0]
            dy = dst_coords[1] - src_coords[1]
            dist = math.sqrt(dx**2 + dy**2)
            if dist == 0:
                logging.warning(f"Skipping route #{i} between pin {src_idx} and {dst_idx} due to zero distance.")
                continue

            norm_x = -dy / dist
            norm_y = dx / dist

            # Adjust curvature based on distance and route index to avoid overlaps
            base_offset_scale = dist * 0.1 # Base curvature related to distance
            # Add variation based on route index to separate parallel routes
            offset_variation = (i % 7) * 0.03 # Cycle through 7 offsets
            offset_direction = 1 if (i // 7) % 2 == 0 else -1 # Alternate direction
            offset_scale = base_offset_scale * (1 + offset_variation) * offset_direction

            ctrl_x = mid_x + norm_x * offset_scale
            ctrl_y = mid_y + norm_y * offset_scale

            Path = mpath.Path
            path_data = [
                (Path.MOVETO, src_coords),
                (Path.CURVE3, (ctrl_x, ctrl_y)), # Single control point for quadratic Bezier
                (Path.LINETO, dst_coords) # End with line to ensure arrow points correctly
            ]
            # Use CURVE4 for smoother curves if needed, requires two control points
            # path_data = [
            #     (Path.MOVETO, src_coords),
            #     (Path.CURVE4, (src_coords[0] + dx*0.2 + norm_x*offset_scale, src_coords[1] + dy*0.2 + norm_y*offset_scale)),
            #     (Path.CURVE4, (dst_coords[0] - dx*0.2 + norm_x*offset_scale, dst_coords[1] - dy*0.2 + norm_y*offset_scale)),
            #     (Path.CURVE4, dst_coords),
            # ]


            codes, verts = zip(*path_data)
            path = Path(verts, codes)

            patch = FancyArrowPatch(path=path, arrowstyle=ARROW_STYLE, mutation_scale=ROUTE_MUTATION_SCALE,
                                    edgecolor=ROUTE_COLOR, facecolor=ROUTE_COLOR,
                                    lw=ROUTE_LINE_WIDTH, # Use defined thinner line width
                                    alpha=0.7, zorder=2, shrinkA=2, shrinkB=2) # Shrink ends slightly away from pins
            patch.route_data = route # Store the original route dict here
            patch.original_lw = ROUTE_LINE_WIDTH # Store original thinner width
            patch.original_edgecolor = ROUTE_COLOR
            patch.original_facecolor = ROUTE_COLOR
            patch.original_zorder = 2
            patch.set_visible(show_routes) # Set visibility based on parameter
            ax.add_patch(patch)
            route_patches.append(patch)

        except KeyError as e:
            logging.warning(f"Skipping route due to missing pin index: {e}. Route data: {route}")
        except Exception as e:
            logging.error(f"Error drawing route #{i} between pin {src_idx} and {dst_idx}: {e}", exc_info=True)

    ax.set_aspect('equal', adjustable='box')
    ax.invert_yaxis()
    ax.invert_xaxis()
    ax.axis('off')

    # --- Add Title/Subtitle ---
    title_parts = []
    if parsed.get("cmdctr"):
        title_parts.append(f"CC Lvl: {parsed['cmdctr']}")
    if parsed.get("diameter"):
        title_parts.append(f"Diameter: {parsed['diameter']}")
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

    active_patch = None

    def on_click(event):
        nonlocal active_patch
        if event.inaxes != ax or toolbar.mode:
            if active_patch and not toolbar.mode:
                # Restore original appearance
                active_patch.set_linewidth(active_patch.original_lw)
                active_patch.set_edgecolor(active_patch.original_edgecolor)
                active_patch.set_facecolor(active_patch.original_facecolor)
                active_patch.set_zorder(active_patch.original_zorder)
                active_patch = None
                if info_panel:
                    _reset_info_panel(info_panel)
                canvas.draw_idle()
            return

        pick_radius = 5
        new_active_patch = None
        # Iterate through visible route patches only
        for patch in reversed(route_patches):
            if not patch.get_visible(): # Skip invisible patches
                continue
            contains, _ = patch.contains(event, radius=pick_radius)
            if contains:
                new_active_patch = patch
                break

        if active_patch and active_patch != new_active_patch:
            # Restore previously active patch
            active_patch.set_linewidth(active_patch.original_lw)
            active_patch.set_edgecolor(active_patch.original_edgecolor)
            active_patch.set_facecolor(active_patch.original_facecolor)
            active_patch.set_zorder(active_patch.original_zorder)
            active_patch = None

        if new_active_patch and new_active_patch != active_patch:
            active_patch = new_active_patch
            # Highlight the new active patch
            active_patch.set_linewidth(active_patch.original_lw * 2.5) # Highlight relative to new thin width
            active_patch.set_edgecolor(ROUTE_HIGHLIGHT_COLOR)
            active_patch.set_facecolor(ROUTE_HIGHLIGHT_COLOR)
            active_patch.set_zorder(10)
            if info_panel:
                # Pass the route data stored in the patch
                _update_info_panel_content(info_panel, active_patch.route_data, pins_by_index, config)
        elif not new_active_patch:
            if active_patch:
                active_patch.set_linewidth(active_patch.original_lw)
                active_patch.set_edgecolor(active_patch.original_edgecolor)
                active_patch.set_facecolor(active_patch.original_facecolor)
                active_patch.set_zorder(active_patch.original_zorder)
                active_patch = None
            if info_panel:
                _reset_info_panel(info_panel)

        canvas.draw_idle()

    def _clear_info_panel_content(info_panel):
        """Clears all widgets except the title widget from the info panel."""
        title_widget = None
        for widget in info_panel.winfo_children():
            is_title = isinstance(widget, tk.Label) and widget.cget('font').endswith("bold") and widget.cget('text') == "Info Panel"
            if is_title:
                title_widget = widget
                break
        widgets_to_destroy = [w for w in info_panel.winfo_children() if w != title_widget]
        for widget in widgets_to_destroy:
            widget.destroy()
        return title_widget

    def _reset_info_panel(info_panel):
        """Resets the info panel to its default state with updated instructions."""
        title_widget = _clear_info_panel_content(info_panel)
        if title_widget:
            default_info = tk.Label(info_panel, text="Click on a route (curved blue arrow)\nto see details here.",
                                    bg=info_panel.cget('bg'), justify=tk.LEFT, wraplength=230)
            default_info.pack(pady=5, padx=10, anchor="nw")

    def _update_info_panel_content(info_panel, route_data, pins_lookup, config):
        """Updates the info panel with details of the selected route."""
        title_widget = _clear_info_panel_content(info_panel)
        if not title_widget:
            logging.error("Info panel title widget not found during update.")
            return

        try:
            source_pin = pins_lookup[route_data['source']]
            target_pin = pins_lookup[route_data['target']]
            source_disp_idx = source_pin.get('original_index', route_data['source'] + 1)
            target_disp_idx = target_pin.get('original_index', route_data['target'] + 1)

            # --- MODIFICATION START: Resolve Pin Type Names for Info Panel, showing ID if unknown ---
            if source_pin.get('category') == 'Unknown':
                source_type_name_display = f"Unknown Type ({source_pin.get('type_id', 'N/A')})"
            else:
                # Use the pre-formatted name from parser which includes category and planet
                source_type_name_display = source_pin.get('type_name', 'Unknown Type')

            if target_pin.get('category') == 'Unknown':
                target_type_name_display = f"Unknown Type ({target_pin.get('type_id', 'N/A')})"
            else:
                target_type_name_display = target_pin.get('type_name', 'Unknown Type')
            # --- MODIFICATION END ---

            # Build source pin display name
            source_name = f"{source_type_name_display} (#{source_disp_idx})"
            source_schematic_name = source_pin.get("schematic_name")
            source_schematic_id = source_pin.get("schematic_id")
            # --- MODIFICATION START: Display Schematic ID if name unknown ---
            if source_schematic_name:
                source_name += f"\n  ({source_schematic_name})"
            elif source_schematic_id:
                 source_name += f"\n  (Unknown Sch: {source_schematic_id})"
            # --- MODIFICATION END ---

            # Build target pin display name
            target_name = f"{target_type_name_display} (#{target_disp_idx})"
            target_schematic_name = target_pin.get("schematic_name")
            target_schematic_id = target_pin.get("schematic_id")
            # --- MODIFICATION START: Display Schematic ID if name unknown ---
            if target_schematic_name:
                target_name += f"\n  ({target_schematic_name})"
            elif target_schematic_id:
                 target_name += f"\n  (Unknown Sch: {target_schematic_id})"
            # --- MODIFICATION END ---

            # Use pre-resolved commodity name from route_data (parser adds ID if unknown)
            # --- MODIFICATION: Simplify commodity display ---
            commodity_name = route_data.get('commodity_name', f"Unknown ({route_data.get('commodity_id', 'N/A')})")
            bg_color = info_panel.cget('bg')

            tk.Label(info_panel, text="Route Details", font=("Segoe UI", 11, "bold"),
                     bg=bg_color).pack(pady=(0, 5), anchor='nw', padx=10)
            tk.Label(info_panel, text=f"From: {source_name}", bg=bg_color, justify=tk.LEFT,
                     anchor='w', wraplength=230).pack(fill='x', padx=10)
            tk.Label(info_panel, text=f"To: {target_name}", bg=bg_color, justify=tk.LEFT,
                     anchor='w', wraplength=230).pack(fill='x', padx=10)
            # The commodity_name already includes the ID like "Unknown (1234)" if it was unresolved by the parser
            tk.Label(info_panel, text=f"Commodity: {commodity_name}", bg=bg_color, justify=tk.LEFT,
                     anchor='w', wraplength=230).pack(fill='x', padx=10)
            # No separate ID label needed here anymore
            tk.Label(info_panel, text=f"Quantity: {route_data['quantity']:,}", bg=bg_color,
                     justify=tk.LEFT, anchor='w').pack(fill='x', padx=10)
            # --- MODIFICATION END ---

        except KeyError as e:
            logging.error(f"Info panel update failed: Missing key {e} in route or pin data. Route: {route_data}")
            tk.Label(info_panel, text="Error displaying route details.\nMissing data.", fg="red",
                     bg=bg_color, justify=tk.LEFT).pack(pady=5, padx=10, anchor="nw")
        except Exception as e:
            logging.exception("Unexpected error updating info panel")
            tk.Label(info_panel, text="Error displaying route details.", fg="red",
                     bg=bg_color).pack(pady=5, padx=10, anchor="nw")

    canvas.mpl_connect("button_press_event", on_click)
    canvas.draw()

