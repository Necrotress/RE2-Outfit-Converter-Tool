# RE2 Remake Outfit Converter

**Version 1.0**

A Windows GUI tool that converts Resident Evil 2 Remake (Fluffy Mod Manager)
Claire costume mods from one outfit slot to another — e.g. take a mod made for
Elza Walker and re-target it to Noir or Jacket.

## Quick start (release builds)

**Windows** — extract `RE2.Outfit.Converter.v1.0.0.Windows.zip`, run
`RE2 Outfit Converter.exe` (single-file build; first launch may be a bit slower).

**Linux** — extract `RE2.Outfit.Converter.v1.0.0.Linux.zip`, run `./run.sh`
(see that package’s guide).

Windows GUI steps:
1. Drop a mod folder or `.zip` / `.rar` / `.7z` onto the window
   (`.rar` / `.7z` need [7-Zip](https://www.7-zip.org/) installed).
2. Confirm source / target outfits, set an output folder, click **Convert**.
3. Drop the resulting `.zip` into Fluffy’s `Games\RE2R\Mods` folder
   **without extracting**.

Multi-select a main mod plus its AddonFor options to get one multi-mod `.zip`.

## Run from source

```
pip install -r requirements.txt
python main.py
```

Requires Python 3.10+.

## CLI (Windows / Linux)

The Windows `.exe` GUI is Windows-only. On Linux use the CLI package or run from source.

**Linux release zip:** extract and run `./run.sh`.

**From source:**

```
pip install -r requirements-cli.txt
python -m re2_outfit_converter list-outfits
python -m re2_outfit_converter analyze ./MyMod.zip
python -m re2_outfit_converter convert ./MyMod.zip --from elza --to noir -o ./out
```

Options: `--name "Display Name"`, `--folder` (single mod), `--no-tag`,
`--batch-name NAME` (multi-mod zip). Outfit keys match `list-outfits`
(`elza`, `noir`, `military`, …). Prefer `.zip` inputs; for `.rar` / `.7z`
install `p7zip` so `7z` is on `PATH`.

See also:

- [docs/PIPELINE.md](docs/PIPELINE.md) — conversion stage order
- [docs/BINARY_PATCHING.md](docs/BINARY_PATCHING.md) — path overlay limits
- [docs/REVIEW_NOTES.md](docs/REVIEW_NOTES.md) — short review checklist

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

Convert menus follow that order (Jacket → Elza). `'98 Classic` is
detect-only and omitted from convert menus — its mesh layout differs from
the other Claire outfits.

## What conversion does

- Renames Claire body PFB slots and mesh folders to the target outfit.
- Isolates shared face / hair meshes onto private IDs so Fluffy mods stop
  fighting over `pl1050` / `pl1070`.
- Isolates common shared outfit texture folders (`Pl2020`,
  `Escape/Character/Textures`) used by many CR-AW packs.
- Injects a hair redirect when converting into Noir / Military so
  vanilla hats do not reappear.
- Patches same-length path strings inside engine binaries.

The original mod is never modified.

Fluffy may still warn about **Ada** packs, weapon motion banks, or shared VFX
files — those are outside Claire outfit isolation.

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
