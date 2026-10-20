"""Generate simple bin images (1280x800, Echo Show friendly) into ./images."""

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

BINS = {
    "grey": ("#6b7078", "GREY BIN", "General waste"),
    "green": ("#2e8b57", "GREEN BIN", "Recycling"),
    "brown": ("#7a4a24", "BROWN BIN", "Garden waste"),
    "food": ("#c9a227", "FOOD CADDY", "Food waste"),
}
W, H = 1280, 800
OUT = Path(__file__).with_name("images")


def font(size: int):
    for name in ("DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def draw_bin(d: ImageDraw.ImageDraw, colour: str, x: int, y: int) -> None:
    # lid
    d.rounded_rectangle([x - 20, y, x + 300, y + 50], radius=14, fill=colour, outline="#1b1b1b", width=6)
    d.rectangle([x + 110, y - 22, x + 170, y + 4], fill=colour, outline="#1b1b1b", width=5)
    # body (slight taper)
    d.polygon([(x, y + 56), (x + 280, y + 56), (x + 258, y + 440), (x + 22, y + 440)],
              fill=colour, outline="#1b1b1b")
    for i in range(3):
        lx = x + 70 + i * 70
        d.line([(lx, y + 110), (lx - 4, y + 390)], fill="#1b1b1b", width=6)
    # wheels
    for wx in (x + 40, x + 240):
        d.ellipse([wx - 32, y + 420, wx + 32, y + 484], fill="#222", outline="#000", width=4)


def main() -> None:
    OUT.mkdir(exist_ok=True)
    for key, (colour, title, sub) in BINS.items():
        img = Image.new("RGB", (W, H), "#101418")
        d = ImageDraw.Draw(img)
        d.rectangle([0, 0, W, 24], fill=colour)
        draw_bin(d, colour, 110, 180)
        d.text((560, 220), "Tomorrow", font=font(60), fill="#c8ccd2")
        d.text((560, 300), title, font=font(110), fill=colour)
        d.text((560, 440), sub, font=font(56), fill="#e9ecef")
        d.text((560, 540), "Out by 7am", font=font(48), fill="#9aa1a9")
        img.save(OUT / f"{key}.png", optimize=True)
        print("wrote", OUT / f"{key}.png")


if __name__ == "__main__":
    main()
