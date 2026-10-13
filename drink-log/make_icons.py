"""Draw the Drink Log Home Screen icons. Run from drink-log/: python3 make_icons.py
Replace icons/*.png with your own artwork to customise (180, 192, 512 px, opaque)."""
from PIL import Image, ImageDraw

def glass(size: int) -> Image.Image:
    s = size * 4
    img = Image.new("RGB", (s, s), (47, 111, 143))
    d = ImageDraw.Draw(img)
    top, bot = s * 0.2, s * 0.8
    tl, tr = s * 0.27, s * 0.73
    bl, br = s * 0.33, s * 0.67
    d.polygon([(tl, top), (tr, top), (br, bot), (bl, bot)], fill=(232, 244, 250))
    # water level
    wl = s * 0.38
    f = (wl - top) / (bot - top)
    wl_l, wl_r = tl + (bl - tl) * f, tr + (br - tr) * f
    d.polygon([(wl_l, wl), (wl_r, wl), (br, bot), (bl, bot)], fill=(127, 186, 217))
    # rim highlight
    d.rectangle((tl, top, tr, top + s * 0.025), fill=(255, 255, 255))
    return img.resize((size, size), Image.LANCZOS)

for px, name in ((180, "apple-touch-icon.png"), (512, "icon-512.png"), (192, "icon-192.png")):
    glass(px).save(f"icons/{name}", optimize=True)
    print("wrote", name, px)
