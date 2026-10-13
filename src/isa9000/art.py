from __future__ import annotations

from pathlib import Path

from google.genai import types


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
    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_modalities=["IMAGE"],
            image_config=types.ImageConfig(aspect_ratio="1:1"),
        ),
    )
    part = next((p for p in response.parts or [] if p.inline_data and p.inline_data.data), None)
    if part is None:
        raise RuntimeError(f"{model} returned no cover image")
    extension = ".png" if "png" in (part.inline_data.mime_type or "") else ".jpg"
    path = folder / f"cover{extension}"
    path.write_bytes(part.inline_data.data)
    return path.name
