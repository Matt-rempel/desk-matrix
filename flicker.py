"""Bounded software-only A/B trials. No shell commands, GPIO wiring or library edits."""
from contextlib import contextmanager
from functools import lru_cache
import fcntl
import json
import math
import os
from pathlib import Path
import pwd
import re
import secrets
import tempfile
import time

DRIVER_KEYS = ('gpio_slowdown', 'pwm_bits', 'pwm_lsb_nanoseconds', 'pwm_dither_bits', 'limit_refresh_rate_hz')
RESTART_EXIT = 75


def _profile(name, detail, driver=None, fps=20, pause=False, freeze=False):
    return {'name':name, 'detail':detail, 'driver':driver or {}, 'fps':fps, 'pause':pause, 'freeze':freeze}


PROFILES = {
    'baseline': _profile('Current baseline', 'Your normal driver settings and 20 FPS rendering.'),
    **{f'gpio-{v}':_profile(f'GPIO slowdown {v}', 'Slower data/clock edges; may reduce random pixels at the cost of refresh speed.', {'gpio_slowdown':v}) for v in (3,4,5,8)},
    **{f'pwm-{v}':_profile(f'PWM depth {v} bits', 'Fewer color levels, less refresh work. Dim colors may disappear.', {'pwm_bits':v}) for v in (9,7,5)},
    **{f'lsb-{v}':_profile(f'Longer PWM pulse {v} ns', 'Longer shortest pulse; may help panel settling but lowers refresh speed.', {'pwm_lsb_nanoseconds':v}) for v in (180,240,300)},
    **{f'dither-{v}':_profile(f'Dither {v} bit'+('s' if v>1 else ''), 'Temporal color dithering trades fine color detail for refresh behavior.', {'pwm_dither_bits':v}) for v in (1,2)},
    **{f'cap-{v}':_profile(f'Refresh cap {v} Hz', 'A maximum, not a measured refresh rate. Has no effect if the panel is already slower.', {'limit_refresh_rate_hz':v}) for v in (120,200)},
    **{f'fps-{v}':_profile(f'App rendering {v} FPS', 'Reduce Python rendering load; hardware scanning continues independently.', fps=v) for v in (10,5,1)},
    'quiet': _profile('Pause live-data polling', 'Use cached data while pausing new provider requests. Tailscale and the web app stay on.', pause=True),
    'freeze': _profile('Freeze each rendered screen', 'Render each screen once, then hold its pixels. Hardware scanning continues.', freeze=True),
}
PATTERNS = {'pattern:contrast':'Sharp white text', 'pattern:rgb':'RGB color bars',
            'pattern:gray':'Grayscale ramp', 'pattern:grid':'Checkerboard'}
REF_RE = re.compile(r'(?:[a-z][a-z0-9-]{0,80}|pattern:(?:contrast|rgb|gray|grid)|lineup)\Z')
RUN_RE = re.compile(r'[a-f0-9]{32}\Z')


def read_json(path, default=None):
    try:
        with Path(path).open('rb') as f:
            raw = f.read(262145)
        if len(raw)>262144: return default
        value = json.loads(raw)
        return value if isinstance(value,dict) else default
    except (OSError,ValueError,TypeError):
        return default


def _owner(fd):
    if os.geteuid()==0:
        try:
            account=pwd.getpwnam('flightboard')
            os.fchown(fd,account.pw_uid,account.pw_gid)
        except KeyError: pass


def write_json(path, value):
    path=Path(path)
    with tempfile.NamedTemporaryFile('w',dir=path.parent,prefix='.flicker-',delete=False) as f:
        name=f.name
        try:
            os.fchmod(f.fileno(),0o640)
            _owner(f.fileno())
            json.dump(value,f,separators=(',',':'),allow_nan=False)
            f.flush()
            os.fsync(f.fileno())
            os.replace(name,path)
        finally:
            if os.path.exists(name): os.unlink(name)


def _integer(value, low, high, name):
    if isinstance(value,bool) or not isinstance(value,int) or not low<=value<=high:
        raise ValueError(f'{name} must be {low}–{high}')
    return value


