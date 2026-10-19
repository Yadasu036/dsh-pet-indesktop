import json,time
from pathlib import Path
from pet.config import _default_base,APP_DIR_NAME
def read_value():
 p=Path(_default_base())/APP_DIR_NAME/"codex-quota.json"
 d=json.loads(p.read_text())
 if not d.get("ok") or time.time()-d["updated_at"]>420:raise ValueError("Codex额度不可用")
 w=d.get('primary')
 if not w or w.get("usedPercent") is None:raise ValueError("额度窗口不可用")
 return max(0,min(100,100-float(w["usedPercent"])))
def format_value(v):return str(round(v))
