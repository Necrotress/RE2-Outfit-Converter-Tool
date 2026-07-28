RE2 Outfit Converter (Linux)
============================

Same GUI and conversion engine as the Windows app. Converts RE2 Remake Claire
outfit mods between slots. Your original mod is never changed.

Quick start (GUI)
-----------------
  chmod +x run.sh
  ./run.sh

Needs:
  - Python 3.10+ with venv
  - Tkinter (GUI)
      Debian/Ubuntu:  sudo apt install python3 python3-venv python3-pip python3-tk
      Arch:           sudo pacman -S python python-pip tk
      Fedora:         sudo dnf install python3 python3-pip python3-tkinter
  - A graphical desktop (DISPLAY or Wayland). Steam Deck: use Desktop Mode.

The first run creates a local .venv and installs Python packages (internet once).

Use the window like Windows: pick/drop a mod, set from/to outfit, Convert.
Prefer .zip mods. For .rar / .7z, install p7zip so "7z" is on PATH.

Drop the output .zip into Fluffy's RE2R Mods folder — do not extract it.

CLI (optional)
--------------
  ./convert.sh list-outfits
  ./convert.sh analyze ./MyMod.zip
  ./convert.sh convert ./MyMod.zip --from elza --to noir -o ./out
  ./menu.sh          # interactive text menu (no GUI)

Outfit keys: jacket, tanktop, classic_jacket, classic_tanktop,
noir, military, elza
