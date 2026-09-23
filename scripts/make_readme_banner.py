"""Build the README banner strip from the brand artwork.

The source is 16:9, which eats half the README before a word is read. The
lockup only occupies a band in the middle, so this crops to that band and
widens the canvas to 5:1 by extending the sky sideways.

The source hero carries a typo in its subtitle -- "A CITED RETRIEVAL AGENT OVEN
THE AIRBUS A320/321". Rather than put that on the front page of the repository,
the two subtitle lines are painted out with the sky that surrounds them (each
row is filled from that row's own colour at the far left, where the gradient is
clean), leaving the logomark and the PURSER / AGENT lockup intact.
"""

from pathlib import Path

from PIL import Image, ImageFilter

SRC = Path("assets/ChatGPT Image Sep 22, 2026, 05_56_46 PM.png")
OUT = Path("docs/banner.png")
BAND = (430, 563, 1460, 629)  # the two subtitle lines, measured, with room for the feather

im = Image.open(SRC).convert("RGB")
px = im.load()

x0, y0, x1, y1 = BAND
span = y1 - y0
for x in range(x0, x1):
    # Interpolate each column between the clean row above the band and the
    # clean row below it. The sky is a smooth vertical gradient, so this
    # reconstructs exactly what sits behind the text -- sampling sideways
    # would drag the bright dawn at the left edge across the dark navy.
    top = px[x, y0 - 1]
    bot = px[x, y1 + 1]
    edge = min(x - x0, x1 - x, 90) / 90  # feather the left/right seams
    for y in range(y0, y1):
        t = (y - y0) / span
        fill = tuple(round(top[c] + (bot[c] - top[c]) * t) for c in range(3))
        cur = px[x, y]
        px[x, y] = tuple(round(cur[c] + (fill[c] - cur[c]) * edge) for c in range(3))

OUT.parent.mkdir(parents=True, exist_ok=True)

# --- cut it down to a strip -------------------------------------------------
# A 16:9 hero eats half the README before a word is read. The lockup only
# occupies a band in the middle, so crop to that band and then widen the canvas
# by repeating the edge columns: the sky is a smooth vertical gradient, so an
# edge-extension is invisible, and it keeps the dawn at the left and the deep
# navy at the right exactly where the artwork put them.
# The band sits above the cloud deck: the lockup spans y 282-675 in the source,
# and the clouds start around y 740. Including them puts high-contrast detail on
# the edge columns, which the extension below would smear into hard stripes.
BAND_TOP, BAND_BOT = 236, 722
band = im.crop((0, BAND_TOP, im.size[0], BAND_BOT))
bw, bh = band.size

TARGET_RATIO = 5.0
canvas_w = int(bh * TARGET_RATIO)
pad = (canvas_w - bw) // 2


def extend(slice_box: tuple[int, int, int, int], width: int) -> Image.Image:
    """Stretch an edge slice, then blur it into a smooth gradient.

    Repeating a single column verbatim reproduces every wisp of cloud in it as a
    hard horizontal stripe. Taking a wider slice and blurring heavily leaves only
    the vertical gradient, which is the part that has to match.
    """
    return (
        band.crop(slice_box)
        .resize((width, bh), Image.BILINEAR)
        .filter(ImageFilter.GaussianBlur(radius=28))
    )


strip = Image.new("RGB", (canvas_w, bh))
strip.paste(extend((0, 0, 40, bh), pad + 90), (0, 0))
strip.paste(extend((bw - 40, 0, bw, bh), canvas_w - pad - bw + 90), (pad + bw - 90, 0))

# Feather the band into the extensions. A hard paste leaves a faint vertical
# seam where the blurred sky meets the sharp sky; 90px of cross-fade hides it.
FEATHER = 90
mask = Image.new("L", (bw, bh), 255)
for x in range(FEATHER):
    v = round(255 * x / FEATHER)
    for y in range(bh):
        mask.putpixel((x, y), v)
        mask.putpixel((bw - 1 - x, y), v)
strip.paste(band, (pad, 0), mask)

strip.resize((1600, int(1600 * bh / canvas_w)), Image.LANCZOS).save(OUT, optimize=True)
w, h = Image.open(OUT).size
print(f"wrote {OUT} {w}x{h} ({w / h:.2f}:1) {OUT.stat().st_size // 1024} KB")
