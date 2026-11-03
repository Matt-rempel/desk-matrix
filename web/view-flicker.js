// Long-running, software-only display trials. Scheduling lives on the Pi.
import { state, subscribe, findScreen } from './store.js';
import { api } from './api.js';
import { h, header, messageLine, chips, busy } from './ui.js';
import { createMatrix } from './matrix.js';

const selectedProfiles = new Set(['baseline', 'gpio-3', 'pwm-9']);
const selectedScreens = new Set(['time-classic', 'time-clockwork', 'time-tracker']);
const date = value => new Date(value * 1000).toLocaleString();
const minutes = seconds => `${Math.max(0, Math.ceil(seconds / 60))} min`;

export function render(root) {
  root.classList.add('flicker-page');
  let data = null, closed = false, polling = false, rating = 'same', choicesKey = '';
  const msg = messageLine();
  root.append(header({ back:'#/device', backLabel:'Back to device', title:'Debug flicker' }),
    h('p', { class:'intro' }, 'Compare software settings on the real display. Runs keep going when you close this page and return to normal at the end.'));
  const status = h('div', { class:'card card-pad', role:'status', 'aria-live':'polite' });
  const matrix = createMatrix({ pitch:10, label:'Current physical display content (intended pixels)' });
  const stop = h('button', { type:'button', class:'btn btn-danger-outline', disabled:true }, 'Stop and restore normal');
  const download = h('button', { type:'button', class:'btn btn-secondary' }, 'Download test report');
  root.append(status, h('div', { class:'flicker-preview' }, matrix.el), h('div', { class:'btn-row' }, stop, download), msg);
  const profiles = h('div', { class:'flicker-choices' });
  const profileCount = h('span', { class:'subtle' });
  const screenChoices = h('div', { class:'flicker-choices' });
  const screenCount = h('span', { class:'subtle' });
  const search = h('input', { class:'input', type:'search', 'aria-label':'Find test screens', placeholder:'Find a screen…' });
  const form = h('form', { class:'card card-pad flicker-form' });
  const configure = h('fieldset', { class:'flicker-fieldset' });
  const select = (label, values, initial) => {
    const id = `flicker-${label.toLowerCase().replace(/\W+/g,'-')}`;
    const input = h('select', { class:'input', id }, values.map(([value,name]) => h('option', { value, selected:value===initial }, name)));
    return { input, el:h('div', { class:'field' }, h('label', { class:'field-label', for:id }, label), input) };
  };
  const duration = select('Total run time', [[30,'30 minutes'],[60,'1 hour'],[120,'2 hours'],[240,'4 hours'],[480,'8 hours'],[1440,'24 hours']],60);
  const dwell = select('Time per profile', [[5,'5 minutes'],[10,'10 minutes'],[15,'15 minutes'],[30,'30 minutes'],[60,'1 hour']],15);
  const hold = select('Time per screen', [[30,'30 seconds'],[60,'1 minute'],[120,'2 minutes'],[300,'5 minutes']],60);
  const level = select('Fixed brightness', [[5,'5%'],[10,'10%'],[20,'20%'],[30,'30%'],[40,'40%'],[50,'50%']],20);
  const start = h('button', { type:'submit', class:'btn btn-primary', disabled:true }, 'Start test run');
  configure.append(h('legend', { class:'row-title strong' }, 'Set up a comparison'),
    h('details', { open:true }, h('summary', null, 'Software profiles · ',profileCount),
      h('p', { class:'card-note' }, 'Profiles run in the order below, then repeat. Include Current baseline for comparison. Each timing preset changes one driver control.'), profiles),
    h('details', null, h('summary', null, 'Screens to loop · ',screenCount),
      h('p', { class:'card-note' }, 'Each profile uses the same screen order. Choose up to 12 screens. Freeze + Current lineup holds the first screen it sees.'), search, screenChoices),
    h('div', { class:'field-pair' }, duration.el, dwell.el), h('div', { class:'field-pair' }, hold.el, level.el),
    h('p', { class:'card-note' }, 'Test brightness respects your device ceiling. Your normal brightness, lineup and pins are saved separately.'),
    h('p', { class:'card-note' }, 'The display restarts between profiles, usually taking 10–30 seconds; that time counts toward the run. Stop or expiry restores your normal driver settings.'),start);
  form.append(configure);root.append(form);
  const notes = h('textarea', { class:'input', rows:3, maxlength:500, 'aria-label':'Flicker observation', placeholder:'What flashed? Which rows or colors? How often?' });
  const saveNote = h('button', { type:'button', class:'btn btn-secondary', disabled:true }, 'Record observation');
  const observations = h('div', { class:'flicker-observations' });
  root.append(h('section', { class:'card card-pad flicker-notes' }, h('h2', { class:'row-title strong' }, 'What do you see?'),
    h('p', { class:'card-note' }, 'The Pi cannot count physical flashes. These ratings are your observations; rendering timings below are software measurements.'),
    chips({ label:'Flicker rating', value:rating, choices:[['none','No flashes seen'],['better','Better'],['same','Same'],['worse','Worse']].map(([id,label])=>({id,label})), onChange:value=>{rating=value;} }), notes, saveNote, observations));
  const details = h('div', { class:'card card-pad' });root.append(details);
  root.append(h('p', { class:'foot-note' }, 'Stock Bonnet software timing has a known flicker limitation. These are experiments, not guaranteed fixes. Wiring, audio, CPU governor, networking and kernel settings are not changed.'));
  const checkbox = (id,title,detail,set,disabled=false) => {
    const input = h('input', { type:'checkbox', checked:set.has(id), disabled, value:id });
    const label = h('label', { class:'flicker-choice' }, input, h('span', null, h('span', { class:'row-title' }, title), detail ? h('span', { class:'row-detail' }, detail) : null));
    input.addEventListener('change',()=>{ if(input.checked)set.add(id);else set.delete(id); updateCounts(); });
    return label;
  };
  function updateCounts() { profileCount.textContent=`${selectedProfiles.size} selected`; screenCount.textContent=`${selectedScreens.size} selected`; }
  function drawChoices() {
    const key = JSON.stringify(data.presets.map(p=>[p.id,p.supported]));
    if (key===choicesKey)return;choicesKey=key;
    for (const p of data.presets) if (!p.supported) selectedProfiles.delete(p.id);
    profiles.replaceChildren(...data.presets.map(p=>checkbox(p.id,p.name,p.supported?p.detail:'Not supported by this driver',selectedProfiles,!p.supported)));
    const screens = [{id:'lineup',name:'Current lineup',detail:'Includes its normal schedules and alerts'},
      ...Object.entries(data.patterns).map(([id,name])=>({id,name,detail:'Diagnostic pattern'})),
      ...(state.library?.screens||[]).map(s=>({id:s.id,name:s.name,detail:'Your screen'})),
      ...(state.catalog?.shelves||[]).flatMap(s=>s.screens.map(findScreen).filter(Boolean)).map(s=>({id:s.id,name:s.name,detail:s.source||'Built-in'}))];
    const seen = new Set();
    screenChoices.replaceChildren(...screens.filter(s=>{if(seen.has(s.id))return false;seen.add(s.id);return true;}).map(s=>{
      const label = checkbox(s.id,s.name,s.detail,selectedScreens);label.dataset.search=s.name.toLowerCase();return label;
    }));
    updateCounts();
  }
  function show() {
    if (!data)return;
    drawChoices();
    const live=data.live||{}, actual=live.trial, desired=data.trial;
    const acknowledged=desired ? actual?.target===desired.target : !actual;
    const fresh=Date.now()/1000-(live.updated_at||0)<15;
    const title = data.state==='running' ? acknowledged&&fresh ? actual.profile.name : 'Applying the next profile…'
      : data.state==='error' ? 'Test stopped after a display error' : !acknowledged ? 'Restoring normal display…'
      : ({idle:'Ready to compare',stopped:'Run stopped',completed:'Run completed'}[data.state]||'Debug flicker');
    status.replaceChildren(...[h('h2', { class:'row-title strong' },title),
      h('p', { class:'row-detail' }, desired ? `${minutes(desired.remaining_s)} left · ${minutes(desired.profile_remaining_s)} in this profile` : 'Normal settings return automatically after a run.'),
      h('p', { class:'card-note' }, actual ? `On the panel: ${live.screen_name||actual.screen_id}. ${actual.profile.freeze?'Frame frozen. ':''}${actual.profile.pause?'Live-data requests paused.':''}` : data.ready?'Display service ready.':'Waiting for the updated display service…'),
      data.error?h('p',{class:'error'},data.error):null].filter(Boolean));
    configure.disabled=data.state==='running';start.disabled=!data.ready||data.state==='running';
    stop.disabled=!data.current||(!actual&&data.state!=='running');saveNote.disabled=!actual||actual.run_id!==data.current?.run_id||!fresh;
    observations.replaceChildren(...(data.notes||[]).slice(-8).reverse().map(n=>h('p',{class:'card-note'},`${date(n.at)} · ${n.profile_id||'Run'} · ${n.screen_id||''} · ${n.rating}: ${n.text}`)));
    const driver=live.driver||{}, effective=driver.effective||{}, metrics=live.metrics||{};
    details.replaceChildren(h('h2',{class:'row-title strong'},'Applied settings & measurements'),
      h('p',{class:'card-note'}, `Mapping: ${driver.mapping||'unknown'} · ${driver.software_pulse?'software pulse':'pulse mode not reported'} · App limit: ${live.app_fps_limit||20} FPS`),
      h('dl',{class:'flicker-metrics'}, ...[
        ['GPIO slowdown',effective.gpio_slowdown],['PWM bits',effective.pwm_bits],['Dither bits',effective.pwm_dither_bits],
        ['Shortest pulse',effective.pwm_lsb_nanoseconds==null?'—':`${effective.pwm_lsb_nanoseconds} ns`],
        ['Refresh cap',effective.limit_refresh_rate_hz?`${effective.limit_refresh_rate_hz} Hz`:'Uncapped'],
        ['Mean render',metrics.render_ms_mean==null?'—':`${metrics.render_ms_mean.toFixed(2)} ms`],
        ['Max render',metrics.render_ms_max==null?'—':`${metrics.render_ms_max.toFixed(2)} ms`],
        ['Mean paint',metrics.paint_ms_mean==null?'—':`${metrics.paint_ms_mean.toFixed(2)} ms`],
        ['Mean swap wait',metrics.swap_ms_mean==null?'—':`${metrics.swap_ms_mean.toFixed(2)} ms`],
        ['Software render errors',metrics.render_errors??0],
        ['CPU temperature',live.health?.cpu_temp_c==null?'—':`${live.health.cpu_temp_c}°C`],
        ['Under-voltage',live.health?.under_voltage==null?'Not reported':live.health.under_voltage?'Yes':'No'],
        ['CPU throttling',live.health?.throttled==null?'Not reported':live.health.throttled?'Yes':'No'],
      ].flatMap(([label,value])=>[h('dt',null,label),h('dd',null,String(value??'—'))])),
      h('p',{class:'card-note'},'Hardware refresh Hz is not measured. The refresh cap is only a limit; app FPS is a separate rendering rate.'),
      h('p',{class:'card-note'},`Report includes ${data.aggregates?.length||0} whole-run comparison aggregates, the latest ${data.measurements?.length||0} detailed timing records (up to 160), and ${data.runs?.length||0} previous run summaries.`));
    if(state.status?.frame)matrix.setFrame(state.status.frame);
  }
  async function poll() {
    if(closed||document.hidden||polling)return;polling=true;
    try { const result=await api.flicker();if(!closed){data=result;show();} }
    catch(error){if(!closed)msg.error(error);} finally{polling=false;}
  }
  form.addEventListener('submit',async event=>{
    event.preventDefault();busy(start,true,'Starting…');
    try {
      data=await api.flickerAction({action:'start',profiles:data.presets.filter(p=>selectedProfiles.has(p.id)).map(p=>p.id),
        screens:[...screenChoices.querySelectorAll('input:checked')].map(input=>input.value),duration_minutes:Number(duration.input.value),profile_minutes:Number(dwell.input.value),
        screen_seconds:Number(hold.input.value),brightness:Number(level.input.value)});show();msg.show('Run started. You can leave this page open or close it.');
    } catch(error){msg.error(error);}finally{busy(start,false);if(data)start.disabled=!data.ready||data.state==='running';}
  });
  stop.addEventListener('click',async()=>{busy(stop,true,'Restoring…');try{data=await api.flickerAction({action:'stop'});show();msg.show('Stopping. The display will return to normal shortly.');}catch(error){msg.error(error);}finally{busy(stop,false);}});
  saveNote.addEventListener('click',async()=>{try{data=await api.flickerAction({action:'note',rating,text:notes.value.trim()});notes.value='';show();msg.show('Observation recorded.');}catch(error){msg.error(error);}});
  download.addEventListener('click',()=>{if(!data)return;const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));const a=h('a',{href:url,download:'desk-matrix-flicker-report.json'});a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
  search.addEventListener('input',()=>{for(const row of screenChoices.children)row.hidden=!row.dataset.search.includes(search.value.toLowerCase());});
  const unsubscribe=subscribe(what=>{if(what==='status'&&state.status?.frame)matrix.setFrame(state.status.frame);});
  poll();const timer=setInterval(poll,3000);
  document.addEventListener('visibilitychange',poll);
  return ()=>{closed=true;clearInterval(timer);document.removeEventListener('visibilitychange',poll);unsubscribe();matrix.destroy();};
}
