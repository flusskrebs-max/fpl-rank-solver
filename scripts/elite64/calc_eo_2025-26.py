# Cowork original (handed over 2026-10-06), kept as written for the record; not maintained or linted.
# Run it from a scratch folder holding its inputs under the names it reads:
#   eo.csv / meta.csv / picks.csv / players_map.csv = datasets/elite_ownership/elite64_{eo,meta,picks,players_map}_2025-26.csv
#   ref/players_raw.csv, ref/merged_gw.csv = vaastav 2025-26 files: github.com/vaastav/Fantasy-Premier-League,
#     data/2025-26/ (fplrank.data.historical downloads them to data/raw/vaastav/2025-26/, gws/merged_gw.csv)
#   ownership_2025-26.csv = datasets/elite_ownership/elite64_ownership_2025-26.csv
# Output committed as datasets/elite_ownership/elite64_eo_calculated_2025-26.csv.
"""Calculated EO for every player and GW, 2025-26, both groups.
EO% = 100/n * [ own*s + own*(1-s)*BB/n + captain_extra ]
own: rebuilt squad ownership (counts). s: P(starts | owned), from FPL xP and fixtures, fitted on
weeks where EO is listed, then rescaled each GW so starters total exactly n GKs and 10n outfielders.
captain_extra: captain counts (+1 each), plus Triple Captains (+1 more; unlabelled TCs go to the top captain)."""
import pandas as pd, numpy as np
R=lambda f: pd.read_csv(f,keep_default_na=False)
O=pd.read_csv('ownership_2025-26.csv'); me=R('meta.csv'); eo=R('eo.csv'); pm=R('players_map.csv')
pid={p:int(i) for p,i in zip(pm.player,pm.fpl_id) if i!=''}
g=pd.read_csv('ref/merged_gw.csv')
X=g.groupby(['element','round']).agg(xp=('value','max'),nfix=('fixture','count'),st=('starts','sum')).reset_index().rename(columns={'element':'fpl_id','round':'gw'})
X['stp']=(X.st/X.nfix.clip(lower=1))
X=X.sort_values(['fpl_id','gw'])
X['srate']=X.groupby('fpl_id').stp.transform(lambda s: s.rolling(5,center=True,min_periods=1).mean())
pr=pd.read_csv('ref/players_raw.csv'); POS=dict(zip(pr.id,pr.element_type.map({1:'G',2:'D',3:'M',4:'F'}))); NAME=dict(zip(pr.id,pr.web_name))
eo['fpl_id']=eo.fpl_id.astype(int)
def chips(gw,gr):
    c=me[(me.table=='chip_active')&(me.gw==gw)].set_index('item')[gr]; return {k:float(c.get(k,0)) for k in ['WC','FH','TC','BB']}
def capx(gw,gr):
    c=me[(me.table=='captain')&(me.gw==gw)]; out={}; labelled=0
    for it,v in zip(c['item'],c[gr]):
        if it.endswith('(TC)'): out[it[:-5]]=out.get(it[:-5],0)+2*v; labelled+=v
        else: out[it]=out.get(it,0)+v
    tc=chips(gw,gr)['TC']-labelled
    if tc>0 and out:
        top=max((k for k in out),key=lambda k:out[k]); out[top]+=tc
    return {pid[k]:v for k,v in out.items() if k in pid}
def capn(gw,gr):
    c=me[(me.table=='captain')&(me.gw==gw)]; out={}
    for it,v in zip(c['item'],c[gr]):
        k=it.replace(' (TC)',''); out[k]=out.get(k,0)+v
    return {pid[k]:v for k,v in out.items() if k in pid}
