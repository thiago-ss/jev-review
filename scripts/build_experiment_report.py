"""Build portable HTML and an optional publication PNG from captured evidence."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from jev_review.experiment_report import render_report

LABELS = {'auth-ownership': 'Ownership boundary', 'bounds': 'Index boundary', 'monetary-precision': 'Money precision', 'logging-secret': 'Secret logging'}


def build(source, destination, poster=False):
    evidence = json.loads(Path(source).read_text())
    rows = []
    for fixture in evidence['fixtures']:
        observed = fixture.get('observed', {})
        rows.append({'label': LABELS.get(fixture['pair_id'], fixture['pair_id']) + ' / ' + fixture['variant'], 'family': fixture['pair_id'], 'variant': fixture['variant'], 'expected': fixture['expected']['disposition'], 'choice': observed.get('disposition', 'unavailable'), 'expected_failure': fixture['expected']['dominant_failure_class'], 'observed_failure': observed.get('dominant_failure_class'), 'probabilities': observed.get('disposition_probabilities', {}), 'state': fixture['state'], 'evidence': fixture, 'error': fixture.get('failure')})
    models = sorted({f['model'] for f in evidence['fixtures'] if f.get('model')})
    metadata = {'model': ', '.join(models) or 'No completed provider responses', 'experiment': evidence}
    output = Path(destination)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_report(rows, metadata))
    if poster:
        draw_poster(rows, metadata, output.with_suffix('.png'))
    return output


def draw_poster(rows, metadata, output):
    # Build-time optional Pillow; the deployed bot and HTML have no dependency.
    from PIL import Image, ImageDraw, ImageFont
    fonts = Path('/System/Library/Fonts/Supplemental')
    if not fonts.exists():
        raise RuntimeError('Poster font directory unavailable; HTML is already built. Set up compatible fonts before exporting PNG.')
    def font(size, bold=False, serif=False):
        return ImageFont.truetype(str(fonts / ('Georgia.ttf' if serif else 'Arial Bold.ttf' if bold else 'Arial.ttf')), size)
    image = Image.new('RGB', (1800, 1440), '#f5f4ed')
    draw = ImageDraw.Draw(image)
    ink, muted, blue, red, purple = '#17231f', '#55605b', '#2459c4', '#b43d28', '#6d4e96'
    draw.text((90,55), 'jev.', font=font(44, True), fill=ink)
    draw.text((1270,70), 'EXPERIMENT ATLAS / 001', font=font(21, True), fill=ink)
    draw.line((90,127,1710,127), fill=ink, width=3)
    draw.text((85,168), 'Where does Jev break?', font=font(100, serif=True), fill=ink)
    draw.text((90,300), 'One code change. A different verdict?', font=font(36, serif=True), fill=red)
    draw.text((90,362), 'Real API observations on hand-authored synthetic cases. Not production calibration.', font=font(25), fill=muted)
    draw.text((670,435), 'OBSERVED PROBABILITY OF APPROVAL', font=font(20, True), fill=muted)
    draw.text((670,475), '0%', font=font(20), fill=muted)
    draw.text((1517,475), '100%', font=font(20), fill=muted)
    families = list(dict.fromkeys(row['family'] for row in rows))
    for index, family in enumerate(families):
        y = 550 + index * 132
        draw.text((90,y-15), LABELS.get(family,family), font=font(30, True), fill=ink)
        draw.line((680,y,1560,y), fill='#c6ccc4', width=2)
        for row in [r for r in rows if r['family']==family]:
            p = row.get('probabilities',{}).get('approve')
            if not isinstance(p,(int,float)): continue
            x=680+p*880
            color=blue if row['variant']=='safe' else red if row['variant']=='broken' else purple
            dy=-14 if row['variant']=='safe' else 14 if row['variant']=='broken' else 65
            draw.line((x,y,x,y+dy),fill=color,width=2)
            draw.ellipse((x-9,y+dy-9,x+9,y+dy+9),fill=color)
            label=row['variant']+' '+f'{p:.0%}'
            text_x=max(660,min(1560-draw.textlength(label,font=font(19)),x-20))
            draw.text((text_x,y+dy+15 if dy>0 else y+dy-38),label,font=font(19),fill=color)
    draw.line((90,1110,1710,1110),fill=ink,width=2)
    draw.text((90,1150),'Inspect the diff. Challenge the story.',font=font(41,serif=True),fill=ink)
    draw.text((90,1210),'The interactive HTML report includes exact inputs, full distributions,',font=font(25),fill=muted)
    draw.text((90,1245),'request IDs and a hypothetical threshold simulator.',font=font(25),fill=muted)
    draw.text((90,1330),metadata['model']+'  /  '+str(len(rows))+' designed probes',font=font(21,True),fill=ink)
    draw.text((90,1370),'Same model. Limited examples. No independent accuracy or safety claim.',font=font(20),fill=muted)
    image.save(output)


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',default='docs/evidence/stress-lab.json')
    parser.add_argument('--output',default='docs/reports/jev-experiment.html')
    parser.add_argument('--poster',action='store_true')
    args=parser.parse_args()
    print(build(args.input,args.output,args.poster))
