"""Recover named Figure 6/7 graphical references, never MATLAB result arrays.

No native prediction is loaded or used for marker matching or curve identity.
Requires the independently inspected, hash-pinned user-supplied paper.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import numpy as np
from pypdf import PdfReader

PAPER_SHA256 = 'f72e78c41036f84db849fb080187562777e6b6696b407b6bcce2b8ca9d11ada1'
COLORS = {'blue': (0,114,189), 'orange': (217,83,25), 'yellow': (237,177,32), 'purple': (126,47,142)}
GROUPS = {'blue':500, 'orange':750, 'yellow':1000, 'purple':2000}
CAL = {
 'base': dict(image='Image173.png', page=11, x0=74, x1=528, xv0=0., xv1=.4, y0=479, y1=42, yv0=0., yv1=.4, scale=.001, unit='m', field='BaseThickness', legend=[277,347,522,467]),
 'velocity': dict(image='Image174.png', page=11, x0=59, x1=513, xv0=0., xv1=10., y0=479, y1=42, yv0=0., yv1=10., scale=1., unit='m/s', field='WaveVelocity', legend=[164,56,408,174]),
 'number_density': dict(image='Image175.png', page=11, x0=63, x1=456, xv0=0., xv1=10., y0=476, y1=100, yv0=0., yv1=10., scale=1., unit='1/m', field='WaveNumberDensity', legend=[168,345,412,463]),
 'velocity_048': dict(image='Image185.png', page=12, x0=252, x1=515, xv0=0., xv1=200., y0=438, y1=40, yv0=0., yv1=9., scale=1., unit='m/s', quantity='wave_velocity', quality=.48, legend=[66,52,293,169]),
 'velocity_088': dict(image='Image185.png', page=12, x0=889, x1=1152, xv0=0., xv1=200., y0=438, y1=40, yv0=0., yv1=9., scale=1., unit='m/s', quantity='wave_velocity', quality=.88, legend=[955,51,1183,168]),
 'period_048': dict(image='Image186.png', page=12, x0=258, x1=520, xv0=0., xv1=200., y0=406, y1=8, yv0=30., yv1=90., scale=.001, unit='s', quantity='wave_period', quality=.48, legend=[72,20,300,137]),
 'period_088': dict(image='Image186.png', page=12, x0=897, x1=1160, xv0=0., xv1=200., y0=406, y1=8, yv0=0., yv1=200., scale=.001, unit='s', quantity='wave_period', quality=.88, legend=[711,21,939,138]),
}

def sha(data): return hashlib.sha256(data).hexdigest()
def xvalue(c,p): return (c['xv0']+(p-c['x0'])*(c['xv1']-c['xv0'])/(c['x1']-c['x0']))*c['scale']
def yvalue(c,p): return (c['yv0']+(p-c['y0'])*(c['yv1']-c['yv0'])/(c['y1']-c['y0']))*c['scale']
def components(mask):
    points=set(map(tuple,np.argwhere(mask).tolist()))
    while points:
        seed=points.pop();todo=[seed];found=[seed]
        while todo:
            y,x=todo.pop()
            for dy in (-1,0,1):
                for dx in (-1,0,1):
                    p=(y+dy,x+dx)
                    if p in points:
                        points.remove(p);todo.append(p);found.append(p)
        yield np.array(found)

def write_csv(path,rows):
    with path.open('w',newline='',encoding='utf-8') as handle:
        writer=csv.DictWriter(handle,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)

def extract(paper, database, output):
    if sha(paper.read_bytes())!=PAPER_SHA256: raise ValueError('Uninspected source paper hash')
    if output.exists(): raise FileExistsError(output)
    reader=PdfReader(paper);images={};image_metadata={}
    for c in CAL.values():
        if c['image'] in images:continue
        item=next(i for i in reader.pages[c['page']-1].images if i.name==c['image'])
        images[c['image']]=np.asarray(item.image.convert('RGB'))
        image_metadata[c['image']]={'sha256':sha(item.data),'size':list(item.image.size),'pdf_page':c['page']}
    wurtz=database/'+Wurtz1978/+src/Wurtz1978.xml'
    sawai=database/'+Sawai1989/+src/Sawai1989.xml'
    records=[]
    for entry in ET.parse(wurtz).getroot().findall('dataset'):
        if entry.findtext('TestName')=='TS 20':
            records.append({key:float(entry.findtext(key)) if entry.findtext(key) else float('nan') for key in ['TestID','MassFlux','Pressure','BaseThickness','WaveVelocity','WaveNumberDensity']})
    sawai_ids={(float(e.findtext('Xout')),float(e.findtext('MassFlux'))):int(e.findtext('TestID')) for e in ET.parse(sawai).getroot().findall('dataset') if int(e.findtext('TestID')) in (1,2,5,6)}
    points=[];exclusions=[]
    for panel in ('base','velocity','number_density'):
        c=CAL[panel];im=images[c['image']]
        for color,rgb in COLORS.items():
            mask=np.all(im==rgb,axis=2)
            lx,ly,rx,ry=c['legend'];mask[ly:ry+1,lx:rx+1]=False
            mask[:43,:]=False;mask[479:,:]=False;mask[:,:int(c['x0'])+1]=False
            for comp in components(mask):
                lo=comp.min(axis=0);hi=comp.max(axis=0);height,width=hi-lo+1
                yp,xp=(lo+hi)/2
                # Full circle-dot connected components are 5-6 pixels wide;
                # full asterisks are 13-15 pixels wide. Fragments are excluded.
                if 4<=width<=7 and 4<=height<=7 and len(comp)>=13:
                    marker='prediction_dot'
                elif panel=='base' and 11<=width<=17 and 11<=height<=17 and len(comp)>=24:
                    marker='measured_film_flow_correlation_star'
                else:
                    exclusions.append(dict(figure=6,panel=panel,color=color,pixel_bbox=[int(lo[1]),int(lo[0]),int(hi[1]),int(hi[0])],reason='marker_fragment_overlap_or_unclassified_shape',pixels=len(comp)))
                    continue
                measured=xvalue(c,xp);bound=abs(xvalue(c,xp+3)-measured)
                candidates=[int(r['TestID']) for r in records if r['MassFlux']==GROUPS[color] and abs(r[c['field']]-measured)<=bound]
                points.append(dict(figure=6,panel=panel,series=marker,mass_flux_kg_m2_s=GROUPS[color],pressure_Pa=7000000,
                    test_id=candidates[0] if len(candidates)==1 else '',candidate_test_ids=';'.join(map(str,candidates)),
                    coordinate=measured,coordinate_name='measured_'+c['field'],coordinate_unit=c['unit'],value=yvalue(c,yp),unit=c['unit'],
                    pixel_x=xp,pixel_y=yp,coordinate_reading_bound=bound,value_reading_bound=abs(yvalue(c,yp+3)-yvalue(c,yp)),
                    source='paper_raster_digitization',image=c['image']))
    curves=[]
    for panel in ('velocity_048','velocity_088','period_048','period_088'):
        c=CAL[panel];im=images[c['image']];mask=np.all(im==0,axis=2)
        lx,ly,rx,ry=c['legend'];mask[ly:ry+1,lx:rx+1]=False
        for target in (65,85,105,145,165,185):
            xp=round(c['x0']+target*(c['x1']-c['x0'])/200)
            rows=np.flatnonzero(mask[:,xp]);rows=rows[(rows>c['y1']+2)&(rows<c['y0']-2)]
            clusters=np.split(rows,np.where(np.diff(rows)>2)[0]+1) if len(rows) else []
            if len(clusters)!=2:
                exclusions.append(dict(figure=7,panel=panel,requested_coordinate=target,pixel_x=xp,reason='both_model_branches_not_uniquely_visible',candidate_clusters=len(clusters)))
                continue
            for index,cluster in enumerate(clusters):
                # Legends and inspected non-crossing branches identify these;
                # sample columns avoid measurement-star centers. No native fits.
                mass_flux=(500,300)[index] if c['quantity']=='wave_velocity' else (300,500)[index]
                yp=float(np.median(cluster));coordinate=(xp-c['x0'])*200/(c['x1']-c['x0'])
                curves.append(dict(figure=7,panel=panel,series=c['quantity'],test_id=sawai_ids[(c['quality'],mass_flux)],
                    outlet_quality=c['quality'],mass_flux_kg_m2_s=mass_flux,line_style='solid' if mass_flux==300 else 'dashed',
                    coordinate=coordinate,coordinate_name='distance_from_heated_exit_over_diameter',coordinate_unit='1',
                    value=yvalue(c,yp),unit=c['unit'],pixel_x=xp,pixel_y=yp,coordinate_reading_bound=3*200/(c['x1']-c['x0']),
                    value_reading_bound=abs(yvalue(c,yp+3)-yvalue(c,yp)),source='paper_raster_digitization',image=c['image']))
    output.mkdir(parents=True)
    write_csv(output/'digitized_figure6.csv',sorted(points,key=lambda p:(p['panel'],p['mass_flux_kg_m2_s'],p['series'],p['coordinate'])))
    write_csv(output/'digitized_figure7.csv',curves)
    metadata=dict(schema='openstream-paper-raster-reference-v1',paper_sha256=PAPER_SHA256,source_type='digitized_published_raster_not_MATLAB_arrays',
      images=image_metadata,axis_calibrations=CAL,extractor_sha256=sha(Path(__file__).read_bytes()),
      database_xml_sha256={str(p.relative_to(database)):sha(p.read_bytes()) for p in (wurtz,sawai)},
      figure6_method='Exact legend RGB; eight-connected colored components; whole dot/asterisk morphology classified separately. Case identity uses only mass-flux color and measured horizontal value within 3-pixel reading bound. Ambiguous/missing IDs remain blank; no native predictions used.',
      figure7_method='Inspected axis ticks and legends; exact black pixels at preselected columns away from measurement stars. Only two separately visible model branches are accepted. Solid G300 and dashed G500 identified from non-crossing curve branches, independently of native results.',
      reading_bound_policy='Conservative +/-3 original image pixels each axis; not statistical uncertainty, measurement uncertainty or a numerical equivalence tolerance. Propagate horizontal and vertical bounds when comparing curves.',
      figure6_points=len(points),figure7_points=len(curves),exclusions=exclusions,
      limitations=['Raster reading only; original paper model arrays and producing revision are unavailable.', 'Base-thickness stars are Le Corre2022 correlation using measured film flow; only dots are model predictions.', 'Overlapping/partially hidden markers are excluded. Duplicate measured values within a group preclude unique case pairing.', 'Figure7 period axis is milliseconds; exported values are converted to seconds.', 'Figure7 downstream coordinate is (z-0.8m)/0.004m for these cases; measurement points beyond the 1.648m channel are not extrapolated.', 'Paper states Sawai RELAXTW=0.2s while both historical/current companion scripts say 0.1s; these curves alone do not identify which input produced them.'])
    (output/'metadata.json').write_text(json.dumps(metadata,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'figure6_points':len(points),'figure7_points':len(curves),'exclusions':len(exclusions),'unmatched_figure6':sum(p['test_id']=='' for p in points)},indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--paper',type=Path,required=True)
    parser.add_argument('--database',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();extract(args.paper,args.database,args.output)
