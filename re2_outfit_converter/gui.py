"""customtkinter GUI for the RE2 Outfit Converter."""

from __future__ import annotations

import os
import shutil
import threading
import tkinter as tk
import tkinter.filedialog  # noqa: F401
import tkinter.messagebox  # noqa: F401
from dataclasses import dataclass
from pathlib import Path

import customtkinter as ctk

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    HAS_DND = True
except ImportError:
    HAS_DND = False

from . import __version__
from .cancel import cancel_requested, request_cancel, reset_cancel
from .analyzer import (
    AnalysisResult,
    GAME_BUILDS,
    game_build_direction,
    game_build_for,
    game_label_for,
)
from .archive import ModSource
from .gui_analysis import (
    collect_warnings,
    count_patch_skips,
    format_mod_row,
    format_multi_outfit_row,
    format_outfit_row,
    is_game_build_load,
)
from .gui_name_pack import open_name_pack_dialog, preview_hex_for_name
from .gui_settings import open_settings_dialog
from .gui_workers import analyze_paths, convert_game_builds, convert_loaded
from .name_ui import (
    SHARED_NAME_PACK_HINT,
    active_convert_name_target,
    collect_display_names_by_target,
    from_checkbox_label,
    is_convert_namable,
    uses_shared_name_pack,
)
from .outfit_health import incomplete_outfits_for_load
from .outfit_ops import OutfitOp
from .outfits import (
    Outfit,
    convertible_outfits_for,
    is_convertible_outfit,
)
from .reports import BatchReport, ConversionCancelled, ConversionError
from .session import LoadedPackage, close_loaded, package_label
from .settings import (
    app_dir,
    default_output_dir,
    icon_path,
    initial_output_dir,
    load_settings,
    outfit_from_menu_label,
    outfit_menu_label,
    outfit_menu_labels,
    settings_path,
    strip_tag_markers,
    tag_marker_for,
    write_settings,
)

DELETE_ACTION = "Delete 🗑"
INCOMPLETE_COLOR = "#e74c3c"
FOCUS_COLOR = "#5dade2"

# Re-export for callers that historically imported these from gui.
__all__ = ["App", "LoadedMod", "run", "app_dir", "settings_path", "default_output_dir"]

ACCENT = "#c0392b"
CONVERT = "#0f766e"
CONVERT_HOVER = "#0d9488"
OK_COLOR = "#2ecc71"
WARN_COLOR = "#f1c40f"
DIM = "#9a9a9a"
QUIET_BORDER = "#3a3a3a"


@dataclass
class LoadedMod:
    source: ModSource
    analysis: AnalysisResult

    @classmethod
    def from_package(cls, pkg: LoadedPackage) -> "LoadedMod":
        return cls(source=pkg.source, analysis=pkg.analysis)


if HAS_DND:
    class _Root(ctk.CTk, TkinterDnD.DnDWrapper):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.TkdndVersion = TkinterDnD._require(self)
else:
    _Root = ctk.CTk


def _quiet_button(parent, text: str, command, **kwargs):
    """Secondary action: border only, so Convert stays the one solid button."""
    opts = dict(
        fg_color="transparent",
        hover_color="#2a2a2a",
        border_width=1,
        border_color=QUIET_BORDER,
        text_color=("#f2f2f2", "#f2f2f2"),
        height=32,
    )
    opts.update(kwargs)
    return ctk.CTkButton(parent, text=text, command=command, **opts)


def _settings_gear_image() -> ctk.CTkImage | None:
    """White gear glyph for the header Settings button."""
    try:
        import math
        from PIL import Image, ImageDraw
    except ImportError:
        return None
    size = 64
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    cx = cy = (size - 1) / 2.0
    teeth = 8
    r_tip = size * 0.46
    r_valley = size * 0.33
    r_hole = size * 0.14
    pts = []
    for i in range(teeth):
        a = 2 * math.pi * i / teeth - math.pi / 2
        da = math.pi / teeth
        for ang, r in (
            (a - da * 0.82, r_valley),
            (a - da * 0.32, r_tip),
            (a + da * 0.32, r_tip),
            (a + da * 0.82, r_valley),
        ):
            pts.append((cx + r * math.cos(ang), cy + r * math.sin(ang)))
    draw.polygon(pts, fill=255)
    draw.ellipse(
        [cx - r_hole, cy - r_hole, cx + r_hole, cy + r_hole],
        fill=0,
    )
    img = Image.new("RGBA", (size, size), (245, 245, 245, 255))
    img.putalpha(mask)
    return ctk.CTkImage(light_image=img, dark_image=img, size=(18, 18))


def _costume_names_image() -> ctk.CTkImage | None:
    """White clothing-tag glyph for the Costume names button."""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return None
    size = 64
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle((6, 18, 58, 46), radius=10, fill=255)
    draw.ellipse((14, 26, 26, 38), fill=0)
    draw.rounded_rectangle((32, 26, 50, 30), radius=2, fill=0)
    draw.rounded_rectangle((32, 34, 46, 38), radius=2, fill=0)
    img = Image.new("RGBA", (size, size), (245, 245, 245, 255))
    img.putalpha(mask)
    return ctk.CTkImage(light_image=img, dark_image=img, size=(18, 18))


