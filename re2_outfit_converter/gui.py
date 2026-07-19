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
    format_characters,
    format_mod_row,
    format_multi_characters,
    format_outfit_row,
    mod_label,
)
from .gui_settings import open_settings_dialog
from .gui_workers import analyze_paths, convert_loaded
from .outfits import CONVERTIBLE_OUTFITS, is_convertible_outfit
from .reports import ConversionError
from .session import LoadedPackage, close_loaded
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
        self.minsize(760, 540)
        ctk.set_widget_scaling(1.0)
        ctk.set_window_scaling(1.0)
        icon = icon_path()
        if icon is not None:
            try:
                self.iconbitmap(str(icon))
            except tk.TclError:
                pass

        self.loaded: list[LoadedMod] = []
        self.settings = load_settings()
        self._busy = False
        self._suggested_outfit_name = ""
        self._name_user_edited = False
        self._settings_win: ctk.CTkToplevel | None = None
        self._settings_persist = None
        self._resize_after: str | None = None
        self._last_wrap_width = 0
        self._settings_write_warned = False

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
        self.grid_rowconfigure(1, weight=2)
        self.grid_rowconfigure(2, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=14, pady=(14, 0))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            header,
            text=f"RE2 Remake Outfit Converter  v{__version__}",
            font=ctk.CTkFont(size=14, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(
            header, text="Settings", width=96,
            command=self._open_settings,
        ).grid(row=0, column=1, sticky="e")

        top = ctk.CTkFrame(self, corner_radius=12)
        top.grid(row=1, column=0, sticky="nsew", padx=14, pady=(10, 6))
        top.grid_columnconfigure(0, weight=1)
        top.grid_rowconfigure(0, weight=1)

        drop_text = ("Drop mod folder(s) or .zip / .rar / .7z archive(s) here"
                     if HAS_DND else "Select a mod folder or archive")
        self.drop_label = ctk.CTkLabel(
            top, text=drop_text, font=ctk.CTkFont(size=16, weight="bold"),
            height=56)
        self.drop_label.grid(row=0, column=0, sticky="nsew", padx=16, pady=(12, 0))

        self.path_label = ctk.CTkLabel(top, text="No mod loaded", text_color=DIM)
        self.path_label.grid(row=1, column=0, sticky="ew", padx=16)

        btns = ctk.CTkFrame(top, fg_color="transparent")
        btns.grid(row=2, column=0, pady=(6, 12))
        ctk.CTkButton(btns, text="Browse Folder...", width=150,
                      command=self._browse_folder).pack(side="left", padx=6)
        ctk.CTkButton(btns, text="Browse Archive...", width=150,
                      command=self._browse_archive).pack(side="left", padx=6)

        mid = ctk.CTkFrame(self, corner_radius=12)
        mid.grid(row=2, column=0, sticky="nsew", padx=14, pady=6)
        mid.grid_columnconfigure(1, weight=1)
        mid.grid_rowconfigure(6, weight=1)

        ctk.CTkLabel(mid, text="ANALYSIS", font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=DIM).grid(row=0, column=0, columnspan=2,
                                          sticky="w", padx=16, pady=(10, 2))

        self.info_rows = {}
        for i, (key, label) in enumerate([
            ("mod", "Mod"),
            ("characters", "Characters"),
            ("outfit", "Detected outfit"),
        ], start=1):
            ctk.CTkLabel(mid, text=label, width=160, anchor="w",
                         text_color=DIM).grid(row=i, column=0, sticky="nw",
                                              padx=(16, 4), pady=2)
            val = ctk.CTkLabel(mid, text="-", anchor="w", justify="left")
            val.grid(row=i, column=1, sticky="ew", padx=(0, 16), pady=2)
            self.info_rows[key] = val

        name_row = ctk.CTkFrame(mid, fg_color="transparent")
        name_row.grid(row=4, column=0, columnspan=2, sticky="ew",
                      padx=16, pady=(12, 0))
        name_row.grid_columnconfigure(1, weight=1)

        self.set_name_var = tk.BooleanVar(
            value=bool(self.settings.get("set_outfit_name", False)))
        self.set_name_cb = ctk.CTkCheckBox(
            name_row, text="Set in-game outfit name",
            variable=self.set_name_var,
            command=self._on_set_name_toggled)
        self.set_name_cb.grid(row=0, column=0, sticky="w")
        self._bind_tooltip(
            self.set_name_cb,
            "Sets the costume-select name shown in-game.\n"
            "Works for Tank Top, Classic Tank Top, Elza, Noir,\n"
            "and Military.\n"
            "Jacket and Classic Jacket share those same name files,\n"
            "so renaming them would conflict with Tank Top renames.")

        self.outfit_name_var = tk.StringVar(value="")
        self.outfit_name_entry = ctk.CTkEntry(
            name_row, textvariable=self.outfit_name_var,
            placeholder_text="In-game outfit name")
        self.outfit_name_entry.grid(row=0, column=1, sticky="ew", padx=(12, 0))
        self.outfit_name_var.trace_add("write", self._on_outfit_name_typed)

        self.name_hint = ctk.CTkLabel(
            name_row, text="", text_color=DIM, anchor="w",
            font=ctk.CTkFont(size=11))
        self.name_hint.grid(row=1, column=0, columnspan=2, sticky="w", pady=(2, 0))

        out = ctk.CTkFrame(mid, fg_color="transparent")
        out.grid(row=5, column=0, columnspan=2, sticky="ew", padx=16, pady=(8, 0))
        out.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(out, text="Output folder", width=160, anchor="w",
                     text_color=DIM).grid(row=0, column=0, sticky="w")
        self.out_var = tk.StringVar(value=initial_output_dir(self.settings))
        self.out_entry = ctk.CTkEntry(out, textvariable=self.out_var)
        self.out_entry.grid(row=0, column=1, sticky="ew", padx=8)
        ctk.CTkButton(out, text="...", width=40,
                      command=self._browse_output).grid(row=0, column=2)

        ctk.CTkFrame(mid, fg_color="transparent", height=1).grid(
            row=6, column=0, columnspan=2, sticky="nsew", pady=(0, 14))

        bottom = ctk.CTkFrame(self, corner_radius=12)
        bottom.grid(row=3, column=0, sticky="ew", padx=14, pady=(6, 14))
        bottom.grid_columnconfigure(0, weight=1)

        conv = ctk.CTkFrame(bottom, fg_color="transparent")
        conv.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 8))

        ctk.CTkLabel(conv, text="Convert from").pack(side="left")
        self.from_var = tk.StringVar(value="-")
        self.from_menu = ctk.CTkOptionMenu(conv, variable=self.from_var,
                                           values=["-"], width=200,
                                           state="disabled")
        self.from_menu.pack(side="left", padx=8)

        ctk.CTkLabel(conv, text="to").pack(side="left")
        to_labels = outfit_menu_labels(self.settings)
        self.to_var = tk.StringVar(value=to_labels[0])
        self.to_menu = ctk.CTkOptionMenu(
            conv, variable=self.to_var,
            values=to_labels, width=260,
            state="disabled",
            command=self._on_target_outfit_changed)
        self.to_menu.pack(side="left", padx=8)

        self.convert_btn = ctk.CTkButton(
            bottom, text="Convert", height=44, state="disabled",
            fg_color=CONVERT, hover_color=CONVERT_HOVER,
            font=ctk.CTkFont(size=15, weight="bold"),
            command=self._start_convert)
        self.convert_btn.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 12))

        progress_row = ctk.CTkFrame(bottom, fg_color="transparent")
        progress_row.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 14))
        progress_row.grid_columnconfigure(0, weight=1)

        self.progress_bar = ctk.CTkProgressBar(
            progress_row, height=14, corner_radius=7,
            progress_color=CONVERT, fg_color="#2a2a2a",
            border_width=0)
        self.progress_bar.grid(row=0, column=0, sticky="ew")
        self.progress_bar.set(0)

        self.status_label = ctk.CTkLabel(
            progress_row, text="", anchor="center",
            font=ctk.CTkFont(size=12),
            text_color=DIM)
        self.status_label.grid(row=1, column=0, sticky="ew", pady=(6, 0))

        self._sync_name_ui()
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
        self.geometry("920x640")

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
        self._capture_geometry()

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

    def _refresh_to_menu(self) -> None:
        labels = outfit_menu_labels(self.settings)
        if not labels:
            return
        current = self._target_outfit()
        self.to_menu.configure(values=labels)
        self.to_var.set(
            self._outfit_menu_label(current) if current else labels[0])

    def _refresh_from_menu(self) -> None:
        sources = self._convertible_source_names()
        if not sources:
            self.from_menu.configure(values=["-"], state="disabled")
            self.from_var.set("-")
            return
        current = self._outfit_from_menu_label(self.from_var.get())
        self.from_menu.configure(values=sources, state="normal")
        if current is not None:
            label = self._outfit_menu_label(current)
            self.from_var.set(label if label in sources else sources[0])
        else:
            self.from_var.set(sources[0])

    def _refresh_convert_menus(self) -> None:
        self._refresh_to_menu()
        if self.loaded:
            self._refresh_from_menu()

    def _target_outfit(self):
        return self._outfit_from_menu_label(self.to_var.get())

    def _on_target_outfit_changed(self, _value=None):
        self._sync_name_ui()

    def _on_set_name_toggled(self):
        if self.set_name_var.get() and not self._name_user_edited:
            self.outfit_name_var.set(self._suggested_outfit_name)
            self._name_user_edited = False
        self._sync_name_ui()
        self._save_settings()

    def _on_outfit_name_typed(self, *_args):
        if not getattr(self, "outfit_name_entry", None):
            return
        if getattr(self, "_filling_name", False):
            return
        self._name_user_edited = True

    def _sync_name_ui(self):
        target = self._target_outfit()
        supported = bool(target and target.msg_stem)
        converting = self._convertible()

        if not supported:
            self.set_name_cb.configure(state="disabled")
            self.outfit_name_entry.grid_remove()
            self.name_hint.configure(
                text="Custom names: Tank Top, Classic Tank Top, Elza, "
                     "Noir, Military.")
            return

        self.set_name_cb.configure(
            state="normal" if converting else "disabled")
        if self.set_name_var.get() and converting:
            self.outfit_name_entry.grid()
            self.name_hint.configure(text="")
        else:
            self.outfit_name_entry.grid_remove()
            self.name_hint.configure(text="")

    def _refresh_suggested_name(self):
        if not self.loaded:
            self._suggested_outfit_name = ""
            self._filling_name = True
            self.outfit_name_var.set("")
            self._filling_name = False
            self._name_user_edited = False
            return
        primary = next(
            (m for m in self.loaded if not m.analysis.modinfo.addonfor),
            self.loaded[0])
        fallback = self._mod_label(primary.analysis, primary.source)
        self._suggested_outfit_name = (
            primary.analysis.suggested_outfit_display_name(fallback)
            or fallback)
        self._filling_name = True
        self.outfit_name_var.set(self._suggested_outfit_name)
        self._filling_name = False
        self._name_user_edited = False

    def _close_loaded(self):
        close_loaded([
            LoadedPackage(source=m.source, analysis=m.analysis)
            for m in self.loaded
        ])
        self.loaded.clear()

    def _mod_label(self, analysis: AnalysisResult, source: ModSource) -> str:
        return mod_label(analysis, source)

    def _suggest_bundle_name(self) -> str:
        mains = [m for m in self.loaded if m.analysis.claire_outfits]
        if not mains:
            mains = [m for m in self.loaded if not m.analysis.modinfo.addonfor]
        if mains:
            return mod_label(mains[0].analysis, mains[0].source)
        for m in self.loaded:
            if m.analysis.modinfo.addonfor:
                return m.analysis.modinfo.addonfor
        return mod_label(self.loaded[0].analysis, self.loaded[0].source)

    def _detected_outfit_names(self) -> list[str]:
        names: list[str] = []
        seen: set[str] = set()
        for m in self.loaded:
            for o in m.analysis.claire_outfits:
                if o.name not in seen:
                    names.append(o.name)
                    seen.add(o.name)
        return names

    def _convertible_source_names(self) -> list[str]:
        detected: set[str] = set()
        for m in self.loaded:
            for o in m.analysis.claire_outfits:
                if is_convertible_outfit(o):
                    detected.add(o.key)
        return [
            self._outfit_menu_label(o) for o in CONVERTIBLE_OUTFITS
            if o.key in detected
        ]

    def _convertible(self) -> bool:
        return bool(self.loaded and self._convertible_source_names())

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
        self.after(0, self._analysis_done, loaded, errors, infos)

    def _analyze_worker_safe(self, paths: list[Path]):
        try:
            self._analyze_worker(paths)
        except Exception as e:
            self.after(0, self._analysis_done, [], [f"Unexpected error: {e!r}"], [])

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
            self.from_menu.configure(values=["-"], state="disabled")
            self.from_var.set("-")
            self.to_menu.configure(state="disabled")
            self.convert_btn.configure(state="disabled")
            self._refresh_suggested_name()
            self._sync_name_ui()
            msg = "\n".join(errors) if errors else "No valid mods found."
            tk.messagebox.showerror("Could not load mod", msg)
            return

        if len(loaded) == 1:
            self._show_single_analysis(loaded[0])
        else:
            self._show_multi_analysis(loaded)

        sources = self._convertible_source_names()
        if sources:
            self.from_menu.configure(values=sources, state="normal")
            self.from_var.set(sources[0])
            self.to_menu.configure(state="normal")
            self.convert_btn.configure(state="normal")
        else:
            self.from_menu.configure(values=["-"], state="disabled")
            self.from_var.set("-")
            self.to_menu.configure(state="disabled")
            self.convert_btn.configure(state="disabled")

        self._refresh_suggested_name()
        self._sync_name_ui()

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
        self.info_rows["characters"].configure(text=format_characters(analysis))
        outfit_text, outfit_ok = format_outfit_row(analysis)
        self.info_rows["outfit"].configure(
            text=outfit_text,
            text_color=OK_COLOR if outfit_ok else WARN_COLOR)

    def _show_multi_analysis(self, loaded: list[LoadedMod]):
        mains = [m for m in loaded if not m.analysis.modinfo.addonfor]
        addons = [m for m in loaded if m.analysis.modinfo.addonfor]
        names = [mod_label(m.analysis, m.source) for m in loaded]
        self.path_label.configure(
            text=f"{len(loaded)} mods loaded  ·  "
                 f"{len(mains)} main, {len(addons)} addon")
        preview = ", ".join(names[:4])
        if len(names) > 4:
            preview += f", +{len(names) - 4} more"
        self.info_rows["mod"].configure(
            text=f"{len(loaded)} mods: {preview}")
        self.info_rows["characters"].configure(
            text=format_multi_characters(loaded))
        outfit_names = self._detected_outfit_names()
        passthrough = sum(1 for m in loaded if not m.analysis.claire_outfits)
        outfit_text = ", ".join(outfit_names) if outfit_names else "None detected"
        if passthrough:
            outfit_text += f"  (+ {passthrough} addon(s) with no outfit remap)"
        self.info_rows["outfit"].configure(
            text=outfit_text,
            text_color=OK_COLOR if outfit_names else WARN_COLOR)

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

    def _resolve_outfits(self):
        return (
            self._outfit_from_menu_label(self.from_var.get()),
            self._outfit_from_menu_label(self.to_var.get()),
        )

    def _start_convert(self):
        if self._busy or not self.loaded or not self._convertible():
            return
        out_path = self._ensure_output()
        if out_path is None:
            return
        source_outfit, target_outfit = self._resolve_outfits()
        if not source_outfit or not target_outfit:
            return

        if (source_outfit.key == target_outfit.key
                and not self._skip_convert_confirm()):
            if not tk.messagebox.askokcancel(
                    "Confirm conversion",
                    f"Convert this mod on {target_outfit.name} to itself?\n\n"
                    "Face and hair will be isolated so this mod won't "
                    "conflict with other Claire outfits."):
                return

        outfit_display_name = None
        if self.set_name_var.get() and target_outfit.msg_stem:
            outfit_display_name = self.outfit_name_var.get().strip()
            if not outfit_display_name:
                tk.messagebox.showwarning(
                    "Outfit name",
                    "Enter an in-game outfit name, or uncheck "
                    "\"Set in-game outfit name\".")
                return

        self._busy = True
        self.convert_btn.configure(state="disabled", text="Converting...")
        self._start_progress_ui()
        threading.Thread(
            target=self._convert_worker_safe,
            args=(source_outfit, target_outfit, out_path, outfit_display_name),
            daemon=True).start()

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

    def _convert_worker_safe(self, source_outfit, target_outfit, out_path: Path,
                             outfit_display_name: str | None = None):
        try:
            self._convert_worker(
                source_outfit, target_outfit, out_path, outfit_display_name)
        except Exception as e:
            self.after(0, self._convert_failed, f"Unexpected error: {e!r}")

    def _convert_worker(self, source_outfit, target_outfit, out_path: Path,
                        outfit_display_name: str | None = None):
        def progress(msg: str):
            self.after(0, self._on_progress_msg, msg)

        try:
            report = convert_loaded(
                self.loaded, source_outfit, target_outfit, out_path,
                outfit_display_name=outfit_display_name,
                tag_output=self._tag_output_enabled(),
                tag_marker=tag_marker_for(self.settings, target_outfit),
                strip_tags=strip_tag_markers(self.settings),
                bundle_name=self._suggest_bundle_name(),
                mod_label=self._mod_label,
                progress=progress,
            )
            self.after(0, self._convert_done, report)
        except (ConversionError, OSError) as e:
            self.after(0, self._convert_failed, str(e))
        except Exception as e:
            self.after(0, self._convert_failed, f"Unexpected error: {e!r}")

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
        self.destroy()


def run():
    app = App()
    app.mainloop()
