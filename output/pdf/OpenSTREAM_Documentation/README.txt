OpenSTREAM native Python documentation - PDF library

52 PDFs: 50 source documents, a four-page index, and a 387-page combined volume.

Start with 00_INDEX.pdf or OpenSTREAM_Complete_Documentation.pdf.
The combined volume includes document/heading bookmarks and 117 checked internal links.
Numbered folders contain the individual reports, documentation, complete acceptance
matrix/ledger, options/methods annexes, pilot run records and preserved pilot figure.

Scientific content and acceptance statuses have not been rewritten. The native port
remains incomplete. Historical reports retain their original scope and test counts.
No numerical solver or MATLAB reference calculation was rerun for this export.

DOCUMENT_MANIFEST.json records source and output hashes, page counts and content checks.
SOURCE_INVENTORY.json records the complete source scope and exclusions.
PDF_VERIFICATION.json records geometry, text, font, link and sampled visual checks.

Rebuild from the original project checkout on Windows (not from the ZIP alone):
1. Use an isolated documentation environment with tools/requirements-pdf.lock.
2. The exporter uses installed Segoe UI and Consolas fonts from C:/Windows/Fonts.
3. From the project root, run:
   python tools/export_documentation_pdf.py --inventory output/pdf/OpenSTREAM_Documentation/SOURCE_INVENTORY.json --output output/pdf/Rebuilt_Documentation
4. Recheck rendering before redistributing a regenerated set.

The frozen inventory rejects changed source hashes. A later documentation snapshot
needs a fresh reviewed inventory. Raw scientific data, original upstream manuals,
supplied literature PDFs and personal GUI runs are not repackaged in this library.