def validate_spec(body, lib=None):
    keys={'profiles','screens','duration_minutes','profile_minutes','screen_seconds','brightness'}
    if set(body)!=keys: raise ValueError('Choose profiles, screens, duration, time per profile/screen and brightness')
    profiles,screens=body['profiles'],body['screens']
    if not isinstance(profiles,list) or not 1<=len(profiles)<=20 or any(not isinstance(p,str) or p not in PROFILES for p in profiles):
        raise ValueError('Choose 1–20 software profiles')
    if len(set(profiles))!=len(profiles): raise ValueError('Choose each profile once; the sequence repeats automatically')
    if not isinstance(screens,list) or not 1<=len(screens)<=12 or any(not isinstance(s,str) or not REF_RE.fullmatch(s) for s in screens):
        raise ValueError('Choose 1–12 screens')
    if len(set(screens))!=len(screens): raise ValueError('Choose each screen once')
    if lib is not None:
        from library import resolve_screen
        for sid in screens:
            if sid!='lineup' and sid not in PATTERNS and resolve_screen(lib,sid) is None:
                raise ValueError('One selected screen is no longer available')
    duration=_integer(body['duration_minutes'],5,1440,'Run minutes')
    dwell=_integer(body['profile_minutes'],5,120,'Minutes per profile')
    if duration < dwell*len(profiles): raise ValueError('Run long enough to try every selected profile once')
    _integer(body['screen_seconds'],10,3600,'Seconds per screen')
    _integer(body['brightness'],1,50,'Test brightness')
    if dwell*60 < body['screen_seconds']*len(screens): raise ValueError('Each profile needs enough time to show all selected screens')
    return {**body,'profiles':list(profiles),'screens':list(screens)}


def driver_settings(baseline, trial):
    return {**baseline, **(trial['profile']['driver'] if trial else {})}


