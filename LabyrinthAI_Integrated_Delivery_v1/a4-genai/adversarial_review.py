import json, os, shutil, tempfile, subprocess, sys
from world_model import build_world
from generators import plan_artifacts, gen_db_tables, HONEY_SALARIES
from quality_gate import QualityGate
from rag_pipeline import RAG, InMemoryStore, FakeLLM
from build_artifacts import run

w=build_world(); failures=[]
def check(name, cond, detail=''):
    if not cond: failures.append((name, detail))
    print(('PASS' if cond else 'FAIL'), name, detail)

# Boundary planner exactness / rejection
for n in [1, 8, 9]:
    try: plan_artifacts(w,n); check(f'plan rejects {n}', False, 'did not raise')
    except ValueError: check(f'plan rejects {n}', True)
for n in [10,11,12,20,300]:
    p=plan_artifacts(w,n); db=next(x for x in p if x['type']=='_dbplan')
    check(f'plan exact {n}', len([x for x in p if x['type'] in ('email','memo')])+db['n_db']==n, str(db))

# Invalid world inputs
for n in [-1,0,8]:
    try: build_world(n_employees=n); check(f'world rejects {n}',False,'did not raise')
    except ValueError: check(f'world rejects {n}',True)

# Quality gate numeric and DB integrity
T=gen_db_tables(w,2,1); schema={**w['db_tables'],'salaries_archive':HONEY_SALARIES}; ref={'customer_ids':{c['customer_id'] for c in w['customers']},'order_ids':{o['order_id'] for o in T['orders']}}
for value in [float('nan'),float('inf'),float('-inf')]:
    row=dict(T['orders'][0]); row['total_amount']=value
    r=QualityGate(w).check_db_batch('orders',[row],schema,ref,register=False)
    check(f'reject {value}', 'wrong_type' in r.reasons, str(r.reasons))

# Dry run exact at minimum and normal target
for n in [10,300]:
    d=tempfile.mkdtemp(); r=RAG(InMemoryStore(),FakeLLM()); r.ingest(w); rep=run(w,r,n,d,log=lambda *_:None)
    check(f'run exact {n}',rep['total_artifacts_on_disk']==n and rep['target_met'],str(rep))

# Resume mismatch
r=RAG(InMemoryStore(),FakeLLM()); r.ingest(w); d=tempfile.mkdtemp(); run(w,r,10,d,log=lambda *_:None)
try: run(w,r,11,d,log=lambda *_:None); check('resume mismatch rejected',True)
except ValueError: check('resume mismatch rejected',True)

# Failed planning must not poison a fresh output directory
r=RAG(InMemoryStore(),FakeLLM()); r.ingest(w); d=tempfile.mkdtemp()
try: run(w,r,6,d,log=lambda *_:None)
except ValueError: pass
try: run(w,r,10,d,log=lambda *_:None); check('failed plan does not poison output',True)
except Exception as e: check('failed plan does not poison output',False,repr(e))

print('FAILURES', failures)
sys.exit(1 if failures else 0)
