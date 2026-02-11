# Toolbox

PySide6 desktop app for address and route management.

## Setup

```bash
pip install -r requirements.txt
```

### Google Maps API Key (for map views)

**Option A – Environment variable (recommended):**
```bash
set GOOGLE_MAPS_API_KEY=your_key_here   # Windows
export GOOGLE_MAPS_API_KEY=your_key_here   # Linux/macOS
```

**Option B – Local config file:**
```bash
copy config.example.json config.json
# Edit config.json and add your API key
```

`config.json` is in `.gitignore` and should not be committed.

## Run

```bash
python main.py
```

## Build exe (Windows)

For **map display** in the exe, install QtWebEngine in the build environment:

```bash
pip install pyside6-addons
```

Then build:

```bash
pip install pyinstaller
python -m PyInstaller --noconfirm Toolbox.spec
# Output: dist/Toolbox/
```

Without `pyside6-addons`, the exe runs but shows "Map module not available" when opening map views.

## GitHub Actions releases

Push a version tag to trigger a build and automatic GitHub release:

```bash
git tag v1.0.0
git push origin v1.0.0
```

The workflow builds a Windows exe and attaches `Toolbox-Windows.zip` to the release.
