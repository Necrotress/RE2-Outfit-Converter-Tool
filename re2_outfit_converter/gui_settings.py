"""Settings dialog for the CustomTkinter GUI."""

from __future__ import annotations

import tkinter as tk
from typing import Callable

import customtkinter as ctk

from .outfits import CONVERTIBLE_OUTFITS, default_outfit_tag_markers, default_tag_marker
from .settings import outfit_tag_markers

DIM = "#9a9a9a"


def open_settings_dialog(
    app,
    *,
    on_persist: Callable[[], None],
    on_closed: Callable[[], None],
) -> ctk.CTkToplevel:
    """Build and show the Settings toplevel. ``app`` is the main App instance."""
    win = ctk.CTkToplevel(app)
    win.title("Settings")
    win.transient(app)
    win.grab_set()

    body = ctk.CTkFrame(win, corner_radius=12)
    body.pack(fill="both", expand=True, padx=12, pady=12)

    ctk.CTkLabel(
        body, text="Settings",
        font=ctk.CTkFont(size=15, weight="bold"),
        anchor="w",
    ).pack(anchor="w", padx=10, pady=(6, 6))

    def _option(parent, text, var, hint):
        ctk.CTkCheckBox(parent, text=text, variable=var).pack(
            anchor="w", padx=10, pady=(2, 0))
        ctk.CTkLabel(
            parent, text=hint, text_color=DIM,
            font=ctk.CTkFont(size=11), anchor="w",
            wraplength=400, justify="left",
        ).pack(anchor="w", padx=32, pady=(0, 4))

    skip_confirm_var = tk.BooleanVar(
        value=bool(app.settings.get("skip_convert_confirm", False)))
    _option(
        body, "Skip conversion confirmation", skip_confirm_var,
        "Start Convert without a confirmation popup.")

    skip_done_var = tk.BooleanVar(
        value=bool(app.settings.get("skip_completion_dialog", False)))
    _option(
        body, "Skip completion dialog", skip_done_var,
        'Show "Conversion completed" under the bar instead of a popup.')

    show_name_var = tk.BooleanVar(
        value=bool(app.settings.get("menu_show_outfit_name", True)))
    _option(
        body, "Show outfit names in convert menus", show_name_var,
        "Example: Classic (Jacket)")

    show_tag_var = tk.BooleanVar(
        value=bool(app.settings.get("menu_show_outfit_tag", True)))
    _option(
        body, "Show outfit tags in convert menus", show_tag_var,
        "Example: [Classic]")

    tag_var = tk.BooleanVar(
        value=bool(app.settings.get("tag_output", True)))
    _option(
        body, "Add outfit tag to zip name and modinfo", tag_var,
        "Example: MyMod [Noir].zip")

    ctk.CTkLabel(
        body, text="Outfit tags",
        font=ctk.CTkFont(size=13, weight="bold"),
        anchor="w",
    ).pack(anchor="w", padx=10, pady=(6, 0))
    ctk.CTkLabel(
        body,
        text="Text appended to names. Include brackets if wanted "
             "(e.g. [Elza], {X}).",
        text_color=DIM,
        font=ctk.CTkFont(size=11),
        anchor="w",
        wraplength=400,
        justify="left",
    ).pack(anchor="w", padx=10, pady=(0, 4))

    tag_list = ctk.CTkFrame(body, fg_color="transparent")
    tag_list.pack(fill="x", padx=10, pady=(0, 4))

    current_tags = outfit_tag_markers(app.settings)
    tag_vars: dict[str, tk.StringVar] = {}
    for outfit in CONVERTIBLE_OUTFITS:
        row = ctk.CTkFrame(tag_list, fg_color="transparent")
        row.pack(fill="x", pady=1)
        ctk.CTkLabel(
            row, text=outfit.name, width=150, anchor="w",
        ).pack(side="left", padx=(2, 6))
        var = tk.StringVar(value=current_tags.get(
            outfit.key, default_tag_marker(outfit)))
        tag_vars[outfit.key] = var
        ctk.CTkEntry(row, textvariable=var, width=180, height=28).pack(
            side="left", fill="x", expand=True)

    def _reset_tag_defaults():
        defaults = default_outfit_tag_markers()
        for key, var in tag_vars.items():
            var.set(defaults[key])

    def _persist_settings_dialog():
        app.settings["skip_convert_confirm"] = bool(skip_confirm_var.get())
        app.settings["skip_completion_dialog"] = bool(skip_done_var.get())
        app.settings["menu_show_outfit_name"] = bool(show_name_var.get())
        app.settings["menu_show_outfit_tag"] = bool(show_tag_var.get())
        app.settings["tag_output"] = bool(tag_var.get())
        app.settings["outfit_tags"] = {
            key: var.get().strip() for key, var in tag_vars.items()
        }
        on_persist()

    def _close_settings():
        _persist_settings_dialog()
        on_closed()
        win.destroy()

    btn_row = ctk.CTkFrame(body, fg_color="transparent")
    btn_row.pack(fill="x", padx=10, pady=(6, 6))
    ctk.CTkButton(
        btn_row, text="Reset tags", width=100, height=30,
        command=_reset_tag_defaults,
        fg_color="#3a3a3a", hover_color="#4a4a4a",
    ).pack(side="left")
    ctk.CTkButton(
        btn_row, text="Close", width=90, height=30, command=_close_settings,
    ).pack(side="right")
    win.protocol("WM_DELETE_WINDOW", _close_settings)

    win.update_idletasks()
    req_w = max(win.winfo_reqwidth(), 440)
    req_h = win.winfo_reqheight()
    win.geometry(f"{req_w}x{req_h}")
    win.minsize(req_w, req_h)
    win.resizable(False, False)

    # Expose persist so App can flush on main-window close.
    win._re2oc_persist = _persist_settings_dialog  # type: ignore[attr-defined]
    return win
