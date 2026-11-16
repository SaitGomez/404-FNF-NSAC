import json, sys, os, csv, io
src, out = sys.argv[1], sys.argv[2]
b = json.load(open(src, encoding='utf-8'))
os.makedirs(f"{out}/metadata", exist_ok=True); os.makedirs(f"{out}/tables", exist_ok=True)
json.dump(b['search'], open(f"{out}/metadata/search_combustion.json","w"), indent=1)
inv = b['investigations']
for k,v in inv.items():
    json.dump(v, open(f"{out}/metadata/{k}.json","w"), indent=1)
for fn, txt in b['tables'].items():
    open(f"{out}/tables/{fn}","w",encoding='utf-8').write(txt)
print("harvested", b['harvested'], "inv", len(inv), "tables", len(b['tables']))
for fn, txt in sorted(b['tables'].items()):
    rows = list(csv.reader(io.StringIO(txt)))
    rows = [r for r in rows if any(c.strip() for c in r)]
    print(f"{fn[:60]:60s} rows={len(rows)-1:4d} cols={len(rows[0]) if rows else 0}")
# file inventory: which keys hold file lists?
k='PSI-25'; d=inv[k]
print({kk:(len(vv) if isinstance(vv,list) else type(vv).__name__) for kk,vv in d.items() if isinstance(vv,list)})
