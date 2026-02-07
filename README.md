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
