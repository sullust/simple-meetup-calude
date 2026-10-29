"""Draw the Pill Schedule Home Screen icons (pill emoji). Run from pill-schedule/: python3 make_icons.py
Needs Noto Color Emoji. Replace icons/*.png with your own artwork to customise (180, 192, 512 px, opaque)."""
from PIL import Image, ImageDraw, ImageFont

FONT = "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"
BG = (30, 111, 92)  # pharmacy green, matches the app accent

def icon(size: int) -> Image.Image:
    glyph = ImageFont.truetype(FONT, 109).getmask("\U0001F48A", mode="RGBA")  # bitmap strike is 136x128
    em = Image.new("RGBA", glyph.size)
    em.im.paste(glyph, (0, 0) + glyph.size)
    target = int(size * 0.74)
    em = em.resize((target, int(target * em.height / em.width)), Image.LANCZOS)
    img = Image.new("RGB", (size, size), BG)
    img.paste(em, ((size - em.width) // 2, (size - em.height) // 2), em)
    return img

for px, name in ((180, "apple-touch-icon.png"), (512, "icon-512.png"), (192, "icon-192.png")):
    icon(px).save(f"icons/{name}", optimize=True)
    print("wrote", name, px)
