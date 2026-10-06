# Cowork original (handed over 2026-10-06), kept as written for the record; not maintained or linted.
# Run it from a scratch folder holding its inputs under the names it reads:
#   eo.csv / meta.csv / picks.csv / players_map.csv = datasets/elite_ownership/elite64_{eo,meta,picks,players_map}_2025-26.csv
#   ref/players_raw.csv, ref/merged_gw.csv = vaastav 2025-26 files: github.com/vaastav/Fantasy-Premier-League,
#     data/2025-26/ (fplrank.data.historical downloads them to data/raw/vaastav/2025-26/, gws/merged_gw.csv)
# (The maintained port, scripts/elite_flows.py, was removed in the 2026-10-06 clean-up; git history has it.) Its outputs are committed as datasets/elite_ownership/elite64_{weekly_summary,flows_player_gw}_2025-26.csv.
import pandas as pd, numpy as np, json
R=lambda f: pd.read_csv(f,keep_default_na=False)
eo=R('eo.csv'); me=R('meta.csv'); pk=R('picks.csv'); pm=R('players_map.csv')
g=pd.read_csv('ref/merged_gw.csv')
pts=g.groupby(['element','round']).agg(pts=('total_points','sum'),mins=('minutes','sum')).reset_index()
pid={p:int(i) for p,i in zip(pm.player,pm.fpl_id) if i!=''}
G=['ae64','e64']; gws=range(1,39)
def T(t): return me[me.table==t]
n=T('chip_active').groupby('gw')[G].sum()
out={}
rows=[]
for gw in gws:
    r={'gw':gw}
    for grp in G:
        N=n.loc[gw,grp] if gw in n.index else np.nan; r[grp+'_n']=N
        c=T('captain'); c=c[c.gw==gw]
        if len(c):
            s=c.copy(); s['base']=s.item.str.replace(r' \(TC\)$','',regex=True)
            sh=s.groupby('base')[grp].sum()/s[grp].sum()
            r[grp+'_cap_top']=sh.idxmax(); r[grp+'_cap_share']=round(sh.max(),3); r[grp+'_cap_eff']=round(1/(sh**2).sum(),2)
        ch=T('chip_active'); ch=ch[ch.gw==gw].set_index('item')[grp]
        for k in ['WC','FH','TC','BB']: r[grp+'_chip_'+k]=int(ch.get(k,0))
        fu=T('fts_used'); fu=fu[(fu.gw==gw)]
        if len(fu):
            norm=fu[~fu.item.isin(['WC','FH'])]; k=norm.item.astype(int); w=norm[grp]
            r[grp+'_transfers_pm']=round((k*w).sum()/w.sum(),2) if w.sum() else np.nan
            r[grp+'_roll_share']=round(w[k==0].sum()/w.sum(),3) if w.sum() else np.nan
        fn=T('fts_remaining_next'); fn=fn[fn.gw==gw]
        if len(fn): k=fn.item.astype(int); r[grp+'_ft_bank_next']=round((k*fn[grp]).sum()/fn[grp].sum(),2)
        h=T('hits'); h=h[h.gw==gw]
        if len(h): r[grp+'_hit_share']=round(h[h.item!='0'][grp].sum()/h[grp].sum(),3)
        ti=T('transfer_in'); ti=ti[ti.gw==gw]
        if len(ti) and ti[grp].sum():
            top=ti.sort_values(grp,ascending=False).iloc[0]
            r[grp+'_in_top']=top['item']; r[grp+'_in_top_n']=int(top[grp]); r[grp+'_in_top_share_of_all']=round(top[grp]/ti[grp].sum(),3)
        e=eo[eo.gw==gw]
        if len(e):
            r[grp+'_n50']=int((e[grp+'_eo']>=50).sum())
            r[grp+'_eo_listed']=int(e[grp+'_eo'].sum())
            e2=e.assign(pts=[pts.set_index(['element','round']).pts.get((pid.get(p),gw),0) for p in e.player])
            r[grp+'_listed_score']=round((e2[grp+'_eo']*e2.pts).sum()/100,1)
    e=eo[eo.gw==gw]
    if len(e):
        r['divergence']=int((e.ae64_eo-e.e64_eo).abs().sum()/2)
        e2=e.assign(pts=[pts.set_index(['element','round']).pts.get((pid.get(p),gw),0) for p in e.player])
        r['delta_ae_minus_e']=round(((e2.ae64_eo-e2.e64_eo)*e2.pts).sum()/100,1)
    rows.append(r)
W=pd.DataFrame(rows); W.to_csv('weekly_summary.csv',index=False)
# --- flows vs previous points (pile-in model input)
ti=T('transfer_in'); to=T('transfer_out')
flow=ti.groupby(['gw','item'])[G].sum().sub(to.groupby(['gw','item'])[G].sum(),fill_value=0).reset_index().rename(columns={'item':'player'})
flow['fpl_id']=flow.player.map(pid)
# universe: every player who played minutes in the previous GW
P=pts.rename(columns={'element':'fpl_id','round':'gw'})
fl=[]
for gw in range(2,39):
    prev=P[(P.gw==gw-1)&(P.mins>0)][['fpl_id','pts']]
    prev2=P[(P.gw==gw-2)][['fpl_id','pts']].rename(columns={'pts':'pts2'})
    f=flow[flow.gw==gw]
    m=prev.merge(f,on='fpl_id',how='left').merge(prev2,on='fpl_id',how='left').fillna({'ae64':0,'e64':0,'pts2':0})
    m['gw']=gw; fl.append(m)
FL=pd.concat(fl)
nn=n.reindex(range(1,39)).ffill()
for grp in G: FL[grp+'_net_pct']=100*FL[grp]/FL.gw.map(nn[grp])
FL['bucket']=pd.cut(FL.pts,[-10,2,5,9,14,99],labels=['≤2','3–5','6–9','10–14','15+'])
# exclude WC/FH-heavy weeks? transfers lists exclude WC/FH already.
B=FL.groupby('bucket',observed=True).agg(n=('pts','size'),ae_net=('ae64_net_pct','mean'),e_net=('e64_net_pct','mean'),
   ae_big=('ae64_net_pct',lambda x:(x>=10).mean()),e_big=('e64_net_pct',lambda x:(x>=10).mean())).round(3)
print(B)
B.to_csv('flow_by_prev_points.csv')
FL.to_csv('flows_player_gw.csv',index=False)
# biggest pile-ins
big=flow.copy(); big['pts_prev']=[P.set_index(['fpl_id','gw']).pts.get((i,gw-1),np.nan) for i,gw in zip(big.fpl_id,big.gw)]
big['pts_prev2']=[P.set_index(['fpl_id','gw']).pts.get((i,gw-2),np.nan) for i,gw in zip(big.fpl_id,big.gw)]
big['pts_this']=[P.set_index(['fpl_id','gw']).pts.get((i,gw),np.nan) for i,gw in zip(big.fpl_id,big.gw)]
big['both']=big.ae64+big.e64
top=big.sort_values('both',ascending=False).head(25)
print(top[['gw','player','ae64','e64','pts_prev2','pts_prev','pts_this']].to_string())
top.to_csv('top_pileins.csv',index=False)
