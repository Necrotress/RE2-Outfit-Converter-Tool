# RE2 Remake Outfit Converter

**Version 1.1.0**

A GUI tool (Windows exe + Linux package) that converts Resident Evil 2 Remake
(Fluffy Mod Manager) Claire costume mods from one outfit slot to another ΓÇö
e.g. take a mod made for Elza Walker and re-target it to Noir or Jacket.

## Screenshots

<p align="center">
  <img src="screenshots/icon.png" alt="App icon" width="128">
</p>

**Main window**

![Main window](screenshots/main.png)

**Settings**

![Settings](screenshots/settings.png)

## Quick start (release builds)

**Windows** ΓÇö extract `RE2.Outfit.Converter.v1.1.0.Windows.zip`, run
`RE2 Outfit Converter.exe` (single-file build; first launch may be a bit slower).

**Linux** ΓÇö extract `RE2.Outfit.Converter.v1.1.0.Linux.zip`, run `./run.sh`
(opens the same GUI; needs Python 3.10+, `python3-tk`, and a desktop session ΓÇö
see that packageΓÇÖs `README.txt`). Pack from source with `pack-linux.bat`.

GUI steps (Windows / Linux):
1. Drop a mod folder or `.zip` / `.rar` / `.7z` onto the window
   (Windows: `.rar` / `.7z` need [7-Zip](https://www.7-zip.org/);
   Linux: install `p7zip` so `7z` is on `PATH`).
2. Confirm source / target outfits, set an output folder, click **Convert**.
3. Drop the resulting `.zip` into FluffyΓÇÖs `Games\RE2R\Mods` folder
   **without extracting**.

Multi-select a main mod plus its AddonFor options to get one multi-mod `.zip`.

## Run from source

```
pip install -r requirements.txt
python main.py
```

Requires Python 3.10+.

## CLI (Windows / Linux)

The Linux release zip launches the **GUI** via `./run.sh`. CLI remains available
via `./convert.sh` (or `./menu.sh` for a text menu). On Windows, use the `.exe`
or run from source.

**From source (CLI only):**

```
pip install -r requirements-cli.txt
python -m re2_outfit_converter list-outfits
python -m re2_outfit_converter analyze ./MyMod.zip
python -m re2_outfit_converter convert ./MyMod.zip --from elza --to noir -o ./out
python -m re2_outfit_converter convert ./Pack.zip \
  --map tanktop:noir --delete jacket -o ./out
```

**Linux GUI from source / release tree:** `pip install -r requirements-linux.txt`
then `python main.py` (system Tkinter required).

Options: `--name "Display Name"`, `--folder` (single mod), `--no-tag`,
`--batch-name NAME` (multi-mod zip), `--military-face dirty|clean`
(any convert target; ignored if the mod already has a face),
`--map SRC:DST` / `--delete KEY` (multi-slot packs; instead of `--from`/`--to`).
Outfit keys match `list-outfits` (`elza`, `noir`, `military`, ΓÇª). Prefer `.zip`
inputs; for `.rar` / `.7z` install `p7zip` so `7z` is on `PATH`.

See also:

- [CHANGELOG.md](CHANGELOG.md) ΓÇö release notes
- [docs/PIPELINE.md](docs/PIPELINE.md) ΓÇö conversion stage order
- [docs/BINARY_PATCHING.md](docs/BINARY_PATCHING.md) ΓÇö path overlay limits
- [docs/REVIEW_NOTES.md](docs/REVIEW_NOTES.md) ΓÇö short review checklist

## Supported outfits (Claire)

| Outfit            | PFB slot(s)              | Body mesh ID |
|-------------------|--------------------------|--------------|
| Jacket (Default)  | default, costume_1/2     | pl1000       |
| Tank Top          | costume_3/4              | pl1001       |
| Classic (Jacket)  | costume_5/6/7            | pl1002       |
| Classic (Tank Top)| costume_8/9              | pl1003       |
| Noir              | costume_a                | pl1005       |
| Military          | costume_b                | pl1006       |
| Elza Walker       | costume_c                | pl1004       |
| '98 Classic       | costume_d                | pl1007       |

Convert menus follow that order (Jacket ΓåÆ Elza). `'98 Classic` is
detect-only and omitted from convert menus ΓÇö its mesh layout differs from
the other Claire outfits.

## What conversion does

- Renames Claire body PFB slots and mesh folders to the target outfit.
- Isolates shared face / hair meshes onto private IDs so Fluffy mods stop
  fighting over `pl1050` / `pl1070`.
- Isolates common shared outfit texture folders (`Pl2020`,
  `Escape/Character/Textures`) used by many CR-AW packs.
- Injects a hair redirect when converting into Noir / Military so
  vanilla hats do not reappear in gameplay, and seeds `pl1075` /
  `pl1071` with Claire hair meshes so the costume-select 3D preview
  matches (hat/headband hidden).
- Strips author figure-gallery scenes so Records viewers do not bleed
  across DLC outfit slots (vanilla gallery + remapped body mesh).
- Patches same-length path strings inside engine binaries.

The original mod is never modified.

Fluffy may still warn about **Ada** packs, weapon motion banks, or shared VFX
files ΓÇö those are outside Claire outfit isolation.

## Tests

```
pip install -r requirements.txt
pytest
```

## Build the Windows app

### Local / folder build

From the project root, run `rebuild.bat`. That installs dependencies, builds with
`RE2 Outfit Converter.spec`, and copies the app to `Build\RE2 Outfit Converter\`.

Manual equivalent:

```
pip install -r requirements.txt pyinstaller
pyinstaller --noconfirm --workpath pyi-work --distpath dist "RE2 Outfit Converter.spec"
```

Then copy `dist\RE2 Outfit Converter\` to `Build\RE2 Outfit Converter\`.

On Windows, avoid letting PyInstaller use a default `build\` work folder named
the same as `Build\` (case-insensitive collision).

### Release (single-file exe)

The Windows release zip uses the onefile build:

```
pip install -r requirements.txt pyinstaller
python -m PyInstaller --noconfirm --workpath pyi-work-onefile --distpath dist-onefile "RE2 Outfit Converter.onefile.spec"
```

Output: `dist-onefile\RE2 Outfit Converter.exe`  
Zip that with `USER GUIDE.txt` for the release package.

## Build the Linux package

From the project root on Windows, run `pack-linux.bat`. That stages the GUI
scripts, `main.py`, `requirements-linux.txt`, and `re2_outfit_converter/`, then
writes `RE2 Outfit Converter (Linux).zip` next to this README.

On Linux: extract, `chmod +x run.sh`, `./run.sh`.
