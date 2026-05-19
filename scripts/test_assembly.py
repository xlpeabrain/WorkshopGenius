"""Smoke test: assemble a small deck from the first two decks in the catalog."""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.assembler import assemble_deck, build_output_path
from app.catalog import load_or_rebuild_catalog
from app.config import settings

catalog = load_or_rebuild_catalog(settings.slides_dir, settings.catalog_path)
decks = catalog["decks"]

if len(decks) < 1:
    print("ERROR: no decks found in catalog")
    sys.exit(1)

# Pick first 3 slides from each of the first two decks
selections = []
for deck in decks[:2]:
    indices = [s["index"] for s in deck["slides"][:3]]
    selections.append({"deck_id": deck["id"], "slide_indices": indices})

output_path = build_output_path("Test_Assembly", settings.output_dir)
print(f"Assembling {sum(len(s['slide_indices']) for s in selections)} slides into {output_path}...")

result = assemble_deck(selections, catalog, settings.slides_dir, output_path)
print(f"Done: {result}")
print("Opening file...")
subprocess.run(["open", str(result)])
