"""Dialog to build a Fluffy Claire / Leon costume name pack."""

from __future__ import annotations

import re
import tkinter as tk
import tkinter.colorchooser
import tkinter.messagebox  # noqa: F401
from pathlib import Path
from typing import Callable

import customtkinter as ctk

from .analyzer import GAME_BUILDS
from .gui_settings import clamp_dialog_geometry, work_area_size
from .msg_name import (
    CLAIRE_NAME_PACK_KEYS,
    LEON_NAME_PACK_KEYS,
    SHARED_COSTUME_NAME_KEYS,
    SHARED_COSTUME_NAME_LABELS,
    SHARED_COSTUME_NAME_VANILLA,
)
from .name_pack import (
    build_costume_name_pack,
    find_existing_name_pack,
    name_pack_game_build,
    read_name_pack_fields,
)

DIM = "#9a9a9a"
CONVERT = "#0f766e"
CONVERT_HOVER = "#0d9488"

_BLURBS = {
    "claire": (
        "Jacket, Tank Top, Classic Jacket, and Classic Tank Top "
        "share one name file in Fluffy with Leon's outfits. Set names "
        "here together so separate mods don't overwrite each other. "
        "Leave a box blank to keep the vanilla name."
    ),
    "leon": (
        "Casual, Police, Classic Police (and Injured variants) share "
        "one name file in Fluffy with Claire's outfits. Set names here "
        "together so separate mods don't overwrite each other. Leave a "
        "box blank to keep the vanilla name."
    ),
}

# (button label, RRGGBB, preview hex). Every chip writes <COLOR RRGGBB>.
NAME_COLOR_SWATCHES: tuple[tuple[str, str, str], ...] = (
    ("Red", "FF4040", "#ff4040"),
    ("Yellow", "FFE14A", "#ffe14a"),
    ("Green", "3DDC6A", "#3ddc6a"),
    ("Blue", "4DA3FF", "#4da3ff"),
    ("Purple", "C084FC", "#c084fc"),
    ("Orange", "FF8A2A", "#ff8a2a"),
    ("Pink", "FF7EB3", "#ff7eb3"),
    ("White", "F2F2F2", "#f2f2f2"),
)
_LEGACY_NAMED_PREVIEW = {
    "RED": "#ff4040",
    "GREEN": "#3ddc6a",
    "BLUE": "#4da3ff",
    "WHITE": "#f2f2f2",
}
_OPEN_COLOR_RE = re.compile(
    r"^<(?:COL\s+[^>]+|COLOR\s+[0-9A-Fa-f]{6})>",
    re.IGNORECASE,
)
_CLOSE_COLOR_RE = re.compile(r"</COLOR>\s*$", re.IGNORECASE)
_PREVIEW_RE = re.compile(
    r"^<(?:COL\s+([^>]+)|COLOR\s+([0-9A-Fa-f]{6}))>",
    re.IGNORECASE,
)


def _plain_name(text: str) -> str:
    rest = _OPEN_COLOR_RE.sub("", text or "", count=1)
    return _CLOSE_COLOR_RE.sub("", rest).strip()


def apply_col_tag(text: str, spec: str) -> str:
    """Wrap a costume name in ``<COLOR RRGGBB>…</COLOR>``."""
    rest = _plain_name(text)
    token = (spec or "").strip().upper().lstrip("#")
    named = _LEGACY_NAMED_PREVIEW.get(token)
    hex_color = (named or f"#{token}").lstrip("#")
    if not re.fullmatch(r"[0-9A-F]{6}", hex_color):
        hex_color = "FFFFFF"
    if rest:
        return f"<COLOR {hex_color}>{rest}</COLOR>"
    return f"<COLOR {hex_color}>"


def preview_hex_for_name(text: str) -> str | None:
    """Hex color for the leading color tag, or None when the name is plain."""
    match = _PREVIEW_RE.match((text or "").lstrip())
    if match is None:
        return None
    named, hex_color = match.group(1), match.group(2)
    if hex_color:
        return f"#{hex_color.lower()}"
    return _LEGACY_NAMED_PREVIEW.get((named or "").strip().upper())


