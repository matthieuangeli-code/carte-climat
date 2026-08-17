#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Carte climat — France & voisins. Tkinter, sans dépendance pip."""
import json, math, threading, urllib.parse, urllib.request
import tkinter as tk
from tkinter import ttk, messagebox
from climate_data import DATA, POLYS, MONTHS, MONTH_NUM

METRICS = {
    "Jours avec ≥ 5 h de soleil": "sun",
    "Température maximale moyenne": "tmax",
    "Température minimale moyenne": "tmin",
}
LON0,LON1,LAT0,LAT1=-10.0,16.0,40.0,66.0

class ClimateApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Carte climat — France & voisins")
        self.geometry("1280x820"); self.minsize(980,650)
        self.month_var=tk.StringVar(value="Janvier")
        self.metric_var=tk.StringVar(value="Jours avec ≥ 5 h de soleil")
        self.scope_var=tk.StringVar(value="France + voisins")
        self.top_var=tk.IntVar(value=15); self.show_names_var=tk.BooleanVar(value=True)
        self.status_var=tk.StringVar(value="Données intégrées — prêt.")
        self.selected_city=None; self.city_hitboxes=[]; self.fetching=False; self._redraw_job=None
        self._build_ui(); self.bind("<Configure>",self._schedule_redraw); self.after(100,self.redraw)

    def _build_ui(self):
        self.columnconfigure(1,weight=1); self.rowconfigure(0,weight=1)
        side=ttk.Frame(self,padding=14); side.grid(row=0,column=0,sticky="ns"); side.columnconfigure(0,weight=1)
        ttk.Label(side,text="Carte climat",font=("Segoe UI",17,"bold")).grid(row=0,column=0,sticky="w")
        ttk.Label(side,text="France + voisins · septembre → avril\nUne journée solaire = ≥ 5 h de soleil effectif.",foreground="#667085",justify="left").grid(row=1,column=0,sticky="w",pady=(2,12))
        r=2
        for title,var,values in [
            ("Mois",self.month_var,MONTHS),
            ("Indicateur",self.metric_var,list(METRICS)),
            ("Zone",self.scope_var,["France + voisins","France seulement","Étranger seulement"]),
        ]:
            ttk.Label(side,text=title).grid(row=r,column=0,sticky="w"); r+=1
            cb=ttk.Combobox(side,textvariable=var,values=values,state="readonly",width=31)
            cb.grid(row=r,column=0,sticky="ew",pady=(2,9)); cb.bind("<<ComboboxSelected>>",lambda e:self.redraw()); r+=1
        opt=ttk.Frame(side); opt.grid(row=r,column=0,sticky="ew",pady=(0,8)); r+=1
        ttk.Checkbutton(opt,text="Afficher noms",variable=self.show_names_var,command=self.redraw).pack(side="left")
        ttk.Label(opt,text="Top :").pack(side="left",padx=(12,4))
        top=ttk.Combobox(opt,textvariable=self.top_var,values=[10,15,20,31],state="readonly",width=4); top.pack(side="left"); top.bind("<<ComboboxSelected>>",lambda e:self.redraw())
        ttk.Button(side,text="Recalculer soleil exact 1991–2020",command=self.recalculate_sun_openmeteo).grid(row=r,column=0,sticky="ew",pady=(2,4)); r+=1
        ttk.Label(side,text="Option Internet : recompte les jours ≥300 min via Open‑Meteo.",foreground="#667085",wraplength=310).grid(row=r,column=0,sticky="w",pady=(0,10)); r+=1
        cards=ttk.LabelFrame(side,text="Repères",padding=9); cards.grid(row=r,column=0,sticky="ew",pady=(0,10)); r+=1
        self.card_labels={}
        for i,name in enumerate(["Meilleur","Biot","Embrun","Oslo"]):
            f=ttk.Frame(cards); f.grid(row=i//2,column=i%2,sticky="nsew",padx=5,pady=4)
            ttk.Label(f,text=name,foreground="#667085").pack(anchor="w")
            lab=ttk.Label(f,text="—",font=("Segoe UI",14,"bold")); lab.pack(anchor="w"); self.card_labels[name]=lab
        cards.columnconfigure(0,weight=1); cards.columnconfigure(1,weight=1)
        ttk.Label(side,text="Classement",font=("Segoe UI",11,"bold")).grid(row=r,column=0,sticky="w"); r+=1
        rf=ttk.Frame(side); rf.grid(row=r,column=0,sticky="nsew"); side.rowconfigure(r,weight=1); r+=1
        self.ranking=tk.Listbox(rf,width=42,height=18,borderwidth=0,highlightthickness=0,font=("Consolas",9))
        sc=ttk.Scrollbar(rf,orient="vertical",command=self.ranking.yview); self.ranking.configure(yscrollcommand=sc.set)
        self.ranking.pack(side="left",fill="both",expand=True); sc.pack(side="right",fill="y"); self.ranking.bind("<<ListboxSelect>>",self._ranking_click)
        ttk.Label(side,textvariable=self.status_var,foreground="#475467",wraplength=310,justify="left").grid(row=r,column=0,sticky="ew",pady=(10,0))
        mf=ttk.Frame(self); mf.grid(row=0,column=1,sticky="nsew"); mf.rowconfigure(0,weight=1); mf.columnconfigure(0,weight=1)
        self.canvas=tk.Canvas(mf,bg="#eaf4fb",highlightthickness=0,cursor="arrow"); self.canvas.grid(row=0,column=0,sticky="nsew")
        self.canvas.bind("<Button-1>",self._map_click); self.canvas.bind("<Motion>",self._map_motion)
        self.info=ttk.Label(mf,text="Clique sur une ville pour le détail.",anchor="w",padding=(10,7)); self.info.grid(row=1,column=0,sticky="ew")

    def _schedule_redraw(self,event=None):
        if self._redraw_job: self.after_cancel(self._redraw_job)
        self._redraw_job=self.after(80,self.redraw)
    def current_month_index(self): return MONTHS.index(self.month_var.get())
    def current_metric(self): return METRICS[self.metric_var.get()]
    def visible_data(self):
        s=self.scope_var.get()
        if s=="France seulement": return [d for d in DATA if d["country"]=="FR"]
        if s=="Étranger seulement": return [d for d in DATA if d["country"]!="FR"]
        return DATA[:]
    @staticmethod
    def fmt(v,metric): return f"{v:.1f} j" if metric=="sun" else f"{v:.1f} °C"
    @staticmethod
    def color_for(v,vmin,vmax,metric):
        t=.5 if vmax==vmin else max(0,min(1,(v-vmin)/(vmax-vmin)))
        if metric=="sun": r,g,b=int(248-22*t),int(231-105*t),int(151-117*t)
        else: r,g,b=int(53+167*t),int(113-53*t),int(181-131*t)
        return f"#{r:02x}{g:02x}{b:02x}"
    @staticmethod
    def project(lon,lat,w,h):
        p=32; return p+(lon-LON0)/(LON1-LON0)*max(1,w-2*p), p+(LAT1-lat)/(LAT1-LAT0)*max(1,h-2*p)

    def redraw(self):
        if not hasattr(self,"canvas"): return
        self._redraw_job=None; self.canvas.delete("all"); self.city_hitboxes.clear()
        w=max(self.canvas.winfo_width(),650); h=max(self.canvas.winfo_height(),560)
        self.canvas.create_rectangle(0,0,w,h,fill="#eaf4fb",outline="")
        for pts in POLYS.values():
            coords=[]
            for lon,lat in pts: coords.extend(self.project(lon,lat,w,h))
            self.canvas.create_polygon(*coords,fill="#eef0e9",outline="#9aa6b2",width=1.2)
        ds=self.visible_data(); m=self.current_month_index(); metric=self.current_metric(); vals=[d[metric][m] for d in ds]; vmin,vmax=min(vals),max(vals)
        self.canvas.create_text(18,16,anchor="nw",text=f"{self.month_var.get()} — {self.metric_var.get()}",fill="#172033",font=("Segoe UI",15,"bold"))
        self.canvas.create_text(w-18,18,anchor="ne",text=f"min {self.fmt(vmin,metric)}   •   max {self.fmt(vmax,metric)}",fill="#475467",font=("Segoe UI",9))
        for d in ds:
            x,y=self.project(d["lon"],d["lat"],w,h); v=d[metric][m]; t=.5 if vmax==vmin else (v-vmin)/(vmax-vmin); rad=7+11*math.sqrt(max(0,t))
            selected=d["name"]==self.selected_city
            self.canvas.create_oval(x-rad,y-rad,x+rad,y+rad,fill=self.color_for(v,vmin,vmax,metric),outline="#7f1d1d" if selected else "#101828",width=3 if selected else 1.2)
            self.canvas.create_text(x,y,text=f"{round(v)}" if metric=="sun" else f"{v:.0f}",fill="white" if metric=="sun" and t>.55 else "#172033",font=("Segoe UI",8,"bold"))
            if self.show_names_var.get(): self.canvas.create_text(x+rad+3,y-rad-2,anchor="sw",text=d["name"],fill="#344054",font=("Segoe UI",8))
            self.city_hitboxes.append((x,y,max(11,rad),d))
        ordered=sorted(ds,key=lambda d:d[metric][m],reverse=True); self.ranking.delete(0,tk.END)
        for i,d in enumerate(ordered[:self.top_var.get()],1): self.ranking.insert(tk.END,f"{i:>2}. {d['name']:<20} {self.fmt(d[metric][m],metric):>8}")
        self.card_labels["Meilleur"].configure(text=f"{ordered[0]['name']}\n{self.fmt(ordered[0][metric][m],metric)}")
        for name in ["Biot","Embrun","Oslo"]:
            d=next(x for x in DATA if x["name"]==name); self.card_labels[name].configure(text=self.fmt(d[metric][m],metric))
        if self.selected_city: self._show_city(self.selected_city)

    def _nearest_city(self,event):
        best=None; dist0=10**9
        for x,y,r,d in self.city_hitboxes:
            dist=math.hypot(event.x-x,event.y-y)
            if dist<=max(16,r+5) and dist<dist0: best,dist0=d,dist
        return best
    def _map_click(self,event):
        d=self._nearest_city(event)
        if d: self.selected_city=d["name"]; self.redraw()
    def _map_motion(self,event): self.canvas.configure(cursor="hand2" if self._nearest_city(event) else "arrow")
    def _ranking_click(self,event=None):
        sel=self.ranking.curselection()
        if not sel: return
        text=self.ranking.get(sel[0]).split(".",1)[1].strip()
        for d in DATA:
            if text.startswith(d["name"]): self.selected_city=d["name"]; self.redraw(); return
    def _show_city(self,name):
        d=next(x for x in DATA if x["name"]==name); m=self.current_month_index()
        self.info.configure(text=f"{d['name']} ({d['country']}) — {MONTHS[m]} : {d['sun'][m]:.1f} jours ≥5 h soleil · Tmin {d['tmin'][m]:.1f} °C · Tmax {d['tmax'][m]:.1f} °C")

    def recalculate_sun_openmeteo(self):
        if self.fetching: return
        self.fetching=True; self.status_var.set("Téléchargement Open‑Meteo en cours…")
        threading.Thread(target=self._openmeteo_worker,daemon=True).start()
    def _openmeteo_worker(self):
        try:
            for start in range(0,len(DATA),5):
                batch=DATA[start:start+5]
                q=urllib.parse.urlencode({"latitude":",".join(str(d["lat"]) for d in batch),"longitude":",".join(str(d["lon"]) for d in batch),"start_date":"1991-01-01","end_date":"2020-12-31","daily":"sunshine_duration","timezone":"auto"})
                with urllib.request.urlopen("https://archive-api.open-meteo.com/v1/archive?"+q,timeout=90) as r: payload=json.loads(r.read().decode("utf-8"))
                results=payload if isinstance(payload,list) else [payload]
                if len(results)!=len(batch): raise RuntimeError("Réponse Open‑Meteo inattendue")
                for city,res in zip(batch,results):
                    counts={mo:{} for mo in MONTH_NUM}
                    for date_s,sec in zip(res["daily"]["time"],res["daily"]["sunshine_duration"]):
                        if sec is None: continue
                        y,mo,_=map(int,date_s.split("-"))
                        if mo in counts:
                            counts[mo].setdefault(y,0)
                            if sec>=18000: counts[mo][y]+=1
                    city["sun"]=[sum(v.values())/len(v) if v else 0.0 for v in (counts[mo] for mo in MONTH_NUM)]
                done=min(start+len(batch),len(DATA)); self.after(0,lambda n=done:self.status_var.set(f"Open‑Meteo : {n}/{len(DATA)} villes…"))
            self.after(0,self._online_done)
        except Exception as exc: self.after(0,lambda:self._online_error(str(exc)))
    def _online_done(self): self.fetching=False; self.status_var.set("Soleil recalculé jour par jour (1991–2020)."); self.redraw()
    def _online_error(self,msg):
        self.fetching=False; self.status_var.set("Échec Open‑Meteo — données intégrées conservées."); messagebox.showwarning("Open‑Meteo",msg)

if __name__=="__main__": ClimateApp().mainloop()
