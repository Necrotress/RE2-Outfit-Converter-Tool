"""Settings dialog for the CustomTkinter GUI."""

from __future__ import annotations

import re
import sys
import tkinter as tk
import tkinter.filedialog  # noqa: F401
import webbrowser
from typing import Callable

import customtkinter as ctk

from .outfits import (
    CONVERTIBLE_CLAIRE_OUTFITS,
    CONVERTIBLE_LEON_OUTFITS,
    default_outfit_tag_markers,
    default_tag_marker,
)
from .platform.blender_detect import (
    BLENDER_DOWNLOAD,
    RE_MESH_EDITOR_URL,
    find_blender,
    probe_blender,
)
from .settings import outfit_tag_markers

DIM = "#9a9a9a"
_GEO_RE = re.compile(
    r"^(?:(\d+)x(\d+))?(?:([+-]\d+)([+-]\d+))?$")


def work_area_size(win) -> tuple[int, int]:
    """Usable screen size (taskbar excluded on Windows)."""
    try:
        if sys.platform == "win32":
            import ctypes
            from ctypes import wintypes
            rect = wintypes.RECT()
            if ctypes.windll.user32.SystemParametersInfoW(
                    48, 0, ctypes.byref(rect), 0):
                w = max(320, rect.right - rect.left)
                h = max(360, rect.bottom - rect.top)
                return w, h
    except Exception:
        pass
    try:
        return (
            max(320, int(win.winfo_screenwidth())),
            max(360, int(win.winfo_screenheight()) - 80),
        )
    except tk.TclError:
        return 1280, 720


def clamp_dialog_geometry(
    geo: str,
    *,
    max_w: int,
    max_h: int,
    min_w: int = 280,
    min_h: int = 200,
) -> str:
    """Keep a Tk ``WxH+x+y`` string on-screen by clamping size."""
    text = (geo or "").strip()
    if not text:
        return ""
    match = _GEO_RE.match(text)
    if match is None:
        return text
    w, h, x, y = match.group(1), match.group(2), match.group(3), match.group(4)
    out = ""
    if w and h:
        cw = max(min_w, min(int(w), max_w))
        ch = max(min_h, min(int(h), max_h))
        out = f"{cw}x{ch}"
    if x and y:
        out += f"{x}{y}"
    return out


def dialog_position(geo: str) -> str:
    """Return ``+x+y`` from a Tk geometry string, or empty."""
    text = (geo or "").strip()
    if not text:
        return ""
    match = _GEO_RE.match(text)
    if match is None:
        return ""
    x, y = match.group(3), match.group(4)
    if x and y:
        return f"{x}{y}"
    return ""


