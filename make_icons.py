"""Draw the arc-reactor app icons into docs/ (run once, or after changing the look)."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

OUT = Path(__file__).parent / "docs"
BG, CYAN, DIM, CORE = (3, 7, 13), (63, 216, 255), (27, 111, 143), (234, 250, 255)


def reactor(size):
    s = size * 4  # supersample, then downscale for smooth edges
    img = Image.new("RGB", (s, s), BG)
    glow = Image.new("RGB", (s, s), (0, 0, 0))
    d, g = ImageDraw.Draw(img), ImageDraw.Draw(glow)
    c = s / 2

    def ring(draw, r, width, color):
        draw.ellipse([c - r, c - r, c + r, c + r], outline=color, width=int(width))

    ring(d, s * .40, s * .012, DIM)
    for i in range(24):  # dashed segment ring
        d.arc([c - s * .34, c - s * .34, c + s * .34, c + s * .34], i * 15, i * 15 + 9, fill=CYAN, width=int(s * .035))
    ring(d, s * .25, s * .014, CYAN)
    ring(g, s * .25, s * .03, CYAN)
    d.ellipse([c - s * .15, c - s * .15, c + s * .15, c + s * .15], fill=(12, 58, 82), outline=CYAN, width=int(s * .02))
    d.ellipse([c - s * .07, c - s * .07, c + s * .07, c + s * .07], fill=CORE)
    g.ellipse([c - s * .17, c - s * .17, c + s * .17, c + s * .17], fill=CYAN)

    # Opaque RGB on purpose: iOS fills icon transparency with black.
    img = Image.blend(img, Image.composite(glow, img, glow.convert("L")), .35)
    img = Image.blend(img, img.filter(ImageFilter.GaussianBlur(s * .02)), .25)
    return img.resize((size, size), Image.LANCZOS)


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    for name, size in [("icon-192.png", 192), ("icon-512.png", 512), ("apple-touch-icon.png", 180)]:
        reactor(size).save(OUT / name, optimize=True)
        print(OUT / name)
