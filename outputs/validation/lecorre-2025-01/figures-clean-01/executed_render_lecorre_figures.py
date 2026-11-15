"""Render clean figures from an immutable completed Le Corre campaign.

No solver execution or new comparison statistics. The main Figure 7 uses the
author-confirmed 0.2 s setting; the two-setting plot remains a separate file.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from compare_lecorre_results import make_plots


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--campaign', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError('Choose a new presentation output directory')
    report_path = args.campaign/'report.json'
    analysis_path = args.campaign/'analysis/analysis.json'
    report = json.loads(report_path.read_text(encoding='utf-8'))
    analysis = json.loads(analysis_path.read_text(encoding='utf-8'))
    if analysis['report_sha256'] != sha(report_path) or analysis['incomplete_preview']:
        raise ValueError('A complete analysis matching the unchanged campaign is required')
    # Freeze the existing evidence before adding a presentation-only directory.
    original_files = {str(p.relative_to(args.campaign)): sha(p)
                      for p in args.campaign.rglob('*') if p.is_file()}
    args.output.mkdir(parents=True)
    import matplotlib
    matplotlib.use('Agg')
    from matplotlib.figure import Figure
    saved_figures = []
    original_savefig = Figure.savefig

    def checked_savefig(figure, filename, *positional, **keywords):
        banner = figure._suptitle
        if banner is not None and banner.get_text().strip():
            raise ValueError('Figure-wide banner text must be absent')
        labels = [line.get_label() for axis in figure.axes for line in axis.lines]
        legends = [text.get_text() for legend in figure.legends for text in legend.get_texts()]
        name = Path(filename).name
        if name == 'figure7_measurement_comparison.png':
            if any('0.1' in text for text in labels+legends):
                raise ValueError('Main Figure 7 must contain only the 0.2 s branch')
            if sum('τ=0.2s' in text for text in labels) != 8:
                raise ValueError('Main Figure 7 must contain all four cases and both quantities')
        if name == 'figure7_relaxation_comparison.png':
            if any(sum(f'τ={tau}s' in text for text in labels) != 8 for tau in ('0.1','0.2')):
                raise ValueError('The separate comparison must preserve both full branches')
        original_savefig(figure, filename, *positional, **keywords)
        saved_figures.append({'file': name, 'sha256': sha(Path(filename)),
                              'figure_wide_banner': None, 'line_labels': labels,
                              'legend_labels': legends})

    Figure.savefig = checked_savefig
    try:
        make_plots(args.campaign, args.output, report, analysis['paper_comparison'],
                   analysis['experimental_comparison'], analysis['paper_figures6_7_comparison'])
    finally:
        Figure.savefig = original_savefig
    for name, digest in original_files.items():
        if sha(args.campaign/name) != digest:
            raise ValueError(f'Original evidence changed: {name}')
    correlation = 'figure6_measured_film_correlation.json'
    if json.loads((args.output/correlation).read_text()) != json.loads((args.campaign/'analysis'/correlation).read_text()):
        raise ValueError('The displayed Figure 6 correlation changed numerically')
    scripts = [Path(__file__), Path(__file__).with_name('compare_lecorre_results.py')]
    for script in scripts:
        (args.output/('executed_'+script.name)).write_bytes(script.read_bytes())
    receipt = {'schema': 'openstream-lecorre-figure-presentation-v1',
        'created_utc': datetime.now(timezone.utc).isoformat(),
        'authority': 'User requested no top banners and only tau=0.2 s in the main Figure 7, with both-setting comparison preserved separately.',
        'source_report_sha256': sha(report_path), 'source_analysis_sha256': sha(analysis_path),
        'source_files_sha256': original_files, 'all_original_evidence_unchanged': True,
        'figure6_correlation_numerically_unchanged': True,
        'solver_executed': False, 'comparison_statistics_recomputed': False,
        'scripts_sha256': {s.name: sha(s) for s in scripts}, 'figures': saved_figures,
        'explanations': {'figures3_4': 'Lines are native calculations; open markers are digitized paper readings.',
            'figure6_measurement': 'Dotted factor-1.2 guides are not acceptance limits. Stars use measured film flow in Eq.55.',
            'figure6_paper': 'Error bars are estimated graphical reading bounds, not measurement uncertainty.',
            'figure7': 'Circles are measurements; open squares are outside the stored channel; open triangles are digitized paper curves. Dotted equilibrium period is from the 0.2 s branch.'},
        'scientific_scope': 'Presentation revision does not establish numerical equivalence or experimental validation; original assessments remain in the immutable campaign. Current acceptance policy is documented separately.'}
    (args.output/'PRESENTATION.json').write_text(json.dumps(receipt, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    print(f'{len(saved_figures)} figures rendered; all {len(original_files)} original files unchanged.')


if __name__ == '__main__':
    main()
