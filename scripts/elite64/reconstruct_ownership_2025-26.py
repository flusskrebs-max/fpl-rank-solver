# Cowork original (handed over 2026-10-06), kept as written for the record; not maintained or linted.
# Run it from a scratch folder holding its inputs under the names it reads:
#   eo.csv / meta.csv / picks.csv / players_map.csv = datasets/elite_ownership/elite64_{eo,meta,picks,players_map}_2025-26.csv
#   ref/players_raw.csv, ref/merged_gw.csv = vaastav 2025-26 files: github.com/vaastav/Fantasy-Premier-League,
#     data/2025-26/ (fplrank.data.historical downloads them to data/raw/vaastav/2025-26/, gws/merged_gw.csv)
# Maintained port: scripts/reconstruct_elite_ownership.py. Output committed as datasets/elite_ownership/elite64_ownership_2025-26.csv.
"""Squad ownership by GW for AE64/E64, 2025-26.
Forward pass: GW1 picks + complete transfer lists. Unknown WC squads: GW6 from the WC pick table;
other WC weeks start from 'WC managers mirror the group', then are corrected so that ownership never
goes negative before the next WC week and is never below listed EO minus captaincy (GW10+).
Mass is moved within position, so squads stay 2/5/5/3."""
import pandas as pd, numpy as np, os
USE_EO=os.environ.get("USE_EO","1")=="1"
OUT=os.environ.get("OUT","ownership_reconstructed.csv")
R=lambda f: pd.read_csv(f,keep_default_na=False)
me=R('meta.csv'); pk=R('picks.csv'); pm=R('players_map.csv'); eo=R('eo.csv')
pid={p:int(i) for p,i in zip(pm.player,pm.fpl_id) if i!=''}
pr=pd.read_csv('ref/players_raw.csv'); POS=dict(zip(pr.id,pr.element_type.map({1:'G',2:'D',3:'M',4:'F'})))
SL={'G':2,'D':5,'M':5,'F':3}; IDS=sorted(POS); ix={i:k for k,i in enumerate(IDS)}
posv=np.array([POS[i] for i in IDS])
def T(t,gw): return me[(me.table==t)&(me.gw==gw)]
def vec(pairs):
    v=np.zeros(len(IDS))
    for p,x in pairs:
        if p in pid: v[ix[pid[p]]]+=x
    return v
res={}; report=[]
for g in ['ae64','e64']:
    N={gw:(63.0 if g=='ae64' and gw>=29 else 64.0) for gw in range(1,39)}
    W={gw:float(T('chip_active',gw).set_index('item')[g].get('WC',0)) for gw in range(1,39)}
    NET={gw:vec(zip(T('transfer_in',gw)['item'],T('transfer_in',gw)[g]))-vec(zip(T('transfer_out',gw)['item'],T('transfer_out',gw)[g])) for gw in range(1,39)}
    # EO lower bound on ownership count: (EO - captain extra) * n / 100
    LB={}
    for gw in range(10,39):
        c=T('captain',gw); extra={}
        for it,v in zip(c['item'],c[g]):
            b=it.replace(' (TC)',''); extra[b]=extra.get(b,0)+v*(2 if '(TC)' in it else 1)
        fh=float(T('chip_active',gw).set_index('item')[g].get('FH',0))
        e=eo[eo.gw==gw]; lb=np.zeros(len(IDS))
        for p,v in zip(e.player,e[g+'_eo']):
            if p in pid: lb[ix[pid[p]]]=max(0,(v*N[gw]/100-extra.get(p,0)-fh))
        if USE_EO: LB[gw]=lb-0.5  # rounding tolerance
    wcweeks=[gw for gw in range(2,39) if W[gw]>0]
    own=vec(zip(pk.player,pk[g+'_own']*64/100)); S={1:own.copy()}
    for gw in range(2,39):
        n=N[gw]; nprev=N[gw-1]
        if n<nprev: own=own*n/nprev
        w=W[gw]
        if gw==6 and w:
            wc=T('wc_pick_pct',6); new=vec(zip(wc['item'],wc[g].astype(float)*w/100))
            own=own*(1-w/n)+new
            for ps,k in SL.items():
                m=posv==ps; short=k*n-own[m].sum(); base=np.clip(own[m]-new[m],0,None)
                if short>0 and base.sum()>0: own[m]+=short*base/base.sum()
            own=own+NET[gw]
        elif w:
            own=(own*(1-w/n)+NET[gw])*n/(n-w)
        else:
            own=own+NET[gw]
        if w:  # correct the WC-week state using constraints up to the next WC week
            nxt=min([x for x in wcweeks if x>gw]+[39]); need=np.maximum(0,LB.get(gw,np.zeros(len(IDS)))); cum=np.zeros(len(IDS))
            for s in range(gw+1,nxt):
                cum+=NET[s]; need=np.maximum(need,np.maximum(0,LB.get(s,0))-cum)
            need=np.minimum(need,n)
            moved=0
            for ps in SL:
                m=posv==ps; o=own[m]; nd=need[m]
                add=np.clip(nd-o,0,None); A=add.sum()
                if A<=0: continue
                slack=np.clip(o-nd,0,None)
                o=o+add-A*slack/slack.sum(); own[m]=o; moved+=A
            report.append((g,gw,w,round(moved,1)))
        S[gw]=own.copy()
    res[g]=S
rows=[]
for gw in range(1,39):
    a=res['ae64'][gw]; e=res['e64'][gw]
    for k,i in enumerate(IDS):
        if abs(a[k])>0.05 or abs(e[k])>0.05: rows.append((gw,i,POS[i],a[k],e[k]))
O=pd.DataFrame(rows,columns=['gw','fpl_id','pos','ae64_own','e64_own'])
O['web_name']=O.fpl_id.map(dict(zip(pr.id,pr.web_name)))
O.to_csv(OUT,index=False)
print('WC-week corrections (group, gw, WC managers, ownership moved):'); print(report)
for g in ['ae64','e64']:
    neg=O[O[g+'_own']<-0.5]; print(g,'negative cells',len(neg),round(neg[g+'_own'].sum(),1))
