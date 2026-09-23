"""Build the README banner from the brand artwork.

The source hero carries a typo in its subtitle -- "A CITED RETRIEVAL AGENT OVEN
THE AIRBUS A320/321". Rather than put that on the front page of the repository,
the two subtitle lines are painted out with the sky that surrounds them (each
row is filled from that row's own colour at the far left, where the gradient is
clean), leaving the logomark and the PURSER / AGENT lockup intact.
"""

from pathlib import Path

from PIL import Image

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
im.resize((1254, int(1254 * im.size[1] / im.size[0])), Image.LANCZOS).save(
    OUT, optimize=True
)
print(f"wrote {OUT} {OUT.stat().st_size // 1024} KB")
