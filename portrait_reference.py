"""Face-only reference for POV shots; preserves the original uploaded avatar."""
import base64
from functools import lru_cache
import io
import json
import subprocess

from PIL import Image, ImageDraw, ImageFilter, ImageOps

from model_registry import ROOT
import reference_images


@lru_cache(maxsize=64)
def _crop(path):
    detector = ROOT / 'bin/face-box'
    if not detector.is_file():
        return None
    try:
        result = subprocess.run([str(detector), path], capture_output=True, text=True, timeout=5, check=True)
        boxes = json.loads(result.stdout)
        if not boxes:
            return None
        face = max(boxes, key=lambda b: b['width'] * b['height'])
        with Image.open(path) as image:
            x, y = (face['x'] + face['width'] / 2) * image.width, (1 - face['y'] - face['height'] / 2) * image.height
            width, height = face['width'] * image.width * 1.65, face['height'] * image.height * 1.9
            rectangle = (max(0, round(x - width / 2)), max(0, round(y - height / 2)),
                         min(image.width, round(x + width / 2)), min(image.height, round(y + height / 2)))
            if min(rectangle[2] - rectangle[0], rectangle[3] - rectangle[1]) < 64:
                return None
            output = io.BytesIO()
            image.crop(rectangle).convert('RGB').save(output, format='PNG')
            return output.getvalue()
    except (OSError, ValueError, KeyError, subprocess.SubprocessError):
        return None


def prepare(reference):
    raw = _crop(str(reference_images.resolve(reference['id'])))
    if raw is None:
        return reference
    return reference_images.upload(dict(image=base64.b64encode(raw).decode('ascii')))


@lru_cache(maxsize=64)
def _identity_crop(path):
    """A tight, feathered identity sample, not an entire portrait composition."""
    try:
        result = subprocess.run([str(ROOT / 'bin/face-box'), path], capture_output=True,
                                text=True, timeout=5, check=True)
        boxes = json.loads(result.stdout)
        if not boxes:
            return None
        face = max(boxes, key=lambda b: b['width'] * b['height'])
        with Image.open(path) as source:
            image = ImageOps.exif_transpose(source).convert('RGB')
            x = (face['x'] + face['width'] / 2) * image.width
            y = (1 - face['y'] - face['height'] / 2) * image.height
            width, height = face['width'] * image.width * 1.2, face['height'] * image.height * 1.4
            box = (max(0, round(x-width/2)), max(0, round(y-height/2)),
                   min(image.width, round(x+width/2)), min(image.height, round(y+height/2)))
            if min(box[2]-box[0], box[3]-box[1]) < 64:
                return None
            crop = image.crop(box)
            mask = Image.new('L', crop.size, 0)
            ImageDraw.Draw(mask).ellipse((2, 2, crop.width-3, crop.height-3), fill=255)
            mask = mask.filter(ImageFilter.GaussianBlur(max(2, min(crop.size)/40)))
            neutral = Image.new('RGB', crop.size, '#a0a0a0')
            neutral.paste(crop, mask=mask)
            neutral.thumbnail((480, 480), Image.Resampling.LANCZOS)
            canvas = Image.new('RGB', (512, 512), '#a0a0a0')
            canvas.paste(neutral, ((512-neutral.width)//2, (512-neutral.height)//2))
            output = io.BytesIO();canvas.save(output, format='PNG')
            return output.getvalue()
    except (OSError, ValueError, KeyError, subprocess.SubprocessError):
        return None


def prepare_identity(path):
    """Return a separately saved sample; originals and other shot inputs stay intact."""
    raw = _identity_crop(str(path))
    if raw is None:
        return str(path), False
    reference = reference_images.upload(dict(image=base64.b64encode(raw).decode('ascii')))
    return str(reference_images.resolve(reference['id'])), True