class Store:
    def __init__(self, root):
        self.root=Path(root)
        self.path=self.root/'flicker.json'
        self.live_path=self.root/'flicker-live.json'

    def load(self):
        try: stamp=self.path.stat().st_mtime_ns
        except OSError: stamp=None
        if not hasattr(self,'_stamp') or self._stamp!=stamp:
            self._stamp,self._state=stamp,read_json(self.path,{})
        return self._state

    @contextmanager
    def transaction(self):
        fd=os.open(self.root/'flicker.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o640)
        try:
            _owner(fd)
            fcntl.flock(fd,fcntl.LOCK_EX)
            yield
        finally: os.close(fd)

    def active(self, now=None):
        now=time.time() if now is None else now
        state=self.load()
        plan=state.get('current')
        try:
            if not isinstance(plan,dict) or state.get('blocked_run')==plan['run_id'] or plan.get('stopped_at') is not None: return None
            if not isinstance(plan['run_id'],str) or not RUN_RE.fullmatch(plan['run_id']): return None
            spec=validate_spec({k:plan[k] for k in ('profiles','screens','duration_minutes','profile_minutes','screen_seconds','brightness')})
            start=plan['started_at']
            if isinstance(start,bool) or not isinstance(start,(int,float)) or not math.isfinite(start): return None
            elapsed=now-start
            if not 0<=elapsed<spec['duration_minutes']*60: return None
            step=int(elapsed//(spec['profile_minutes']*60))
            if len(spec['profiles'])==1:step=0
            profile_id=spec['profiles'][step%len(spec['profiles'])]
            within=elapsed%(spec['profile_minutes']*60)
            if len(spec['profiles'])==1:within=elapsed
            return {'run_id':plan['run_id'],'target':f'{plan["run_id"]}:{step}','step':step,
                    'profile_id':profile_id,'profile':PROFILES[profile_id],
                    'screen_id':spec['screens'][int(within//spec['screen_seconds'])%len(spec['screens'])],
                    'brightness':spec['brightness'],'remaining_s':max(0,int(spec['duration_minutes']*60-elapsed)),
                    'profile_remaining_s':max(0,int((spec['duration_minutes'] if len(spec['profiles'])==1 else spec['profile_minutes'])*60-within))}
        except (KeyError,TypeError,ValueError,OverflowError): return None

    def startup(self, now=None):
        now=time.time() if now is None else now
        trial=self.active(now)
        if not trial: return None
        previous=read_json(self.root/'flicker-attempt.json',{})
        if previous.get('target')==trial['target'] and 0<=now-previous.get('at',0)<120:
            with self.transaction():
                state=self.load()
                state.update(blocked_run=trial['run_id'],error='Trial stopped after an unexpected display restart. Returning to baseline.')
                write_json(self.path,state)
            return None
        write_json(self.root/'flicker-attempt.json',{'target':trial['target'],'at':now})
        return trial

    def status(self, live=None, now=None):
        now=time.time() if now is None else now
        state=self.load()
        live=live if live is not None else read_json(self.live_path,{})
        plan=state.get('current') or {}
        trial=self.active(now)
        mode=('error' if plan and state.get('blocked_run')==plan.get('run_id') else 'running' if trial else
              'stopped' if plan.get('stopped_at') else 'completed' if plan else 'idle')
        baseline=(live.get('driver') or {}).get('baseline') or {}
        saved=read_json(self.root/'flicker-measurements.json',{})
        current=[] if saved.get('archive_id')==live.get('measurement_id') else live.get('measurements',[])
        measurements=saved.get('rows',[])+current
        return {'state':mode,'current':plan or None,'trial':trial,'live':live,
                'error':state.get('error') if mode=='error' else None,
                'notes':state.get('notes',[]),'runs':state.get('runs',[]),
                'presets':[{'id':k,**v,'supported':all(key in baseline for key in v['driver'])} for k,v in PROFILES.items()],
                'patterns':PATTERNS,'normal_baseline':baseline,
                'measurements':[row for row in measurements if row.get('run_id')==plan.get('run_id')][-160:],
                'aggregates':aggregate(saved.get('aggregates',[]),current,plan.get('run_id')),
                'ready':bool(live.get('restart_supported') and 0<=now-live.get('updated_at',0)<30)}

    def action(self, body, lib, live=None, now=None):
        now=time.time() if now is None else now
        live=live if live is not None else read_json(self.live_path,{})
        if not isinstance(body,dict): raise ValueError('Send a flicker action')
        action=body.get('action')
        with self.transaction():
            state=self.load()
            if action=='start':
                spec=validate_spec({k:v for k,v in body.items() if k!='action'},lib)
                if not self.status(live,now)['ready']: raise ValueError('The display service is not ready for automatic trial restarts')
                if self.active(now): raise ValueError('Stop the current run before starting another')
                baseline=(live.get('driver') or {}).get('baseline') or {}
                for profile in spec['profiles']:
                    if any(key not in baseline for key in PROFILES[profile]['driver']): raise ValueError('That profile is not supported by the installed driver')
                runs=list(state.get('runs',[]))
                if state.get('current'): runs.append({'plan':state['current'],'notes':state.get('notes',[])[-20:],
                                                      'last_metrics':live.get('metrics')})
                state={'current':{**spec,'run_id':secrets.token_hex(16),'started_at':now},'runs':runs[-8:],'notes':[]}
            elif action=='stop' and set(body)=={'action'}:
                if state.get('current'): state['current']['stopped_at']=now
            elif action=='note' and set(body)=={'action','rating','text'}:
                if not state.get('current'): raise ValueError('Start a run before recording an observation')
                if body['rating'] not in ('none','better','same','worse'): raise ValueError('Choose an observation rating')
                if not isinstance(body['text'],str) or len(body['text'])>500: raise ValueError('Notes may contain up to 500 characters')
                # Attribute observations to what the display acknowledged, even
                # if the clock has already queued the next driver restart.
                observed=live.get('trial') or {}
                if observed.get('run_id') != state['current']['run_id']:
                    raise ValueError('Wait for the display to acknowledge this run before recording an observation')
                note={'at':now,'run_id':state['current']['run_id'],'profile_id':observed.get('profile_id'),
                      'screen_id':observed.get('screen_id'),'step':observed.get('step'),
                      'rating':body['rating'],'text':body['text']}
                state['notes']=(state.get('notes',[])+[note])[-200:]
            else: raise ValueError('Unknown flicker action')
            write_json(self.path,state)
        return self.status(live,now)


@lru_cache(maxsize=4)
def pattern(name):
    from clock_canvas import Canvas
    c=Canvas()
    if name=='pattern:contrast':
        c.text('88:88',0,0,64,22,'#FFFFFF',face='block',size='xl')
        c.text('PIXEL TEST',0,27,64,5,'#FFFFFF')
    elif name=='pattern:rgb':
        for x,color in ((0,'#FF0000'),(21,'#00FF00'),(42,'#0000FF')):c.rect(x,0,min(63,x+20),31,color)
    elif name=='pattern:gray':
        for x in range(64):c.line(x,0,x,31,(round(x*255/63),)*3)
    else:
        for y in range(32):
            for x in range(64):
                if (x//2+y//2)%2==0:c.point(x,y,'#FFFFFF')
    return c.pixels


class TrialRenderer:
    def __init__(self):
        self.key=None
        self.cached=None

    def draw(self,trial,draw):
        key=(trial['target'],trial['screen_id']) if trial else None
        if trial and trial['profile']['freeze'] and key==self.key and self.cached is not None:
            return self.cached
        result=draw()
        self.key,self.cached=key,result
        return result


class Measurements:
    """App render/swap timings, never an optical glitch detector or refresh-Hz estimate."""
    def __init__(self):
        self.rows={}
        self.started=time.monotonic()
        self.instance_id=secrets.token_hex(8)

    def add(self, trial, render_ms, swap_ms, swapped, paint_ms=0, error=False):
        if not trial:return
        key=(trial['target'],trial['screen_id'])
        row=self.rows.setdefault(key,{'run_id':trial['run_id'],'step':trial['step'],
            'profile_id':trial['profile_id'],'screen_id':trial['screen_id'],
            'selection_id':trial.get('selection_id',trial['screen_id']),'measurement_id':self.instance_id,
            'samples':0,'swaps':0,'render_ms_total':0,'render_ms_max':0,'swap_ms_total':0,
            'paint_ms_total':0,'render_errors':0,
            'started_at':time.time()})
        row['samples']+=1
        row['swaps']+=int(swapped)
        row['render_ms_total']+=render_ms
        row['render_ms_max']=max(row['render_ms_max'],render_ms)
        row['swap_ms_total']+=swap_ms
        row['paint_ms_total']+=paint_ms
        row['render_errors']+=int(bool(error))
        row['updated_at']=time.time()

    def report(self):
        return [{**row,'render_ms_mean':round(row['render_ms_total']/row['samples'],3),
                 'paint_ms_mean':round(row['paint_ms_total']/max(1,row['swaps']),3),
                 'swap_ms_mean':round(row['swap_ms_total']/max(1,row['swaps']),3),
                 'render_ms_max':round(row['render_ms_max'],3)} for row in self.rows.values()]

    def archive(self, root):
        if not self.rows:return
        path=Path(root)/'flicker-measurements.json'
        saved=read_json(path,{})
        rows=self.report()
        write_json(path,{'rows':(saved.get('rows',[])+rows)[-160:], 'archive_id':self.instance_id,
                         'aggregates':aggregate(saved.get('aggregates',[]),rows,rows[0]['run_id'])})

    def current(self, trial):
        if not trial:return {}
        return next((row for row in self.report() if row['run_id']==trial['run_id']
                     and row['step']==trial['step'] and row['screen_id']==trial['screen_id']),{})


def aggregate(previous, rows, run_id):
    """Retain whole-run comparisons, bounded by profiles × selected sources."""
    groups={(r['profile_id'],r['selection_id']):dict(r) for r in previous if r.get('run_id')==run_id}
    for row in rows:
        if row.get('run_id')!=run_id:continue
        selected=row.get('selection_id',row['screen_id'])
        key=(row['profile_id'],selected)
        if key not in groups:
            groups[key]={k:v for k,v in row.items() if k not in ('step','screen_id','measurement_id')}
            groups[key]['selection_id']=selected
            continue
        value=groups[key]
        for field in ('samples','swaps','render_ms_total','paint_ms_total','swap_ms_total','render_errors'):
            value[field]+=row[field]
        value['render_ms_max']=max(value['render_ms_max'],row['render_ms_max'])
        value['started_at']=min(value['started_at'],row['started_at'])
        value['updated_at']=max(value['updated_at'],row['updated_at'])
    for value in groups.values():
        value['render_ms_mean']=round(value['render_ms_total']/value['samples'],3)
        value['paint_ms_mean']=round(value['paint_ms_total']/max(1,value['swaps']),3)
        value['swap_ms_mean']=round(value['swap_ms_total']/max(1,value['swaps']),3)
    return list(groups.values())
