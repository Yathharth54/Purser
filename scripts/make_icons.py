"""Cut the app icons out of the brand logomark.

The mark occupies a clean 580x580 square inside the 1254x1254 source; measured
bounding box (380, 326)-(960, 906). We crop with 14% padding -> (299, 245,
1041, 987), which keeps the gold crescent off the icon edge and survives the
circular mask Android applies to maskable icons.
"""

from pathlib import Path

from PIL import Image

SRC = Path("assets/ChatGPT Image Sep 22, 2026, 05_50_45 PM.png")
OUT = Path("web/public/icons")
CROP = (299, 245, 1041, 987)
NAVY = (9, 15, 33)

OUT.mkdir(parents=True, exist_ok=True)
mark = Image.open(SRC).convert("RGB").crop(CROP)

for size in (16, 32, 180, 192, 512):
    mark.resize((size, size), Image.LANCZOS).save(OUT / f"icon-{size}.png")

# Maskable: Android crops to a circle inscribed in the middle 80%, so the mark
# is inset to 60% on a full navy bleed or the wingtip gets clipped.
canvas = Image.new("RGB", (512, 512), NAVY)
inner = mark.resize((307, 307), Image.LANCZOS)
canvas.paste(inner, ((512 - 307) // 2, (512 - 307) // 2))
canvas.save(OUT / "maskable-512.png")

print("wrote", *(p.name for p in sorted(OUT.glob("*.png"))))
