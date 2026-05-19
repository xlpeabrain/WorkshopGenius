# WorkshopGenius

Generates tailored Kong/Konnect workshop slide decks from client challenge descriptions.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
```

## Run

```bash
source .venv/bin/activate
uvicorn app.main:app --port 8080 --reload
# Open http://localhost:8080
```

Port 8000 is used by Kong Gateway locally — use 8080.

## Adding new slides

Drop new `.pptx` files into the appropriate subfolder under `slides/`, then click **Reindex slides** in the app footer. The catalog rebuilds automatically on server restart too.

## Scripts (for testing without the UI)

```bash
# Verify catalog indexes all decks
python scripts/test_catalog.py

# Verify PPTX assembly (opens the output file)
python scripts/test_assembly.py

# Verify AI slide selection (requires ANTHROPIC_API_KEY in .env)
python scripts/test_ai.py
```
