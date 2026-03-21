# SEMI Task Template (POLICY-MEDIUM)

Use for medium-risk tasks that require independent critique before build.

## Paste Template

RISK: SEMI  
PIPELINE: ARCHITECT -> CRITIC -> PLANNER -> BUILDER -> AUDITOR  
GOAL: <one-line goal>  
SCOPE (ALLOWED FILES ONLY):  
- <path 1>  
- <path 2>  
KNOWN RISKS: <list>  
FORBIDDEN: Tier-1 edits, schema/migration changes unless reclassified CORE, unsafe side-effects  
OUTPUT CONTRACT PER PHASE:  
- ARCHITECT: design + constraints + WAITING_FOR_APPROVE  
- CRITIC: findings + required fixes + WAITING_FOR_APPROVE  
- PLANNER: steps + validation + WAITING_FOR_APPROVE  
- BUILDER: implementation summary  
- AUDITOR: final compliance verdict  
APPROVE GATE: explicit `approve` required between every phase.
