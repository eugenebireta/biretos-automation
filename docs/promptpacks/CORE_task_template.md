# CORE Task Template (CORE-CRITICAL)

Use for Tier-1, schema, invariants, governance, or any high-risk core mutation.

## Paste Template

RISK: CORE  
PIPELINE: SCOUT -> ARCHITECT -> CRITIC -> JUDGE(external) -> PLANNER -> BUILDER -> AUDITOR  
GOAL: <one-line goal>  
SCOPE (TARGET FILES):  
- <path 1>  
- <path 2>  
WHY CORE: <explicit trigger: Tier-1 / schema / invariant / policy-pack / side-effects>  
NON-NEGOTIABLES:  
- One step at a time  
- No role merging  
- JUDGE external chat only  
- Approve gate between phases  
REQUIRED JUDGE PACKET:  
1) task and risk classification  
2) architect summary  
3) critic findings and unresolved risks  
4) proposed implementation boundaries  
RETURN FORMAT FROM CURSOR: per-phase artifact + `WAITING_FOR_APPROVE`.
