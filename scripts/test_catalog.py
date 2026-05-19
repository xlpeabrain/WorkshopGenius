"""Smoke test: build catalog and print summary."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.catalog import load_or_rebuild_catalog, get_catalog_for_prompt
from app.config import settings

catalog = load_or_rebuild_catalog(settings.slides_dir, settings.catalog_path)

print("\n=== CATALOG SUMMARY ===")
for deck in catalog["decks"]:
    print(f"\n{deck['id']}")
    print(f"  Topic:  {deck['topic']}")
    print(f"  File:   {deck['filename']}")
    print(f"  Slides: {deck['slide_count']}")
    print(f"  First 3 slides:")
    for s in deck["slides"][:3]:
        print(f"    [{s['index']}] {s['title']}")

print(f"\n=== PROMPT REPRESENTATION (first 1000 chars) ===")
prompt_text = get_catalog_for_prompt(catalog)
print(prompt_text[:1000])
print(f"\nTotal prompt chars: {len(prompt_text)}")