def open_settings_dialog(
    app,
    *,
    on_persist: Callable[[], None],
    on_closed: Callable[[], None],
) -> ctk.CTkToplevel:
    """Build and show the Settings toplevel. ``app`` is the main App instance."""
    win = ctk.CTkToplevel(app)
    win.withdraw()
    win.title("Settings")
    win.transient(app)

    body = ctk.CTkFrame(win, corner_radius=12)
    body.pack(fill="both", expand=True, padx=12, pady=12)

    ctk.CTkLabel(
        body, text="Settings",
        font=ctk.CTkFont(size=15, weight="bold"),
        anchor="w",
    ).pack(anchor="w", padx=10, pady=(6, 6))

    general = ctk.CTkFrame(body, fg_color="transparent")
    general.pack(fill="x", padx=0, pady=(0, 4))

    scroll = ctk.CTkScrollableFrame(
        body, fg_color="transparent", corner_radius=0)
    scroll.pack(fill="both", expand=True)

    def _option(parent, text, var, hint):
        ctk.CTkCheckBox(parent, text=text, variable=var).pack(
            anchor="w", padx=10, pady=(2, 0))
        ctk.CTkLabel(
            parent, text=hint, text_color=DIM,
            font=ctk.CTkFont(size=11), anchor="w",
            wraplength=380, justify="left",
        ).pack(anchor="w", padx=32, pady=(0, 4))

    write_log_var = tk.BooleanVar(
        value=bool(app.settings.get("write_convert_log", True)))
    _option(
        general, "Write convert log", write_log_var,
        "Embeds convert.log in the output (single mod: next to modinfo; "
        "multi-mod zip: one root log covering each subfolder).")

    skip_done_var = tk.BooleanVar(
        value=bool(app.settings.get("skip_completion_dialog", False)))
    _option(
        general, "Skip completion dialog", skip_done_var,
        'Show "Conversion completed" under the bar instead of a popup.')

    menu_label_var = tk.StringVar(
        value=(
            "tag" if app.settings.get("menu_outfit_labels") == "tag"
            else "name"))
    ctk.CTkLabel(
        general, text="Convert menus", anchor="w",
        font=ctk.CTkFont(size=13),
    ).pack(anchor="w", padx=10, pady=(8, 0))
    ctk.CTkRadioButton(
        general, text="Outfit names", variable=menu_label_var, value="name",
    ).pack(anchor="w", padx=32, pady=(2, 0))
    ctk.CTkRadioButton(
        general, text="Outfit tags", variable=menu_label_var, value="tag",
    ).pack(anchor="w", padx=32, pady=(0, 4))

    tag_zip_var = tk.BooleanVar(
        value=bool(app.settings.get("tag_zip_name", True)))
    tag_desc_var = tk.BooleanVar(
        value=bool(app.settings.get("tag_modinfo_description", True)))
    tag_build_zip_var = tk.BooleanVar(
        value=bool(app.settings.get("tag_build_zip_name", True)))
    tag_build_desc_var = tk.BooleanVar(
        value=bool(app.settings.get("tag_build_modinfo_description", True)))

    current_tags = outfit_tag_markers(app.settings)
    tag_vars: dict[str, tk.StringVar] = {}
    section_open: dict[str, tk.BooleanVar] = {}

    def _stable_window_size() -> tuple[int, int]:
        area_w, area_h = work_area_size(win)
        max_w = max(440, area_w - 24)
        max_h = max(360, area_h - 24)
        width = min(540, max_w)
        height = min(640, max(520, int(area_h * 0.62)))
        height = min(height, max_h)
        return width, height

    def _add_collapsible(
        parent,
        title: str,
        *,
        key: str,
        expanded: bool,
        padx: int = 10,
    ) -> ctk.CTkFrame:
        section = ctk.CTkFrame(parent, fg_color="transparent")
        section.pack(fill="x", padx=padx, pady=(2, 2))
        open_var = tk.BooleanVar(value=expanded)
        section_open[key] = open_var
        header = ctk.CTkFrame(section, fg_color="transparent")
        header.pack(fill="x")
        toggle_btn = ctk.CTkButton(
            header, width=28, height=24,
            fg_color="#3a3a3a", hover_color="#4a4a4a",
            text="▾" if expanded else "▸",
        )
        toggle_btn.pack(side="left", padx=(0, 6))
        ctk.CTkLabel(
            header, text=title,
            font=ctk.CTkFont(size=12, weight="bold"),
            anchor="w",
        ).pack(side="left")

        inner = ctk.CTkFrame(section, fg_color="transparent")
        if expanded:
            inner.pack(fill="x", padx=(34, 0), pady=(2, 0))

        def _toggle():
            if open_var.get():
                inner.pack_forget()
                open_var.set(False)
                toggle_btn.configure(text="▸")
            else:
                inner.pack(fill="x", padx=(34, 0), pady=(2, 0))
                open_var.set(True)
                toggle_btn.configure(text="▾")

        toggle_btn.configure(command=_toggle)
        header.bind("<Button-1>", lambda _e: _toggle())
        return inner

    tags_inner = _add_collapsible(
        scroll, "Outfit tags",
        key="outfit_tags",
        expanded=bool(app.settings.get("settings_outfit_tags_open", True)),
    )
    _option(
        tags_inner, "Outfit tag to zip name", tag_zip_var,
        "Example: MyMod [Noir].zip")
    _option(
        tags_inner, "Outfit tag to description", tag_desc_var,
        "Example: Description=... [Noir]")
    _option(
        tags_inner, "[RTX] / [Non-RTX] to zip name", tag_build_zip_var,
        "Example: MyMod [Noir] [RTX].zip")
    _option(
        tags_inner, "[RTX] / [Non-RTX] to description", tag_build_desc_var,
        "Example: Description=... [Non-RTX]")
    ctk.CTkLabel(
        tags_inner,
        text="Custom tag text (include brackets if wanted, e.g. [Elza], {X}):",
        text_color=DIM,
        font=ctk.CTkFont(size=11),
        anchor="w",
        wraplength=360,
        justify="left",
    ).pack(anchor="w", padx=10, pady=(4, 4))

    def _add_tag_rows(parent, outfits: list) -> None:
        for outfit in outfits:
            row = ctk.CTkFrame(parent, fg_color="transparent")
            row.pack(fill="x", pady=1)
            ctk.CTkLabel(
                row, text=outfit.name, width=160, anchor="w",
            ).pack(side="left", padx=(2, 6))
            var = tk.StringVar(value=current_tags.get(
                outfit.key, default_tag_marker(outfit)))
            tag_vars[outfit.key] = var
            ctk.CTkEntry(row, textvariable=var, width=180, height=28).pack(
                side="left", fill="x", expand=True)

    claire_inner = _add_collapsible(
        tags_inner, "Claire",
        key="claire",
        expanded=bool(app.settings.get("settings_claire_tags_open", True)),
        padx=0,
    )
    _add_tag_rows(claire_inner, CONVERTIBLE_CLAIRE_OUTFITS)

    leon_inner = _add_collapsible(
        tags_inner, "Leon",
        key="leon",
        expanded=bool(app.settings.get("settings_leon_tags_open", False)),
        padx=0,
    )
    _add_tag_rows(leon_inner, CONVERTIBLE_LEON_OUTFITS)

    use_blender_var = tk.BooleanVar(
        value=bool(app.settings.get("use_blender", True)))
    blender_var = tk.StringVar(
        value=str(app.settings.get("blender_path") or ""))
    ctk.CTkLabel(
        scroll, text="Blender (mesh / material)",
        font=ctk.CTkFont(weight="bold"), anchor="w",
    ).pack(anchor="w", padx=10, pady=(12, 2))
    ctk.CTkCheckBox(
        scroll,
        text="Use Blender for mesh and material conversion",
        variable=use_blender_var,
    ).pack(anchor="w", padx=10, pady=(2, 0))
    ctk.CTkLabel(
        scroll, text="blender.exe", anchor="w",
    ).pack(anchor="w", padx=10, pady=(6, 0))
    path_row = ctk.CTkFrame(scroll, fg_color="transparent")
    path_row.pack(fill="x", padx=10, pady=(2, 0))
    ctk.CTkEntry(path_row, textvariable=blender_var).pack(
        side="left", fill="x", expand=True)

    blender_status = ctk.CTkLabel(
        scroll, text="", anchor="w", justify="left", wraplength=470,
        font=ctk.CTkFont(size=11),
    )

    def browse_blender() -> None:
        path = tk.filedialog.askopenfilename(
            title="Select blender.exe",
            filetypes=[("Blender", "blender.exe"), ("All", "*.*")],
        )
        if path:
            blender_var.set(path)

    def auto_detect() -> None:
        found = find_blender(blender_var.get() or None) or find_blender()
        if found:
            blender_var.set(str(found))
            blender_status.configure(
                text=f"Found: {found}", text_color="#2ecc71")
        else:
            blender_status.configure(
                text="Blender 4.3 not found. Install Blender 4.3 first.",
                text_color="#f1c40f",
            )

    def test_blender() -> None:
        found = find_blender(blender_var.get().strip() or None)
        if found is None:
            blender_status.configure(
                text="Set a valid blender.exe path first.",
                text_color="#e74c3c")
            return
        blender_status.configure(text="Testing Blender…", text_color=DIM)
        win.update_idletasks()
        result = probe_blender(found)
        blender_var.set(str(found))
        detail = result.message
        if result.blender_version:
            detail = f"Blender {result.blender_version}: {detail}"
        blender_status.configure(
            text=detail[:180],
            text_color="#2ecc71" if result.ok else "#e74c3c",
        )

    ctk.CTkButton(
        path_row, text="…", width=36, command=browse_blender,
    ).pack(side="left", padx=(6, 0))
    actions = ctk.CTkFrame(scroll, fg_color="transparent")
    actions.pack(fill="x", padx=10, pady=(6, 0))
    ctk.CTkButton(
        actions, text="Auto-detect", width=104, command=auto_detect,
    ).pack(side="left", padx=(0, 6))
    ctk.CTkButton(
        actions, text="Test", width=72, command=test_blender,
    ).pack(side="left", padx=(0, 6))
    ctk.CTkButton(
        actions, text="Blender download", width=148,
        command=lambda: webbrowser.open(BLENDER_DOWNLOAD),
    ).pack(side="left", padx=(0, 6))
    ctk.CTkButton(
        actions, text="RE Mesh Editor", width=128,
        command=lambda: webbrowser.open(RE_MESH_EDITOR_URL),
    ).pack(side="left")
    blender_status.pack(anchor="w", padx=10, pady=(4, 0))
    ctk.CTkLabel(
        scroll,
        text=(
            "Mesh and material conversion needs Blender 4.3 and RE Mesh "
            "Editor. Texture conversion does not. If a convert needs "
            "Blender and it is missing, or Test fails, the convert stops."
        ),
        text_color=DIM, font=ctk.CTkFont(size=11), anchor="w",
        wraplength=470, justify="left",
    ).pack(anchor="w", padx=10, pady=(2, 8))

    def _reset_tag_defaults():
        defaults = default_outfit_tag_markers()
        for key, var in tag_vars.items():
            var.set(defaults[key])

    def _capture_position() -> str:
        win.update_idletasks()
        return (
            f"{win.winfo_width()}x{win.winfo_height()}"
            f"+{win.winfo_x()}+{win.winfo_y()}"
        )

    def _persist_settings_dialog():
        app.settings["write_convert_log"] = bool(write_log_var.get())
        app.settings.pop("skip_convert_confirm", None)
        app.settings.pop("skip_same_outfit_popup", None)
        app.settings["skip_completion_dialog"] = bool(skip_done_var.get())
        app.settings["menu_outfit_labels"] = (
            "tag" if menu_label_var.get() == "tag" else "name")
        app.settings.pop("menu_show_outfit_name", None)
        app.settings.pop("menu_show_outfit_tag", None)
        app.settings["tag_zip_name"] = bool(tag_zip_var.get())
        app.settings["tag_modinfo_description"] = bool(tag_desc_var.get())
        app.settings["tag_modinfo_name"] = False
        app.settings["tag_build_zip_name"] = bool(tag_build_zip_var.get())
        app.settings["tag_build_modinfo_description"] = bool(
            tag_build_desc_var.get())
        app.settings["use_blender"] = bool(use_blender_var.get())
        app.settings["blender_path"] = blender_var.get().strip()
        app.settings["tag_output"] = bool(tag_zip_var.get())
        app.settings["outfit_tags"] = {
            key: var.get().strip() for key, var in tag_vars.items()
        }
        app.settings["settings_outfit_tags_open"] = bool(
            section_open["outfit_tags"].get())
        app.settings["settings_claire_tags_open"] = bool(
            section_open["claire"].get())
        app.settings["settings_leon_tags_open"] = bool(
            section_open["leon"].get())
        try:
            if win.winfo_ismapped():
                app.settings["settings_geometry"] = _capture_position()
        except tk.TclError:
            pass
        on_persist()

    def _close_settings(_event=None):
        _persist_settings_dialog()
        try:
            win.grab_release()
        except tk.TclError:
            pass
        try:
            win.withdraw()
        except tk.TclError:
            pass
        on_closed()
        win.destroy()
        return "break"

    btn_row = ctk.CTkFrame(body, fg_color="transparent")
    ctk.CTkButton(
        btn_row, text="Reset tags", width=100, height=30,
        command=_reset_tag_defaults,
        fg_color="#3a3a3a", hover_color="#4a4a4a",
    ).pack(side="left")
    ctk.CTkButton(
        btn_row, text="Close", width=90, height=30, command=_close_settings,
    ).pack(side="right")
    scroll.pack_forget()
    btn_row.pack(side="bottom", fill="x", padx=10, pady=(6, 6))
    scroll.pack(fill="both", expand=True)
    win.protocol("WM_DELETE_WINDOW", _close_settings)
    win.bind("<Escape>", _close_settings)
    scroll.bind("<Escape>", _close_settings)

    win.resizable(False, True)
    req_w, req_h = _stable_window_size()
    saved_geo = str(app.settings.get("settings_geometry") or "")
    saved_match = _GEO_RE.match(saved_geo.strip())
    if saved_match and saved_match.group(2):
        _, area_h = work_area_size(win)
        req_h = max(360, min(int(saved_match.group(2)), max(360, area_h - 24)))
    win.minsize(req_w, 360)
    win.maxsize(req_w, work_area_size(win)[1])
    xy = dialog_position(saved_geo)
    if not xy:
        try:
            app.update_idletasks()
            x = app.winfo_rootx() + max(
                0, (app.winfo_width() - req_w) // 2)
            y = app.winfo_rooty() + max(
                0, (app.winfo_height() - req_h) // 2)
            xy = f"+{x}+{y}"
        except tk.TclError:
            xy = ""
    win.geometry(f"{req_w}x{req_h}{xy}")
    win.deiconify()
    win.lift()
    win.focus()

    win._re2oc_persist = _persist_settings_dialog  # type: ignore[attr-defined]
    return win
