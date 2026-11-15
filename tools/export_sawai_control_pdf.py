"""Export exactly the Sawai numerical-control study report and acceptance matrix.

Reuse the frozen-inventory guards, documentation renderer and A3 figure-plate
layout. Never rewrite source, other reports, old PDFs, or scientific results.
"""
from __future__ import annotations
import argparse
from contextlib import redirect_stdout
from datetime import datetime, timezone
from importlib.metadata import version
import io
from pathlib import Path
import platform

import export_lecorre_pdf as guarded

ROOT = Path(__file__).resolve().parents[1]
SOURCES = (
    ("docs/SAWAI_CONTROL_STUDY.md", "Sawai entry 1: relaxation and iteration-control study"),
    ("docs/ACCEPTANCE_MATRIX.md", "Acceptance matrix"),
)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--source-commit",default="HEAD")
    args=parser.parse_args(argv)
    if args.output.exists():
        raise FileExistsError(f"Choose a new output directory: {args.output}")
    # Restrict reused guards to exactly these two sources, in this process only.
    guarded.SOURCES=SOURCES
    inventory=guarded.inventory_for(args.source_commit)
    inventory["schema"]="openstream-sawai-control-pdf-inventory-v1"
    inventory["scope"]="Exactly the Sawai numerical-control study report and acceptance matrix; source text unchanged."
    from export_documentation_pdf import Exporter
    from reportlab.platypus import CondPageBreak, Table, Spacer
    class MatchedExporter(Exporter):
        def markdown_story(self, meta, width):
            story=super().markdown_story(meta,width)
            for i,item in enumerate(story):
                if meta["source"]==SOURCES[1][0] and hasattr(item,"style") and (item.style.name=="body" or item.style.name.startswith("list")):
                    item.spaceAfter=6
                if hasattr(item,"getPlainText") and item.getPlainText().strip()=="Acceptance evidence required:":
                    # Keep the matrix label with its first criterion, including
                    # intervening spacing. Scientific source text is unchanged.
                    item.keepWithNext=True
                    following=i+1
                    while following<len(story) and isinstance(story[following],Spacer):
                        story[following].keepWithNext=True
                        following+=1
            if meta["source"]!=SOURCES[0][0]:
                return story
            arranged=[]
            for i,item in enumerate(story):
                following=i+1
                while following<len(story) and isinstance(story[following],Spacer):
                    following+=1
                if hasattr(item,"heading_level") and following<len(story) and isinstance(story[following],Table):
                    # Reserve room for the heading, table header and first row.
                    # This affects pagination only, never the source content.
                    arranged.append(CondPageBreak(180))
                arranged.append(item)
            return arranged
    assets=guarded.figure_assets(inventory)
    expected="outputs/verification/sawai-control-study-01/analysis/control_study.png"
    if len(assets)!=1 or assets[0]["source"]!=expected:
        raise ValueError("Expected exactly the committed Sawai control-study plot")
    scripts=("tools/export_sawai_control_pdf.py","tools/export_lecorre_pdf.py","tools/export_documentation_pdf.py")
    script_hashes={p:guarded.sha((ROOT/p).read_bytes()) for p in scripts}
    args.output.mkdir(parents=True,exist_ok=False)
    guarded.write_json(args.output/"SOURCE_INVENTORY.json",inventory)
    exporter=MatchedExporter(inventory,args.output)
    for index,document in enumerate(inventory["documents"],1):
        with redirect_stdout(io.StringIO()):
            exporter.build_one(document)
        if document["source"]==SOURCES[0][0]:
            # Source PNG unchanged, no added title; only the existing footer caption.
            guarded.append_figure_plates(args.output/document["pdf_relative_path"],exporter.audit[-1],assets,inventory["source_commit"])
        print(f"{index}/2 {document['pdf_relative_path']}: {exporter.audit[-1]['pages']} pages",flush=True)
    for document in inventory["documents"]:
        if guarded.sha((ROOT/document["source"]).read_bytes())!=document["source_sha256"]:
            raise ValueError("Source changed during PDF export")
    if any(guarded.sha((ROOT/p).read_bytes())!=h for p,h in script_hashes.items()):
        raise ValueError("Renderer changed during PDF export")
    if any(guarded.sha((ROOT/a["source"]).read_bytes())!=a["source_sha256"] for a in assets):
        raise ValueError("Plot changed during PDF export")
    guarded.write_json(args.output/"DOCUMENT_MANIFEST.json",{
        **inventory,"created_utc":datetime.now(timezone.utc).isoformat(),
        "python":platform.python_version(),
        "versions":{p:version(p) for p in ("reportlab","pypdf","Pillow","markdown-it-py","mdurl")},
        "exporter_source_sha256":script_hashes,"documents":exporter.audit,
        "verification":{"source_hashes_matched_before_and_after":True,
            "figure_assets_match_source_commit_and_unchanged_after_export":True,
            "all_numeric_tokens_retained":True,"all_source_text_fragments_retained":True,
            "rendered_layout_review":"pending; separate QA receipt records rendered inspection"}})
    print("Two PDFs exported; source and numerical-text retention passed. Rendered review remains required.")
    return 0


if __name__=="__main__":
    raise SystemExit(main())
