#!/usr/bin/env python3
"""Thread-safe, smoothly drifting HVAC-001 telemetry simulator."""
from collections import deque
from datetime import datetime, timezone
import json, math, random, threading, time

UNITS = {"supply_air_temperature":"°C","return_air_temperature":"°C","airflow":"m³/h","filter_differential_pressure":"Pa","motor_current":"A","fan_vibration":"mm/s","temperature_setpoint":"°C"}
BASELINES = {"supply_air_temperature":14.0,"return_air_temperature":23.0,"airflow":3600.0,"filter_differential_pressure":100.0,"motor_current":10.0,"fan_vibration":1.1,"temperature_setpoint":20.0}
CHART_MAXIMA = {"supply_air_temperature":25.0,"return_air_temperature":35.0,"airflow":6000.0,"filter_differential_pressure":300.0,"motor_current":20.0,"fan_vibration":6.0,"temperature_setpoint":30.0}
BOUNDS = {"supply_air_temperature":(10,22),"return_air_temperature":(18,30),"airflow":(1800,5200),"filter_differential_pressure":(40,260),"motor_current":(4,18),"fan_vibration":(.3,5),"temperature_setpoint":(18,24)}
RANGES = {"1m":(60,1),"1h":(120,30),"1d":(144,600)}

class HVAC001Simulator:
    def __init__(self, history_limit=120, seed=None):
        self.history_limit=history_limit; self._history=deque(maxlen=history_limit); self._lock=threading.Lock(); self._rng=random.Random(seed); self._last=0.0
        self._values={"supply_air_temperature":14.4,"return_air_temperature":23.7,"airflow":3680.,"filter_differential_pressure":91.,"motor_current":10.4,"fan_vibration":1.15,"temperature_setpoint":20.0}; self._sample(time.time())
    def _severity(self, key, value):
        warn={"supply_air_temperature":(12,18),"return_air_temperature":(20,27),"airflow":(2300,4700),"filter_differential_pressure":(0,170),"motor_current":(0,14),"fan_vibration":(0,2.8),"temperature_setpoint":(18,24)}
        alarm={"supply_air_temperature":(10.8,20),"return_air_temperature":(19,29),"airflow":(1950,5000),"filter_differential_pressure":(0,225),"motor_current":(0,16.5),"fan_vibration":(0,4.2),"temperature_setpoint":(18,24)}
        lo,hi=warn[key]
        if lo<=value<=hi: return "nominal"
        alo,ahi=alarm[key]
        return "warning" if alo<=value<=ahi else "alarm"
    def _sample(self, now):
        phase=now/38; target_set=20+.25*math.sin(phase/4); self._values["temperature_setpoint"]+=(target_set-self._values["temperature_setpoint"])*.08
        ret_target=23.5+1.1*math.sin(phase/3); self._values["return_air_temperature"]+=(ret_target-self._values["return_air_temperature"])*.06+self._rng.uniform(-.06,.06)
        load=max(0,min(1,(self._values["return_air_temperature"]-self._values["temperature_setpoint"])/6+.35)); airflow_target=2800+1700*load
        self._values["airflow"]+=(airflow_target-self._values["airflow"])*.09+self._rng.uniform(-18,18)
        self._values["supply_air_temperature"]+=(14.2+.6*(1-load)-self._values["supply_air_temperature"])*.1+self._rng.uniform(-.04,.04)
        self._values["filter_differential_pressure"]+=(72+self._values["airflow"]/95-self._values["filter_differential_pressure"])*.04+self._rng.uniform(-.5,.5)
        self._values["motor_current"]+=(3.5+self._values["airflow"]/540-self._values["motor_current"])*.12+self._rng.uniform(-.04,.04)
        self._values["fan_vibration"]+=(.65+self._values["motor_current"]*.045-self._values["fan_vibration"])*.08+self._rng.uniform(-.015,.015)
        for k,(lo,hi) in BOUNDS.items(): self._values[k]=max(lo,min(hi,self._values[k]))
        values={k:{"value":round(v,0 if k in {"airflow","filter_differential_pressure"} else 2),"unit":UNITS[k],"severity":self._severity(k,v)} for k,v in self._values.items()}
        reading={"timestamp":datetime.fromtimestamp(now,timezone.utc).isoformat(),"hvac_on":True,"state":{"value":"ON","severity":"nominal"},"values":values,"status":"nominal"}
        self._history.append(reading); self._last=now
    def snapshot(self):
        return self.snapshot_range("1m")

    def _historical_reading(self, timestamp):
        # Stable multi-period curves create correlated, immediately useful backfill.
        daily=math.sin(timestamp/86400*2*math.pi); short=math.sin(timestamp/3700*2*math.pi)
        ret=23.0+1.45*daily+.35*short; load=max(0,min(1,(ret-20)/6+.32)); airflow=2750+1750*load+90*math.sin(timestamp/1100)
        raw={"supply_air_temperature":14.2+.55*(1-load)+.12*short,"return_air_temperature":ret,"airflow":airflow,"filter_differential_pressure":72+airflow/95,"motor_current":3.5+airflow/540,"fan_vibration":.65+(3.5+airflow/540)*.045+.06*short,"temperature_setpoint":20+.25*math.sin(timestamp/21600)}
        values={k:{"value":round(max(BOUNDS[k][0],min(BOUNDS[k][1],v)),0 if k in {"airflow","filter_differential_pressure"} else 2),"unit":UNITS[k],"severity":self._severity(k,v)} for k,v in raw.items()}
        return {"timestamp":datetime.fromtimestamp(timestamp,timezone.utc).isoformat(),"hvac_on":True,"state":{"value":"ON","severity":"nominal"},"values":values,"status":"nominal"}

    def snapshot_range(self, range_key="1m"):
        if range_key not in RANGES: raise ValueError("invalid telemetry range")
        with self._lock:
            now=time.time()
            while now-self._last>=1: self._sample(self._last+1)
            count,step=RANGES[range_key]
            if range_key == "1m":
                recent=list(self._history)[-count:]; missing=count-len(recent)
                history=[self._historical_reading(now-(count-1-i)) for i in range(missing)]+recent
            else: history=[self._historical_reading(now-step*(count-1-i)) for i in range(count-1)]+[self._history[-1]]
            metadata={k:{"unit":UNITS[k],"baseline":BASELINES[k],"chart_max":CHART_MAXIMA[k]} for k in UNITS}
            return {"asset_id":"HVAC-001","range":range_key,"poll_interval_ms":1000,"reading":self._history[-1],"history":history,"metadata":metadata}

if __name__ == "__main__":
    sim=HVAC001Simulator()
    try:
        while True: print(json.dumps(sim.snapshot()["reading"],indent=2)); time.sleep(1)
    except KeyboardInterrupt: pass
