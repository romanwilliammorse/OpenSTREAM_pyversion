"""Digitize visible, identifiable plotted curves from the supplied NURETH paper.

These are raster plot coordinates, NEVER original MATLAB numerical arrays.
Source hashes, axis calibrations, exclusions and conservative pixel-reading
bounds accompany every value. No predicted native output enters extraction.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image
from pypdf import PdfReader

PAPER_SHA256='f72e78c41036f84db849fb080187562777e6b6696b407b6bcce2b8ca9d11ada1'
COLORS={'blue':(0,114,189),'orange':(217,83,25),'yellow':(237,177,32),'purple':(126,47,142),'red':(255,0,0)}
# Pixel coordinates refer to the original embedded PNG, origin upper left.
# Two inspected axis ticks define each linear calibration; no curve fitting.
CALIBRATIONS={
 'fig3_heat':{'page':9,'image':'Image154.png','figure':3,'panel':'wall_heat_flux','x0':77,'x1':485,'xv0':0.,'xv1':5.,'y0':455,'y1':38,'yv0':0.,'yv1':1.e6,'unit':'W/m^2','scale':1.,'legend':[0,0,0,0]},
 'fig3_mass':{'page':9,'image':'Image154.png','figure':3,'panel':'liquid_mass_flow','x0':658,'x1':1067,'xv0':0.,'xv1':5.,'y0':455,'y1':38,'yv0':0.,'yv1':.08,'unit':'kg/s','scale':1.,'legend':[860,49,1097,247]},
 'fig3_void':{'page':9,'image':'Image154.png','figure':3,'panel':'void_and_quality','x0':1240,'x1':1648,'xv0':0.,'xv1':5.,'y0':455,'y1':38,'yv0':0.,'yv1':1.,'unit':'1','scale':1.,'legend':[1377,331,1679,444]},
 'fig4_thickness':{'page':9,'image':'Image155.png','figure':4,'panel':'film_dimensions','x0':79,'x1':489,'xv0':0.,'xv1':5.,'y0':453,'y1':29,'yv0':0.,'yv1':1.5,'unit':'m','scale':.001,'legend':[205,40,519,126]},
 'fig4_velocity':{'page':9,'image':'Image155.png','figure':4,'panel':'field_velocities','x0':662,'x1':1073,'xv0':0.,'xv1':5.,'y0':453,'y1':29,'yv0':0.,'yv1':30.,'unit':'m/s','scale':1.,'legend':[672,40,898,211]},
 'fig4_frequency':{'page':9,'image':'Image155.png','figure':4,'panel':'wave_frequency','x0':1245,'x1':1655,'xv0':0.,'xv1':5.,'y0':453,'y1':29,'yv0':0.,'yv1':250.,'unit':'Hz','scale':1.,'legend':[1258,40,1450,100]},
}


def sha(data):return hashlib.sha256(data).hexdigest()
def xval(c,p):return c['xv0']+(p-c['x0'])*(c['xv1']-c['xv0'])/(c['x1']-c['x0'])
def yval(c,p):return (c['yv0']+(p-c['y0'])*(c['yv1']-c['yv0'])/(c['y1']-c['y0']))*c['scale']


def row_clusters(rows):
    if not len(rows):return []
    return np.split(rows,np.where(np.diff(rows)>2)[0]+1)


def extract(pdf_path,output):
    data=pdf_path.read_bytes()
    if sha(data)!=PAPER_SHA256:raise ValueError('Paper hash differs from inspected source')
    if output.exists():raise FileExistsError(output)
    reader=PdfReader(pdf_path)
    images={}
    image_meta={}
    for pageno in (9,):
        for item in reader.pages[pageno-1].images:
            if item.name in ('Image154.png','Image155.png'):
                images[item.name]=np.asarray(item.image.convert('RGB'))
                image_meta[item.name]={'sha256':sha(item.data),'size':list(item.image.size),'pdf_page':pageno}
    specs=[]
    targets=[.25,.5,1.,1.5,2.,2.5,3.,3.25,3.75,4.,4.5,5.,5.25]
    specs.append(('fig3_heat','wall_heat_flux','blue',targets,None,'single',False))
    # Colors/line identities are transcribed from each panel's visible legend.
    for color,name in [('blue','mixture_liquid_mass_flow'),('orange','twofluid_liquid_mass_flow')]:
        specs.append(('fig3_mass',name,color,targets,None,'single',False))
    for color,name in [('blue','mixture_void_fraction'),('orange','twofluid_void_fraction')]:
        specs.append(('fig3_void',name,color,[1.,1.5,2.,2.5,3.,3.75,4.5,5.25],(.80,1.01),'single',False))
    for color,name in [('blue','mixture_vapor_quality'),('orange','twofluid_vapor_quality')]:
        specs.append(('fig3_void',name,color,[1.,1.5,2.,2.5,3.,3.75,4.5,5.25],(0.,.78),'single',False))
    for panel,color,series,selector,require_two,band in [
      ('fig3_mass','yellow','threefield_film_mass_flow','upper',True,None),
      ('fig3_mass','yellow','threefield_drop_mass_flow','lower',True,None),
      ('fig3_mass','purple','fourfield_base_mass_flow','lower',True,None),
      ('fig3_mass','purple','fourfield_wave_mass_flow','upper',True,None),
      ('fig4_thickness','yellow','threefield_film_thickness','single',False,None),
      ('fig4_thickness','purple','fourfield_base_thickness','lower',True,None),
      ('fig4_thickness','purple','fourfield_wave_amplitude','upper',True,None),
      ('fig4_velocity','blue','mixture_vapor_velocity','single',False,None),
      ('fig4_velocity','orange','twofluid_liquid_velocity','single',False,None),
      ('fig4_velocity','yellow','threefield_film_velocity','lower',True,None),
      ('fig4_velocity','yellow','threefield_drop_velocity','upper',True,None),
      ('fig4_velocity','purple','fourfield_base_velocity','lower',True,None),
      ('fig4_velocity','purple','fourfield_wave_velocity','upper',True,None),
    ]:
        # Yellow film/drop mass-flow curves cross. Only known branch-separated
        # intervals are extracted and explicitly named, never paired by a model.
        sample=[1.,1.25,1.5] if series in ('threefield_film_mass_flow','threefield_drop_mass_flow') else [1.,1.25,1.5,2.,2.5,3.,4.,4.5,5.]
        specs.append((panel,series,color,sample,band,selector,require_two))
    # The frequency curves are unambiguous and largely unobscured: keep every
    # fourth visible image column. Missing dotted-line columns remain missing.
    frequency_x=[xval(CALIBRATIONS['fig4_frequency'],p) for p in range(1308,1696,4)]
    specs.extend([('fig4_frequency','fourfield_wave_frequency','purple',frequency_x,None,'single',False),
                  ('fig4_frequency','fourfield_equilibrium_wave_frequency','red',frequency_x,None,'single',False)])
    points=[];exclusions=[]
    for key,series,color,xs,band,selector,require_two in specs:
        c=CALIBRATIONS[key];im=images[c['image']]
        mask=np.all(im==COLORS[color],axis=2)
        xlo,ylo,xhi,yhi=c['legend'];mask[ylo:yhi+1,xlo:xhi+1]=False
        for desired_x in xs:
            xp=int(round(c['x0']+(desired_x-c['xv0'])*(c['x1']-c['x0'])/(c['xv1']-c['xv0'])))
            rows=np.flatnonzero(mask[:,xp])
            rows=rows[(rows>min(c['y0'],c['y1']))&(rows<max(c['y0'],c['y1']))]
            if band is not None:rows=np.array([p for p in rows if band[0]<=yval(c,p)/c['scale']<=band[1]],dtype=int)
            clusters=row_clusters(rows)
            if not clusters or (require_two and len(clusters)!=2) or (selector=='single' and len(clusters)!=1):
                exclusions.append({'series':series,'requested_coordinate_m':desired_x,'pixel_x':xp,'reason':'not_uniquely_visible_at_sample_column','candidate_clusters':len(clusters)})
                continue
            chosen=clusters[0] if selector in ('upper','single') else clusters[-1]
            yp=float(np.median(chosen))
            points.append({'figure':c['figure'],'panel':c['panel'],'series':series,
                'coordinate':xval(c,xp),'coordinate_name':'Elevation','coordinate_unit':'m',
                'value':yval(c,yp),'unit':c['unit'],'pixel_x':xp,'pixel_y':yp,
                'coordinate_reading_bound':abs(xval(c,xp+3)-xval(c,xp)),
                'value_reading_bound':abs(yval(c,yp+3)-yval(c,yp)),
                'source':'paper_raster_digitization','image':c['image']})
    output.mkdir(parents=True)
    with (output/'digitized_curves.csv').open('w',encoding='utf-8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(points[0]));writer.writeheader();writer.writerows(points)
    metadata={'schema':'openstream-paper-raster-reference-v1','paper_filename':pdf_path.name,'paper_sha256':PAPER_SHA256,
      'source_type':'digitized_published_raster_curves_not_MATLAB_arrays','images':image_meta,
      'axis_calibrations':CALIBRATIONS,'method':'Inspected linear axis ticks; exact MATLAB line RGB; visible median row at fixed image column; legend rectangles masked. No native prediction informs extraction.',
      'reading_bound_policy':'Conservative +/-3 image pixels per axis includes line thickness and inspected tick placement. It is a graphical reading envelope, not a confidence interval, numerical acceptance tolerance, or experimental uncertainty.',
      'limitations':['No full-precision arrays or original producing runtime metadata are present in the paper.','Only named, unambiguously separated visible curves/locations are retained.','Overlapping/hidden/dashed-gap samples are explicitly excluded; no filling or interpolation of missing plotted points.','Pixel-source positions remain in output for manual review; raster references support graphical consistency only.'],
      'points':len(points),'exclusions':exclusions,'extractor_sha256':sha(Path(__file__).read_bytes())}
    (output/'metadata.json').write_text(json.dumps(metadata,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps({'points':len(points),'exclusions':len(exclusions),'series':{s:sum(p['series']==s for p in points) for s in sorted({p['series'] for p in points})}},indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--paper',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();extract(args.paper,args.output)
