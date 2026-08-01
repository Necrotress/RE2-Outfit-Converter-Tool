"""customtkinter GUI for the RE2 Outfit Converter."""

from __future__ import annotations

import os
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
from .analyzer import AnalysisResult
from .archive import ModSource
from .gui_analysis import (
    collect_warnings,
    count_patch_skips,
    format_mod_row,
    format_multi_outfit_row,
    format_outfit_row,
)
from .gui_name_pack import open_name_pack_dialog
from .gui_settings import open_settings_dialog
from .gui_workers import analyze_paths, convert_loaded
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
from .outfits import CONVERTIBLE_OUTFITS, Outfit, is_convertible_outfit
from .reports import BatchReport, ConversionError
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


class App(_Root):
    def __init__(self):
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")
        super().__init__()

        self.title(f"RE2 Remake Outfit Converter  v{__version__}")
        self.minsize(780, 620)
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
        self._closed = False
        self._filling_name = False
        self._suggested_outfit_name = ""
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
        self.grid_rowconfigure(3, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=14, pady=(10, 0))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            header,
            text=f"RE2 Remake Outfit Converter  v{__version__}",
            font=ctk.CTkFont(size=14, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="w")
        header_btns = ctk.CTkFrame(header, fg_color="transparent")
        header_btns.grid(row=0, column=1, sticky="e")
        ctk.CTkButton(
            header_btns, text="Costume names", width=120,
            command=self._open_name_pack,
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            header_btns, text="Settings", width=96,
            command=self._open_settings,
        ).pack(side="left")

        top = ctk.CTkFrame(self, corner_radius=12)
        top.grid(row=1, column=0, sticky="nsew", padx=14, pady=(8, 4))
        top.grid_columnconfigure(0, weight=1)
        top.grid_rowconfigure(0, weight=1)

        drop_text = ("Drop mod folder(s) or .zip / .rar / .7z archive(s) here"
                     if HAS_DND else "Select a mod folder or archive")
        self.drop_label = ctk.CTkLabel(
            top, text=drop_text, font=ctk.CTkFont(size=15, weight="bold"),
            height=48)
        self.drop_label.grid(row=0, column=0, sticky="nsew", padx=14, pady=(10, 0))

        self.path_label = ctk.CTkLabel(top, text="No mod loaded", text_color=DIM)
        self.path_label.grid(row=1, column=0, sticky="ew", padx=14)

        btns = ctk.CTkFrame(top, fg_color="transparent")
        btns.grid(row=2, column=0, pady=(4, 10))
        ctk.CTkButton(btns, text="Browse Folder...", width=140,
                      command=self._browse_folder).pack(side="left", padx=6)
        ctk.CTkButton(btns, text="Browse Archive...", width=140,
                      command=self._browse_archive).pack(side="left", padx=6)

        mid = ctk.CTkFrame(self, corner_radius=12)
        mid.grid(row=2, column=0, sticky="ew", padx=14, pady=4)
        mid.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(mid, text="ANALYSIS", font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=DIM).grid(row=0, column=0, columnspan=2,
                                          sticky="w", padx=14, pady=(8, 2))

        self.info_rows = {}
        for i, (key, label) in enumerate([
            ("mod", "Mod"),
            ("outfit", "Outfits"),
        ], start=1):
            ctk.CTkLabel(mid, text=label, width=140, anchor="w",
                         text_color=DIM).grid(row=i, column=0, sticky="nw",
                                              padx=(14, 8), pady=2)
            val = ctk.CTkLabel(mid, text="-", anchor="w", justify="left")
            val.grid(row=i, column=1, sticky="ew", padx=(0, 14), pady=2)
            self.info_rows[key] = val

        out = ctk.CTkFrame(mid, fg_color="transparent")
        out.grid(row=3, column=0, columnspan=2, sticky="ew", padx=14, pady=(8, 10))
        out.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(out, text="Output folder", width=140, anchor="w",
                     text_color=DIM).grid(row=0, column=0, sticky="w")
        self.out_var = tk.StringVar(value=initial_output_dir(self.settings))
        self.out_entry = ctk.CTkEntry(out, textvariable=self.out_var)
        self.out_entry.grid(row=0, column=1, sticky="ew", padx=(8, 6))
        ctk.CTkButton(out, text="...", width=36,
                      command=self._browse_output).grid(row=0, column=2)

        bottom = ctk.CTkFrame(self, corner_radius=12)
        bottom.grid(row=3, column=0, sticky="nsew", padx=14, pady=(4, 12))
        bottom.grid_columnconfigure(0, weight=1)

        conv = ctk.CTkFrame(bottom, fg_color="transparent")
        conv.grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 4))
        conv.grid_columnconfigure(0, weight=1)

        self.from_label = ctk.CTkLabel(conv, text="Convert from", anchor="w")
        self.from_label.grid(row=0, column=0, sticky="w")

        # Sizes to content and wraps; avoids a tall empty scroll area.
        self.from_checks_frame = ctk.CTkFrame(conv, fg_color="transparent")
        self.from_checks_frame.grid(row=1, column=0, sticky="ew", pady=(4, 2))

        to_row = ctk.CTkFrame(conv, fg_color="transparent")
        to_row.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        ctk.CTkLabel(to_row, text="Convert to", anchor="w", width=100).pack(
            side="left")
        to_labels = self._to_menu_values()
        self.to_var = tk.StringVar(value=to_labels[0] if to_labels else "-")
        self.to_menu = ctk.CTkOptionMenu(
            to_row, variable=self.to_var,
            values=to_labels or ["-"], width=260,
            state="disabled",
            command=self._on_target_outfit_changed)
        self.to_menu.pack(side="left", padx=(8, 0))

        opts = ctk.CTkFrame(bottom, fg_color="transparent")
        opts.grid(row=1, column=0, sticky="ew", padx=14, pady=(6, 4))
        opts.grid_columnconfigure(0, weight=1)

        name_row = ctk.CTkFrame(opts, fg_color="transparent")
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
            "Works for Elza, Noir, and Military on Convert.\n"
            "Jacket / Tank Top / Classic Jacket / Classic Tank Top\n"
            "share one name file — use Costume names instead.")

        self.outfit_name_var = tk.StringVar(value="")
        self.outfit_name_entry = ctk.CTkEntry(
            name_row, textvariable=self.outfit_name_var,
            placeholder_text="In-game outfit name", height=28,
            state="disabled")
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
            command=self._start_convert)
        self.convert_btn.grid(row=2, column=0, sticky="ew", padx=14, pady=(8, 8))

        progress_row = ctk.CTkFrame(bottom, fg_color="transparent")
        progress_row.grid(row=3, column=0, sticky="ew", padx=14, pady=(0, 12))
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

    def _skip_convert_confirm(self) -> bool:
        return bool(self.settings.get("skip_convert_confirm", False))

    def _skip_completion_dialog(self) -> bool:
        return bool(self.settings.get("skip_completion_dialog", False))

    def _tag_output_enabled(self) -> bool:
        return bool(self.settings.get("tag_output", True))

    def _restore_geometry(self):
        geo = str(self.settings.get("window_geometry", "")).strip()
        if geo:
            try:
                self.geometry(geo)
                return
            except tk.TclError:
                pass
        self.geometry("820x680")

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
            width = max(240, self.winfo_width() - 200)
        except tk.TclError:
            return
        if abs(width - self._last_wrap_width) < 24:
            return
        self._last_wrap_width = width
        for label in self.info_rows.values():
            try:
                label.configure(wraplength=width)
            except tk.TclError:
                pass

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

        def on_created(path: Path):
            self.out_var.set(str(path.parent))
            self._save_settings()
            if self._skip_completion_dialog():
                self.status_label.configure(
                    text=f"Name pack created: {path.name}",
                    text_color=OK_COLOR)
            else:
                tk.messagebox.showinfo(
                    "Costume names",
                    f"Created Fluffy name pack:\n{path}\n\n"
                    "Enable this mod in Fluffy to apply the costume-menu "
                    "names. Use only one such name pack at a time.")

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

    def _outfit_from_menu_label(self, label: str):
        return outfit_from_menu_label(self.settings, label)

    def _delete_action_available(self) -> bool:
        """Delete only makes sense when the pack has more than one outfit slot."""
        if not self.loaded:
            return False
        return len(self._convertible_source_outfits()) > 1

    def _to_menu_values(self) -> list[str]:
        labels = list(outfit_menu_labels(self.settings))
        if self._delete_action_available():
            if DELETE_ACTION not in labels:
                labels.append(DELETE_ACTION)
        return labels

    def _sanitize_delete_choices(self) -> None:
        """Clear stored Delete targets when Delete is not offered."""
        if self._delete_action_available():
            return
        for key, choice in list(self._outfit_to_choice.items()):
            if not str(choice).startswith("Delete"):
                continue
            outfit = next(
                (o for o in CONVERTIBLE_OUTFITS if o.key == key), None)
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
            for o in m.analysis.claire_outfits:
                if is_convertible_outfit(o):
                    detected.add(o.key)
        return [o for o in CONVERTIBLE_OUTFITS if o.key in detected]

    def _from_check_outfits(self) -> list[Outfit]:
        """Outfits shown as From checkboxes (detected, or all while idle)."""
        if not self.loaded:
            return list(CONVERTIBLE_OUTFITS)
        detected = self._convertible_source_outfits()
        # Keep the same strip layout even when nothing is convertible.
        return detected if detected else list(CONVERTIBLE_OUTFITS)

    def _show_idle_convert_ui(self) -> None:
        """Idle / no-mod convert strip — same layout, clickable, convert locked."""
        self._incomplete = {}
        self._outfit_display_names.clear()
        self._outfit_name_edited.clear()
        self._outfit_to_choice.clear()
        self._active_source_key = None
        self._suggested_outfit_name = ""
        self._filling_name = True
        self.outfit_name_var.set("")
        self._filling_name = False
        self._name_user_edited = False
        self._refresh_to_menu()
        self._rebuild_from_checks(select_first=True)

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
                    self._suggested_outfit_name or label)
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
            self.convert_btn.configure(state="disabled")
            self._sync_name_ui()
            return

        if active is None:
            self._active_source_key = checked[0].key
            active = self._active_source_key

        self.to_menu.configure(state="normal")
        can_convert = bool(
            self.loaded
            and not self._busy
            and self._convertible_source_outfits()
        )
        self.convert_btn.configure(
            state="normal" if can_convert else "disabled")
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

    def _on_outfit_name_typed(self, *_args):
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
        self._suggested_outfit_name = (
            primary.analysis.suggested_outfit_display_name(fallback)
            or fallback)
        # Seed per-outfit names with the mod suggestion (separate slots can diverge).
        for outfit in self._convertible_source_outfits():
            self._outfit_display_names.setdefault(
                outfit.key, self._suggested_outfit_name)
            self._outfit_name_edited.setdefault(outfit.key, False)
        self._load_active_name()

    def _close_loaded(self):
        close_loaded([
            LoadedPackage(source=m.source, analysis=m.analysis)
            for m in self.loaded
        ])
        self.loaded.clear()

    def _suggest_bundle_name(self) -> str:
        mains = [m for m in self.loaded if m.analysis.claire_outfits]
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
        self.convert_btn.configure(state="disabled")
        if len(paths) == 1:
            self.path_label.configure(text=str(paths[0]))
        else:
            self.path_label.configure(text=f"{len(paths)} items selected...")
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
            self.path_label.configure(text="No mod loaded")
            for key in self.info_rows:
                self.info_rows[key].configure(text="-")
            self._show_idle_convert_ui()
            msg = "\n".join(errors) if errors else "No valid mods found."
            tk.messagebox.showerror("Could not load mod", msg)
            return

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
        self._rebuild_from_checks(select_first=True)
        if not self._convertible_source_outfits():
            self.convert_btn.configure(state="disabled")

        if errors:
            tk.messagebox.showwarning(
                "Some mods skipped",
                "Could not load every selected file:\n\n" + "\n".join(errors[:12]))
        elif infos:
            self.path_label.configure(
                text=self.path_label.cget("text") + "  ·  " + infos[0])

    def _show_single_analysis(self, item: LoadedMod):
        analysis = item.analysis
        source = item.source
        self.path_label.configure(text=str(source.original))
        self.info_rows["mod"].configure(text=format_mod_row(analysis, source))
        outfit_text, outfit_ok = format_outfit_row(analysis)
        self.info_rows["outfit"].configure(
            text=outfit_text,
            text_color=OK_COLOR if outfit_ok else WARN_COLOR)

    def _show_multi_analysis(self, loaded: list[LoadedMod]):
        mains = [m for m in loaded if not m.analysis.modinfo.addonfor]
        addons = [m for m in loaded if m.analysis.modinfo.addonfor]
        names = [package_label(m.analysis, m.source) for m in loaded]
        self.path_label.configure(
            text=f"{len(loaded)} mods loaded  ·  "
                 f"{len(mains)} main, {len(addons)} addon")
        preview = ", ".join(names[:4])
        if len(names) > 4:
            preview += f", +{len(names) - 4} more"
        self.info_rows["mod"].configure(
            text=f"{len(loaded)} mods: {preview}")
        outfit_text, outfit_ok = format_multi_outfit_row(loaded)
        self.info_rows["outfit"].configure(
            text=outfit_text,
            text_color=OK_COLOR if outfit_ok else WARN_COLOR)

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

    def _start_convert(self):
        if self._busy or not self.loaded or not self._convertible():
            return
        out_path = self._ensure_output()
        if out_path is None:
            return
        self._persist_active_name()
        ops = self._collect_ops()
        if not ops:
            return

        converts = [op for op in ops if op.target is not None]
        identity = [
            op for op in converts if op.source.key == op.target.key  # type: ignore[union-attr]
        ]
        if identity and not self._skip_convert_confirm():
            names = ", ".join(op.source.name for op in identity)
            if not tk.messagebox.askokcancel(
                    "Confirm conversion",
                    f"Convert on {names} to itself?\n\n"
                    "Face and hair will be isolated so this mod won't "
                    "conflict with other Claire outfits."):
                return

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
        tag_output = self._tag_output_enabled()
        tag_marker = tag_marker_for(self.settings, package_target)
        strip_tags = strip_tag_markers(self.settings)
        bundle_name = self._suggest_bundle_name()
        source_outfit = ops[0].source
        write_log = bool(self.settings.get("write_convert_log", True))

        self._busy = True
        self.convert_btn.configure(state="disabled", text="Converting...")
        self._start_progress_ui()
        threading.Thread(
            target=self._convert_worker_safe,
            args=(
                loaded, ops, source_outfit, package_target, out_path,
                outfit_display_name, outfit_display_names, tag_output,
                tag_marker, strip_tags, bundle_name, write_log,
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
        tag_output: bool, tag_marker: str,
        strip_tags: list[str], bundle_name: str,
        write_log: bool,
    ):
        try:
            self._convert_worker(
                loaded, ops, source_outfit, package_target, out_path,
                outfit_display_name, outfit_display_names, tag_output,
                tag_marker, strip_tags, bundle_name, write_log)
        except Exception as e:
            self._ui_after(
                self._convert_failed, f"Unexpected error: {e!r}")

    def _convert_worker(
        self, loaded, ops, source_outfit, package_target, out_path: Path,
        outfit_display_name: str | None,
        outfit_display_names: dict[str, str] | None,
        tag_output: bool, tag_marker: str,
        strip_tags: list[str], bundle_name: str,
        write_log: bool,
    ):
        def progress(msg: str):
            self._ui_after(self._on_progress_msg, msg)

        try:
            report = convert_loaded(
                loaded, source_outfit, package_target, out_path,
                outfit_display_name=outfit_display_name,
                tag_output=tag_output,
                tag_marker=tag_marker,
                strip_tags=strip_tags,
                bundle_name=bundle_name,
                mod_label=package_label,
                progress=progress,
                ops=ops,
                write_log=write_log,
                outfit_display_names=outfit_display_names,
            )
            self._ui_after(self._convert_done, report)
        except (ConversionError, OSError) as e:
            self._ui_after(self._convert_failed, str(e))
        except Exception as e:
            self._ui_after(
                self._convert_failed, f"Unexpected error: {e!r}")

    def _on_progress_msg(self, msg: str):
        short = msg if len(msg) <= 72 else msg[:69] + "..."
        self.status_label.configure(text=short, text_color=DIM)

    def _convert_failed(self, msg: str):
        self._busy = False
        self.convert_btn.configure(
            state="normal" if self._convertible() else "disabled",
            text="Convert")
        self._reset_progress_ui()
        tk.messagebox.showerror("Conversion failed", msg)

    def _convert_done(self, report=None):
        self._busy = False
        self.convert_btn.configure(state="normal", text="Convert")
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
