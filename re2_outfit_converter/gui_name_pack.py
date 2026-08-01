"""Dialog to build a Fluffy Claire / Leon costume name pack."""

from __future__ import annotations

import tkinter as tk
import tkinter.messagebox  # noqa: F401
from pathlib import Path
from typing import Callable

import customtkinter as ctk

from .msg_name import (
    CLAIRE_NAME_PACK_KEYS,
    LEON_NAME_PACK_KEYS,
    SHARED_COSTUME_NAME_KEYS,
    SHARED_COSTUME_NAME_LABELS,
    SHARED_COSTUME_NAME_VANILLA,
)
from .name_pack import build_costume_name_pack

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


def open_name_pack_dialog(
    app,
    *,
    output_dir: Path,
    on_created: Callable[[Path], None] | None = None,
) -> ctk.CTkToplevel:
    """Show the shared costume-name editor. Writes a zip under ``output_dir``."""
    win = ctk.CTkToplevel(app)
    win.title("Costume name pack")
    win.transient(app)
    win.grab_set()
    win.minsize(440, 560)

    body = ctk.CTkFrame(win, corner_radius=12)
    body.pack(fill="both", expand=True, padx=12, pady=12)
    body.grid_columnconfigure(0, weight=1)

    ctk.CTkLabel(
        body, text="Costume names",
        font=ctk.CTkFont(size=15, weight="bold"),
        anchor="w",
    ).grid(row=0, column=0, sticky="ew", padx=10, pady=(6, 4))

    char_row = ctk.CTkFrame(body, fg_color="transparent")
    char_row.grid(row=1, column=0, sticky="w", padx=10, pady=(0, 8))

    char_var = tk.StringVar(value="claire")
    title_label = ctk.CTkLabel(
        body, text="Claire",
        font=ctk.CTkFont(size=13, weight="bold"),
        anchor="w",
    )
    title_label.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 2))

    blurb_label = ctk.CTkLabel(
        body,
        text=_BLURBS["claire"],
        text_color=DIM,
        font=ctk.CTkFont(size=12),
        anchor="w",
        justify="left",
        wraplength=400,
    )
    blurb_label.grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 8))

    fields_host = ctk.CTkFrame(body, fg_color="transparent")
    fields_host.grid(row=4, column=0, sticky="nsew", padx=4)
    fields_host.grid_columnconfigure(0, weight=1)
    body.grid_rowconfigure(4, weight=1)

    fields: dict[str, tk.StringVar] = {
        key: tk.StringVar(value="") for key in SHARED_COSTUME_NAME_KEYS
    }
    pages: dict[str, ctk.CTkFrame] = {}

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
            ctk.CTkEntry(
                page, textvariable=fields[key],
                placeholder_text=vanilla, height=28,
            ).grid(row=i * 2 + 1, column=0, sticky="ew", padx=6, pady=(2, 0))
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

    btn_row = ctk.CTkFrame(body, fg_color="transparent")
    btn_row.grid(row=5, column=0, sticky="ew", padx=10, pady=(16, 8))
    btn_row.grid_columnconfigure(0, weight=1)

    def _cancel():
        win.destroy()

    def _create():
        values = {k: fields[k].get() for k in SHARED_COSTUME_NAME_KEYS}
        try:
            out = build_costume_name_pack(Path(output_dir), values)
        except ValueError as e:
            tk.messagebox.showwarning("Costume names", str(e), parent=win)
            return
        except Exception as e:
            tk.messagebox.showerror(
                "Costume names",
                f"Could not create name pack:\n{e}",
                parent=win,
            )
            return
        win.destroy()
        if on_created is not None:
            on_created(out)
        else:
            tk.messagebox.showinfo(
                "Costume names",
                f"Created:\n{out}",
                parent=app,
            )

    ctk.CTkButton(
        btn_row, text="Cancel", width=100, command=_cancel,
    ).grid(row=0, column=1, padx=(0, 8))
    ctk.CTkButton(
        btn_row, text="Create", width=100, command=_create,
        fg_color=CONVERT, hover_color=CONVERT_HOVER,
    ).grid(row=0, column=2)

    _show_character("claire")

    win.protocol("WM_DELETE_WINDOW", _cancel)
    win.update_idletasks()
    try:
        app.update_idletasks()
        x = app.winfo_rootx() + max(
            0, (app.winfo_width() - win.winfo_width()) // 2)
        y = app.winfo_rooty() + max(
            0, (app.winfo_height() - win.winfo_height()) // 2)
        win.geometry(f"+{x}+{y}")
    except tk.TclError:
        pass
    win.focus()
    return win
