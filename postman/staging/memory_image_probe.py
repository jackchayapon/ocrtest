"""Network-free synthetic image lifetime probe; never reads a private environment."""
import argparse
import hashlib
import io
import json
import threading
import time
from pathlib import Path

from app.core.config import Settings
from app.services.image_service import ImageService
from PIL import Image, ImageDraw


def usage():
    cg = Path('/sys/fs/cgroup')
    rss = next(r.split()[1] for r in Path('/proc/self/status').read_text().splitlines() if r.startswith('VmRSS:'))
    return {'time': time.monotonic(), 'rss': int(rss) * 1024,
            'current': int((cg / 'memory.current').read_text()), 'peak': int((cg / 'memory.peak').read_text()),
            'stat': {k: int(v) for k, v in (r.split() for r in (cg / 'memory.stat').read_text().splitlines())},
            'events': (cg / 'memory.events').read_text(),
            'swap_current': int((cg / 'memory.swap.current').read_text())}


def main(args):
    samples, phases = [], []
    stop = threading.Event()
    def monitor():
        while not stop.wait(.01):
            row = usage()
            samples.append(row)
            with Path(args.output + '.samples.jsonl').open('a') as log:
                log.write(json.dumps(row) + '\n')
    thread = threading.Thread(target=monitor, daemon=True)
    thread.start()
    service = ImageService(Settings(_env_file=None, database_url='sqlite://'))
    try:
        with Image.new('RGB', (8000, 5000), 'white') as synthetic:
            draw = ImageDraw.Draw(synthetic)
            for i in range(8):
                draw.rectangle((i * 800, 100, i * 800 + 600, 400), fill=(20 * i, 30 * i, 255 - 20 * i))
            del draw  # Do not retain the synthetic fixture's pixel buffer during the probe.
            buffer = io.BytesIO()
            synthetic.save(buffer, format='PNG')
            data = buffer.getvalue()
        begin = time.monotonic()
        uploaded, width, height = service.decode_upload(data, 'image/png')
        phases.append({'phase': 'decode_upload', 'seconds': time.monotonic() - begin, 'measurement': usage()})
        begin = time.monotonic()
        with service.open(uploaded) as image:
            phases.append({'phase': 'open', 'seconds': time.monotonic() - begin, 'measurement': usage()})
            begin = time.monotonic()
            crops = [service.canonical_crop(image, {'x1': i * 800, 'y1': 100, 'x2': i * 800 + 600, 'y2': 400}) for i in range(8)]
            phases.append({'phase': 'eight_crops', 'seconds': time.monotonic() - begin, 'measurement': usage()})
        result = {'dimensions': [width, height], 'upload_bytes': len(uploaded),
                  'upload_sha256': hashlib.sha256(uploaded).hexdigest(), 'crop_sha256': [c.sha256 for c in crops],
                  'phases': phases, 'peak_rss': max(s['rss'] for s in samples),
                  'kernel_peak': usage()['peak'], 'peak_sample': max(samples, key=lambda s: s['current']), 'final': usage()}
        Path(args.output).write_text(json.dumps(result, indent=2))
        print(json.dumps({'kernel_peak': result['kernel_peak'], 'peak_rss': result['peak_rss']}))
    finally:
        stop.set()
        thread.join()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    main(parser.parse_args())
