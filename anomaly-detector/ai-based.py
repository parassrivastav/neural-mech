"""Adaptive, unsupervised diagonal-Mahalanobis HVAC stream detector."""
from collections import deque
from datetime import datetime, timezone
import math, threading

MEANS={"supply_air_temperature":14.,"return_air_temperature":23.,"airflow":3600.,"filter_differential_pressure":100.,"motor_current":10.,"fan_vibration":1.1}
SCALES={"supply_air_temperature":1.5,"return_air_temperature":2.,"airflow":550.,"filter_differential_pressure":35.,"motor_current":1.6,"fan_vibration":.55}
PROFILES=[
 ("Air filtration","Filter loading / clogging",{"filter_differential_pressure":1,"airflow":-1},"Inspect filters and pressure taps; replace filters, then verify design airflow."),
 ("Cooling coil","Coil fouling / capacity degradation",{"supply_air_temperature":1,"airflow":-1},"Clean and inspect the cooling coil; validate valve response and leaving-air temperature."),
 ("Supply fan","Fan imbalance / bearing degradation",{"fan_vibration":1,"motor_current":1},"Perform vibration route inspection and check wheel balance, bearings, and alignment."),
 ("Fan drive","Drive belt slip / wear",{"airflow":-1,"motor_current":-1},"Inspect belt tension, wear, and pulley alignment; plan belt-set replacement."),
]
def finite(x):
 try: x=float(x); return x if math.isfinite(x) else None
 except (TypeError,ValueError): return None
def rul_label(seconds):
 return "Monitoring" if seconds is None else (f"~{round(seconds)} sec · simulation estimate" if seconds<60 else f"~{round(seconds/60)} min · simulation estimate")

class AdaptiveDetector:
 def __init__(self):
  self.lock=threading.Lock(); self.means=dict(MEANS); self.vars={k:v*v for k,v in SCALES.items()}; self.samples=0; self.last_timestamp=None; self.scores=deque(maxlen=20); self.hits={p[1]:0 for p in PROFILES}; self.last_result=None
 def process(self,reading):
  with self.lock:
   ts=reading.get("timestamp") if isinstance(reading,dict) else None
   if ts and ts==self.last_timestamp and self.last_result:
    result=dict(self.last_result); result["status"]="duplicate_ignored"; return result
   raw=reading.get("values",{}) if isinstance(reading,dict) else {}
   vals={}
   for k in MEANS:
    payload=raw.get(k) if isinstance(raw,dict) else None
    value=payload.get("value") if isinstance(payload,dict) else payload
    value=finite(value)
    if value is not None: vals[k]=value
   contributions={k:min(25,((v-self.means[k])**2/max(self.vars[k],SCALES[k]**2*.25))) for k,v in vals.items()}
   score=math.sqrt(sum(contributions.values())/max(1,len(contributions))); self.scores.append(score); self.samples+=1; self.last_timestamp=ts
   fixed={k:(v-MEANS[k])/SCALES[k] for k,v in vals.items()}
   profiles=[]
   for component,mode,profile,rec in PROFILES:
    directed=[fixed.get(k,0)*direction for k,direction in profile.items()]
    # A strong discriminative primary symptom, or correlated moderate symptoms.
    strong=directed[0]>=2.0
    candidate=strong or sum(x>=.45 for x in directed)>=2
    self.hits[mode]=min(25,self.hits[mode]+1) if candidate else max(0,self.hits[mode]-2)
    if self.hits[mode]>=4: profiles.append((component,mode,profile,rec,directed))
   # Train only deep inside the fixed engineering-reference envelope. Clamp drift so
   # a slowly developing fault can never redefine nominal operation.
   if vals and max(abs(x) for x in fixed.values())<.42 and not profiles:
    for k,v in vals.items():
     delta=v-self.means[k]; learned=self.means[k]+.01*delta
     self.means[k]=max(MEANS[k]-.25*SCALES[k],min(MEANS[k]+.25*SCALES[k],learned))
     self.vars[k]=max(SCALES[k]**2*.5,min(SCALES[k]**2*2,.99*self.vars[k]+.01*delta*delta))
   warm=min(100,round(self.samples/20*100)); alerts=[]
   top=sorted(contributions,key=contributions.get,reverse=True)[:3]
   if profiles and len(vals)>=4:
    # Prefer the most specific developed signature, while allowing multiple risks.
    profiles.sort(key=lambda p:sum(max(0,x) for x in p[4]),reverse=True)
    for component,mode,profile,rec,directed in profiles:
     profile_score=sum(max(0,x) for x in directed)/len(directed)
     risk=max(1,min(100,round(38+profile_score*25))); severity="critical" if risk>=80 else "warning" if risk>=55 else "advisory"
     relevant=sorted(profile,key=lambda k:abs(fixed.get(k,0)),reverse=True)
     evidence=[f"{k.replace('_',' ')} fixed-reference residual {fixed.get(k,0):+.1f}σ" for k in relevant]
     slope=0
     if len(self.scores)>=6:
      n=len(self.scores); slope=(self.scores[-1]-self.scores[max(0,n-6)])/min(5,n-1)
     seconds=max(30,min(86400,(4.5-score)/slope)) if slope>.004 and score<4.5 else None
     alerts.append({"detector":"ai_based","method":"adaptive diagonal Mahalanobis","component":component,"fault_mode":mode,"severity":severity,"risk_score":risk,"confidence":min(95,round(warm*.7+min(25,profile_score*8))),"estimated_time_remaining_seconds":round(seconds) if seconds else None,"estimated_time_remaining":rul_label(seconds),"evidence":evidence,"top_signals":relevant,"recommendation":rec,"timestamp":ts or datetime.now(timezone.utc).isoformat(),"status":"active"})
   result={"detector":"ai_based","status":"alerting" if alerts else "monitoring","model_status":"warm_up" if self.samples<20 else "adaptive_ready","model_confidence":warm,"health_score":round(score,3),"samples":self.samples,"last_analysis_time":ts,"alerts":alerts,"disclaimer":"Adaptive simulation model; production accuracy requires site training and validation."}; self.last_result=result; return result
