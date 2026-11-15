"""
ichor_voice_monitor.py - live microphone monitor (runs 100 % in the browser, nothing is recorded or uploaded)
that estimates breathing rate and voice stress, classifies the state and plays calming music.

HONEST LIMITS (also shown in the UI):
 * This is a HEURISTIC screening aid, NOT a medical device and NOT validated. Thresholds are team assumptions
   built on published reference values (adult resting breathing 12-20 /min; >20 /min is abnormal at rest).
 * Voice-stress detection needs a personal calm baseline (the CALIBRATE button). Without it only breathing rules run.
 * Breathing is measured from the sound envelope of the 300-2500 Hz band while the person is NOT speaking.
 * Microphone access needs https:// or http://localhost, and the browser will ask permission.

The music is generated live with the Web Audio API (no copyrighted tracks) from parameters taken from the
music-and-stress literature, see MUSIC_REFERENCES below.
"""
from __future__ import annotations

import json

# ---- thresholds (shared with ichor_mind.py so Python and JS always agree) --------------------------------------
REST_LO, REST_HI = 12, 20      # normal adult resting breaths per minute
HEAVY_RATE = 24                # heavy breathing
PANIC_RATE = 30                # panic-like / hyperventilation (or HEAVY_RATE + voice stress)
STRESS_SCORE = 50              # voice stress score 0-100 vs personal baseline
IRREGULAR_CV = 0.35            # coefficient of variation of breath intervals

MUSIC_PARAMS = {
    "tempo_bpm": 60, "breaths_per_min": 6, "inhale_s": 4, "exhale_s": 6,
    "register": "C2-A4 (low to mid)", "harmony": "C major pentatonic, consonant, no lyrics",
    "dynamics": "soft, no sudden changes, slow swell synced to breathing, silent pauses",
}
MUSIC_REFERENCES = [
    "Bernardi L, Porta C, Sleight P. Heart 2006;92:445-452: slow-tempo music and the pauses between pieces lower "
    "heart rate / blood pressure / breathing, fast music raises them (basis of the 60 bpm tempo and the silences).",
    "Lehrer PM, Gevirtz R. Front Psychol 2014;5:756: breathing at about 6 breaths/min (0.1 Hz, 'resonance "
    "frequency') maximises heart-rate-variability (basis of the 4 s inhale / 6 s exhale swell).",
    "Zaccaro A et al. Front Hum Neurosci 2018;12:353: slow breathing is linked to calm / relaxed states.",
    "Thoma MV et al. PLoS ONE 2013;8:e70156: listening to relaxing music speeds recovery of the stress response (cortisol, alpha-amylase).",
    "de Witte M et al. Health Psychol Rev 2020;14:294-324: music interventions reduce stress with a small-to-moderate "
    "effect (about d = 0.4). Effects are real but modest: music supports, it does not replace, treatment.",
]

