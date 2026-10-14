from __future__ import annotations

from pathlib import Path


def draw_cover(client, model: str, title: str, concept: str, brand: str, folder: Path) -> str:
    branding = f"Small text '{brand}' in the bottom-right corner. " if brand else ""
    prompt = (
        "Minimalist flat-design podcast cover. "
        "Single unified image, not a collage, not multiple panels. "
        f"Title text: '{title}'. {concept} "
        f"{branding}"
        "Solid color background, simple shapes, clean typography. "
        "No other text, code, charts or screenshots in the image."
    )
    data, extension = client.draw(model, prompt)
    path = folder / f"cover{extension}"
    path.write_bytes(data)
    return path.name
