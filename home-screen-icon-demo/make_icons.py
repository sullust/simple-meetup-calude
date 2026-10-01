"""Draw the smiley-face Home Screen icons. Run: python3 make_icons.py"""
from PIL import Image, ImageDraw

def smiley(size: int) -> Image.Image:
    # Draw at 4x and downsample for smooth edges.
    s = size * 4
    img = Image.new("RGBA", (s, s), (255, 204, 51, 255))   # opaque: iOS fills alpha with black
    d = ImageDraw.Draw(img)
    # Face (slightly darker ring at the edge for depth)
    d.ellipse((s*0.06, s*0.06, s*0.94, s*0.94), fill=(255, 221, 77, 255), outline=(230, 160, 20, 255), width=int(s*0.025))
    # Eyes
    for cx in (0.36, 0.64):
        d.ellipse((s*(cx-0.055), s*0.33, s*(cx+0.055), s*0.47), fill=(40, 30, 20, 255))
    # Smile
    d.arc((s*0.26, s*0.36, s*0.74, s*0.78), start=20, end=160, fill=(40, 30, 20, 255), width=int(s*0.045))
    return img.resize((size, size), Image.LANCZOS)

for px, name in ((180, "apple-touch-icon.png"), (512, "icon-512.png"), (192, "icon-192.png")):
    smiley(px).save(f"icons/{name}", optimize=True)
    print("wrote", name, px)