CORE_JS = r"""
var VM=(function(){
  var C=__CONST__;
  function clamp(x,a,b){return Math.max(a,Math.min(b,x));}
  function smooth(a,k){var out=new Array(a.length),s=0,q=[];for(var i=0;i<a.length;i++){s+=a[i];q.push(a[i]);if(q.length>k){s-=q.shift();}out[i]=s/q.length;}return out;}
  /* breathing from a band-pass envelope sampled at hz (>= 15 s of data) */
  function breathing(env,hz){
    var n=env.length;if(n<hz*15)return {rate:null,reason:'short'};
    var sm=smooth(env,Math.max(3,Math.round(hz*0.5))),mn=1e9,mx=-1e9,sum=0,i;
    for(i=0;i<n;i++){if(sm[i]<mn)mn=sm[i];if(sm[i]>mx)mx=sm[i];sum+=env[i];}
    var amp=mx-mn;if(amp<0.0008)return {rate:null,reason:'no-signal',mean:sum/n};
    var thr=mn+0.4*amp,gap=Math.round(hz*1.0),pk=[];
    for(i=1;i<n-1;i++){
      if(sm[i]>thr&&sm[i]>=sm[i-1]&&sm[i]>sm[i+1]){
        if(pk.length&&i-pk[pk.length-1]<gap){if(sm[i]>sm[pk[pk.length-1]])pk[pk.length-1]=i;}else pk.push(i);
      }
    }
    if(pk.length<3)return {rate:null,reason:'few-peaks',mean:sum/n};
    var iv=[],j;for(j=1;j<pk.length;j++)iv.push((pk[j]-pk[j-1])/hz);
    var s=iv.slice().sort(function(a,b){return a-b;}),med=s[Math.floor(s.length/2)];
    var m=0;for(j=0;j<iv.length;j++)m+=iv[j];m/=iv.length;
    var v=0;for(j=0;j<iv.length;j++)v+=(iv[j]-m)*(iv[j]-m);v=Math.sqrt(v/iv.length);
    return {rate:60/med,cv:v/m,mean:sum/n,amp:amp,peaks:pk.length};
  }
  /* fundamental frequency by autocorrelation, 75-400 Hz; returns {f0,r} or null if not voiced */
  function pitch(buf,sr){
    var n=buf.length,mean=0,i,lag;for(i=0;i<n;i++)mean+=buf[i];mean/=n;
    var x=new Float32Array(n),r0=0;for(i=0;i<n;i++){x[i]=buf[i]-mean;r0+=x[i]*x[i];}
    if(r0<=1e-9)return null;
    var lo=Math.floor(sr/400),hi=Math.min(Math.floor(sr/75),n>>1),nr=new Float32Array(hi+2),best=0;
    for(lag=lo;lag<=hi;lag++){var s=0;for(i=0;i<n-lag;i++)s+=x[i]*x[i+lag];nr[lag]=s/r0*(n/(n-lag));if(nr[lag]>best)best=nr[lag];}
    if(best<0.5)return null;
    for(lag=lo+1;lag<hi;lag++){
      if(nr[lag]>=0.9*best&&nr[lag]>=nr[lag-1]&&nr[lag]>=nr[lag+1]){
        var a=nr[lag-1],b=nr[lag],c=nr[lag+1],d=a-2*b+c,off=d!==0?0.5*(a-c)/d:0;
        return {f0:sr/(lag+off),r:nr[lag]};
      }
    }
    return null;
  }
  function stats(a){var m=0,i;for(i=0;i<a.length;i++)m+=a[i];m/=a.length;var v=0;for(i=0;i<a.length;i++)v+=(a[i]-m)*(a[i]-m);return {mean:m,sd:Math.sqrt(v/a.length)};}
  /* voice features of a set of voiced frames: mean f0, sd in semitones, mean level in dBFS */
  function voiceFeat(f0s,dbs){
    if(f0s.length<15)return null;
    var st=f0s.map(function(f){return 12*Math.log(f)/Math.LN2;});
    return {f0:stats(f0s).mean,sd:stats(st).sd,db:stats(dbs).mean};
  }
  function stressScore(v,b){
    if(!v||!b)return null;
    var df=(v.f0-b.f0)/b.f0*100,sdr=v.sd/Math.max(b.sd,0.3),dd=v.db-b.db;
    return Math.round(40*clamp(df/15,0,1)+30*clamp((sdr-1)/0.5,0,1)+30*clamp(dd/6,0,1));
  }
  function classify(rate,cv,stress){
    var s=stress==null?0:stress,kind='NORMAL';
    if(s>=C.STRESS)kind='STRESS';
    if(rate!=null&&rate>=C.HEAVY)kind='HEAVY_BREATHING';
    if(rate!=null&&(rate>=C.PANIC||(rate>=C.HEAVY&&s>=C.STRESS)))kind='PANIC';
    return kind;
  }
  var RANK={NORMAL:0,STRESS:1,HEAVY_BREATHING:2,PANIC:3};
  /* sustained state: every one of the last k raw results must be abnormal; state = the mildest of them */
  function sustained(hist,k){
    if(hist.length<k)return 'NORMAL';
    var last=hist.slice(-k),min=3,i;
    for(i=0;i<last.length;i++){var r=RANK[last[i]];if(r<min)min=r;}
    for(var key in RANK){if(RANK[key]===min)return key;}
    return 'NORMAL';
  }
  return {breathing:breathing,pitch:pitch,voiceFeat:voiceFeat,stressScore:stressScore,classify:classify,sustained:sustained,RANK:RANK,C:C};
})();
"""

