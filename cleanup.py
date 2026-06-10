import json, os, urllib.request

BASE = "https://api.loobric.com"
KEY = os.environ["KEY"]

def req(method, path, body=None):
  r = urllib.request.Request(BASE + path, data=json.dumps(body).encode() if body else None, method=method)
  r.add_header("Authorization", "Bearer " + KEY)
  r.add_header("Content-Type", "application/json")
  return json.load(urllib.request.urlopen(r))

items = req("GET", "/api/v1/tool-records")["items"]
by_name = {}
for rec in items:
  by_name.setdefault(rec["name"], []).append(rec)

doomed = []
for name, recs in sorted(by_name.items()):
  if len(recs) == 1:
    continue
  bound = [r for r in recs if r.get("machines")]
  keep = bound[0] if bound else recs[0]
  extra_bound = [r for r in bound if r["id"] != keep["id"]]
  victims = [r for r in recs if r["id"] != keep["id"] and not r.get("machines")]
  doomed += [r["id"] for r in victims]
  tag = " (bound to T%s)" % keep["machines"][0]["tool_number"] if bound else ""
  print("%-20s keep %s%s, delete %d twin(s)" % (name, keep["id"][:8], tag, len(victims)))
  for r in extra_bound:
    print("  WARNING: %s is ALSO bound - left alone, resolve by hand" % r["id"][:8])

if doomed:
  result = req("DELETE", "/api/v1/tool-records", {"ids": doomed})
  print("\ndeleted %d, errors: %s" % (result["success_count"], result["errors"] or "none"))
else:
  print("nothing to delete")

names = [r["name"] for r in req("GET", "/api/v1/tool-records")["items"]]
print("remaining:", sorted(names))