BINS=[-1,42,45,50,60,80,200]
rows=[]
for gr in ['ae64','e64']:
    own=O[['gw','fpl_id',gr+'_own']].rename(columns={gr+'_own':'own'})
    D=own.merge(X,on=['gw','fpl_id'],how='left').fillna({'xp':0,'nfix':0,'srate':0})
    D['pos']=D.fpl_id.map(POS); D['n']=np.where((gr=='ae64')&(D.gw>=29),63.0,64.0)
    for k in ['FH','BB','TC']: D[k]=D.gw.map(lambda t: chips(t,gr)[k])
    D['capx']=[capx(t,gr).get(i,0) for t,i in zip(D.gw,D.fpl_id)]
    L=eo[['gw','fpl_id',gr+'_eo']].rename(columns={gr+'_eo':'eo_listed'})
    D=D.merge(L,on=['gw','fpl_id'],how='left')
    # fit start share by position and xP band on clean weeks
    fit=D[D.eo_listed.notna()&(D.FH==0)&(D.BB==0)&(D.own>=3)].copy()
    fit['r']=((fit.eo_listed*fit.n/100-fit.capx)/fit.own).clip(0,1)
    SB=[-0.01,0.2,0.5,0.8,0.99,1.01]
    for F in (fit,D): F['band']=np.where(F.pos=='G','GK',pd.cut(F.xp,BINS).astype(str))+'|'+pd.cut(F.srate,SB).astype(str); F['sband']=pd.cut(F.srate,SB).astype(str)
    tab2=fit.groupby(['pos','sband']).apply(lambda x: np.average(x.r,weights=x.own)).rename('s1')
    D=D.join(tab2,on=['pos','sband'])
    tab=fit.groupby(['pos','band'],observed=True).apply(lambda x: np.average(x.r,weights=x.own)).rename('s0')
    D=D.join(tab,on=['pos','band'])
    D['s0']=D.s0.where(D.groupby(['pos','band']).own.transform('size')>0).fillna(D.s1).fillna(0.5)
    D['s0']=D.s0.clip(lower=0.05); D.loc[D.nfix==0,'s0']=0.0
    # rescale per GW: n GK starters, 10n outfield starters
    D['s']=D.s0
    lg=lambda p: np.log(np.clip(p,1e-4,1-1e-4)/(1-np.clip(p,1e-4,1-1e-4)))
    for (t,grp),idx in D.groupby(['gw',D.pos.eq('G')]).groups.items():
        need=D.loc[idx,'n'].iloc[0]*(1 if grp else 10)
        if grp:  # keepers: each manager starts one; owners start the pricier regular starter
            sub=D.loc[idx]; nn=sub.n.iloc[0]
            pref=(sub.srate>0.5).astype(int)*1000+sub.xp
            order=pref.sort_values(ascending=False).index; left=1.0; sv=pd.Series(0.0,index=idx)
            for i in order:
                if sub.at[i,'nfix']==0: continue
                sv[i]=left; left*=max(0,1-sub.at[i,'own']/nn)
            tot=(sub.own*sv).sum()
            if tot>0: sv=(sv*nn/tot).clip(upper=1)
            D.loc[idx,'s']=sv.values; continue
        z=lg(D.loc[idx,'s0'].values); o=D.loc[idx,'own'].values; zero=D.loc[idx,'s0'].values==0
        lo,hi=-15,15
        for _ in range(60):
            c=(lo+hi)/2; sv=np.where(zero,0,1/(1+np.exp(-(z+c))))
            if (o*sv).sum()>need: hi=c
            else: lo=c
        D.loc[idx,'s']=sv
    D['ncap']=[capn(t,gr).get(i,0) for t,i in zip(D.gw,D.fpl_id)]
    D['s']=np.maximum(D.s,np.minimum(1,D.ncap/D.own.clip(lower=1e-6)))  # captains start
    D['eo_calc']=100*(D.own*D.s+D.own*(1-D.s)*D.BB/D.n+D.capx)/D.n
    D['group']=gr; rows.append(D)
A=pd.concat(rows)
A['web_name']=A.fpl_id.map(NAME)
# validation on listed weeks
for gr in ['ae64','e64']:
    v=A[(A.group==gr)&A.eo_listed.notna()]
    for lab,m in [('all',v),('non-FH',v[v.FH==0])]:
        d=m.eo_calc-m.eo_listed; print(gr,lab,'n=%d MAE %.1fpp median %.1f p10 %.1f p90 %.1f'%(len(m),d.abs().mean(),d.median(),d.quantile(.1),d.quantile(.9)))
    t=A[A.group==gr].groupby('gw').apply(lambda x:(x.eo_calc*x.n).sum()/100/x.n.iloc[0]); print(' total EO per manager GW1-5:',t.head(5).round(2).tolist())
A.to_pickle('calc_long.pkl')
W=A.pivot_table(index=['gw','fpl_id','web_name','pos'],columns='group',values=['eo_calc','eo_listed']).reset_index()
W.columns=['_'.join([c for c in col if c]) for col in W.columns]
W.to_csv('eo_calculated_2025-26.csv',index=False)
print(W.head(3))
