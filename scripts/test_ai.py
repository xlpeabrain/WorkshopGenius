"""Smoke test: run AI analysis against a hardcoded challenge description."""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import anthropic

from app.ai import analyze_challenges
from app.catalog import load_or_rebuild_catalog
from app.config import settings

SAMPLE_CHALLENGE = """\
Our client is a financial services company adopting Kong Konnect as their API gateway platform.
Key challenges they are facing:
1. They need to understand how to secure their APIs using JWT authentication and rate limiting plugins.
2. They want to set up observability for their API traffic to detect anomalies.
3. Their team is unfamiliar with Konnect's deployment architecture (hybrid mode vs self-managed).
4. They want to automate their API lifecycle management using APIOps and deck.

Workshop duration: 3 hours.
"""


async def main():
    catalog = load_or_rebuild_catalog(settings.slides_dir, settings.catalog_path)
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    print("Sending challenge to Claude...\n")
    result = await analyze_challenges(SAMPLE_CHALLENGE, catalog, client)

    print("=== AI RESPONSE ===")
    print(json.dumps(result, indent=2))
    print(f"\nWorkshop title: {result.get('workshop_title')}")
    print(f"Duration: {result.get('estimated_duration_hours')}h")
    print(f"Decks selected: {len(result.get('selections', []))}")
    total_slides = sum(len(s.get('slide_indices', [])) for s in result.get('selections', []))
    print(f"Total slides: {total_slides}")

    # Validate deck IDs exist in catalog
    catalog_ids = {d["id"] for d in catalog["decks"]}
    for sel in result.get("selections", []):
        if sel["deck_id"] not in catalog_ids:
            print(f"  WARNING: unknown deck_id '{sel['deck_id']}'")


asyncio.run(main())
