"""Draw the Sleep Log Home Screen icons (bed emoji). Run from sleep-log/: python3 make_icons.py
Needs Noto Color Emoji. Replace icons/*.png with your own artwork to customise (180, 192, 512 px, opaque)."""
from PIL import Image, ImageDraw, ImageFont

FONT = "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"
BG = (43, 52, 103)

def icon(size: int) -> Image.Image:
    glyph = ImageFont.truetype(FONT, 109).getmask("\U0001F6CF", mode="RGBA")  # bitmap strike is 136x128
    em = Image.new("RGBA", glyph.size)
    em.im.paste(glyph, (0, 0) + glyph.size)
    target = int(size * 0.78)
    em = em.resize((target, int(target * em.height / em.width)), Image.LANCZOS)
    img = Image.new("RGB", (size, size), BG)
    img.paste(em, ((size - em.width) // 2, (size - em.height) // 2), em)
    return img

for px, name in ((180, "apple-touch-icon.png"), (512, "icon-512.png"), (192, "icon-192.png")):
    icon(px).save(f"icons/{name}", optimize=True)
    print("wrote", name, px)
