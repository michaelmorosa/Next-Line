"""Share cards: an image of a feature for Instagram and TikTok, made on a rider's first clean, and the "feature of
the week" export for Next Line's own posts.

Two sizes: story (1080x1920, Stories and TikTok) and feed (1080x1350, Instagram's portrait post). The feature
photo fills the card under a dark gradient; the name, grade and trail sit at the bottom, with a small Next Line mark.
Fonts are Barlow (SIL Open Font License, trails/fonts/OFL.txt).
"""
import io
import zipfile
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from .models import MediaKind, PHOTO_KINDS

SIZES = {'story': (1080, 1920), 'feed': (1080, 1350)}
FONTS = Path(__file__).resolve().parent / 'fonts'
BG = (16, 20, 15)
ACCENT = (242, 153, 74)
TEXT = (232, 237, 228)
MUTED = (154, 165, 150)
MARGIN = 72


@lru_cache
def font(name, size):
    return ImageFont.truetype(str(FONTS / name), size)


def display(size):
    return font('BarlowCondensed_700Bold.ttf', size)


def semibold(size):
    return font('Barlow_600SemiBold.ttf', size)


def regular(size):
    return font('Barlow_400Regular.ttf', size)


def cover_photo(feature):
    photos = [m for m in feature.media.all() if m.kind in PHOTO_KINDS and m.file]
    return next((m for m in photos if m.kind == MediaKind.FEATURE), photos[0] if photos else None)


def background(feature, width, height):
    """The feature photo cropped to fill the card, or a plain dark card if there's no photo."""
    media = cover_photo(feature)
    if media:
        try:
            with media.file.open('rb') as f:
                photo = Image.open(f)
                photo.load()
            return ImageOps.fit(ImageOps.exif_transpose(photo).convert('RGB'), (width, height))
        except (OSError, ValueError):
            pass  # a missing or unreadable file: fall back to the plain card
    card = Image.new('RGB', (width, height), BG)
    draw = ImageDraw.Draw(card)
    for y in range(height):  # a faint lift toward the top
        shade = int(18 * (1 - y / height))
        draw.line([(0, y), (width, y)], fill=(BG[0] + shade, BG[1] + shade + 4, BG[2] + shade))
    return card


def shade_bottom(card, start):
    """Darken from `start` (0-1 of the height) to the bottom, so white text reads over any photo."""
    width, height = card.size
    overlay = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    top = int(height * start)
    for y in range(top, height):
        alpha = int(235 * ((y - top) / (height - top)) ** 0.8)
        draw.line([(0, y), (width, y)], fill=(*BG, alpha))
    band = int(height * 0.14)  # a soft fade behind the top label
    for y in range(band):
        draw.line([(0, y), (width, y)], fill=(0, 0, 0, int(110 * (1 - y / band))))
    return Image.alpha_composite(card.convert('RGBA'), overlay)


def wrap(draw, text, face, max_width, max_lines=3):
    words, lines, line = text.split(), [], ''
    for word in words:
        trial = f'{line} {word}'.strip()
        if draw.textlength(trial, font=face) <= max_width or not line:
            line = trial
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip('.,') + '…'
    return lines


def render(feature, size='story', headline='First clean', rider_line=None):
    """JPEG bytes of a card for `feature`."""
    width, height = SIZES[size]
    story = size == 'story'
    card = shade_bottom(background(feature, width, height), 0.38 if story else 0.3)
    draw = ImageDraw.Draw(card)

    # Top: what this card is.
    draw.text((MARGIN, int(height * 0.04)), headline.upper(), font=semibold(40), fill=ACCENT)

    # Bottom block, laid out upward from the bottom margin by text baselines.
    baseline = height - MARGIN - (48 if story else 24)
    mark, mark_face = 'NEXT LINE', display(32)
    draw.text((width - MARGIN, baseline), mark, font=mark_face, fill=(*TEXT, 115), anchor='rs')
    if rider_line:
        draw.text((MARGIN, baseline), rider_line, font=regular(40), fill=MUTED, anchor='ls')
        baseline -= 40 + 34
    draw.text((MARGIN, baseline), f'{feature.get_type_display()} · {feature.trail.name}'.upper(), font=semibold(42),
              fill=TEXT, anchor='ls')
    baseline -= 42 + 44

    name_face = display(150 if story else 128)
    lines = wrap(draw, feature.name.upper(), name_face, width - 2 * MARGIN - 200)
    line_h = int(name_face.size * 0.94)
    for i, line in enumerate(reversed(lines)):
        draw.text((MARGIN, baseline - line_h * i), line, font=name_face, fill=TEXT, anchor='ls')
    cap = int(name_face.size * 0.7)  # cap height, roughly: the name is all capitals
    name_top = baseline - line_h * (len(lines) - 1) - cap

    # Grade badge, centred on the name block.
    if feature.grade:
        r = 82
        cx, cy = width - MARGIN - r, (name_top + baseline) // 2
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=ACCENT)
        draw.text((cx, cy - 30), 'GRADE', font=semibold(26), fill=BG, anchor='ms')
        draw.text((cx, cy + 50), str(feature.grade), font=display(96), fill=BG, anchor='ms')

    out = io.BytesIO()
    card.convert('RGB').save(out, 'JPEG', quality=88, optimize=True)
    return out.getvalue()


def rider_line(level):
    return f"Level {level['level']} · {level['title']}"


def feature_of_the_week(feature, request=None):
    """A zip for Next Line's own posts: the card in both sizes, the original photo, and the text to post."""
    pov = next((m for m in feature.media.all() if m.kind == MediaKind.POV and m.file), None)
    pov_link = (request.build_absolute_uri(pov.file.url) if request else pov.file.url) if pov else 'No POV clip yet'
    lines = [
        f'{feature.name}',
        f'Grade {feature.grade} {feature.get_type_display().lower()} on {feature.trail.name}'
        + (f', {feature.trail.system.name}' if feature.trail.system_id else ''),
        '',
        'How to ride it:',
        feature.how_to_ride or '(not written yet)',
        '',
        f'Ride-around: {"yes" + (f", grade {feature.ride_around_grade}" if feature.ride_around_grade else "") if feature.has_ride_around else "none"}',
        f'POV clip: {pov_link}',
        '',
        "Grades are our team's opinion and trails change. Ride within your limits.",
    ]
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        for size in SIZES:
            z.writestr(f'card-{size}.jpg', render(feature, size, headline='Feature of the week'))
        photo = cover_photo(feature)
        if photo:
            with photo.file.open('rb') as f:
                z.writestr('photo.jpg', f.read())
        z.writestr('post.txt', '\n'.join(lines) + '\n')
    return out.getvalue()