HTML = r"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@500;700;900&family=Share+Tech+Mono&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box}
html,body{margin:0;background:#04100a;color:#d4ffe2;font-family:'Share Tech Mono',monospace}
#w{padding:12px;background:radial-gradient(ellipse at 50% 0%,#0a2a1a 0%,#030a07 75%)}
.hud{background:rgba(2,18,10,.85);border:1px solid rgba(0,255,102,.38);box-shadow:0 0 14px rgba(0,255,102,.10) inset;padding:10px 12px}
h3{margin:0 0 8px;font-family:Orbitron,sans-serif;font-size:.8rem;letter-spacing:.16em;color:#eafff1;text-shadow:0 0 8px #00ff66}
.row{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.btn{font-family:Orbitron,sans-serif;font-size:.64rem;letter-spacing:.1em;color:#9dffc4;background:rgba(2,18,10,.9);border:1px solid rgba(0,255,102,.45);padding:8px 11px;cursor:pointer;user-select:none}
.btn:hover{background:rgba(0,255,102,.16)}.btn.on{background:rgba(0,255,102,.3);color:#fff;box-shadow:0 0 10px rgba(0,255,102,.5)}
.btn.warn{border-color:#ff8a00;color:#ffc27a}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:10px}
@media(max-width:760px){.grid{grid-template-columns:1fr}}
#state{font-family:Orbitron,sans-serif;font-weight:900;font-size:1.2rem;letter-spacing:.12em;padding:10px;text-align:center;border:1px solid;margin-bottom:8px}
.k{display:flex;justify-content:space-between;font-size:.76rem;margin:4px 0}.k b{color:#eafff1}
.bar{height:7px;background:rgba(0,255,102,.12);margin-top:2px}.bar i{display:block;height:100%;background:#00ff66;width:0}
#pacer{width:150px;height:150px;margin:6px auto;border-radius:50%;border:2px solid #00ff66;display:flex;align-items:center;justify-content:center;
 font-family:Orbitron,sans-serif;font-size:.7rem;letter-spacing:.12em;color:#eafff1;box-shadow:0 0 18px rgba(0,255,102,.35);transform:scale(.6)}
#log{max-height:120px;overflow:auto;font-size:.7rem;color:#8fe8b0}
.note{color:#4bb87a;font-size:.68rem;line-height:1.35;margin-top:6px}
input[type=range]{accent-color:#00ff66;width:120px}
#msg{color:#ff9aa8;font-size:.76rem;min-height:1em;margin-top:6px}
/* pop-up: asks for the microphone when the mental-health category opens */
#ask{position:fixed;inset:0;background:rgba(1,8,4,.88);display:flex;align-items:flex-start;justify-content:center;padding-top:60px;z-index:10}
#ask .box{max-width:460px;background:#04140b;border:1px solid #00ff66;box-shadow:0 0 24px rgba(0,255,102,.35);padding:18px 20px;text-align:center}
#ask p{font-size:.82rem;line-height:1.45;color:#d4ffe2;margin:8px 0 14px}
#ask.hide{display:none}
</style></head><body>
<div id="ask"><div class="box">
 <h3>🎙 ICHOR WOULD LIKE TO HEAR YOU</h3>
 <p id="askTxt">Your browser is asking for the microphone: press <b>Allow</b>, then just talk.
 ICHOR listens to your voice and breathing, live, in this browser. Nothing is recorded or uploaded.</p>
 <div class="row" style="justify-content:center"><div class="btn on" id="askYes">START LISTENING</div><div class="btn" id="askNo">NOT NOW</div></div>
</div></div>
<div id="w">
<div class="hud">
 <h3>VOICE &amp; BREATHING MONITOR <span style="color:#4bb87a;font-weight:400;letter-spacing:.04em">· local only, nothing is recorded</span></h3>
 <div class="row">
  <div class="btn" id="bMic">🎙 START MICROPHONE</div>
  <div class="btn" id="bCal">CALIBRATE VOICE (20 s)</div>
  <div class="btn" id="bMus">🎵 RELAXING MUSIC</div>
  <div class="btn" id="bTest">🔊 TEST SOUND</div>
  <span style="font-size:.7rem">volume</span><input id="vol" type="range" min="0" max="100" value="70">
 </div>
 <div class="row" style="margin-top:6px"><span style="font-size:.68rem;color:#4bb87a">TEST (simulated):</span>
  <div class="btn warn" id="sS">STRESS</div><div class="btn warn" id="sH">HEAVY BREATHING</div><div class="btn warn" id="sP">PANIC</div></div>
 <div id="msg"></div>
</div>
<div class="grid">
 <div class="hud">
  <div id="state" style="color:#00ff66;border-color:#00ff66">NOT RUNNING</div>
  <div class="k"><span>Breathing rate</span><b id="rBr">–</b></div><div class="bar"><i id="bBr"></i></div>
  <div class="k"><span>Breath regularity (CV)</span><b id="rCv">–</b></div>
  <div class="k"><span>Voice pitch F0</span><b id="rF0">–</b></div>
  <div class="k"><span>Voice level</span><b id="rDb">–</b></div>
  <div class="k"><span>Voice stress score</span><b id="rSt">–</b></div><div class="bar"><i id="bSt"></i></div>
  <div class="k"><span>Calibration</span><b id="rCal">none</b></div>
  <h3 style="margin-top:10px">EVENT LOG</h3><div id="log">–</div>
 </div>
 <div class="hud" style="text-align:center">
  <h3>PACED BREATHING · 6 / MIN</h3>
  <div id="pacer">INHALE</div>
  <div id="mstat" style="font-size:.74rem;color:#8fe8b0">music off</div>
  <div class="note" style="text-align:left">Music: 60 bpm, C-major pentatonic, no lyrics, soft, 4 s inhale / 6 s exhale swell + silent pauses.
  Evidence: Bernardi 2006, Lehrer &amp; Gevirtz 2014, Thoma 2013, de Witte 2020 (small-to-moderate effect).<br>
  Heuristic screening aid, not a medical device. Thresholds: rest 12–20/min, heavy ≥ __HEAVY__, panic ≥ __PANIC__ (or heavy + voice stress). Voice stress needs calibration.</div>
 </div>
</div></div>
<script>
__CORE__
(function(){
"use strict";
function $(i){return document.getElementById(i);}
var C=VM.C, HZ=20, ctx=null, an=null, anB=null, stream=null, timer=null, envBuf=[], voicedBuf=[], vF0=[], vDb=[];
var base=null, calibrating=0, calF0=[], calDb=[], raw=[], state='NORMAL', sim=null, calmCount=0, autoMusic=false, manualMusic=false, musicBlocked=false, logN=0;
try{var sb=localStorage.getItem('ichor_voice_base');if(sb)base=JSON.parse(sb);}catch(e){}
function msg(t){$('msg').textContent=t||'';}
function logEv(t){var L=$('log');if(!logN)L.innerHTML='';logN++;var d=document.createElement('div');d.textContent=new Date().toLocaleTimeString()+'  '+t;L.insertBefore(d,L.firstChild);}
function showBase(){$('rCal').textContent=base?('F0 '+base.f0.toFixed(0)+' Hz · sd '+base.sd.toFixed(1)+' st'):'none (breathing rules only)';}
showBase();

/* ---------------- relaxing music (Web Audio) ---------------- */
var CALM_B64='__AUDIO__', calmBuf=null, calmLoading=null;
function loadCalm(c){
  if(calmBuf)return Promise.resolve(calmBuf);
  if(calmLoading)return calmLoading;
  if(!CALM_B64||CALM_B64.indexOf('__AUDIO')===0)return Promise.resolve(null);
  try{
    var bin=atob(CALM_B64),n=bin.length,u=new Uint8Array(n),i;for(i=0;i<n;i++)u[i]=bin.charCodeAt(i);
    calmLoading=new Promise(function(res,rej){c.decodeAudioData(u.buffer,res,rej);})
      .then(function(b){calmBuf=b;return b;}).catch(function(){calmLoading=null;return null;});
    return calmLoading;
  }catch(e){return Promise.resolve(null);}
}
var Music=(function(){
  var master,bus,run=false,starting=false,nodes=[],timers=[],nextBreath=0,noteStep=3,noteCount=0,vol=0.7,gBreath,master;
  var SCALE=[196.0,220.0,261.63,293.66,329.63,392.0,440.0,523.25,587.33,659.25];
  function pink(c){var len=c.sampleRate*4,b=c.createBuffer(1,len,c.sampleRate),d=b.getChannelData(0),b0=0,b1=0,b2=0,b3=0,b4=0,b5=0,b6=0;
    for(var i=0;i<len;i++){var w=Math.random()*2-1;b0=0.99886*b0+w*0.0555179;b1=0.99332*b1+w*0.0750759;b2=0.969*b2+w*0.153852;b3=0.8665*b3+w*0.3104856;b4=0.55*b4+w*0.5329522;b5=-0.7616*b5-w*0.016898;d[i]=(b0+b1+b2+b3+b4+b5+b6+w*0.5362)*0.11;b6=w*0.115926;}return b;}
  function scheduleBreaths(){var t=Math.max(ctx.currentTime,nextBreath);for(var k=0;k<6;k++){var s=t+k*10;gBreath.gain.setTargetAtTime(1.0,s,1.3);gBreath.gain.setTargetAtTime(0.55,s+4,1.9);}nextBreath=t+60;}
  function note(){
    var t=ctx.currentTime+0.05;noteStep=Math.max(0,Math.min(SCALE.length-1,noteStep+[-2,-1,-1,0,1,1,2][Math.floor(Math.random()*7)]));
    var f=SCALE[noteStep];[[f,'triangle',0.5],[f*2,'sine',0.18]].forEach(function(p){
      var o=ctx.createOscillator(),g=ctx.createGain();o.type=p[1];o.frequency.value=p[0];
      g.gain.setValueAtTime(0,t);g.gain.linearRampToValueAtTime(0.30*p[2],t+1.2);g.gain.exponentialRampToValueAtTime(0.0008,t+5.5);
      o.connect(g);g.connect(bus);o.start(t);o.stop(t+5.8);});
  }
  var aud=null,fadeT=null,mode='';
  function hasFile(){return !!CALM_B64&&CALM_B64.indexOf('__AUDIO')!==0;}
  function makeAudio(){
    if(aud)return aud;
    var bin=atob(CALM_B64),n=bin.length,u=new Uint8Array(n),i;for(i=0;i<n;i++)u[i]=bin.charCodeAt(i);
    aud=new Audio(URL.createObjectURL(new Blob([u],{type:'audio/wav'})));aud.loop=true;aud.preload='auto';
    aud.addEventListener('error',function(){var m=aud&&aud.error?aud.error.message||('code '+aud.error.code):'unknown';$('mstat').textContent='audio file error';msg('Audio file error: '+m);});
    return aud;
  }
  function fade(to,ms,done){
    clearInterval(fadeT);var from=aud.volume,t0=Date.now();
    fadeT=setInterval(function(){var k=Math.min(1,(Date.now()-t0)/ms);aud.volume=Math.max(0,Math.min(1,from+(to-from)*k));if(k>=1){clearInterval(fadeT);if(done)done();}},50);
  }
  async function startFile(){
    var a=makeAudio();a.volume=0;
    await a.play();                       /* rejects with a clear message if the browser blocks it */
    mode='file';fade(Math.min(1,vol),2500);
  }
  async function start(c){
    if(run||starting)return;starting=true;
    if(hasFile()){
      try{
        await startFile();run=true;starting=false;
        $('mstat').textContent='♪ music playing (60 bpm)';$('bMus').classList.add('on');msg('');
        return;
      }catch(e){
        if(e&&e.name==='NotAllowedError'){starting=false;throw e;}   /* needs a click: handled by the caller */
        /* any other problem with the file: fall back to the generated music below */
      }
    }
    mode='synth';ctx=c;
    try{
      if(ctx.state!=='running')await ctx.resume();
      if(ctx.state!=='running')throw new Error('The browser kept audio playback suspended. Check site sound permissions and click RELAXING MUSIC again.');
    }catch(e){starting=false;throw e;}
    var buf=null;try{buf=await loadCalm(ctx);}catch(e){buf=null;}
    run=true;starting=false;
    ctx.onstatechange=function(){if(run&&ctx.state!=='running'){try{ctx.resume();}catch(e){}}};
    master=ctx.createGain();master.gain.value=0;master.connect(ctx.destination);
    if(buf){
      var src=ctx.createBufferSource();src.buffer=buf;src.loop=true;src.connect(master);src.start();nodes.push(src);
      master.gain.setTargetAtTime(vol,ctx.currentTime,2.0);
      timers.push(setInterval(function(){if(run&&ctx.state!=='running'){try{ctx.resume();}catch(e){}}},2000));
      $('mstat').textContent='♪ music playing (60 bpm)';$('bMus').classList.add('on');msg('');
      return;
    }
    var lp=ctx.createBiquadFilter();lp.type='lowpass';lp.frequency.value=1800;lp.connect(master);
    gBreath=ctx.createGain();gBreath.gain.value=0.55;gBreath.connect(lp);
    bus=ctx.createGain();bus.gain.value=1;bus.connect(gBreath);
    [[65.41,0.12],[65.6,0.07],[130.81,0.14],[196.0,0.12],[261.63,0.08],[392.0,0.04]].forEach(function(p){var o=ctx.createOscillator(),g=ctx.createGain();o.type='sine';o.frequency.value=p[0];g.gain.value=p[1];o.connect(g);g.connect(bus);o.start();nodes.push(o);});
    var ns=ctx.createBufferSource();ns.buffer=pink(ctx);ns.loop=true;var nl=ctx.createBiquadFilter();nl.type='lowpass';nl.frequency.value=420;var ng=ctx.createGain();ng.gain.value=0.35;
    ns.connect(nl);nl.connect(ng);ng.connect(gBreath);ns.start();nodes.push(ns);
    nextBreath=ctx.currentTime;scheduleBreaths();
    timers.push(setInterval(scheduleBreaths,50000));
    timers.push(setInterval(function(){if(run&&ctx.state!=='running'){try{ctx.resume();}catch(e){}}},2000));
    timers.push(setInterval(function(){noteCount++;if(noteCount%9===0)return;/* silent pause (Bernardi 2006) */ if(Math.random()<0.45)note();},1000)); /* 60 bpm grid */
    master.gain.setTargetAtTime(vol,ctx.currentTime,2.0);note();
    $('mstat').textContent='♪ music playing (60 bpm)';$('bMus').classList.add('on');msg('');
  }
  function stop(){
    if(!run)return;run=false;timers.forEach(clearInterval);timers=[];
    if(mode==='file'&&aud){fade(0,1500,function(){if(!run){aud.pause();}});$('mstat').textContent='music off';$('bMus').classList.remove('on');return;}
    try{master.gain.setTargetAtTime(0,ctx.currentTime,1.5);}catch(e){}
    var ns=nodes,oldMaster=master;nodes=[];setTimeout(function(){ns.forEach(function(o){try{o.stop();}catch(e){}});try{oldMaster.disconnect();}catch(e){}},7000);
    $('mstat').textContent='music off';$('bMus').classList.remove('on');
  }
  function setVol(v){vol=v;if(run&&mode==='file'&&aud){clearInterval(fadeT);aud.volume=Math.max(0,Math.min(1,v));}else if(run&&master)master.gain.setTargetAtTime(v,ctx.currentTime,0.3);}
  return {start:start,stop:stop,setVol:setVol,isOn:function(){return run;}};
})();
function ensureCtx(){if(!ctx){var AC=window.AudioContext||window.webkitAudioContext;ctx=new AC();}return ctx;}
var wantMusic=false;
function unlockAudio(){
  try{if(wantMusic&&!Music.isOn()){/* retry below */}}catch(e){}
  try{var c=ensureCtx();if(c.state!=='running'){c.resume();}
    var b=c.createBuffer(1,1,22050),s=c.createBufferSource();s.buffer=b;s.connect(c.destination);s.start(0);}catch(e){}
  if(wantMusic&&!Music.isOn()){musicBlocked=false;startMusic();}
}
['pointerdown','touchstart','keydown','click'].forEach(function(ev){document.addEventListener(ev,unlockAudio,true);});
function startMusic(){
  msg('');$('mstat').textContent='starting music…';wantMusic=true;
  try{
    Music.start(ensureCtx()).catch(function(e){
      autoMusic=false;musicBlocked=true;wantMusic=true;$('bMus').classList.remove('on');
      $('mstat').textContent='waiting for a click to start audio';
      msg('The browser blocked sound until you click. Click anywhere on this panel (or RELAXING MUSIC) and it will start. ['+(e&&e.name?e.name:'blocked')+']');
    });
  }catch(e){
    autoMusic=false;musicBlocked=true;wantMusic=true;$('bMus').classList.remove('on');
    $('mstat').textContent='waiting for a click to start audio';
    msg('Music could not start: '+(e&&e.message?e.message:e));
  }
}

/* ---------------- state display ---------------- */
var COL={NORMAL:'#00ff66',STRESS:'#ffd60a',HEAVY_BREATHING:'#ff8a00',PANIC:'#ff2d55'};
var TXT={NORMAL:'CALM · NORMAL',STRESS:'VOICE STRESS',HEAVY_BREATHING:'HEAVY BREATHING',PANIC:'PANIC-LIKE EPISODE'};
function setState(s,simulated){
  var prev=state;state=s;var el=$('state');el.textContent=TXT[s]+(simulated?' (SIM)':'');el.style.color=COL[s];el.style.borderColor=COL[s];
  if(s!==prev){logEv(TXT[s]+(simulated?' (simulated)':''));}
  if(s!=='NORMAL'){calmCount=0;if(!Music.isOn()&&!autoMusic&&!musicBlocked){autoMusic=true;startMusic();logEv('relaxing music started automatically');}}
  else if(Music.isOn()&&autoMusic&&!manualMusic){calmCount++;if(calmCount>=30){Music.stop();autoMusic=false;wantMusic=false;logEv('calm again for 60 s: music faded out');}}
}
function setBar(id,p){$(id).style.width=Math.max(0,Math.min(100,p))+'%';$(id).style.background=p>=70?'#ff2d55':p>=40?'#ff8a00':'#00ff66';}

/* ---------------- analysis loop ---------------- */
function frame(){
  var n=an.fftSize,a=new Float32Array(n),b=new Float32Array(n);an.getFloatTimeDomainData(a);anB.getFloatTimeDomainData(b);
  var sa=0,sb2=0,i;for(i=0;i<n;i++){sa+=a[i]*a[i];sb2+=b[i]*b[i];}
  var rmsA=Math.sqrt(sa/n),rmsB=Math.sqrt(sb2/n),voiced=false;
  if(rmsA>0.015){var p=VM.pitch(a,ctx.sampleRate);if(p){voiced=true;vF0.push(p.f0);vDb.push(20*Math.log(rmsA)/Math.LN10);if(vF0.length>200){vF0.shift();vDb.shift();}
      if(calibrating){calF0.push(p.f0);calDb.push(20*Math.log(rmsA)/Math.LN10);}}}
  envBuf.push(rmsB);voicedBuf.push(voiced?1:0);if(envBuf.length>HZ*30){envBuf.shift();voicedBuf.shift();}
}
function update(){
  if(calibrating){var left=Math.max(0,Math.round((calibrating-Date.now())/1000));$('rCal').textContent='calibrating… '+left+' s';
    if(Date.now()>=calibrating){calibrating=0;var f=VM.voiceFeat(calF0,calDb);if(f){base=f;try{localStorage.setItem('ichor_voice_base',JSON.stringify(f));}catch(e){}msg('Calibration saved.');logEv('voice baseline saved');}else{msg('Not enough voiced speech detected. Speak steadily and closer to the microphone, then try again.');}showBase();$('bCal').classList.remove('on');}}
  var rate=null,cv=null,stress=null,simmed=false,spk=0,k;
  for(k=0;k<voicedBuf.length;k++)spk+=voicedBuf[k];spk=voicedBuf.length?spk/voicedBuf.length:0;
  var br=(spk>0.3)?{rate:null,reason:'speaking'}:VM.breathing(envBuf,HZ);rate=br.rate;cv=br.cv==null?null:br.cv;
  var vf=VM.voiceFeat(vF0.slice(-100),vDb.slice(-100));stress=VM.stressScore(vf,base);
  if(sim&&Date.now()<sim.until){simmed=true;rate=sim.rate;stress=sim.stress;cv=0.2;}else{sim=null;}
  $('rBr').textContent=rate==null?(br.reason==='speaking'?'speaking – paused':br.reason==='no-signal'?'no breath signal':'measuring…'):rate.toFixed(0)+' /min';
  setBar('bBr',rate==null?0:rate/40*100);$('rCv').textContent=cv==null?'–':cv.toFixed(2)+(cv>C.IRREG?'  (irregular)':'');
  $('rF0').textContent=vf?vf.f0.toFixed(0)+' Hz':'–';$('rDb').textContent=vf?vf.db.toFixed(0)+' dBFS':'–';
  $('rSt').textContent=stress==null?(base?'–':'needs calibration'):stress+' / 100';setBar('bSt',stress==null?0:stress);
  raw.push(VM.classify(rate,cv,stress));if(raw.length>10)raw.shift();
  setState(VM.sustained(raw,3),simmed);
}
async function startMic(){
  msg('');
  try{
    var c=ensureCtx();if(c.state==='suspended')await c.resume();
    stream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:false,noiseSuppression:false,autoGainControl:false}});
    var src=c.createMediaStreamSource(stream);an=c.createAnalyser();an.fftSize=2048;src.connect(an);
    var hp=c.createBiquadFilter();hp.type='highpass';hp.frequency.value=300;var lp=c.createBiquadFilter();lp.type='lowpass';lp.frequency.value=2500;
    anB=c.createAnalyser();anB.fftSize=2048;src.connect(hp);hp.connect(lp);lp.connect(anB);
    timer=[setInterval(frame,1000/HZ),setInterval(update,2000)];$('bMic').textContent='⏹ STOP MICROPHONE';$('bMic').classList.add('on');
    setState('NORMAL');logEv('microphone started');
  }catch(e){
    msg('Microphone unavailable: '+(e&&e.message?e.message:e)+'. It needs permission and https:// or http://localhost. You can still test with the simulate buttons.');
  }
}
function stopMic(){
  if(timer){timer.forEach(clearInterval);timer=null;}
  if(stream){stream.getTracks().forEach(function(t){t.stop();});stream=null;}
  envBuf=[];voicedBuf=[];vF0=[];vDb=[];raw=[];$('bMic').textContent='🎙 START MICROPHONE';$('bMic').classList.remove('on');
  $('state').textContent='NOT RUNNING';logEv('microphone stopped');
}
$('bMic').addEventListener('click',function(){if(timer)stopMic();else startMic();});
/* the pop-up, when the mental-health category opens:
   1. the browser asks at once for the microphone (its own permission question)
   2. allowed: ICHOR starts listening by itself if the browser lets the audio start without a click,
      otherwise one tap on START LISTENING starts it */
$('askYes').addEventListener('click',function(){$('ask').classList.add('hide');if(!timer)startMic();});
$('askNo').addEventListener('click',function(){$('ask').classList.add('hide');msg('Microphone off. Press START MICROPHONE when you want to talk.');});
if(navigator.mediaDevices&&navigator.mediaDevices.getUserMedia){
  navigator.mediaDevices.getUserMedia({audio:true}).then(function(s){
    s.getTracks().forEach(function(t){t.stop();});                       // only the permission: startMic opens its own stream
    $('askTxt').textContent='Microphone allowed. Press START LISTENING and just talk.';
    var c=ensureCtx();
    Promise.race([c.resume(),new Promise(function(r){setTimeout(r,400);})]).then(function(){
      if(c.state==='running'&&!timer){$('ask').classList.add('hide');startMic();}
    });
  }).catch(function(e){
    $('ask').classList.add('hide');
    msg('Microphone not allowed ('+(e&&e.name?e.name:e)+'). Allow it from the lock icon next to the address bar, then press START MICROPHONE.');
  });
}else{
  $('ask').classList.add('hide');msg('This browser has no microphone access here (it needs https:// or http://localhost).');
}
$('bCal').addEventListener('click',function(){
  if(!timer){msg('Start the microphone first, then speak normally for 20 s while breathing calmly.');return;}
  calF0=[];calDb=[];calibrating=Date.now()+20000;$('bCal').classList.add('on');msg('Speak normally for 20 seconds (read a few sentences aloud).');
});
$('bMus').addEventListener('click',function(){
  if(Music.isOn()){manualMusic=false;autoMusic=false;wantMusic=false;Music.stop();}else{manualMusic=true;autoMusic=false;musicBlocked=false;startMusic();}
});
$('bTest').addEventListener('click',function(){
  var info=(CALM_B64&&CALM_B64.indexOf('__AUDIO')!==0)?('audio file embedded: '+Math.round(CALM_B64.length*0.75/1024)+' KB'):'audio file NOT found (using generated music)';
  try{var c=ensureCtx();c.resume();var o=c.createOscillator(),g=c.createGain();o.frequency.value=440;g.gain.value=0.15;o.connect(g);g.connect(c.destination);o.start();o.stop(c.currentTime+0.6);}catch(e){}
  msg('Test beep played (if you heard it, your speakers work). '+info+'. Now starting the music…');
  if(!Music.isOn()){manualMusic=true;autoMusic=false;musicBlocked=false;startMusic();}
});
$('vol').addEventListener('input',function(){Music.setVol($('vol').value/100*0.9);});
function simulate(kind,rate,stress){sim={kind:kind,rate:rate,stress:stress,until:Date.now()+20000};raw=[kind,kind,kind];update();}
$('sS').addEventListener('click',function(){simulate('STRESS',18,70);});
$('sH').addEventListener('click',function(){simulate('HEAVY_BREATHING',27,30);});
$('sP').addEventListener('click',function(){simulate('PANIC',34,75);});
/* paced-breathing circle: 4 s in, 6 s out */
setInterval(function(){var t=(Date.now()/1000)%10,p=$('pacer'),inh=t<4,s=inh?0.6+0.4*(t/4):1.0-0.4*((t-4)/6);p.style.transform='scale('+s.toFixed(3)+')';p.textContent=inh?'INHALE':'EXHALE';},100);
window.__voice={VM:VM,simulate:simulate,update:update,getState:function(){return state;}};
})();
</script></body></html>
"""


try:
    from ichor_calm_audio import CALM_WAV_B64
except ImportError:                      # file missing: the browser synth is used instead
    CALM_WAV_B64 = ""


def build_html() -> str:
    const = {"STRESS": STRESS_SCORE, "HEAVY": HEAVY_RATE, "PANIC": PANIC_RATE, "IRREG": IRREGULAR_CV}
    core = CORE_JS.replace("__CONST__", json.dumps(const))
    return (HTML.replace("__CORE__", core).replace("__HEAVY__", str(HEAVY_RATE)).replace("__PANIC__", str(PANIC_RATE)).replace("__AUDIO__", CALM_WAV_B64))


def render_voice_monitor(height: int = 640) -> None:
    import streamlit.components.v1 as components
    components.html(build_html(), height=height, scrolling=True)