def _swatch_text_color(hex_color: str) -> str:
    value = hex_color.lstrip("#")
    r, g, b = int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)
    luminance = (0.299 * r) + (0.587 * g) + (0.114 * b)
    return "#1a1a1a" if luminance > 160 else "#f5f5f5"


def open_name_pack_dialog(
    app,
    *,
    output_dir: Path,
    on_created: Callable[[Path, bool], None] | None = None,
) -> ctk.CTkToplevel:
    """Show the shared costume-name editor.

    Loads an existing pack from ``output_dir`` when found and overwrites it
    on Save. ``on_created`` receives ``(path, updated)``.
    """
    win = ctk.CTkToplevel(app)
    win.withdraw()
    win.title("Costume name pack")
    win.transient(app)
    win.minsize(440, 420)

    existing = find_existing_name_pack(Path(output_dir))
    loaded: dict[str, str] = {}
    if existing is not None:
        try:
            loaded = read_name_pack_fields(existing)
        except Exception:
            existing = None

    outer = ctk.CTkFrame(win, corner_radius=12)
    outer.pack(fill="both", expand=True, padx=12, pady=12)
    outer.grid_columnconfigure(0, weight=1)
    outer.grid_rowconfigure(0, weight=1)
    body = ctk.CTkScrollableFrame(
        outer, fg_color="transparent", corner_radius=0)
    body.grid(row=0, column=0, sticky="nsew")
    body.grid_columnconfigure(0, weight=1)

    ctk.CTkLabel(
        body, text="Costume names",
        font=ctk.CTkFont(size=15, weight="bold"),
        anchor="w",
    ).grid(row=0, column=0, sticky="ew", padx=10, pady=(6, 4))

    detected_build = (
        name_pack_game_build(existing) if existing is not None else None)
    menu_build = "Classic"
    main_game = getattr(app, "game_var", None)
    if main_game is not None:
        try:
            choice = main_game.get()
        except tk.TclError:
            choice = ""
        if choice in GAME_BUILDS:
            menu_build = choice
    build_var = tk.StringVar(value=detected_build or menu_build)

    build_row = ctk.CTkFrame(body, fg_color="transparent")
    build_row.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 6))
    ctk.CTkLabel(build_row, text="Game build", anchor="w").pack(side="left")
    ctk.CTkOptionMenu(
        build_row, variable=build_var, values=list(GAME_BUILDS), width=150,
    ).pack(side="left", padx=(8, 0))
    ctk.CTkLabel(
        body,
        text=(
            "Classic writes natives/x64 .msg.14. "
            "Ray tracing writes natives/stm .msg.50397457, the file the game loads."
        ),
        text_color=DIM,
        font=ctk.CTkFont(size=11),
        anchor="w",
        justify="left",
        wraplength=400,
    ).grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 6))

    char_row = ctk.CTkFrame(body, fg_color="transparent")
    char_row.grid(row=3, column=0, sticky="w", padx=10, pady=(0, 8))

    char_var = tk.StringVar(value="claire")
    title_label = ctk.CTkLabel(
        body, text="Claire",
        font=ctk.CTkFont(size=13, weight="bold"),
        anchor="w",
    )
    title_label.grid(row=4, column=0, sticky="ew", padx=10, pady=(0, 2))

    blurb_label = ctk.CTkLabel(
        body,
        text=_BLURBS["claire"],
        text_color=DIM,
        font=ctk.CTkFont(size=12),
        anchor="w",
        justify="left",
        wraplength=400,
    )
    blurb_label.grid(row=5, column=0, sticky="ew", padx=10, pady=(0, 4))

    color_row = ctk.CTkFrame(body, fg_color="transparent")
    color_row.grid(row=6, column=0, sticky="ew", padx=10, pady=(0, 2))
    ctk.CTkLabel(
        color_row, text="Color",
        font=ctk.CTkFont(size=12, weight="bold"),
        anchor="w",
    ).pack(anchor="w")
    swatch_row = ctk.CTkFrame(color_row, fg_color="transparent")
    swatch_row.pack(anchor="w", pady=(2, 0))
    ctk.CTkLabel(
        color_row,
        text="Click a name, then a color.  <COLOR FF4040>Name</COLOR>",
        text_color=DIM,
        font=ctk.CTkFont(size=11),
        anchor="w",
    ).pack(anchor="w", pady=(2, 0))

    fields_host = ctk.CTkFrame(body, fg_color="transparent")
    fields_host.grid(row=7, column=0, sticky="ew", padx=4)
    fields_host.grid_columnconfigure(0, weight=1)

    fields: dict[str, tk.StringVar] = {
        key: tk.StringVar(value=loaded.get(key, ""))
        for key in SHARED_COSTUME_NAME_KEYS
    }
    entries: dict[str, ctk.CTkEntry] = {}
    focused: dict[str, str | None] = {"key": None}
    default_text = ctk.ThemeManager.theme["CTkEntry"]["text_color"]
    pages: dict[str, ctk.CTkFrame] = {}

    def _paint(key: str) -> None:
        entry = entries.get(key)
        if entry is None:
            return
        color = preview_hex_for_name(fields[key].get())
        entry.configure(text_color=color or default_text)

    def _apply_color(spec: str) -> None:
        key = focused["key"]
        if not key:
            return
        fields[key].set(apply_col_tag(fields[key].get(), spec))
        _paint(key)
        try:
            entries[key].focus_set()
        except tk.TclError:
            pass

    def _pick_custom() -> None:
        chosen = tkinter.colorchooser.askcolor(
            parent=win, title="Costume name color")
        if not chosen or not chosen[0]:
            return
        red, green, blue = chosen[0]
        _apply_color(f"{int(red):02X}{int(green):02X}{int(blue):02X}")

    for index, (label, token, hex_color) in enumerate(NAME_COLOR_SWATCHES):
        ctk.CTkButton(
            swatch_row, text=label, width=62, height=24,
            fg_color=hex_color, hover_color=hex_color,
            text_color=_swatch_text_color(hex_color),
            font=ctk.CTkFont(size=11),
            command=lambda token=token: _apply_color(token),
        ).grid(row=index // 4, column=index % 4, padx=(0, 4), pady=2)
    ctk.CTkButton(
        swatch_row, text="Custom", width=62, height=24,
        fg_color="#3a3a3a", hover_color="#4a4a4a",
        font=ctk.CTkFont(size=11),
        command=_pick_custom,
    ).grid(row=1, column=4, padx=(0, 4), pady=2)

    def _build_page(name: str, keys: tuple[str, ...]) -> ctk.CTkFrame:
        page = ctk.CTkFrame(fields_host, fg_color="transparent")
        page.grid_columnconfigure(0, weight=1)
        for i, key in enumerate(keys):
            label = SHARED_COSTUME_NAME_LABELS[key]
            vanilla = SHARED_COSTUME_NAME_VANILLA[key]
            ctk.CTkLabel(
                page, text=label, anchor="w",
                font=ctk.CTkFont(size=12, weight="bold"),
            ).grid(row=i * 2, column=0, sticky="ew", padx=6, pady=(4, 0))
            entry = ctk.CTkEntry(
                page, textvariable=fields[key],
                placeholder_text=vanilla, height=28,
            )
            entry.grid(row=i * 2 + 1, column=0, sticky="ew", padx=6, pady=(2, 0))
            entry.bind("<FocusIn>", lambda _event, key=key: focused.__setitem__("key", key))
            fields[key].trace_add("write", lambda *_args, key=key: _paint(key))
            entries[key] = entry
            _paint(key)
        return page

    pages["claire"] = _build_page("claire", CLAIRE_NAME_PACK_KEYS)
    pages["leon"] = _build_page("leon", LEON_NAME_PACK_KEYS)

    def _show_character(which: str) -> None:
        char_var.set(which)
        title_label.configure(
            text="Claire" if which == "claire" else "Leon")
        blurb_label.configure(text=_BLURBS[which])
        for key, page in pages.items():
            if key == which:
                page.grid(row=0, column=0, sticky="nsew")
            else:
                page.grid_remove()
        claire_btn.configure(
            fg_color=CONVERT if which == "claire" else ("gray75", "gray25"),
            hover_color=CONVERT_HOVER if which == "claire" else ("gray70", "gray30"),
        )
        leon_btn.configure(
            fg_color=CONVERT if which == "leon" else ("gray75", "gray25"),
            hover_color=CONVERT_HOVER if which == "leon" else ("gray70", "gray30"),
        )

    claire_btn = ctk.CTkButton(
        char_row, text="Claire", width=90, height=28,
        command=lambda: _show_character("claire"),
    )
    claire_btn.pack(side="left", padx=(0, 6))
    leon_btn = ctk.CTkButton(
        char_row, text="Leon", width=90, height=28,
        command=lambda: _show_character("leon"),
    )
    leon_btn.pack(side="left")

    if existing is not None:
        ctk.CTkLabel(
            body,
            text=f"Editing {existing.name}",
            text_color=DIM,
            font=ctk.CTkFont(size=12),
            anchor="w",
        ).grid(row=8, column=0, sticky="ew", padx=10, pady=(8, 0))

    btn_row = ctk.CTkFrame(outer, fg_color="transparent")
    btn_row.grid(row=1, column=0, sticky="ew", padx=10, pady=(8, 10))
    btn_row.grid_columnconfigure(0, weight=1)

    def _capture_geometry() -> str:
        win.update_idletasks()
        return (
            f"{win.winfo_width()}x{win.winfo_height()}"
            f"+{win.winfo_x()}+{win.winfo_y()}"
        )

    def _persist_geometry():
        try:
            if win.winfo_ismapped():
                app.settings["name_pack_geometry"] = _capture_geometry()
                persist = getattr(app, "_save_settings", None)
                if callable(persist):
                    persist()
        except tk.TclError:
            pass

    def _cancel(_event=None):
        _persist_geometry()
        try:
            win.grab_release()
        except tk.TclError:
            pass
        try:
            win.withdraw()
        except tk.TclError:
            pass
        win.destroy()
        return "break"

    def _save():
        values = {k: fields[k].get() for k in SHARED_COSTUME_NAME_KEYS}
        updated = existing is not None
        try:
            out = build_costume_name_pack(
                Path(output_dir), values, dest=existing,
                game_build=build_var.get())
        except ValueError as e:
            tk.messagebox.showwarning("Costume names", str(e), parent=win)
            return
        except Exception as e:
            action = "update" if updated else "create"
            tk.messagebox.showerror(
                "Costume names",
                f"Could not {action} name pack:\n{e}",
                parent=win,
            )
            return
        _persist_geometry()
        try:
            win.grab_release()
        except tk.TclError:
            pass
        win.destroy()
        if on_created is not None:
            on_created(out, updated)
        else:
            tk.messagebox.showinfo(
                "Costume names",
                f"{'Updated' if updated else 'Created'}:\n{out}",
                parent=app,
            )

    ctk.CTkButton(
        btn_row,
        text="Save" if existing is not None else "Create",
        width=100, command=_save,
        fg_color=CONVERT, hover_color=CONVERT_HOVER,
    ).grid(row=0, column=1, padx=(0, 8))
    ctk.CTkButton(
        btn_row, text="Cancel", width=100, command=_cancel,
    ).grid(row=0, column=2)

    _show_character("claire")

    win.protocol("WM_DELETE_WINDOW", _cancel)
    win.bind("<Escape>", _cancel)
    win.update_idletasks()
    area_w, area_h = work_area_size(win)
    saved_geo = clamp_dialog_geometry(
        str(getattr(app, "settings", {}).get("name_pack_geometry") or ""),
        max_w=max(440, area_w - 24),
        max_h=max(360, area_h - 24),
        min_w=440,
        min_h=360,
    )
    placed = False
    if saved_geo:
        try:
            win.geometry(saved_geo)
            placed = True
        except tk.TclError:
            placed = False
    if not placed:
        try:
            app.update_idletasks()
            x = app.winfo_rootx() + max(
                0, (app.winfo_width() - win.winfo_width()) // 2)
            y = app.winfo_rooty() + max(
                0, (app.winfo_height() - win.winfo_height()) // 2)
            win.geometry(f"+{x}+{y}")
        except tk.TclError:
            pass
    win.deiconify()
    win.lift()
    win.focus()
    return win
