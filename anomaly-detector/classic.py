"""Explainable EWMA, persistence, and trend detector for HVAC telemetry."""
from collections import defaultdict, deque
from datetime import datetime, timezone
import math, threading

REFERENCE = {
    "supply_air_temperature": (14.0, 18.0, 20.0),
    "return_air_temperature": (23.0, 27.0, 29.0),
    "airflow": (3600.0, 2300.0, 1950.0),
    "filter_differential_pressure": (100.0, 170.0, 225.0),
    "motor_current": (10.0, 14.0, 16.5),
    "fan_vibration": (1.1, 2.8, 4.2),
}

MODES = [
    ("Air filtration", "Filter loading / clogging", {"filter_differential_pressure": 1, "airflow": -1}, "filter_differential_pressure", "Inspect filter bank and differential-pressure taps; replace filters and verify airflow."),
    ("Cooling coil", "Coil fouling / capacity degradation", {"supply_air_temperature": 1, "airflow": -1}, "supply_air_temperature", "Inspect and clean coil surfaces; verify valve travel, condensate drainage, and leaving-air temperature."),
    ("Supply fan", "Fan imbalance / bearing degradation", {"fan_vibration": 1, "motor_current": 1}, "fan_vibration", "Schedule vibration inspection; check bearings, wheel balance, fasteners, and motor alignment."),
    ("Fan drive", "Drive belt slip / wear", {"airflow": -1, "motor_current": -1}, None, "Inspect belt tension and wear; align pulleys and replace the belt set if needed."),
]

def _now(): return datetime.now(timezone.utc).isoformat()
def _rul_label(seconds):
    if seconds is None: return "Monitoring"
    return f"~{round(seconds)} sec · simulation estimate" if seconds<60 else f"~{round(seconds/60)} min · simulation estimate"
def _finite(value):
    try:
        value=float(value); return value if math.isfinite(value) else None
    except (TypeError, ValueError): return None

class ClassicDetector:
    def __init__(self, persistence=3, window=20):
        self.lock=threading.Lock(); self.persistence=persistence; self.window=window
        self.ewma={}; self.series=defaultdict(lambda: deque(maxlen=window)); self.hits=defaultdict(int); self.last_timestamp=None; self.last_result=None

    def process(self, reading):
        with self.lock:
            timestamp=reading.get("timestamp") if isinstance(reading,dict) else None
            if timestamp and timestamp==self.last_timestamp and self.last_result:
                result=dict(self.last_result); result["status"]="duplicate_ignored"; return result
            values=reading.get("values",{}) if isinstance(reading,dict) else {}
            for key,(nominal,warning,alarm) in REFERENCE.items():
                raw=values.get(key,{}); value=_finite(raw.get("value") if isinstance(raw,dict) else raw)
                if value is None: continue
                smooth=value if key not in self.ewma else .28*value+.72*self.ewma[key]
                self.ewma[key]=smooth; self.series[key].append(smooth)
            self.last_timestamp=timestamp
            result=self._result(timestamp, False); self.last_result=result; return result

    def _slope(self,key):
        seq=self.series[key]
        if len(seq)<5:return 0.0
        n=len(seq); xm=(n-1)/2; ym=sum(seq)/n; den=sum((i-xm)**2 for i in range(n))
        return sum((i-xm)*(v-ym) for i,v in enumerate(seq))/den if den else 0.0

    def _result(self,timestamp,duplicate):
        deviations={}; slopes={}
        for key,(nominal,warning,alarm) in REFERENCE.items():
            if key not in self.ewma: continue
            direction=1 if warning>nominal else -1; scale=abs(warning-nominal) or 1
            deviations[key]=direction*(self.ewma[key]-nominal)/scale; slopes[key]=self._slope(key)
        alerts=[]
        for component,mode,symptoms,strong_key,recommendation in MODES:
            evidence=[]; scores=[]
            for key,direction in symptoms.items():
                nominal,warning,_=REFERENCE[key]; scale=abs(warning-nominal) or 1
                score=direction*(self.ewma.get(key,nominal)-nominal)/scale
                if score>.25: evidence.append(f"{key.replace('_',' ')} trend {self.ewma[key]:.2f}")
                scores.append(max(0,score))
            token=component+mode
            strong=strong_key is not None and scores[list(symptoms).index(strong_key)]>=.82
            candidate=strong or sum(score>=.25 for score in scores)>=2
            self.hits[token]=min(20,self.hits[token]+1) if candidate else max(0,self.hits[token]-2)
            if self.hits[token]<self.persistence: continue
            risk=max(1,min(100,round(35+35*sum(scores)/max(1,len(scores)))))
            severity="critical" if risk>=80 else "warning" if risk>=55 else "advisory"
            rul=[]
            for key,direction in symptoms.items():
                slope=slopes.get(key,0); alarm=REFERENCE[key][2]; current=self.ewma.get(key)
                if current is not None and slope*direction>0.002: rul.append((alarm-current)/slope)
            seconds=max(30,min(86400,min([x for x in rul if x>0],default=0))) if any(x>0 for x in rul) else None
            alerts.append({"detector":"classic","method":"EWMA + persistence/trend","component":component,"fault_mode":mode,"severity":severity,"risk_score":risk,"confidence":min(94,55+self.hits[token]*5),"estimated_time_remaining_seconds":round(seconds) if seconds else None,"estimated_time_remaining":_rul_label(seconds),"evidence":evidence,"recommendation":recommendation,"timestamp":timestamp or _now(),"status":"active"})
        return {"detector":"classic","status":"duplicate_ignored" if duplicate else ("alerting" if alerts else "monitoring"),"model_status":"ready" if len(self.series["airflow"])>=5 else "warming_up","samples":len(self.series["airflow"]),"last_analysis_time":timestamp,"alerts":alerts}
