from PIL import Image, ImageDraw

moments = ['0', '1.5', '4.8', '8.8', '13.6', '18.2']
canvas = Image.new('RGB', (1440, 1290), '#202020')
draw = ImageDraw.Draw(canvas)
for i, moment in enumerate(moments):
    x = (i % 2) * 720
    y = (i // 2) * 430
    image = Image.open(f'final-review/frame-{moment}.png').convert('RGB').resize((720,405))
    canvas.paste(image, (x,y+25))
    draw.text((x+12,y+5), f'{moment} seconds', fill='white')
canvas.save('final-review/contact-sheet.jpg', quality=92)
