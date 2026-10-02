"""Recreate the geometric application mark (Pillow is only needed for this utility)."""
from pathlib import Path
from PIL import Image, ImageDraw

output = Path(__file__).with_name('assets')
output.mkdir(exist_ok=True)
image = Image.new('RGBA', (256, 256))
draw = ImageDraw.Draw(image)
draw.rounded_rectangle((4, 4, 252, 252), radius=55, fill='#15213a')
draw.rounded_rectangle((52, 56, 97, 201), radius=12, fill='#8793ff')
draw.rounded_rectangle((106, 101, 151, 201), radius=12, fill='#6776ed')
draw.rounded_rectangle((160, 142, 205, 201), radius=12, fill='#b5beff')
draw.ellipse((161, 55, 204, 98), fill='#6ac9ad')
image.save(output / 'icon.png')
image.save(output / 'icon.ico', sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
