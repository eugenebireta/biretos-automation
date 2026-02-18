import urllib.request
import json

try:
    r = urllib.request.urlopen('http://localhost:8001/health', timeout=3)
    code = r.getcode()
    body = r.read().decode()
    print(f"STATUS_CODE: {code}")
    print(f"RESPONSE: {body}")
    if code == 200:
        data = json.loads(body)
        print(f"CONNECTION: OK")
    else:
        print(f"CONNECTION: FAIL (code {code})")
except urllib.error.HTTPError as e:
    code = e.code
    body = e.read().decode()
    print(f"STATUS_CODE: {code}")
    print(f"RESPONSE: {body}")
    print(f"CONNECTION: FAIL (code {code})")
except Exception as e:
    print(f"ERROR: {type(e).__name__}: {str(e)}")
    print(f"CONNECTION: ERROR")






















