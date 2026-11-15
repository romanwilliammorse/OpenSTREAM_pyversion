"""Faithful PDF export of native OpenSTREAM documentation; no numerical runs.

Use the Python PDF runtime (reportlab, pypdf, pillow, markdown-it-py). A frozen
inventory lists every source and hash. Source documents are never rewritten.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import html
import json
import os
from pathlib import Path
import re
import shutil
import sys
from urllib.parse import unquote, urlsplit
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tmp/pdfs/deps'))
from markdown_it import MarkdownIt
from pypdf import PdfReader, PdfWriter
from reportlab import Version as REPORTLAB_VERSION
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, Frame, PageTemplate, Paragraph,
    Spacer, Table, TableStyle, Image, Preformatted, CondPageBreak)
from PIL import Image as PILImage

BLUE = colors.HexColor('#287fb7')
DARK = colors.HexColor('#303b46')
MUTED = colors.HexColor('#627381')
LIGHT = colors.HexColor('#edf3f7')
MD = MarkdownIt('commonmark').enable('table').enable('strikethrough')
FONT_DIR = Path('C:/Windows/Fonts')
for name, filename in [('Body','segoeui.ttf'), ('BodyBold','segoeuib.ttf'),
    ('BodyItalic','segoeuii.ttf'), ('BodyBoldItalic','segoeuiz.ttf'),
    ('Mono','consola.ttf'), ('MonoBold','consolab.ttf')]:
    pdfmetrics.registerFont(TTFont(name, str(FONT_DIR / filename)))
pdfmetrics.registerFontFamily('Body',normal='Body',bold='BodyBold',italic='BodyItalic',boldItalic='BodyBoldItalic')
pdfmetrics.registerFontFamily('Mono',normal='Mono',bold='MonoBold',italic='Mono',boldItalic='MonoBold')

S = {}
S['body'] = ParagraphStyle('body', fontName='Body', fontSize=10.3, leading=14.5,
                          textColor=DARK, spaceAfter=7, splitLongWords=True)
S['table'] = ParagraphStyle('table',parent=S['body'],fontSize=9.0,leading=12.1,spaceAfter=0)
S['thead'] = ParagraphStyle('thead',parent=S['table'],fontName='BodyBold',textColor=colors.white)
S['small'] = ParagraphStyle('small',parent=S['body'],fontSize=8.2,leading=11.2,textColor=MUTED)
S['code'] = ParagraphStyle('code',fontName='Mono',fontSize=8.4,leading=11.0,
                          backColor=LIGHT,borderPadding=8,spaceBefore=4,spaceAfter=10)
for level, size in [(1,22),(2,15),(3,12.2),(4,10.7),(5,10.3),(6,10.3)]:
    S[f'h{level}'] = ParagraphStyle(f'h{level}',parent=S['body'],fontName='BodyBold',fontSize=size,
                                  leading=size*1.25,textColor=BLUE if level<3 else DARK,
                                  spaceBefore=14 if level>1 else 4,spaceAfter=8,keepWithNext=True)
S['card'] = ParagraphStyle('card',parent=S['body'],fontName='BodyBold',fontSize=10.2,
                           leading=13.5,spaceBefore=11,spaceAfter=5,keepWithNext=True,textColor=BLUE)
S['index_title'] = ParagraphStyle('index_title',parent=S['body'],keepWithNext=True,spaceAfter=3)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def clean(text):
    # Typography-only dash normalization; mathematical minus remains distinct.
    return str(text).translate(str.maketrans({'\u2010':'-','\u2011':'-','\u2012':'-',
        '\u2013':'-','\u2014':' - ','\u00a0':' '}))


def escape(text):
    return html.escape(clean(text), quote=False)


def slug(text):
    return re.sub(r'[^\w\- ]','',text.lower()).replace(' ','-')


class Document(BaseDocTemplate):
    def __init__(self, filename, meta, wide=False):
        self.meta = meta
        self.section = ''
        self.outline_count = 0
        self.anchors = set()
        self.heading_pages = []
        page = landscape(A4) if wide else A4
        super().__init__(str(filename),pagesize=page,leftMargin=42,rightMargin=42,
                         topMargin=45,bottomMargin=43,title=clean(meta['title']),
                         author='OpenSTREAM Python project',pageCompression=1,
                         allowSplitting=True)
        frame = Frame(self.leftMargin,self.bottomMargin,self.width,self.height,
                      leftPadding=0,rightPadding=0,topPadding=0,bottomPadding=0,id='normal')
        self.addPageTemplates(PageTemplate(id='normal',frames=frame,onPage=self.decorate))

    def decorate(self, canvas, doc):
        w,h = self.pagesize
        canvas.saveState()
        canvas.setStrokeColor(BLUE)
        canvas.setLineWidth(.7)
        canvas.line(self.leftMargin,h-30,w-self.rightMargin,h-30)
        canvas.setFont('BodyBold',8)
        canvas.setFillColor(BLUE)
        canvas.drawString(self.leftMargin,h-24,'OpenSTREAM | Native Python documentation')
        canvas.setFont('Body',7.4)
        canvas.setFillColor(MUTED)
        label=clean(self.meta.get('source','Documentation index'))
        while pdfmetrics.stringWidth(label,'Body',7.4)>self.width-55:
            label=label[:-2]
        canvas.drawString(self.leftMargin,25,label)
        canvas.drawRightString(w-self.rightMargin,25,str(doc.page))
        canvas.restoreState()

    def afterFlowable(self, flowable):
        if hasattr(flowable,'heading_level'):
            title=flowable.getPlainText()
            key=f'heading-{self.outline_count}'
            self.outline_count+=1
            self.canv.bookmarkPage(key)
            # Flat outline prevents hierarchy jumps in source fragments.
            self.canv.addOutlineEntry(title,key,level=0,closed=False)
            anchor=slug(title)
            if anchor not in self.anchors:
                self.canv.bookmarkPage(anchor)
                self.anchors.add(anchor)
            self.heading_pages.append({'title':title,'page':self.page})


class Exporter:
    def __init__(self, inventory, out):
        self.inventory=inventory
        self.out=out
        self.map={str((ROOT/d['source']).resolve()):d['pdf_relative_path'] for d in inventory['documents']}
        self.current=None
        self.audit=[]
        self.numeric_checks=[]
        self.render_text=[]

    def link(self, href):
        parsed=urlsplit(href)
        if parsed.scheme in ('http','https','mailto'):
            return href
        if href.startswith('#'):
            return href
        path=(ROOT/self.current['source']).parent/unquote(parsed.path)
        resolved=str(path.resolve())
        if resolved in self.map:
            target=self.out/self.map[resolved]
            relative=os.path.relpath(target,(self.out/self.current['pdf_relative_path']).parent).replace('\\','/')
            return relative+('#'+parsed.fragment if parsed.fragment else '')
        # Keep raw source/data references auditable and portable via pinned GitHub.
        try:
            relative=path.resolve().relative_to(ROOT).as_posix()
        except ValueError:
            return href
        return 'https://github.com/romanwilliammorse/OpenSTREAM_pyversion/blob/'+self.inventory['source_commit']+'/'+relative+('#'+parsed.fragment if parsed.fragment else '')

    def inline(self, tokens):
        result=[]
        for t in tokens or []:
            if t.type=='text':
                result.append(escape(t.content))
                self.render_text.append(clean(t.content))
            elif t.type in ('softbreak','hardbreak'):
                result.append('<br/>' if t.type=='hardbreak' else ' ')
            elif t.type=='code_inline':
                result.append('<font name="Mono" size="9">'+escape(t.content)+'</font>')
                self.render_text.append(clean(t.content))
            elif t.type in ('strong_open','strong_close','em_open','em_close','s_open','s_close'):
                result.append({'strong_open':'<b>','strong_close':'</b>','em_open':'<i>','em_close':'</i>','s_open':'<strike>','s_close':'</strike>'}[t.type])
            elif t.type=='link_open':
                result.append('<a href="'+html.escape(self.link(t.attrGet('href')),quote=True)+'" color="#206b9a">')
            elif t.type=='link_close':
                result.append('</a>')
            elif t.type=='image':
                result.append(escape(t.content))
            elif t.type=='html_inline':
                if t.content.lower() in ('<br>','<br/>','<br />'):
                    result.append('<br/>')
                elif re.fullmatch(r'</?(?:sup|sub|b|i)>',t.content):
                    result.append(t.content)
                else:
                    result.append(escape(t.content))
                    self.render_text.append(clean(t.content))
            else:
                raise ValueError(f'Unhandled inline token {t.type} in {self.current["source"]}')
        return ''.join(result)

    def paragraph(self, value, style='body', **kwargs):
        return Paragraph(value, S[style], **kwargs)

    def heading(self, value, level):
        p=self.paragraph(value,f'h{min(level,6)}')
        p.heading_level=level
        return p

    def intro(self, meta):
        return [self.paragraph(escape(meta['status_label'])+' | Source snapshot '+self.inventory['source_commit'][:12],'small')]

    def table(self, rows, width):
        n=len(rows[0])
        if n==7 and 'Requirement' in rows[0][1]:
            weights=[.12,.28,.13,.12,.11,.11,.13]
        elif n==5 and 'Upstream' in rows[0][0]:
            weights=[.17,.13,.25,.25,.20]
        elif n==3:
            weights=[.30,.27,.43]
        else:
            # Allocate by content size, with floors so status/numeric columns remain readable.
            lengths=[max(len(re.sub('<[^>]*>','',row[i])) for row in rows) for i in range(n)]
            weights=[max(12,min(110,x))**.6 for x in lengths]
            total=sum(weights)
            weights=[x/total for x in weights]
        weights=[x/sum(weights) for x in weights]
        data=[[self.paragraph(cell,'thead' if r==0 else 'table') for cell in row] for r,row in enumerate(rows)]
        table=Table(data,colWidths=[width*x for x in weights],repeatRows=1,hAlign='LEFT',splitByRow=1,splitInRow=0)
        table.setStyle(TableStyle([
            ('BACKGROUND',(0,0),(-1,0),BLUE),('VALIGN',(0,0),(-1,-1),'TOP'),
            ('LEFTPADDING',(0,0),(-1,-1),6),('RIGHTPADDING',(0,0),(-1,-1),6),
            ('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6),
            ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,LIGHT]),
            ('LINEBELOW',(0,0),(-1,0),.6,BLUE),
            ('LINEBELOW',(0,1),(-1,-1),.25,colors.HexColor('#d9e1e7'))]))
        return table

    def markdown_story(self, meta, width):
        text=(ROOT/meta['source']).read_text(encoding='utf-8-sig')
        tokens=MD.parse(text)
        story=self.intro(meta)
        i=0
        lists=[]
        item_first=[]
        while i<len(tokens):
            t=tokens[i]
            if t.type=='heading_open':
                story.append(self.heading(self.inline(tokens[i+1].children),int(t.tag[1:])))
                i+=3
            elif t.type=='paragraph_open':
                inline=tokens[i+1]
                children=inline.children or []
                if len(children)==1 and children[0].type=='image':
                    img=children[0]
                    path=(ROOT/meta['source']).parent/img.attrGet('src')
                    with PILImage.open(path) as im:
                        iw,ih=im.size
                    scale=min(width/iw,430/ih)
                    story.append(Image(str(path),iw*scale,ih*scale,hAlign='CENTER'))
                    story.append(self.paragraph(escape(img.content),'small'))
                else:
                    value=self.inline(children)
                    if item_first:
                        depth=len(lists)
                        style=ParagraphStyle(f'list{depth}',parent=S['body'],leftIndent=14*depth,firstLineIndent=0,bulletIndent=14*(depth-1))
                        bullet=None
                        if item_first[-1]:
                            bullet=str(lists[-1]['next'])+'.' if lists[-1]['ordered'] else '\u2022'
                            lists[-1]['next']+=1
                            item_first[-1]=False
                        story.append(Paragraph(value,style,bulletText=bullet))
                    else:
                        story.append(self.paragraph(value))
                i+=3
            elif t.type in ('bullet_list_open','ordered_list_open'):
                lists.append({'ordered':t.type=='ordered_list_open','next':int(t.attrGet('start') or 1)})
                i+=1
            elif t.type in ('bullet_list_close','ordered_list_close'):
                lists.pop();i+=1
            elif t.type=='list_item_open':
                item_first.append(True);i+=1
            elif t.type=='list_item_close':
                item_first.pop();i+=1
            elif t.type in ('fence','code_block'):
                code=clean(t.content).rstrip('\n')
                self.render_text.append(code)
                maxlen=int((width-20)/pdfmetrics.stringWidth('M','Mono',8.4))
                story.append(Preformatted(code,S['code'],maxLineLength=maxlen,splitChars=' /,;'))
                i+=1
            elif t.type=='table_open':
                rows=[];row=[];i+=1
                while tokens[i].type!='table_close':
                    u=tokens[i]
                    if u.type=='tr_open':row=[]
                    elif u.type=='inline':row.append(self.inline(u.children))
                    elif u.type=='tr_close':rows.append(row)
                    i+=1
                story.extend([Spacer(1,3),self.table(rows,width),Spacer(1,10)])
                i+=1
            elif t.type=='hr':
                story.append(Spacer(1,10));i+=1
            elif t.type in ('blockquote_open','blockquote_close'):
                i+=1
            elif t.type=='html_block':
                story.append(self.paragraph(escape(t.content)))
                self.render_text.append(clean(t.content));i+=1
            else:
                raise ValueError(f'Unhandled block token {t.type}: {meta["source"]}')
        return story

    def csv_story(self, meta, width):
        with (ROOT/meta['source']).open(encoding='utf-8-sig',newline='') as f:
            reader=csv.DictReader(f); rows=list(reader); fields=reader.fieldnames
        story=self.intro(meta)+[self.heading(escape(meta['title']),1)]
        story.append(self.paragraph(f'Complete source export: <b>{len(rows)} records, {len(fields)} fields per record</b>. Record layouts preserve every field. An empty source cell is displayed as [empty].','body'))
        story.append(self.paragraph('Status values are unchanged. Declaration presence is not numerical certification. Read the acceptance plan and each record\'s stated scope.','small'))
        for index,row in enumerate(rows,1):
            story.append(CondPageBreak(100))
            key=row.get('id') or row.get('run_id') or str(index)
            heading=self.paragraph(f'{index:03d} / {len(rows)} &nbsp; '+escape(key),'card')
            story.append(heading)
            for field in fields:
                value=row[field]
                if value is None:raise ValueError('Malformed CSV row')
                self.render_text.append(clean(value))
                # Inline, labeled full-width fields avoid squeezing wide CSVs.
                body=escape(value).replace('\n','<br/>') if value else '[empty]'
                story.append(self.paragraph('<b>'+escape(field)+':</b> '+body,'table'))
            story.append(Spacer(1,8))
        return story,len(rows),len(fields)

    def build_one(self, meta):
        source=ROOT/meta['source']
        if digest(source)!=meta['source_sha256']:
            raise ValueError('Source changed after inventory: '+meta['source'])
        dest=self.out/meta['pdf_relative_path'];dest.parent.mkdir(parents=True,exist_ok=True)
        self.current=meta;self.render_text=[]
        stats={**meta}
        if meta['kind']=='existing_pdf':
            shutil.copyfile(source,dest)
            stats['copied_unchanged']=digest(dest)==meta['source_sha256']
            stats['headings']=[]
        else:
            wide=source.name in ('ACCEPTANCE_MATRIX.md','FEATURE_MAP.md','threefield_review.md','summary.md')
            doc=Document(dest,meta,wide)
            if meta['kind']=='markdown':
                story=self.markdown_story(meta,doc.width)
            else:
                story,rows,fields=self.csv_story(meta,doc.width)
                stats.update(csv_records=rows,csv_fields=fields)
            doc.build(story)
            stats['headings']=doc.heading_pages
        reader=PdfReader(dest)
        extracted=[]
        for n,page in enumerate(reader.pages,1):
            lines=(page.extract_text() or '').splitlines()
            if meta['kind']!='existing_pdf':
                if lines[0]!='OpenSTREAM | Native Python documentation' or lines[2]!=str(n):
                    raise ValueError('Unexpected header/footer extraction order')
                # Decorations are drawn first. Exclude them before checking prose
                # that crosses a page break; retain every source-content line.
                lines=lines[3:]
            extracted.append('\n'.join(lines))
        text='\n'.join(extracted)
        # Every numeric token in rendered source text must survive PDF extraction.
        # Whitespace is removed so harmless line wrapping inside long paths/hashes
        # does not conceal a lost or changed quantity.
        wanted=' '.join(self.render_text)
        flatten=lambda v:re.sub(r'\s+','',v)
        flat=flatten(text)
        numbers=set(re.findall(r'(?<![A-Za-z0-9])[+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?',wanted))
        missing=[x for x in sorted(numbers) if flatten(x) not in flat]
        missing_text=[x for x in self.render_text if flatten(x) and flatten(x) not in flat]
        stats.update(pages=len(reader.pages),pdf_sha256=digest(dest),numeric_tokens_checked=len(numbers),missing_numeric_tokens=missing)
        if missing:raise ValueError(f'Numeric text missing from {dest.name}: {missing[:20]}')
        stats.update(source_text_fragments_checked=len(self.render_text),missing_text_fragments=missing_text)
        if missing_text:raise ValueError(f'Source text missing from {dest.name}: {missing_text[:5]}')
        self.audit.append(stats)
        print(f'{len(self.audit):02d}/50 {dest.name}: {len(reader.pages)} pages',flush=True)

    def index_story(self, page_starts=None):
        meta={'source':'PDF_INDEX','title':'OpenSTREAM documentation library','status_label':'Complete native-port documentation snapshot','pdf_relative_path':'00_INDEX.pdf'}
        self.current=meta
        story=[self.heading('OpenSTREAM',1),self.heading('Reports and documentation',2)]
        story.append(self.paragraph('Native Python port | PDF library | 14 November 2026','body'))
        story.append(self.paragraph('This library preserves the full text of 45 maintained documents, four complete CSV annexes, and the saved pilot comparison figure. The combined volume has a navigation bookmark for each document. Individual PDFs are arranged in numbered folders.','body'))
        story.append(self.paragraph('<b>Scientific status is unchanged.</b> Full MATLAB parity and uncertainty-qualified experimental validation remain incomplete. Read PARITY_STATUS, ACCEPTANCE_MATRIX and BARTOLOMEY_PILOT for the current checkpoint. Earlier verification reports remain scoped or historical evidence; they do not replace later results.','body'))
        story.append(self.paragraph('Source snapshot: '+self.inventory['source_commit']+'<br/>Export includes 81 complete matrix records, 143 option entries, 585 method entries and 40 pilot-run records. These are overlapping inventories, not additive completion scores.','small'))
        story.append(self.paragraph('All source headings, prose, code, tables and numeric values are retained. Typography and line wrapping change for printing; prose is not silently updated. Wide CSVs use labeled records; [empty] marks an empty source cell. Unicode mathematical minus is preserved.','small'))
        story.append(self.paragraph('Original MATLAB/database repository manuals, supplied literature PDFs, raw numerical arrays/JSON, execution logs, and personal GUI runs are outside this documentation export. Links to raw evidence target the pinned public repository. The source files and hashes are listed in DOCUMENT_MANIFEST.json.','small'))
        category=None
        labels={'01-start-and-use':'Getting started and use','02-current-status-and-acceptance':'Current status and acceptance','03-bartolomey-experimental-pilot':'Bartolomey experimental pilot','04-baselines-and-reference-evidence':'Baselines and reference evidence','05-translation-and-numerical-reviews':'Translation and numerical reviews','06-gui-and-release-records':'GUI and release records','07-complete-tabular-annexes':'Complete tabular annexes'}
        for item in self.audit:
            if item['category']!=category:
                category=item['category']
                story.append(self.heading(escape(labels.get(category,category)),2))
            target=item['pdf_relative_path']
            details=f"{item['pages']} pages | {item['status_label']}"
            if page_starts is not None:details+=f" | Combined page {page_starts[target]+1}"
            story.append(self.paragraph('<a href="'+html.escape(target,quote=True)+'" color="#206b9a"><b>'+escape(item['title'])+'</b></a>','index_title'))
            story.append(self.paragraph(escape(details)+'<br/>'+escape(item['source']),'small'))
        return meta,story

    def finish(self):
        # Index first, then add exact combined-volume start pages and rebuild.
        meta,story=self.index_story()
        index_path=self.out/'00_INDEX.pdf'
        Document(index_path,meta).build(story)
        index_pages=len(PdfReader(index_path).pages)
        starts={};offset=index_pages
        for d in self.audit:
            starts[d['pdf_relative_path']]=offset;offset+=d['pages']
        meta,story=self.index_story(starts)
        Document(index_path,meta).build(story)
        if len(PdfReader(index_path).pages)!=index_pages:
            raise ValueError('Index pagination changed when adding page references')
        writer=PdfWriter()
        writer.append(str(index_path),outline_item='Documentation index')
        for item in self.audit:
            writer.append(str(self.out/item['pdf_relative_path']),outline_item=clean(item['title']))
        # Convert relative PDF links into in-volume destinations for the binder.
        from pypdf.generic import NameObject, DictionaryObject, ArrayObject, NullObject
        for page in writer.pages:
            for ref in page.get('/Annots',[]):
                annotation=ref.get_object();action=annotation.get('/A')
                if not action or action.get('/S')!='/URI':continue
                uri=str(action.get('/URI',''));base=unquote(uri.split('#')[0]).replace('\\','/').split('/')[-1]
                candidates=[x for x in self.audit if Path(x['pdf_relative_path']).name==base]
                if len(candidates)==1 and base.endswith('.pdf') and not uri.startswith(('http:','https:')):
                    target=starts[candidates[0]['pdf_relative_path']]
                    annotation[NameObject('/A')]=DictionaryObject({NameObject('/S'):NameObject('/GoTo'),NameObject('/D'):ArrayObject([writer.pages[target].indirect_reference,NameObject('/Fit')])})
        writer.add_metadata({'/Title':'OpenSTREAM Python - Complete Reports and Documentation','/Author':'OpenSTREAM Python project','/Subject':'Preserved native documentation, acceptance matrix, complete annexes and experimental pilot'})
        combined=self.out/'OpenSTREAM_Complete_Documentation.pdf'
        with combined.open('wb') as f:writer.write(f)
        manifest={**self.inventory,'created_utc':datetime.now(timezone.utc).isoformat(),'exporter':'tools/export_documentation_pdf.py','exporter_sha256':digest(Path(__file__)),'reportlab_version':REPORTLAB_VERSION,'documents':self.audit,'index_pages':index_pages,'combined_pages':len(writer.pages),'combined_sha256':digest(combined),'verification':{'source_hashes_matched':True,'all_numeric_tokens_retained':True,'rendered_layout_review':'pending'}}
        (self.out/'DOCUMENT_MANIFEST.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
        (self.out/'README.txt').write_text('OpenSTREAM documentation PDF library\n\nOpen 00_INDEX.pdf or OpenSTREAM_Complete_Documentation.pdf.\nNumbered folders contain individual PDFs. DOCUMENT_MANIFEST.json records exact sources, hashes and counts.\n\nOriginal source content and scientific status have not been rewritten. Earlier reports remain scoped historical evidence.\n',encoding='utf-8')
        print(f'Combined: {len(writer.pages)} pages. Library: 52 PDFs.',flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inventory',type=Path,default=ROOT/'tmp/pdfs/source_inventory.json')
    parser.add_argument('--output',type=Path,default=ROOT/'output/pdf/OpenSTREAM_Documentation')
    args=parser.parse_args()
    inventory=json.loads(args.inventory.read_text(encoding='utf-8'))
    args.output.mkdir(parents=True,exist_ok=True)
    exporter=Exporter(inventory,args.output)
    # Category order keeps the combined volume navigable; within-category source
    # order is retained, and annexes remain separate complete documents.
    items=sorted(inventory['documents'],key=lambda d:(d['category'],d['order']))
    for item in items:exporter.build_one(item)
    exporter.finish()


if __name__=='__main__':
    main()