class App(_Root):
    def __init__(self):
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")
        super().__init__()

        self.title(f"RE2 Remake Outfit Converter  v{__version__}")
        self.minsize(715, 590)
        ctk.set_widget_scaling(1.0)
        ctk.set_window_scaling(1.0)
        icon = icon_path()
        if icon is not None:
            # .ico via iconbitmap is Windows-oriented; ignore failures on Linux.
            try:
                self.iconbitmap(str(icon))
            except (tk.TclError, OSError):
                pass

        self.loaded: list[LoadedMod] = []
        self.settings = load_settings()
        self._busy = False
        self._converting = False
        self._closed = False
        self._filling_name = False
        self._suggested_outfit_name = ""
        self._names_by_outfit_key: dict[str, str] = {}
        self._name_generic = ""
        self._name_user_edited = False
        self._settings_win: ctk.CTkToplevel | None = None
        self._settings_persist = None
        self._resize_after: str | None = None
        self._last_wrap_width = 0
        self._settings_write_warned = False
        self._incomplete: dict[str, str] = {}
        self._from_checks: list[dict] = []
        self._outfit_display_names: dict[str, str] = {}
        self._outfit_name_edited: dict[str, bool] = {}
        self._outfit_to_choice: dict[str, str] = {}
        self._active_source_key: str | None = None
        self._suppress_from_toggle = False

        self._restore_geometry()
        self._build_ui()
        if HAS_DND:
            self.drop_target_register(DND_FILES)
            self.dnd_bind("<<Drop>>", self._on_drop)
        self.bind("<Configure>", self._on_window_configure)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------ UI

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self.grid_rowconfigure(2, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=20, pady=(16, 0))
        header.grid_columnconfigure(0, weight=1, uniform="header")
        header.grid_columnconfigure(2, weight=1, uniform="header")
        title_row = ctk.CTkFrame(header, fg_color="transparent")
        title_row.grid(row=0, column=1)
        ctk.CTkLabel(
            title_row,
            text="RE2 Remake Outfit Converter",
            font=ctk.CTkFont(size=18, weight="bold"),
            anchor="w",
        ).pack(side="left")
        ctk.CTkLabel(
            title_row,
            text=f"v{__version__}",
            font=ctk.CTkFont(size=13),
            text_color=DIM,
            anchor="w",
        ).pack(side="left", padx=(10, 0), pady=(3, 0))
        header_btns = ctk.CTkFrame(header, fg_color="transparent")
        header_btns.grid(row=0, column=2, sticky="e")
        self._names_image = _costume_names_image()
        names_text = "" if self._names_image is not None else "Aa"
        names_extra = {"width": 36, "height": 32}
        if self._names_image is not None:
            names_extra["image"] = self._names_image
        self.names_btn = _quiet_button(
            header_btns, names_text, self._open_name_pack, **names_extra)
        self.names_btn.pack(side="left", padx=(0, 8))
        self._bind_tooltip(self.names_btn, "Costume names")
        self._settings_gear_image = _settings_gear_image()
        gear_kwargs = {
            "command": self._open_settings,
            "width": 36,
            "height": 32,
            "fg_color": "transparent",
            "hover_color": "#2a2a2a",
            "border_width": 1,
            "border_color": QUIET_BORDER,
        }
        if self._settings_gear_image is not None:
            gear_kwargs["image"] = self._settings_gear_image
            gear_kwargs["text"] = ""
        else:
            gear_kwargs["text"] = "⚙"
            gear_kwargs["width"] = 36
        self._gear_btn = ctk.CTkButton(header_btns, **gear_kwargs)
        self._gear_btn.pack(side="left")
        self._bind_tooltip(self._gear_btn, "Settings")

        mod = ctk.CTkFrame(self, corner_radius=16)
        mod.grid(row=1, column=0, sticky="nsew", padx=20, pady=(14, 8))
        mod.grid_columnconfigure(0, weight=1)

        self._idle_subtitle = (
            "Folder, zip, rar, or 7z" if HAS_DND
            else "Select a mod folder or archive")
        self._idle_headline_font = ctk.CTkFont(size=22, weight="bold")
        self._loaded_headline_font = ctk.CTkFont(size=16, weight="bold")
        self.drop_label = ctk.CTkLabel(
            mod, text="Drop a mod",
            font=self._idle_headline_font,
            anchor="w", justify="left")
        self.drop_label.grid(
            row=0, column=0, sticky="ew", padx=20, pady=(22, 0))

        self.path_label = ctk.CTkLabel(
            mod, text=self._idle_subtitle, text_color=DIM,
            anchor="w", justify="left",
            font=ctk.CTkFont(size=13))
        self.path_label.grid(row=1, column=0, sticky="ew", padx=20, pady=(4, 0))

        browse = ctk.CTkFrame(mod, fg_color="transparent")
        browse.grid(row=2, column=0, pady=(14, 0))
        _quiet_button(
            browse, "Folder", self._browse_folder, width=96,
        ).pack(side="left", padx=(0, 8))
        _quiet_button(
            browse, "Archive", self._browse_archive, width=96,
        ).pack(side="left")

        self.facts_row = ctk.CTkFrame(mod, fg_color="transparent")
        self.facts_row.grid(row=3, column=0, sticky="ew", padx=20, pady=(16, 0))
        self.facts_row.grid_columnconfigure(1, weight=1)
        self.facts_row.grid_columnconfigure(3, weight=1)
        fact_font = ctk.CTkFont(size=12)
        ctk.CTkLabel(
            self.facts_row, text="Outfits", width=72, anchor="w",
            text_color=DIM, font=fact_font,
        ).grid(row=0, column=0, sticky="nw")
        outfit_val = ctk.CTkLabel(
            self.facts_row, text="-", anchor="w", justify="left")
        outfit_val.grid(row=0, column=1, sticky="ew", padx=(8, 18))
        ctk.CTkLabel(
            self.facts_row, text="Build", width=52, anchor="w",
            text_color=DIM, font=fact_font,
        ).grid(row=0, column=2, sticky="nw")
        game_val = ctk.CTkLabel(
            self.facts_row, text="-", anchor="w", justify="left")
        game_val.grid(row=0, column=3, sticky="ew")
        self.info_rows = {
            "mod": self.drop_label,
            "outfit": outfit_val,
            "game": game_val,
        }

        out = ctk.CTkFrame(mod, fg_color="transparent")
        out.grid(row=4, column=0, sticky="ew", padx=20, pady=(18, 18))
        out.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            out, text="Output", width=72, anchor="w", text_color=DIM,
            font=fact_font,
        ).grid(row=0, column=0, sticky="w")
        self.out_var = tk.StringVar(value=initial_output_dir(self.settings))
        self.out_entry = ctk.CTkEntry(out, textvariable=self.out_var, height=32)
        self.out_entry.grid(row=0, column=1, sticky="ew", padx=(8, 8))
        _quiet_button(
            out, "...", self._browse_output, width=36,
        ).grid(row=0, column=2)

        bottom = ctk.CTkFrame(self, corner_radius=16)
        bottom.grid(row=2, column=0, sticky="nsew", padx=20, pady=(0, 18))
        bottom.grid_columnconfigure(0, weight=1)

        conv = ctk.CTkFrame(bottom, fg_color="transparent")
        conv.grid(row=0, column=0, sticky="ew", padx=20, pady=(18, 4))
        conv.grid_columnconfigure(0, weight=1)

        self.from_label = ctk.CTkLabel(
            conv, text="Convert from", anchor="w", text_color=DIM,
            font=ctk.CTkFont(size=12))
        self.from_label.grid(row=0, column=0, sticky="w")

        # Sizes to content and wraps; avoids a tall empty scroll area.
        self.from_checks_frame = ctk.CTkFrame(conv, fg_color="transparent")
        self.from_checks_frame.grid(row=1, column=0, sticky="ew", pady=(6, 2))

        menus = ctk.CTkFrame(conv, fg_color="transparent")
        self.menus_row = menus
        menus.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        menus.grid_columnconfigure(0, weight=1)
        menus.grid_columnconfigure(1, weight=1)

        self.to_col = ctk.CTkFrame(menus, fg_color="transparent")
        self.to_col.grid(row=0, column=0, sticky="ew", padx=(0, 12))
        self.to_col.grid_columnconfigure(0, weight=1)
        self.to_label = ctk.CTkLabel(
            self.to_col, text="Convert to", anchor="w", text_color=DIM,
            font=ctk.CTkFont(size=12))
        self.to_label.grid(row=0, column=0, sticky="w")
        to_labels = self._to_menu_values()
        self.to_var = tk.StringVar(value=to_labels[0] if to_labels else "-")
        self.to_menu = ctk.CTkOptionMenu(
            self.to_col, variable=self.to_var,
            values=to_labels or ["-"], width=240,
            state="disabled",
            command=self._on_target_outfit_changed)
        self.to_menu.grid(row=1, column=0, sticky="ew", pady=(6, 0))

        self.game_col = ctk.CTkFrame(menus, fg_color="transparent")
        self.game_col.grid(row=0, column=1, sticky="ew")
        self.game_col.grid_columnconfigure(0, weight=1)
        self.game_label = ctk.CTkLabel(
            self.game_col, text="Game build", anchor="w", text_color=DIM,
            font=ctk.CTkFont(size=12))
        self.game_label.grid(row=0, column=0, sticky="w")
        self.game_var = tk.StringVar(value=GAME_BUILDS[0])
        self.game_menu = ctk.CTkOptionMenu(
            self.game_col, variable=self.game_var,
            values=list(GAME_BUILDS), width=220,
            state="disabled")
        self.game_menu.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        self.game_var.trace_add(
            "write", lambda *_args: self._sync_build_direction())

        self.build_direction = ctk.CTkLabel(
            conv, text="", anchor="w",
            font=ctk.CTkFont(size=13))
        self.build_hint = ctk.CTkLabel(
            conv,
            text=(
                "Meshes and materials use Blender; prefabs and physics "
                "chains are copied, not rewritten."
            ),
            text_color=DIM, anchor="w",
            font=ctk.CTkFont(size=11), justify="left")

        opts = ctk.CTkFrame(bottom, fg_color="transparent")
        opts.grid(row=1, column=0, sticky="ew", padx=20, pady=(8, 4))
        opts.grid_columnconfigure(0, weight=1)

        name_row = ctk.CTkFrame(opts, fg_color="transparent")
        self.name_row = name_row
        name_row.grid(row=0, column=0, sticky="ew")
        name_row.grid_columnconfigure(0, weight=1)

        self.set_name_var = tk.BooleanVar(
            value=bool(self.settings.get("set_outfit_name", False)))
        self.set_name_cb = ctk.CTkCheckBox(
            name_row, text="Set in-game outfit name",
            variable=self.set_name_var,
            command=self._on_set_name_toggled,
            height=28)
        self.set_name_cb.grid(row=0, column=0, sticky="w")
        self._bind_tooltip(
            self.set_name_cb,
            "Sets the costume-select name shown in-game.\n"
            "Claire: Elza / Noir / Military on Convert.\n"
            "Leon: Noir / Arklay Sheriff on Convert.\n"
            "Base Jacket/Tank/Classic* and Leon Casual/Police*\n"
            "share name files — use Costume names instead.\n"
            "<COLOR FF4040>Name</COLOR> previews that color here.")

        self.outfit_name_var = tk.StringVar(value="")
        self.outfit_name_entry = ctk.CTkEntry(
            name_row, textvariable=self.outfit_name_var,
            placeholder_text="In-game outfit name", height=28,
            state="disabled")
        self._outfit_name_default_color = (
            ctk.ThemeManager.theme["CTkEntry"]["text_color"])
        # Always gridded so Convert-to switches don't resize the window.
        self.outfit_name_entry.grid(
            row=1, column=0, sticky="ew", pady=(8, 0))
        self.outfit_name_var.trace_add("write", self._on_outfit_name_typed)

        self.name_hint = ctk.CTkLabel(
            opts, text="", text_color=DIM, anchor="w",
            font=ctk.CTkFont(size=11), height=18)
        self.name_hint.grid(row=1, column=0, sticky="ew", pady=(1, 0))

        self.convert_btn = ctk.CTkButton(
            bottom, text="Convert", height=42, state="disabled",
            fg_color=CONVERT, hover_color=CONVERT_HOVER,
            font=ctk.CTkFont(size=15, weight="bold"),
            command=self._on_convert_click)
        self.convert_btn.grid(
            row=2, column=0, sticky="ew", padx=20, pady=(10, 8))

        progress_row = ctk.CTkFrame(bottom, fg_color="transparent")
        progress_row.grid(row=3, column=0, sticky="ew", padx=20, pady=(0, 16))
        progress_row.grid_columnconfigure(0, weight=1)

        self.progress_bar = ctk.CTkProgressBar(
            progress_row, height=12, corner_radius=6,
            progress_color=CONVERT, fg_color="#2a2a2a",
            border_width=0)
        self.progress_bar.grid(row=0, column=0, sticky="ew")
        self.progress_bar.set(0)

        self.status_label = ctk.CTkLabel(
            progress_row, text="", anchor="center",
            font=ctk.CTkFont(size=12),
            text_color=DIM)
        self.status_label.grid(row=1, column=0, sticky="ew", pady=(4, 0))

        self._show_idle_convert_ui()
        self.after(50, self._update_wraplengths)

    # -------------------------------------------------------------- helpers

    def _skip_completion_dialog(self) -> bool:
        return bool(self.settings.get("skip_completion_dialog", False))

    def _tag_zip_enabled(self) -> bool:
        return bool(self.settings.get("tag_zip_name", True))

    def _tag_description_enabled(self) -> bool:
        return bool(self.settings.get("tag_modinfo_description", True))

    def _restore_geometry(self):
        geo = str(self.settings.get("window_geometry", "")).strip()
        if geo:
            try:
                self.geometry(geo)
                return
            except tk.TclError:
                pass
        self.geometry("920x720")

    def _capture_geometry(self):
        try:
            self.update_idletasks()
            self.settings["window_geometry"] = self.winfo_geometry()
        except tk.TclError:
            pass

    def _on_window_configure(self, event):
        if event.widget is not self:
            return
        if self._resize_after is not None:
            try:
                self.after_cancel(self._resize_after)
            except Exception:
                pass
        self._resize_after = self.after(120, self._after_resize)

    def _after_resize(self):
        self._resize_after = None
        self._update_wraplengths()
        self._relayout_from_checks_if_needed()
        self._capture_geometry()

    def _relayout_from_checks_if_needed(self) -> None:
        if not self._from_checks:
            return
        cols = self._from_check_columns()
        # Count current columns used by existing grid children.
        used = {
            int(child.grid_info().get("column", 0))
            for child in self.from_checks_frame.winfo_children()
            if child.winfo_manager() == "grid"
        }
        current_cols = (max(used) + 1) if used else 0
        if current_cols == cols:
            return
        # Preserve selection while reflowing columns.
        self._rebuild_from_checks(select_first=False)

    def _update_wraplengths(self):
        try:
            width = max(280, self.winfo_width() - 80)
        except tk.TclError:
            return
        if abs(width - self._last_wrap_width) < 24:
            return
        self._last_wrap_width = width
        for label in [
            self.drop_label, self.path_label,
            self.info_rows["outfit"], self.info_rows["game"],
            self.build_direction, self.build_hint,
        ]:
            try:
                label.configure(wraplength=width)
            except tk.TclError:
                pass

    def _is_game_build_mode(self) -> bool:
        return is_game_build_load(m.analysis for m in self.loaded)

    def _apply_ui_mode(self) -> None:
        game = self._is_game_build_mode()
        if game:
            self.from_label.grid_remove()
            self.from_checks_frame.grid_remove()
            self.name_row.grid_remove()
            self.name_hint.grid_remove()
            self.names_btn.pack_forget()
            self.build_direction.grid(
                row=3, column=0, sticky="ew", pady=(8, 0))
            self.build_hint.grid(
                row=4, column=0, sticky="ew", pady=(2, 0))
        else:
            self.from_label.grid(row=0, column=0, sticky="w")
            self.from_checks_frame.grid(
                row=1, column=0, sticky="ew", pady=(4, 2))
            self.name_row.grid(row=0, column=0, sticky="ew")
            self.name_hint.grid(row=1, column=0, sticky="ew", pady=(1, 0))
            if not self.names_btn.winfo_ismapped():
                self.names_btn.pack(
                    side="left", padx=(0, 8), before=self._gear_btn)
            self.build_direction.grid_remove()
            self.build_hint.grid_remove()
        self._layout_to_row(game)
        self._sync_build_direction()
        self._sync_convert_button()

    def _layout_to_row(self, game: bool) -> None:
        self.to_col.grid_remove()
        self.game_col.grid_remove()
        if game:
            self.game_col.grid(row=0, column=0, sticky="ew")
        else:
            self.to_col.grid(row=0, column=0, sticky="ew", padx=(0, 12))
            self.game_col.grid(row=0, column=1, sticky="ew")

    def _sync_build_direction(self) -> None:
        if not self._is_game_build_mode():
            return
        if not hasattr(self, "build_direction"):
            return
        detected = "-"
        if self.loaded:
            detected = game_label_for(m.analysis for m in self.loaded)
        chosen = self.game_var.get()
        if chosen not in GAME_BUILDS:
            chosen = GAME_BUILDS[0]
        self.build_direction.configure(
            text=game_build_direction(detected, chosen))

    def _save_settings(self):
        self._capture_geometry()
        self.settings["output_dir"] = self.out_var.get()
        self.settings["set_outfit_name"] = bool(self.set_name_var.get())
        if not write_settings(self.settings) and not self._settings_write_warned:
            self._settings_write_warned = True
            try:
                tk.messagebox.showwarning(
                    "Settings",
                    "Could not save settings.json "
                    "(folder may be read-only). Preferences will not persist.")
            except tk.TclError:
                pass

    def _open_name_pack(self):
        out = Path(self.out_var.get().strip() or initial_output_dir(self.settings))
        if not out.is_dir():
            try:
                out.mkdir(parents=True, exist_ok=True)
            except OSError:
                tk.messagebox.showerror(
                    "Costume names",
                    f"Output folder is not available:\n{out}")
                return

        def on_created(path: Path, updated: bool):
            self.out_var.set(str(path.parent))
            self._save_settings()
            verb = "updated" if updated else "created"
            if self._skip_completion_dialog():
                self.status_label.configure(
                    text=f"Name pack {verb}: {path.name}",
                    text_color=OK_COLOR)
            elif updated:
                tk.messagebox.showinfo(
                    "Costume names",
                    f"Updated Fluffy name pack:\n{path}\n\n"
                    "The same folder was updated. If the menu text does not "
                    "change, disable and enable that folder once in Fluffy.")
            else:
                tk.messagebox.showinfo(
                    "Costume names",
                    f"Created Fluffy name pack:\n{path}\n\n"
                    "Enable this folder in Fluffy. Later saves update the "
                    "files inside it.")

        open_name_pack_dialog(self, output_dir=out, on_created=on_created)

    def _open_settings(self):
        if self._settings_win is not None and self._settings_win.winfo_exists():
            self._settings_win.focus()
            return

        def on_persist():
            self._save_settings()
            self._refresh_convert_menus()

        def on_closed():
            self._settings_persist = None
            self._settings_win = None

        win = open_settings_dialog(
            self, on_persist=on_persist, on_closed=on_closed)
        self._settings_win = win
        self._settings_persist = getattr(win, "_re2oc_persist", None)

    def _bind_tooltip(self, widget, text: str):
        tip = {"win": None}

        def show(_event=None):
            if tip["win"] is not None:
                return
            x = widget.winfo_rootx() + 12
            y = widget.winfo_rooty() + widget.winfo_height() + 6
            win = tk.Toplevel(self)
            win.wm_overrideredirect(True)
            win.wm_geometry(f"+{x}+{y}")
            label = tk.Label(
                win, text=text, justify="left",
                background="#2b2b2b", foreground="#dddddd",
                relief="solid", borderwidth=1,
                font=("Segoe UI", 9), padx=8, pady=6)
            label.pack()
            tip["win"] = win

        def hide(_event=None):
            win = tip["win"]
            tip["win"] = None
            if win is not None:
                win.destroy()

        widget.bind("<Enter>", show)
        widget.bind("<Leave>", hide)

    def _outfit_menu_label(self, outfit) -> str:
        return outfit_menu_label(self.settings, outfit)

    def _active_character(self) -> str:
        """Character key for From/To menus (loaded pack, else Claire idle)."""
        if self.loaded:
            for m in self.loaded:
                key = m.analysis.character_key
                if key:
                    return key
            for m in self.loaded:
                outfits = m.analysis.outfits or m.analysis.claire_outfits
                if outfits:
                    return outfits[0].character
        return "claire"

    def _menu_outfits(self) -> list[Outfit]:
        return convertible_outfits_for(self._active_character())

    def _outfit_from_menu_label(self, label: str):
        return outfit_from_menu_label(
            self.settings, label, character=self._active_character())

    def _delete_action_available(self) -> bool:
        """Delete only makes sense when the pack has more than one outfit slot."""
        if not self.loaded:
            return False
        return len(self._convertible_source_outfits()) > 1

    def _to_menu_values(self) -> list[str]:
        labels = list(outfit_menu_labels(
            self.settings, character=self._active_character()))
        if self._delete_action_available():
            if DELETE_ACTION not in labels:
                labels.append(DELETE_ACTION)
        return labels

    def _sanitize_delete_choices(self) -> None:
        """Clear stored Delete targets when Delete is not offered."""
        if self._delete_action_available():
            return
        menu = {o.key: o for o in self._menu_outfits()}
        for key, choice in list(self._outfit_to_choice.items()):
            if not str(choice).startswith("Delete"):
                continue
            outfit = menu.get(key)
            if outfit is not None:
                self._outfit_to_choice[key] = self._outfit_menu_label(outfit)

    def _refresh_to_menu(self) -> None:
        self._sanitize_delete_choices()
        labels = self._to_menu_values()
        if not labels:
            return
        current = self.to_var.get()
        if current.startswith("Delete"):
            current = DELETE_ACTION
        self.to_menu.configure(values=labels)
        if current in labels:
            self.to_var.set(current)
        else:
            src = self._selected_source_outfit()
            if src is not None:
                self.to_var.set(self._outfit_menu_label(src))
            else:
                self.to_var.set(labels[0])

    def _refresh_convert_menus(self) -> None:
        self._refresh_to_menu()
        if self.loaded:
            self._rebuild_from_checks(select_first=False)

    def _is_delete_target(self) -> bool:
        return self.to_var.get().startswith("Delete")

    def _target_outfit(self):
        if self._is_delete_target():
            return None
        return self._outfit_from_menu_label(self.to_var.get())

    def _on_target_outfit_changed(self, _value=None):
        src = self._selected_source_outfit()
        if src is not None:
            self._outfit_to_choice[src.key] = self.to_var.get()
        self._sync_name_ui()

    def _collect_incomplete(self) -> dict[str, str]:
        return incomplete_outfits_for_load(
            [m.analysis for m in self.loaded])

    def _convertible_source_outfits(self) -> list[Outfit]:
        detected: set[str] = set()
        for m in self.loaded:
            outfits = m.analysis.outfits or m.analysis.claire_outfits
            for o in outfits:
                if is_convertible_outfit(o):
                    detected.add(o.key)
        menu = self._menu_outfits()
        return [o for o in menu if o.key in detected]

    def _from_check_outfits(self) -> list[Outfit]:
        """Outfits shown as From checkboxes (detected, or all while idle)."""
        menu = self._menu_outfits()
        if not self.loaded:
            return list(menu)
        detected = self._convertible_source_outfits()
        # Keep the same strip layout even when nothing is convertible.
        return detected if detected else list(menu)

    def _show_idle_convert_ui(self) -> None:
        """Idle / no-mod convert strip — same layout, clickable, convert locked."""
        self._incomplete = {}
        self._outfit_display_names.clear()
        self._outfit_name_edited.clear()
        self._outfit_to_choice.clear()
        self._active_source_key = None
        self._suggested_outfit_name = ""
        self._names_by_outfit_key = {}
        self._name_generic = ""
        self._filling_name = True
        self.outfit_name_var.set("")
        self._filling_name = False
        self._name_user_edited = False
        self._refresh_to_menu()
        self.game_var.set(GAME_BUILDS[0])
        self.game_menu.configure(state="disabled")
        self._show_idle_mod_card()
        self._rebuild_from_checks(select_first=True)
        self._apply_ui_mode()

    def _show_idle_mod_card(self) -> None:
        self.drop_label.configure(
            text="Drop a mod", anchor="center", justify="center",
            font=self._idle_headline_font)
        self.path_label.grid()
        self.path_label.configure(
            text=self._idle_subtitle, anchor="center", justify="center")
        self.info_rows["outfit"].configure(text="-")
        self.info_rows["game"].configure(text="-")
        self.facts_row.grid_remove()

    def _clear_from_checks(self) -> None:
        for child in self.from_checks_frame.winfo_children():
            child.destroy()
        self._from_checks.clear()

    def _rebuild_from_checks(self, *, select_first: bool = True) -> None:
        self._incomplete = self._collect_incomplete() if self.loaded else {}
        self._persist_active_name()
        if self._active_source_key is not None:
            self._outfit_to_choice[self._active_source_key] = self.to_var.get()
        prev_checked = {
            r["outfit"].key for r in self._from_checks if bool(r["var"].get())
        }
        prev_active = self._active_source_key
        self._clear_from_checks()
        self._sanitize_delete_choices()
        outfits = self._from_check_outfits()
        if not outfits:
            self._active_source_key = None
            self.to_menu.configure(state="disabled")
            self.convert_btn.configure(state="disabled")
            self._sync_name_ui()
            return

        outfit_keys = {o.key for o in outfits}
        if select_first:
            # Loaded multi-slot packs: tick every detected outfit so Delete +
            # convert targets can be set per row and run together.
            if self.loaded:
                checked_keys = set(outfit_keys)
            else:
                checked_keys = {outfits[0].key}
        else:
            checked_keys = prev_checked & outfit_keys
            if not checked_keys:
                checked_keys = {outfits[0].key}

        if prev_active in checked_keys:
            pick_key = prev_active
        else:
            pick_key = next(
                (o.key for o in outfits if o.key in checked_keys),
                outfits[0].key,
            )

        self._suppress_from_toggle = True
        # Wrap into columns so checkboxes stay inside the window.
        cols = self._from_check_columns()
        for c in range(max(cols, 3)):
            self.from_checks_frame.grid_columnconfigure(
                c, weight=1 if c < cols else 0, uniform="from")
        for i, outfit in enumerate(outfits):
            r, c = divmod(i, cols)
            cell = ctk.CTkFrame(self.from_checks_frame, fg_color="transparent")
            cell.grid(row=r, column=c, sticky="ew", padx=(0, 10), pady=2)
            var = tk.BooleanVar(value=(outfit.key in checked_keys))
            reason = self._incomplete.get(outfit.key)
            label = self._outfit_menu_label(outfit)
            cb = ctk.CTkCheckBox(
                cell,
                text=from_checkbox_label(
                    outfit,
                    incomplete=bool(reason),
                    focused=False,
                    base_label=label,
                ),
                variable=var,
                command=lambda o=outfit: self._on_from_check_toggled(o),
            )
            cb.pack(side="left", anchor="w")
            if reason:
                self._bind_tooltip(cb, reason)
            self._from_checks.append({
                "outfit": outfit,
                "var": var,
                "cb": cb,
                "base_label": label,
            })
            if outfit.key not in self._outfit_display_names:
                self._outfit_display_names[outfit.key] = (
                    self._name_seed_for(outfit.key) or label)
            if outfit.key not in self._outfit_to_choice:
                self._outfit_to_choice[outfit.key] = (
                    self._outfit_menu_label(outfit))
        self._suppress_from_toggle = False
        self._active_source_key = pick_key
        self._apply_source_selection_ui()

    def _from_check_columns(self) -> int:
        """How many checkbox columns fit in the current window width."""
        try:
            width = int(self.winfo_width())
        except tk.TclError:
            width = 0
        if width < 200:
            width = 960  # default / pre-map fallback
        # ~240px per checkbox column (label + padding).
        return max(1, min(3, (width - 100) // 240))

    def _on_from_check_toggled(self, outfit: Outfit) -> None:
        if self._suppress_from_toggle:
            return
        row = next(
            (r for r in self._from_checks if r["outfit"].key == outfit.key),
            None,
        )
        if row is None:
            return
        checked = bool(row["var"].get())
        self._persist_active_name()
        if self._active_source_key is not None:
            self._outfit_to_choice[self._active_source_key] = self.to_var.get()
        if checked:
            # Focus this row's Convert-to settings; keep other ticks.
            self._active_source_key = outfit.key
        elif self._active_source_key != outfit.key:
            # Clicking another already-ticked box toggles it off briefly —
            # treat that as "edit this slot" and keep it ticked.
            self._suppress_from_toggle = True
            row["var"].set(True)
            self._suppress_from_toggle = False
            self._active_source_key = outfit.key
        else:
            # Untick the focused slot for real.
            other = next(
                (r["outfit"].key for r in self._from_checks
                 if r["outfit"].key != outfit.key and bool(r["var"].get())),
                None,
            )
            self._active_source_key = other
        self._apply_source_selection_ui()

    def _apply_source_selection_ui(self) -> None:
        active = self._active_source_key
        checked = self._checked_source_outfits()
        if active is not None and not any(
                o.key == active for o in checked):
            active = checked[0].key if checked else None
            self._active_source_key = active

        for row in self._from_checks:
            row["cb"].configure(state="normal")

        if not checked:
            self.to_menu.configure(state="disabled")
            self._sync_convert_button()
            self._sync_name_ui()
            return

        if active is None:
            self._active_source_key = checked[0].key
            active = self._active_source_key

        self.to_menu.configure(state="normal")
        self._sync_convert_button()
        to_choice = self._outfit_to_choice.get(active)
        if to_choice and to_choice.startswith("Delete"):
            to_choice = DELETE_ACTION
        labels = self._to_menu_values()
        if to_choice in labels:
            self.to_var.set(to_choice)
        else:
            src = self._selected_source_outfit()
            self.to_var.set(
                self._outfit_menu_label(src) if src else labels[0])
            if src is not None:
                self._outfit_to_choice[src.key] = self.to_var.get()
        self._refresh_from_focus_labels()
        self._load_active_name()
        self._sync_name_ui()

    def _refresh_from_focus_labels(self) -> None:
        """Show ▸ on the focused From row; keep incomplete color when needed."""
        active = self._active_source_key
        for row in self._from_checks:
            outfit = row["outfit"]
            reason = self._incomplete.get(outfit.key)
            focused = outfit.key == active
            text = from_checkbox_label(
                outfit,
                incomplete=bool(reason),
                focused=focused,
                base_label=row.get("base_label") or self._outfit_menu_label(
                    outfit),
            )
            kwargs: dict = {"text": text}
            if reason:
                kwargs["text_color"] = INCOMPLETE_COLOR
            elif focused:
                kwargs["text_color"] = FOCUS_COLOR
            else:
                kwargs["text_color"] = ("gray10", "gray90")
            try:
                row["cb"].configure(**kwargs)
            except tk.TclError:
                pass

    def _selected_source_outfit(self) -> Outfit | None:
        if self._active_source_key is None:
            return None
        for row in self._from_checks:
            if row["outfit"].key == self._active_source_key:
                return row["outfit"]
        return None

    def _checked_source_outfits(self) -> list[Outfit]:
        return [
            r["outfit"] for r in self._from_checks if bool(r["var"].get())
        ]

    def _name_seed_for(self, key: str) -> str:
        return (
            self._names_by_outfit_key.get(key)
            or self._name_generic
            or self._suggested_outfit_name
        )

    def _persist_active_name(self) -> None:
        key = self._active_source_key
        if key is None:
            return
        if getattr(self, "_filling_name", False):
            return
        self._outfit_display_names[key] = self.outfit_name_var.get()
        self._outfit_name_edited[key] = bool(self._name_user_edited)

    def _load_active_name(self) -> None:
        key = self._active_source_key
        if key is None:
            return
        name = self._outfit_display_names.get(key, self._suggested_outfit_name)
        self._filling_name = True
        self.outfit_name_var.set(name)
        self._filling_name = False
        self._name_user_edited = bool(self._outfit_name_edited.get(key, False))

    def _choice_for_outfit(self, outfit: Outfit) -> str:
        choice = self._outfit_to_choice.get(
            outfit.key, self._outfit_menu_label(outfit))
        if choice.startswith("Delete"):
            return DELETE_ACTION
        return choice

    def _collect_ops(self) -> list[OutfitOp]:
        """Build ops for every ticked From outfit using its Convert-to choice."""
        self._persist_active_name()
        if self._active_source_key is not None:
            self._outfit_to_choice[self._active_source_key] = self.to_var.get()

        ops: list[OutfitOp] = []
        allow_delete = self._delete_action_available()
        for outfit in self._checked_source_outfits():
            choice = self._choice_for_outfit(outfit)
            if choice.startswith("Delete"):
                if allow_delete:
                    ops.append(OutfitOp(source=outfit, target=None))
                else:
                    ops.append(OutfitOp(source=outfit, target=outfit))
                continue
            target = self._outfit_from_menu_label(choice)
            if target is None:
                continue
            ops.append(OutfitOp(source=outfit, target=target))
        return ops

    def _on_set_name_toggled(self):
        if self.set_name_var.get() and not self._name_user_edited:
            key = self._active_source_key
            suggested = self._suggested_outfit_name
            if key and not self._outfit_name_edited.get(key):
                self.outfit_name_var.set(
                    self._outfit_display_names.get(key, suggested))
                self._name_user_edited = False
        self._sync_name_ui()
        self._save_settings()

    def _paint_outfit_name(self) -> None:
        """Match the costume-names box: a leading color tag tints the text."""
        entry = getattr(self, "outfit_name_entry", None)
        if entry is None:
            return
        color = preview_hex_for_name(self.outfit_name_var.get())
        try:
            entry.configure(
                text_color=color or self._outfit_name_default_color)
        except tk.TclError:
            pass

    def _on_outfit_name_typed(self, *_args):
        self._paint_outfit_name()
        if not getattr(self, "outfit_name_entry", None):
            return
        if getattr(self, "_filling_name", False):
            return
        self._name_user_edited = True
        key = self._active_source_key
        if key is not None:
            self._outfit_name_edited[key] = True
            self._outfit_display_names[key] = self.outfit_name_var.get()

    def _set_name_entry_enabled(self, enabled: bool, *, placeholder: str):
        # CTkEntry only accepts placeholder/text changes while normal.
        self.outfit_name_entry.configure(state="normal")
        self.outfit_name_entry.configure(placeholder_text=placeholder)
        if not enabled:
            self.outfit_name_entry.configure(state="disabled")
        self._paint_outfit_name()

    def _sync_name_ui(self):
        # Name applies to the focused From row's Convert-to target only.
        active = self._selected_source_outfit()
        checked = self._checked_source_outfits()
        choice = self._choice_for_outfit(active) if active else ""
        name_target = active_convert_name_target(
            active, choice, resolve_target=self._outfit_from_menu_label)
        supported = name_target is not None
        converting = bool(checked)
        active_delete = self._is_delete_target()

        if not supported:
            self.set_name_cb.configure(
                state="disabled", text="Set in-game outfit name")
            self._set_name_entry_enabled(
                False, placeholder="In-game outfit name")
            if active_delete and self._delete_action_available():
                self.name_hint.configure(
                    text="Delete strips this slot; other ticked outfits "
                         "still convert.")
            elif active is not None and converting:
                dest_outfit = None if (choice or "").startswith("Delete") else (
                    self._outfit_from_menu_label(choice))
                if uses_shared_name_pack(dest_outfit):
                    self.name_hint.configure(text=SHARED_NAME_PACK_HINT)
                else:
                    dest = "(Delete)" if dest_outfit is None else dest_outfit.name
                    self.name_hint.configure(text=f"{dest} can't be renamed")
            else:
                self.name_hint.configure(text="")
            return

        self.set_name_cb.configure(
            state="normal" if converting else "disabled")
        self.set_name_cb.configure(
            text=f"Set in-game name for {name_target.name}")
        can_edit = bool(self.set_name_var.get() and converting)
        self._set_name_entry_enabled(
            can_edit,
            placeholder=f"In-game name for {name_target.name}")
        self.name_hint.configure(text="")

    def _refresh_suggested_name(self):
        if not self.loaded:
            self._suggested_outfit_name = ""
            self._names_by_outfit_key = {}
            self._name_generic = ""
            self._outfit_display_names.clear()
            self._outfit_name_edited.clear()
            self._outfit_to_choice.clear()
            self._filling_name = True
            self.outfit_name_var.set("")
            self._filling_name = False
            self._name_user_edited = False
            return
        primary = next(
            (m for m in self.loaded if not m.analysis.modinfo.addonfor),
            self.loaded[0])
        fallback = package_label(primary.analysis, primary.source)
        by_key = primary.analysis.english_names_by_outfit_key()
        generic = primary.analysis.modinfo.name.strip() or fallback
        self._names_by_outfit_key = by_key
        self._name_generic = generic
        # The field for one outfit. Other rows keep their own file, or the
        # mod name — not this string.
        focused = self._selected_source_outfit()
        focused_key = focused.key if focused is not None else None
        self._suggested_outfit_name = (
            by_key.get(focused_key or "", "") or generic)
        for outfit in self._convertible_source_outfits():
            self._outfit_display_names.setdefault(
                outfit.key, by_key.get(outfit.key) or generic)
            self._outfit_name_edited.setdefault(outfit.key, False)
        self._load_active_name()

    def _close_loaded(self):
        close_loaded([
            LoadedPackage(source=m.source, analysis=m.analysis)
            for m in self.loaded
        ])
        self.loaded.clear()

    def _suggest_bundle_name(self) -> str:
        def _has_outfits(m) -> bool:
            return bool(m.analysis.outfits or m.analysis.claire_outfits)

        mains = [m for m in self.loaded if _has_outfits(m)]
        if not mains:
            mains = [m for m in self.loaded if not m.analysis.modinfo.addonfor]
        if mains:
            return package_label(mains[0].analysis, mains[0].source)
        for m in self.loaded:
            if m.analysis.modinfo.addonfor:
                return m.analysis.modinfo.addonfor
        return package_label(self.loaded[0].analysis, self.loaded[0].source)

    def _convertible(self) -> bool:
        return bool(
            self.loaded
            and self._convertible_source_outfits()
            and self._checked_source_outfits()
        )

    # ---------------------------------------------------------------- input

    def _on_drop(self, event):
        paths = [Path(p) for p in self.tk.splitlist(event.data)]
        if paths:
            self._load_paths(paths)

    def _browse_folder(self):
        path = tk.filedialog.askdirectory(title="Select mod folder")
        if path:
            self._load_paths([Path(path)])

    def _browse_archive(self):
        paths = tk.filedialog.askopenfilenames(
            title="Select mod archive(s)",
            filetypes=[("Mod archives", "*.zip *.rar *.7z"), ("All files", "*.*")])
        if paths:
            self._load_paths([Path(p) for p in paths])

    def _browse_output(self):
        path = tk.filedialog.askdirectory(title="Select output folder")
        if path:
            self.out_var.set(path)
            self._save_settings()

    def _load_paths(self, paths: list[Path]):
        if self._busy or not paths:
            return
        self._busy = True
        self._sync_convert_button()
        self.drop_label.configure(
            text="Reading…", anchor="w", justify="left",
            font=self._loaded_headline_font)
        self.path_label.grid_remove()
        threading.Thread(target=self._analyze_worker_safe, args=(paths,),
                         daemon=True).start()

    def _analyze_worker(self, paths: list[Path]):
        packages, errors, infos = analyze_paths(paths)
        loaded = [LoadedMod.from_package(p) for p in packages]
        self._ui_after(self._analysis_done, loaded, errors, infos)

    def _analyze_worker_safe(self, paths: list[Path]):
        try:
            self._analyze_worker(paths)
        except Exception as e:
            self._ui_after(
                self._analysis_done, [], [f"Unexpected error: {e!r}"], [])

    def _analysis_done(
        self,
        loaded: list[LoadedMod],
        errors: list[str],
        infos: list[str] | None = None,
    ):
        self._busy = False
        self._close_loaded()
        self.loaded = loaded
        self._reset_progress_ui()
        infos = infos or []

        if not loaded:
            self._show_idle_convert_ui()
            msg = "\n".join(errors) if errors else "No valid mods found."
            tk.messagebox.showerror("Could not load mod", msg)
            return

        self.drop_label.configure(
            anchor="w", justify="left", font=self._loaded_headline_font)
        self.path_label.grid_remove()
        self.facts_row.grid()

        if len(loaded) == 1:
            self._show_single_analysis(loaded[0])
        else:
            self._show_multi_analysis(loaded)

        # Fresh convert state — idle preview choices do not carry over.
        self._outfit_display_names.clear()
        self._outfit_name_edited.clear()
        self._outfit_to_choice.clear()
        self._active_source_key = None
        self._refresh_suggested_name()
        self._refresh_to_menu()
        self._sync_game_build()
        self._rebuild_from_checks(select_first=True)
        self._apply_ui_mode()

        if errors:
            tk.messagebox.showwarning(
                "Some mods skipped",
                "Could not load every selected file:\n\n" + "\n".join(errors[:12]))
        elif infos:
            self.path_label.grid()
            self.path_label.configure(
                text=infos[0], anchor="w", justify="left")

    def _show_single_analysis(self, item: LoadedMod):
        analysis = item.analysis
        self.info_rows["mod"].configure(
            text=format_mod_row(analysis, item.source))
        outfit_text, outfit_ok = format_outfit_row(analysis)
        self.info_rows["outfit"].configure(
            text=outfit_text,
            text_color=OK_COLOR if outfit_ok else WARN_COLOR)
        self._show_game_label(analysis.game_label)

    def _show_multi_analysis(self, loaded: list[LoadedMod]):
        names = [package_label(m.analysis, m.source) for m in loaded]
        preview = ", ".join(names[:4])
        if len(names) > 4:
            preview += f", +{len(names) - 4} more"
        self.info_rows["mod"].configure(
            text=f"{len(loaded)} mods: {preview}")
        outfit_text, outfit_ok = format_multi_outfit_row(loaded)
        self.info_rows["outfit"].configure(
            text=outfit_text,
            text_color=OK_COLOR if outfit_ok else WARN_COLOR)
        self._show_game_label(game_label_for(
            m.analysis for m in loaded))

    def _show_game_label(self, text: str) -> None:
        self.info_rows["game"].configure(
            text=text,
            text_color=OK_COLOR if text != "-" else DIM)

    def _sync_game_build(self) -> None:
        choice = game_build_for(m.analysis for m in self.loaded)
        self.game_var.set(choice)
        self.game_menu.configure(state="normal")
        self._sync_build_direction()

    # ------------------------------------------------------------- convert

    def _ensure_output(self) -> Path | None:
        out_dir = self.out_var.get().strip()
        if not out_dir:
            out_dir = str(default_output_dir())
            self.out_var.set(out_dir)
        out_path = Path(out_dir)
        try:
            out_path.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            tk.messagebox.showerror("Output folder",
                                    f"Cannot create output folder:\n{e}")
            return None
        self._save_settings()
        return out_path

    def _on_convert_click(self):
        if self._converting:
            self._request_cancel()
            return
        self._start_convert()

    def _request_cancel(self):
        if not self._converting:
            return
        request_cancel()
        self._sync_convert_button()
        self.status_label.configure(text="Cancelling...", text_color=DIM)

    def _sync_convert_button(self) -> None:
        if self._converting:
            if cancel_requested():
                self.convert_btn.configure(state="disabled", text="Cancelling...")
            else:
                self.convert_btn.configure(state="normal", text="Cancel")
            return
        if self._is_game_build_mode():
            can = bool(self.loaded and not self._busy)
            self.convert_btn.configure(
                state="normal" if can else "disabled", text="Convert")
            return
        checked = self._checked_source_outfits()
        can = bool(
            checked
            and self.loaded
            and not self._busy
            and self._convertible_source_outfits()
        )
        self.convert_btn.configure(
            state="normal" if can else "disabled", text="Convert")

    def _end_convert_ui(self) -> None:
        self._converting = False
        self._busy = False
        reset_cancel()
        self._sync_convert_button()

    def _discard_output(self, report) -> None:
        paths: list[Path] = []
        if isinstance(report, BatchReport):
            if report.output_zip is not None:
                paths.append(report.output_zip)
        elif report is not None:
            if getattr(report, "output_zip", None) is not None:
                paths.append(report.output_zip)
            if getattr(report, "output_folder", None) is not None:
                paths.append(report.output_folder)
        for path in paths:
            try:
                if path.is_file():
                    path.unlink()
                elif path.is_dir():
                    shutil.rmtree(path)
            except OSError:
                pass

    def _start_game_build_convert(self):
        if self._busy or not self.loaded:
            return
        out_path = self._ensure_output()
        if out_path is None:
            return
        chosen = self.game_var.get()
        if chosen not in GAME_BUILDS:
            chosen = GAME_BUILDS[0]
        loaded = list(self.loaded)
        write_log = bool(self.settings.get("write_convert_log", True))
        tag_build_zip = bool(self.settings.get("tag_build_zip_name", True))
        tag_build_desc = bool(
            self.settings.get("tag_build_modinfo_description", True))
        blender_settings = {
            "use_blender": bool(self.settings.get("use_blender", True)),
            "blender_path": str(self.settings.get("blender_path") or ""),
        }
        bundle_name = self._suggest_bundle_name()
        reset_cancel()
        self._busy = True
        self._converting = True
        self._sync_convert_button()
        self._start_progress_ui()
        threading.Thread(
            target=self._game_build_worker_safe,
            args=(
                loaded, out_path, chosen, bundle_name, write_log,
                tag_build_zip, tag_build_desc, blender_settings,
            ),
            daemon=True).start()

    def _game_build_worker_safe(
        self, loaded, out_path: Path, game_build: str, bundle_name: str,
        write_log: bool, tag_build_zip: bool, tag_build_desc: bool,
        blender_settings: dict,
    ):
        try:
            self._game_build_worker(
                loaded, out_path, game_build, bundle_name, write_log,
                tag_build_zip, tag_build_desc, blender_settings)
        except Exception as e:
            self._ui_after(
                self._convert_failed, f"Unexpected error: {e!r}")

    def _game_build_worker(
        self, loaded, out_path: Path, game_build: str, bundle_name: str,
        write_log: bool, tag_build_zip: bool, tag_build_desc: bool,
        blender_settings: dict,
    ):
        def progress(msg: str):
            self._ui_after(self._on_progress_msg, msg)

        try:
            report = convert_game_builds(
                loaded, out_path,
                game_build=game_build,
                bundle_name=bundle_name,
                progress=progress,
                write_log=write_log,
                tag_build_zip_name=tag_build_zip,
                tag_build_modinfo_description=tag_build_desc,
                settings=blender_settings,
            )
            if cancel_requested():
                self._discard_output(report)
                raise ConversionCancelled("Convert cancelled.")
            self._ui_after(self._convert_done, report)
        except ConversionCancelled:
            self._ui_after(self._convert_cancelled)
        except (ConversionError, OSError) as e:
            self._ui_after(self._convert_failed, str(e))
        except Exception as e:
            self._ui_after(
                self._convert_failed, f"Unexpected error: {e!r}")

    def _start_convert(self):
        if self._is_game_build_mode():
            self._start_game_build_convert()
            return
        if self._busy or not self.loaded or not self._convertible():
            return
        out_path = self._ensure_output()
        if out_path is None:
            return
        self._persist_active_name()
        ops = self._collect_ops()
        if not ops:
            return
        chosen = self.game_var.get()
        if chosen not in GAME_BUILDS:
            chosen = GAME_BUILDS[0]

        converts = [op for op in ops if op.target is not None]
        namable_ops = [
            op for op in converts
            if is_convert_namable(op.target)
        ]
        outfit_display_names: dict[str, str] | None = None
        outfit_display_name = None
        if self.set_name_var.get() and namable_ops:
            # Ensure the focused row's typed name is stored before collection.
            self._persist_active_name()
            missing: list[str] = []
            names_by_source = dict(self._outfit_display_names)
            for op in namable_ops:
                assert op.target is not None
                text = (names_by_source.get(op.source.key) or "").strip()
                if not text:
                    missing.append(op.target.name)
            if missing:
                tk.messagebox.showwarning(
                    "Outfit name",
                    "Enter an in-game name for: "
                    + ", ".join(missing)
                    + "\n(focus each Convert-from row that targets them), "
                    "or uncheck \"Set in-game outfit name\".")
                return
            outfit_display_names = collect_display_names_by_target(
                namable_ops, names_by_source)

        package_target = converts[0].target if converts else ops[0].source
        assert package_target is not None

        # Snapshot UI-thread state before the worker starts (Tk vars are
        # not safe to read from background threads).
        loaded = list(self.loaded)
        tag_output = self._tag_zip_enabled()
        tag_modinfo_description = self._tag_description_enabled()
        tag_modinfo_name = False
        tag_marker = tag_marker_for(self.settings, package_target)
        strip_tags = strip_tag_markers(self.settings)
        bundle_name = self._suggest_bundle_name()
        source_outfit = ops[0].source
        write_log = bool(self.settings.get("write_convert_log", True))
        tag_build_zip = bool(self.settings.get("tag_build_zip_name", True))
        tag_build_desc = bool(
            self.settings.get("tag_build_modinfo_description", True))
        blender_settings = {
            "use_blender": bool(self.settings.get("use_blender", True)),
            "blender_path": str(self.settings.get("blender_path") or ""),
        }

        reset_cancel()
        self._busy = True
        self._converting = True
        self._sync_convert_button()
        self._start_progress_ui()
        threading.Thread(
            target=self._convert_worker_safe,
            args=(
                loaded, ops, source_outfit, package_target, out_path,
                outfit_display_name, outfit_display_names, tag_output,
                tag_modinfo_description, tag_modinfo_name,
                tag_marker, strip_tags, bundle_name, write_log,
                chosen, tag_build_zip, tag_build_desc, blender_settings,
            ),
            daemon=True).start()

    def _ui_after(self, callback, *args):
        """Schedule a UI callback; no-op if the window was closed."""
        if self._closed:
            return

        def _run():
            if self._closed:
                return
            try:
                callback(*args)
            except tk.TclError:
                pass

        try:
            self.after(0, _run)
        except tk.TclError:
            pass

    def _start_progress_ui(self):
        self.status_label.configure(text="Converting...", text_color=DIM)
        self.progress_bar.configure(progress_color=CONVERT)
        self.progress_bar.set(0)
        self.progress_bar.start()

    def _reset_progress_ui(self):
        try:
            self.progress_bar.stop()
        except Exception:
            pass
        self.progress_bar.set(0)
        self.status_label.configure(text="")

    def _convert_worker_safe(
        self, loaded, ops, source_outfit, package_target, out_path: Path,
        outfit_display_name: str | None,
        outfit_display_names: dict[str, str] | None,
        tag_output: bool, tag_modinfo_description: bool, tag_modinfo_name: bool,
        tag_marker: str,
        strip_tags: list[str], bundle_name: str,
        write_log: bool,
        game_build: str,
        tag_build_zip: bool,
        tag_build_desc: bool,
        blender_settings: dict,
    ):
        try:
            self._convert_worker(
                loaded, ops, source_outfit, package_target, out_path,
                outfit_display_name, outfit_display_names, tag_output,
                tag_modinfo_description, tag_modinfo_name,
                tag_marker, strip_tags, bundle_name, write_log,
                game_build, tag_build_zip, tag_build_desc, blender_settings)
        except Exception as e:
            self._ui_after(
                self._convert_failed, f"Unexpected error: {e!r}")

    def _convert_worker(
        self, loaded, ops, source_outfit, package_target, out_path: Path,
        outfit_display_name: str | None,
        outfit_display_names: dict[str, str] | None,
        tag_output: bool, tag_modinfo_description: bool, tag_modinfo_name: bool,
        tag_marker: str,
        strip_tags: list[str], bundle_name: str,
        write_log: bool,
        game_build: str,
        tag_build_zip: bool,
        tag_build_desc: bool,
        blender_settings: dict,
    ):
        def progress(msg: str):
            self._ui_after(self._on_progress_msg, msg)

        try:
            report = convert_loaded(
                loaded, source_outfit, package_target, out_path,
                outfit_display_name=outfit_display_name,
                tag_output=tag_output,
                tag_modinfo_description=tag_modinfo_description,
                tag_modinfo_name=tag_modinfo_name,
                tag_marker=tag_marker,
                strip_tags=strip_tags,
                bundle_name=bundle_name,
                mod_label=package_label,
                progress=progress,
                ops=ops,
                write_log=write_log,
                outfit_display_names=outfit_display_names,
                game_build=game_build,
                tag_build_zip_name=tag_build_zip,
                tag_build_modinfo_description=tag_build_desc,
                settings=blender_settings,
            )
            if cancel_requested():
                self._discard_output(report)
                raise ConversionCancelled("Convert cancelled.")
            self._ui_after(self._convert_done, report)
        except ConversionCancelled:
            self._ui_after(self._convert_cancelled)
        except (ConversionError, OSError) as e:
            self._ui_after(self._convert_failed, str(e))
        except Exception as e:
            self._ui_after(
                self._convert_failed, f"Unexpected error: {e!r}")

    def _on_progress_msg(self, msg: str):
        if not self._converting or cancel_requested():
            return
        short = msg if len(msg) <= 72 else msg[:69] + "..."
        self.status_label.configure(text=short, text_color=DIM)

    def _convert_cancelled(self):
        self._end_convert_ui()
        self._reset_progress_ui()
        self.status_label.configure(text="Convert cancelled", text_color=DIM)

    def _convert_failed(self, msg: str):
        self._end_convert_ui()
        self._reset_progress_ui()
        tk.messagebox.showerror("Conversion failed", msg)

    def _convert_done(self, report=None):
        self._end_convert_ui()
        try:
            self.progress_bar.stop()
        except Exception:
            pass
        self.progress_bar.set(1)
        self.progress_bar.configure(progress_color=OK_COLOR)

        out, warnings = collect_warnings(report)

        if out is not None:
            if warnings:
                status = f"Conversion completed (warnings) → {out.name}"
            else:
                status = f"Conversion completed → {out.name}"
            if len(status) > 72:
                status = status[:69] + "..."
            self.status_label.configure(text=status, text_color=OK_COLOR)

            if self._skip_completion_dialog():
                return

            msg = f"Saved:\n{out}"
            if bool(self.settings.get("write_convert_log", True)):
                if isinstance(report, BatchReport):
                    msg += (
                        "\n\nIncludes convert.log at the zip root "
                        "(covers all package folders)."
                    )
                else:
                    msg += "\n\nIncludes convert.log inside the package."
            if warnings:
                msg += "\n\nWarnings:\n" + "\n".join(f"• {w}" for w in warnings[:12])
                if len(warnings) > 12:
                    msg += f"\n… +{len(warnings) - 12} more"
                patch_skips = count_patch_skips(warnings)
                if patch_skips:
                    msg += f"\n\nBinary path patch skips/notes: {patch_skips}"
            msg += "\n\nOpen the output folder?"
            title = "Converted with warnings" if warnings else "Converted"
            ask = (tk.messagebox.askokcancel if warnings
                   else tk.messagebox.askyesno)
            if ask(title, msg):
                try:
                    os.startfile(str(out.parent))  # type: ignore[attr-defined]
                except (AttributeError, OSError):
                    pass
        else:
            self.status_label.configure(
                text="Conversion completed", text_color=OK_COLOR)

    def _on_close(self):
        if self._busy:
            if not tk.messagebox.askokcancel(
                    "Busy",
                    "A load or convert is still running.\n"
                    "Close anyway? Output may be incomplete."):
                return
        if self._settings_persist is not None:
            try:
                self._settings_persist()
            except Exception:
                pass
        self._save_settings()
        self._close_loaded()
        self._closed = True
        self.destroy()


def run():
    app = App()
    app.mainloop()
