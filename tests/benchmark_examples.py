"""Synthetic result records for reporting/metric tests, not agent achievements."""
from datetime import datetime, timezone
import uuid
from sudarshan.evaluation.runner import configuration
from sudarshan.evaluation.registry import load_suite
from sudarshan.evaluation.scoring import summarize
from sudarshan.evaluation.metrics import clean


def example(status="passed", number=1, checks=None):
    stamp=datetime.now(timezone.utc).isoformat()
    suite=load_suite()
    task=suite["tasks"][0]
    values={"turns":2,"model_requests":1,"tool_calls":1,"successful_tools":1,"failed_tools":0,"denied_tools":0,"retries":0,"timeouts":0,
            "tokens":{"input":100,"output":20,"total":125,"thought":5,"cached":0},
            "token_coverage":{key:{"measured_requests":1,"successful_requests":1} for key in ("input","output","total","thought","cached")},"partial":False}
    flags=checks or ([True]*3 if status=="passed" else [False]*3)
    trial={"trial_id":str(uuid.uuid4()),"task_id":"slug","category":"coding","task_version":"1.0.0","trial_number":number,
           "status":status,"execution_status":"completed","error_category":None,"duration_ms":1000,"started_at":stamp,"completed_at":stamp,
           "verification":{"status":status,"executed":True,"error_category":None,"artifacts_present":1,"artifacts_required":1,"checks":[{"id":name,"passed":flag} for name,flag in zip(task.criteria,flags)]},"metrics":clean(values)}
    return {"schema_version":1,"run_id":str(uuid.uuid4()),"mode":"mock","configuration":configuration(suite,"test-model",max(1,number),True,["slug"]),
            "started_at":stamp,"completed_at":stamp,"trials":[trial],"summary":summarize([trial],max(1,number))}
