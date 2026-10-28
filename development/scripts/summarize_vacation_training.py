"""Compact, auditable results from completed production cases; no acceptance thresholds edited."""
import argparse,hashlib,json
from pathlib import Path

def summarize(root):
 root=Path(root);cases=[]
 for p in sorted(root.glob('*/revision-analysis.json')):
  r=json.loads(p.read_text());report=json.loads((p.parent/'report.json').read_text());m=json.loads((p.parent/'manifest.json').read_text());cm=report.get('sourceAccounting',{}).get('coldMomentum',{});ledger=cm.get('ledger',{})
  momentum_activity=ledger.get('transportActivity',0)+sum(abs(v) for key,obj in ledger.items() if key!='initial' and isinstance(obj,dict) for v in obj.values() if isinstance(v,(float,int)))
  momentum_residual=sum(abs(v) for v in cm.get('residual',{}).values())
  stats=report['stats'];example=r['regeneration'][0] if r['regeneration'] else None
  cases.append({'directory':p.parent.name,'model':r['model'],'seed':r['config']['seed'],'geography':r['config']['geography'],'geometry':r['config'].get('coastalConvergenceGeometry','planar'),'hours':r['durationHours'],'checks':r['checks'],'persistentWindows':len(r['persistentBands']),'trainingWindows':len(r['regeneration']),'rolling':r['rolling'],'births':stats['births'],'coldBirths':stats['coldBirths'],'activityResidual':report['audit']['activityResidual'],'momentumActivityRelativeResidual':momentum_residual/momentum_activity if momentum_activity else None,'coldVolumeRelativeResidual':abs(report['audit']['coldVolumeResidual'])/max(1,stats['coldVolumeSource']+stats['coldVolumeLoss']),'coldHeatRelativeResidual':abs(report['audit']['coldHeatResidual'])/max(1,stats['coldHeatSource']+stats['coldHeatLoss']),'firstTraining':{k:example[k] for k in ['start','end','x','y','birthIDs','passageSpanSeconds','medianPositionDerivedSpeed','centroidDisplacementKm','strongIntervalSeconds']} if example else None,'analysisSha256':hashlib.sha256(p.read_bytes()).hexdigest(),'manifestSha256':hashlib.sha256((p.parent/'manifest.json').read_bytes()).hexdigest()})
 return {'model':'vacation-1.17.0','note':'Overlapping windows are not independent rainbands. Float32 physical products, 120 s sampling. release-* uses final defaults; final-* is curved coast experiment. Prototype disableCold remains positive under prescribed convergence.','evidenceRoot':str(root),'cases':cases,'formal72HourAcceptance':'not_measured','browser200xAcceptance':'not_measured'}
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('root');a.add_argument('output');args=a.parse_args();Path(args.output).write_text(json.dumps(summarize(args.root),ensure_ascii=False,indent=2))
