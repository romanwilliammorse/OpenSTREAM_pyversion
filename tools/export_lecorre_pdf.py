"""Export exactly the finalized Le Corre reports and acceptance matrix.

Use the separate PDF environment from tools/requirements-pdf.lock. The three
sources must match --source-commit (default HEAD); line endings alone may differ.
The destination must be new. No solver, full-library index or binder is run.
Visual review remains required after the retained-text checks complete.
"""
from __future__ import annotations

import argparse
from contextlib import redirect_stdout
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import io
import json
import math
from pathlib import Path
import platform
import subprocess
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
SOURCES = (
    ('docs/LECORRE_REPRODUCTION.md', 'Le Corre reconstruction and discrepancies'),
    ('docs/LECORRE_PHYSICAL_REVIEW.md', 'OpenSTREAM convergence and supplemental diagnostics review'),
    ('docs/ACCEPTANCE_MATRIX.md', 'Acceptance matrix'),
)


def sha(content):
    return hashlib.sha256(content).hexdigest()


def git(*args):
    return subprocess.run(['git', '-C', str(ROOT), *args], check=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout


def inventory_for(commit):
    commit = git('rev-parse', '--verify', '--end-of-options', commit+'^{commit}').decode().strip()
    documents = []
    for source, title in SOURCES:
        content = (ROOT/source).read_bytes()
        committed = git('show', f'{commit}:{source}')
        canonical = content.replace(b'\r\n', b'\n')
        if canonical != committed.replace(b'\r\n', b'\n'):
            raise ValueError(f'{source} differs from {commit}; commit finalized source text before exporting')
        documents.append({
            'source': source, 'kind': 'markdown', 'title': title,
            'status_label': 'Preserved scientific status; see stated evidence and limitations',
            'pdf_relative_path': Path(source).stem+'.pdf',
            'source_sha256': sha(content), 'source_sha256_lf': sha(canonical),
            'source_bytes': len(content),
            'source_git_blob': git('rev-parse', f'{commit}:{source}').decode().strip(),
            'committed_source_sha256': sha(committed),
        })
    return {
        'schema': 'openstream-lecorre-pdf-inventory-v1', 'source_commit': commit,
        'scope': 'Exactly the Le Corre reproduction report, physical review and acceptance matrix; source content unchanged.',
        'source_identity_policy': 'Working source must equal the recorded commit after CRLF-to-LF normalization only; raw hashes also retained.',
        'counts': {'markdown': len(documents), 'total': len(documents)},
        'documents': documents,
    }


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')


def figure_assets(inventory):
    """Inventory local PNGs in the report, requiring exact committed bytes."""
    from export_documentation_pdf import MD
    from PIL import Image
    document = next(d for d in inventory['documents'] if d['source'] == SOURCES[0][0])
    assets = []
    for token in MD.parse((ROOT/document['source']).read_text(encoding='utf-8-sig')):
        for child in token.children or []:
            if child.type != 'image':
                continue
            link = urlsplit(child.attrGet('src'))
            if link.scheme or link.netloc:
                raise ValueError('Figure plates require local committed PNG assets')
            path = ((ROOT/document['source']).parent/unquote(link.path)).resolve()
            source = path.relative_to(ROOT).as_posix()
            if path.suffix.lower() != '.png':
                raise ValueError(f'Figure plate asset is not a PNG: {source}')
            if any(a['source'] == source for a in assets):
                continue
            content = path.read_bytes()
            if content != git('show', f'{inventory["source_commit"]}:{source}'):
                raise ValueError(f'Figure differs from selected source commit: {source}')
            with Image.open(path) as image:
                pixels = list(image.size)
                dpi = image.info.get('dpi')
                if dpi is not None and (len(dpi) != 2 or not all(math.isfinite(x) and x > 0 for x in dpi)):
                    raise ValueError(f'Invalid image DPI metadata: {source}')
            assets.append({'source': source, 'caption': child.content,
                'source_sha256': sha(content), 'source_bytes': len(content),
                'source_git_blob': git('rev-parse', f'{inventory["source_commit"]}:{source}').decode().strip(),
                'pixels': pixels, 'dpi': list(dpi) if dpi is not None else None})
    document['figure_assets'] = assets
    inventory['figure_plate_policy'] = 'Append unchanged referenced PNGs on A3 landscape pages; preserve pixel aspect ratio without cropping; never exceed native DPI size when recorded (otherwise one point per pixel maximum).'
    return assets


def outline_entries(reader, items=None, depth=0):
    result = []
    for item in reader.outline if items is None else items:
        if isinstance(item, list):
            result.extend(outline_entries(reader, item, depth+1))
        else:
            result.append((depth, item.title, reader.get_destination_page_number(item)))
    return result


def append_figure_plates(output, stats, assets, source_commit):
    """Add print plates without changing original PDF pages or scientific data."""
    if not assets:
        return
    from export_documentation_pdf import BLUE, DARK, MUTED, S, escape
    from pypdf import PdfReader, PdfWriter
    from reportlab.lib.pagesizes import A3, landscape
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen.canvas import Canvas
    from reportlab.platypus import Paragraph
    original_bytes = output.read_bytes()
    original = PdfReader(io.BytesIO(original_bytes))
    original_pages = len(original.pages)
    original_outline = outline_entries(original)
    plate_buffer = io.BytesIO()
    width, height = landscape(A3)
    canvas = Canvas(plate_buffer, pagesize=(width, height), pageCompression=1)
    margin = 36
    plates = []
    for index, asset in enumerate(assets, 1):
        path = ROOT/asset['source']
        if sha(path.read_bytes()) != asset['source_sha256']:
            raise ValueError(f'Figure changed after inventory: {asset["source"]}')
        caption = Paragraph(escape(asset['caption'])+'<br/><font size="8">'+escape(asset['source'])+'</font>', S['body'])
        _, caption_height = caption.wrap(width-2*margin, height)
        caption.drawOn(canvas, margin, 32)
        bottom, top = 48+caption_height, height-margin
        pixel_width, pixel_height = asset['pixels']
        # A common scale preserves pixel aspect ratio even with unequal DPI axes;
        # the maximum DPI conservatively respects both recorded native extents.
        native_limit = 72/max(asset['dpi']) if asset['dpi'] else 1.0
        scale = min((width-2*margin)/pixel_width, (top-bottom)/pixel_height, native_limit)
        if scale <= 0:
            raise ValueError(f'Caption leaves no space for figure: {asset["source"]}')
        image_width, image_height = pixel_width*scale, pixel_height*scale
        canvas.drawImage(ImageReader(str(path)), (width-image_width)/2,
            bottom+(top-bottom-image_height)/2, width=image_width, height=image_height,
            preserveAspectRatio=True, mask='auto')
        canvas.setFillColor(DARK); canvas.setFont('Body', 7.4)
        canvas.drawString(margin, 16, f'Source snapshot {source_commit[:12]} | A3 landscape figure supplement')
        canvas.drawRightString(width-margin, 16, str(original_pages+index))
        canvas.showPage()
        plates.append({**asset, 'pdf_page': original_pages+index,
            'page_size_pt': [width, height], 'rendered_size_pt': [image_width, image_height],
            'native_size_limit_applied': scale == native_limit})
    canvas.save(); plate_buffer.seek(0)
    writer = PdfWriter()
    writer.append(original, import_outline=True)
    writer.append(PdfReader(plate_buffer), import_outline=True)
    if original.metadata:
        writer.add_metadata({key: str(value) for key, value in original.metadata.items() if value is not None})
    parent = writer.add_outline_item('Figure plates - A3 print layout', original_pages)
    for plate in plates:
        writer.add_outline_item(plate['caption'], plate['pdf_page']-1, parent=parent)
    merged_buffer = io.BytesIO(); writer.write(merged_buffer)
    merged_bytes = merged_buffer.getvalue(); merged = PdfReader(io.BytesIO(merged_bytes))
    if len(merged.pages) != original_pages+len(assets):
        raise ValueError('Unexpected page count after appending figure plates')
    for index, page in enumerate(original.pages):
        final = merged.pages[index]
        if page.extract_text() != final.extract_text() or page.get_contents().get_data() != final.get_contents().get_data():
            raise ValueError(f'Original source content changed on PDF page {index+1}')
        if list(page.mediabox) != list(final.mediabox) or list(page.cropbox) != list(final.cropbox):
            raise ValueError(f'Original page geometry changed on PDF page {index+1}')
    if outline_entries(merged)[:len(original_outline)] != original_outline:
        raise ValueError('Original bookmarks changed during plate append')
    for name, destination in original.named_destinations.items():
        if name not in merged.named_destinations or original.get_destination_page_number(destination) != merged.get_destination_page_number(merged.named_destinations[name]):
            raise ValueError(f'Original named destination changed: {name}')
    output.write_bytes(merged_bytes)
    stats.update(pre_plate_pdf_sha256=sha(original_bytes), original_pages=original_pages,
        pages=len(merged.pages), pdf_sha256=sha(merged_bytes), added_figure_plate_pages=len(assets),
        figure_plates=plates, original_page_text_and_content_streams_retained=True,
        original_page_geometry_retained=True, original_bookmarks_retained=True,
        original_named_destinations_retained=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path, help='New directory for exactly three PDFs and their provenance manifests')
    parser.add_argument('--source-commit', default='HEAD', help='Commit containing the finalized source text; default HEAD')
    args = parser.parse_args(argv)
    inventory = inventory_for(args.source_commit)
    if args.output.exists():
        raise FileExistsError(f'Output must be a new directory: {args.output}')
    # Defer the existing renderer/dependencies until source preflight completes.
    from export_documentation_pdf import Exporter
    assets = figure_assets(inventory)
    scripts = ('tools/export_lecorre_pdf.py', 'tools/export_documentation_pdf.py')
    script_hashes = {name: sha((ROOT/name).read_bytes()) for name in scripts}
    versions = {name: version(name) for name in ('reportlab', 'pypdf', 'Pillow', 'markdown-it-py', 'mdurl')}
    args.output.mkdir(parents=True, exist_ok=False)
    write_json(args.output/'SOURCE_INVENTORY.json', inventory)
    exporter = Exporter(inventory, args.output)
    for index, document in enumerate(inventory['documents'], 1):
        # The reusable renderer's old progress counter assumes a 50-file library.
        with redirect_stdout(io.StringIO()):
            exporter.build_one(document)
        if document['source'] == SOURCES[0][0]:
            append_figure_plates(args.output/document['pdf_relative_path'], exporter.audit[-1], assets, inventory['source_commit'])
        print(f'{index}/{len(SOURCES)} {document["pdf_relative_path"]}: {exporter.audit[-1]["pages"]} pages', flush=True)
    for document in inventory['documents']:
        if sha((ROOT/document['source']).read_bytes()) != document['source_sha256']:
            raise ValueError(f'Source changed during export: {document["source"]}')
    if any(sha((ROOT/name).read_bytes()) != digest for name, digest in script_hashes.items()):
        raise ValueError('PDF exporter source changed during export')
    if any(sha((ROOT/asset['source']).read_bytes()) != asset['source_sha256'] for asset in assets):
        raise ValueError('Source figure changed during export')
    manifest = {**inventory, 'created_utc': datetime.now(timezone.utc).isoformat(),
        'python': platform.python_version(), 'versions': versions,
        'exporter_source_sha256': script_hashes, 'documents': exporter.audit,
        'verification': {'source_hashes_matched_before_and_after': True,
            'figure_assets_match_source_commit_and_unchanged_after_export': True,
            'all_numeric_tokens_retained': True, 'all_source_text_fragments_retained': True,
            'rendered_layout_review': 'pending; render and inspect all pages before delivery'}}
    write_json(args.output/'DOCUMENT_MANIFEST.json', manifest)
    print('Three PDFs exported; numerical/text retention checks passed. Rendered layout review remains pending.', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
