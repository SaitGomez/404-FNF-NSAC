import json, glob, os, collections, csv, sys
base=sys.argv[1]
rows=[]
for f in sorted(glob.glob(f"{base}/metadata/PSI-*.json")):
    d=json.load(open(f)); pid=d['accession']
    seen={}
    for key in ('added','modified'):
        for x in d.get(key,[]) or []:
            seen[x['file_name']]=x
    for x in seen.values():
        rp=x.get('remote_path','')
        parts=rp.split('/')
        cat=parts[4] if len(parts)>5 else '?'
        rows.append(dict(psi=pid, acronym=d.get('investigationAcronym',''), category=cat, file=x['file_name'], size=x.get('file_size',0), version=x.get('version'), restricted=x.get('restricted')))
with open(f"{base}/file_inventory.csv","w",newline='') as fh:
    w=csv.DictWriter(fh, fieldnames=rows[0].keys()); w.writeheader(); w.writerows(rows)
agg=collections.defaultdict(lambda:[0,0])
for r in rows: a=agg[(r['psi'],r['category'])]; a[0]+=1; a[1]+=r['size']
tot=collections.defaultdict(lambda:[0,0])
for (p,c),(n,s) in agg.items(): tot[c][0]+=n; tot[c][1]+=s
print("files listed:",len(rows))
for c,(n,s) in sorted(tot.items(), key=lambda x:-x[1][1]): print(f"{c:30s} n={n:6d} {s/1e9:9.2f} GB")
print()
for (p,c),(n,s) in sorted(agg.items()):
    if c.lower() in ('reports','science documents','engineering documents','reference data','read me','readme'):
        print(f"{p:8s} {c:22s} n={n:4d} {s/1e6:9.1f} MB")
# compare to totalFileSize
for f in sorted(glob.glob(f"{base}/metadata/PSI-*.json")):
    d=json.load(open(f)); pid=d['accession']
    s=sum(r['size'] for r in rows if r['psi']==pid)
    print(pid, f"inventoried {s/1e9:.1f} GB of {d['totalFileSize']/1e9:.1f} GB")
