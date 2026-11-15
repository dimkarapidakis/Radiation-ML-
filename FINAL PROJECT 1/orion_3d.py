"""
orion_3d.py - interactive 3D model of NASA's Orion spacecraft (crew module + European Service Module)
with a radiation map, for the ICHOR dashboard.

What is accurate and what is schematic
--------------------------------------
ACCURATE (public NASA / ESA / Lockheed Martin figures, see each room's text):
  crew module 5.02 m x 3.3 m, 57.5 deg frustum, heat shield 5.02 m (186 Avcoat blocks), ~1,300 backshell tiles,
  European Service Module 4.1 m x 4 m, four solar wings x 3 panels (19 m span, ~11 kW), 1 main engine (26.6 kN),
  8 auxiliary engines (490 N), 24 RCS thrusters in 6 pods (220 N), 4 propellant tanks (2,000 L each),
  launch abort system (13.4 m), habitable volume ~9 m3, 4 crew, storm shelter built from the two lockers.
SCHEMATIC: the exact position/shape of the interior equipment (NASA does not publish a full interior CAD),
  the window positions, and the per-room radiation shielding factors (TEAM ASSUMPTION, not NASA data).

ADDED in this version
---------------------
  * PICTURES button: gallery of the ML figures (skill by hour, predicted vs observed) and the ISS DosTel figures.
  * ML FORECAST row: loads the newest forecast (live_log.csv / forecast_output.csv, from 05_predict.py / 06_live.py)
    and can drive the room colors. The forecast -> mSv conversion is a TEAM ASSUMPTION (see PEAK_TO_MSV in the JS).
  * WARNING banner: follows the room colors and the forecast; tells the crew when the storm shelter is advised.

Needs internet in the browser (three.js r128 from cdnjs). Everything else is inside this file.
"""
from __future__ import annotations

import json
import os


def _load_pics() -> dict:
    """Pictures for the PICTURES button: put them in a folder called orion_pics next to this file."""
    import base64
    folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "orion_pics")
    out = {}
    for key in ["skill_by_hour", "pred_vs_obs", "iss_event", "iss_daily", "iss_map", "iss_regions"]:
        for ext, mime in (("png", "image/png"), ("jpg", "image/jpeg")):
            path = os.path.join(folder, key + "." + ext)
            if os.path.exists(path):
                with open(path, "rb") as f:
                    out[key] = "data:" + mime + ";base64," + base64.b64encode(f.read()).decode()
    return out


PICS = _load_pics()

THREE_URL = "https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"

HTML = r"""<!doctype html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@500;700;900&family=Share+Tech+Mono&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box}
html,body{margin:0;height:100%;background:#04100a;color:#d4ffe2;font-family:'Share Tech Mono',monospace;overflow:hidden}
#wrap{position:relative;width:100%;height:100vh;min-height:560px;background:radial-gradient(ellipse at 50% 40%,#0a2a1a 0%,#030a07 70%)}
#wrap:after{content:"";position:absolute;inset:0;pointer-events:none;background:repeating-linear-gradient(0deg,rgba(0,255,102,.03) 0 1px,transparent 1px 3px)}
#view{position:absolute;inset:0}
#view canvas{display:block;width:100%;height:100%;touch-action:none;cursor:grab}
.hud{background:rgba(2,18,10,.80);border:1px solid rgba(0,255,102,.38);box-shadow:0 0 14px rgba(0,255,102,.10) inset,0 0 10px rgba(0,255,102,.08);backdrop-filter:blur(3px)}
#top{position:absolute;left:10px;right:10px;top:10px;display:flex;gap:6px;flex-wrap:wrap;align-items:center;z-index:5}
.ttl{font-family:Orbitron,sans-serif;font-weight:900;letter-spacing:.18em;color:#eafff1;text-shadow:0 0 10px #00ff66;padding:7px 12px;font-size:.82rem}
.btn{font-family:Orbitron,sans-serif;font-size:.68rem;letter-spacing:.12em;color:#9dffc4;background:rgba(2,18,10,.85);border:1px solid rgba(0,255,102,.45);padding:8px 12px;cursor:pointer;user-select:none}
.btn:hover{background:rgba(0,255,102,.16)}
.btn.on{background:rgba(0,255,102,.30);color:#fff;box-shadow:0 0 12px rgba(0,255,102,.55)}
.sep{width:1px;height:24px;background:rgba(0,255,102,.3);margin:0 4px}
#rooms{position:absolute;left:10px;top:58px;bottom:112px;width:218px;overflow:auto;padding:8px;z-index:4}
#rooms h4{margin:10px 0 4px;font-family:Orbitron,sans-serif;font-size:.62rem;letter-spacing:.18em;color:#3fd68a}
#rooms h4:first-child{margin-top:0}
.zbtn{display:flex;align-items:center;gap:7px;width:100%;text-align:left;font-family:'Share Tech Mono',monospace;font-size:.74rem;color:#cffbe0;background:transparent;border:1px solid transparent;padding:4px 5px;cursor:pointer}
.zbtn:hover{background:rgba(0,255,102,.10);border-color:rgba(0,255,102,.3)}
.zbtn.sel{background:rgba(0,255,102,.20);border-color:#00ff66}
.dot{width:10px;height:10px;border-radius:50%;flex:none;box-shadow:0 0 8px currentColor}
#panel{position:absolute;right:10px;top:58px;width:310px;max-height:calc(100% - 190px);overflow:auto;padding:10px 12px;z-index:4;font-size:.8rem;line-height:1.35}
.ptitle{font-family:Orbitron,sans-serif;font-weight:700;font-size:1rem;color:#eafff1;text-shadow:0 0 8px #00ff66;letter-spacing:.06em}
.pgr{color:#3fd68a;font-size:.72rem;margin:2px 0 8px}
.rad{border:1px solid;padding:6px 8px;font-family:Orbitron,sans-serif;font-size:.66rem;letter-spacing:.08em;margin-bottom:6px}
.small{color:#6fe89a;font-size:.7rem;margin-bottom:6px}
#panel ul{margin:6px 0 0;padding-left:16px}
#panel li{margin:3px 0}
#storm{position:absolute;left:10px;bottom:10px;width:min(560px,calc(100% - 20px));padding:8px 10px;z-index:4;font-size:.72rem}
#storm .row{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
#storm input[type=range]{flex:1;min-width:120px;accent-color:#00ff66}
#legend{position:absolute;right:10px;bottom:10px;padding:8px 10px;z-index:4;font-size:.68rem;display:flex;gap:10px;flex-wrap:wrap;max-width:420px}
#legend span{display:flex;align-items:center;gap:5px}
#labels{position:absolute;inset:0;pointer-events:none;z-index:3;overflow:hidden}
.lbl{position:absolute;transform:translate(-50%,-130%);font-size:.62rem;padding:1px 5px;white-space:nowrap;background:rgba(2,18,10,.78);border:1px solid;cursor:pointer;pointer-events:auto;letter-spacing:.04em}
#msg{display:none;position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);z-index:9;padding:16px 20px;max-width:80%;border-color:#ff2d55;color:#ffd0d8;font-size:.9rem}

#pics{display:none;position:absolute;inset:58px 10px 10px 10px;z-index:8;padding:10px 12px;flex-direction:column;gap:8px}
#pics.open{display:flex}
#pics .hd{display:flex;gap:6px;align-items:center;flex-wrap:wrap}
#pics .hd b{font-family:Orbitron,sans-serif;letter-spacing:.14em;color:#eafff1;text-shadow:0 0 8px #00ff66;font-size:.8rem;margin-right:8px}
#pics .grow{flex:1}
#pbody{flex:1;min-height:0;display:flex;gap:10px}
#pthumbs{width:190px;overflow:auto;display:flex;flex-direction:column;gap:6px;flex:none}
.th{border:1px solid rgba(0,255,102,.3);background:rgba(2,18,10,.7);padding:4px;cursor:pointer;font-size:.62rem;color:#9dffc4}
.th img{display:block;width:100%;height:auto;background:#fff}
.th:hover{border-color:#00ff66}.th.sel{border-color:#00ff66;box-shadow:0 0 10px rgba(0,255,102,.5)}
#pview{flex:1;min-width:0;display:flex;flex-direction:column;gap:6px}
#pimg{flex:1;min-height:0;display:flex;align-items:center;justify-content:center;background:rgba(255,255,255,.96);border:1px solid rgba(0,255,102,.5);overflow:auto}
#pimg img{max-width:100%;max-height:100%;object-fit:contain}
#pcap{font-size:.76rem;line-height:1.4;max-height:30%;overflow:auto}
#pcap b{font-family:Orbitron,sans-serif;color:#eafff1;letter-spacing:.06em}
#fcrow{margin-top:5px;padding-top:5px;border-top:1px dashed rgba(0,255,102,.3)}
#fct{color:#6fe89a}
#warn{display:none;position:absolute;left:50%;top:58px;transform:translateX(-50%);z-index:6;padding:8px 14px;max-width:min(520px,calc(100% - 600px));min-width:260px;font-size:.74rem;line-height:1.35;text-align:center;border-width:1px;border-style:solid}
#warn.show{display:block}
#warn b{font-family:Orbitron,sans-serif;letter-spacing:.12em}
@media(max-width:1100px){#warn{left:10px;transform:none;top:auto;bottom:140px;max-width:calc(100% - 20px)}}
@media(max-width:820px){#pbody{flex-direction:column}#pthumbs{width:100%;flex-direction:row}.th{min-width:110px}}
@media(max-width:820px){#rooms{width:150px}#panel{width:230px}}
</style></head>
<body>
<div id="wrap">
  <div id="view"></div>
  <div id="labels"></div>
  <div id="top">
    <div class="hud ttl">ORION · MPCV</div>
    <div class="btn" id="bOut">OUTSIDE</div>
    <div class="btn" id="bIn">INSIDE</div>
    <div class="sep"></div>
    <div class="btn" id="bLas">LAUNCH ABORT SYSTEM</div>
    <div class="btn on" id="bLbl">LABELS</div>
    <div class="btn" id="bAuto">AUTO-ROTATE</div>
    <div class="btn on" id="bVoice">🔊 VOICE</div>
    <div class="btn" id="bPics">📷 PICTURES</div>
    <div class="sep"></div>
    <div class="btn" id="bZi">＋</div>
    <div class="btn" id="bZo">－</div>
    <div class="btn" id="bHome">⟲ RESET</div>
  </div>
  <div id="rooms" class="hud"></div>
  <div id="panel" class="hud"></div>
  <div id="storm" class="hud">
    <div class="row"><b style="font-family:Orbitron;letter-spacing:.1em;color:#eafff1">SOLAR EVENT DOSE</b>
      <input id="ev" type="range" min="0" max="400" step="1" value="0">
      <b id="evv" style="min-width:64px;text-align:right">0 mSv</b></div>
    <div class="row" style="margin-top:5px">
      <div class="btn" id="bApp">APP VALUE</div><div class="btn" id="bStorm">☀ SIMULATE SOLAR STORM</div>
      <span id="src" style="color:#6fe89a"></span></div>
    <div class="row" id="fcrow"><b style="font-family:Orbitron;letter-spacing:.1em;color:#eafff1">🤖 ML FORECAST</b><span id="fct"></span></div>
    <div style="color:#3b9a60;margin-top:4px">Shielding factor per room = TEAM ASSUMPTION (not NASA data). Colors = % of the 250 mSv per-event limit (NASA-STD-3001).</div>
  </div>
  <div id="legend" class="hud"></div>
  <div id="warn" class="hud"></div>
  <div id="pics" class="hud">
    <div class="hd"><b>PICTURES</b><div id="ptabs" style="display:flex;gap:6px;flex-wrap:wrap"></div><span class="grow"></span>
      <div class="btn" id="pPrev">◀</div><div class="btn" id="pNext">▶</div><div class="btn" id="pClose">✕ CLOSE</div></div>
    <div id="pbody"><div id="pthumbs"></div><div id="pview"><div id="pimg"></div><div id="pcap"></div></div></div>
  </div>
  <div id="msg" class="hud"></div>
</div>
<script src="__THREE_URL__"></script>
<script>
(function(){
"use strict";
var CFG = __CONFIG__;
var PICS = __PICS__;
function $(id){ return document.getElementById(id); }
function fail(msg){ var m=$('msg'); if(m){ m.style.display='block'; m.textContent=msg; } }
if (typeof THREE === 'undefined'){ fail('The three.js library did not load. Check your internet connection and reload the page.'); return; }
try { start(); } catch(e){ fail('3D model error: ' + (e && e.message ? e.message : e)); if (window.console) console.error(e); }

function start(){
  var LIMIT = CFG.limit || 250;
  var APP_EVENT = Math.max(0, +CFG.eventMsv || 0);
  var eventMsv = APP_EVENT;

  /* ------------------------------------------------------------ helpers */
  function clamp(x,a,b){ return Math.max(a, Math.min(b, x)); }
  function lerp(a,b,t){ return a + (b-a)*t; }
  function angDiff(a,b){ var d=(b-a+Math.PI)%(2*Math.PI); if(d<0) d+=2*Math.PI; return d-Math.PI; }
  var LEVELS = [
    {id:'safe', name:'SAFE',   gr:'', css:'#00ff66', hex:0x00ff66, max:0.15, rng:'< 15%'},
    {id:'low',  name:'LOW',    gr:'',  css:'#ffd60a', hex:0xffd60a, max:0.40, rng:'15–40%'},
    {id:'med',  name:'MEDIUM', gr:'',  css:'#ff8a00', hex:0xff8a00, max:0.70, rng:'40–70%'},
    {id:'high', name:'HIGH',   gr:'',   css:'#ff2d55', hex:0xff2d55, max:1e9,  rng:'≥ 70%'}
  ];
  function levelFor(f){ for (var i=0;i<LEVELS.length;i++){ if (f < LEVELS[i].max) return LEVELS[i]; } return LEVELS[LEVELS.length-1]; }

  /* ------------------------------------------------------------ zones (rooms / parts)
     mult = share of the open-space dose that reaches the zone  -> TEAM ASSUMPTION */
  var ZONES = [
   {id:'arrays', type:'ext', group:'Exterior', name:'Solar Array Wings', gr:'', mult:1.00, pos:[4.2,1.2,4.2], dist:17,
    info:['4 wings, 3 panels each (Airbus / ESA), mounted on the service module.','Each wing ≈ 7.4 m long; deployed span ≈ 19 m tip to tip (≈ 5.2 m wide when stowed).','≈ 11 kW of electrical power.','Fully exposed to space radiation: no shielding at all.']},
   {id:'esm', type:'ext', group:'Exterior', name:'European Service Module (ESM)', short:'Service Module', gr:'', mult:0.85, pos:[0,2.4,0], dist:13,
    info:['Built by Airbus for ESA, derived from the ATV cargo ship.','4.1 m diameter, ≈ 4 m long (≈ 5.2 m with stowed arrays).','Provides power, propulsion, attitude control, water, oxygen and thermal control.','Crew module + ESM ≈ 26.5 t at launch.']},
   {id:'engine', type:'ext', group:'Exterior', name:'Main Engine (OMS-E)', short:'Main Engine', gr:'', mult:1.00, pos:[0,-0.35,0], dist:5.5, cam:[0.6,1.75],
    info:['1 main engine derived from the Aerojet AJ10: 26.6 kN (6,000 lbf).','Used for the big maneuvers: trajectory changes and orbit insertion burns.']},
   {id:'aux', type:'ext', group:'Exterior', name:'Auxiliary Thrusters (8)', short:'Aux Thrusters', gr:'', mult:1.00, pos:[1.2,0.05,0.5], dist:6, cam:[0.5,1.7],
    info:['8 Aerojet R-4D engines, 490 N each (3.92 kN total).','Back-up and trim burns around the main engine.']},
   {id:'rcs', type:'ext', group:'Exterior', name:'RCS Thruster Pods (6 × 4)', short:'RCS Pods', gr:'', mult:1.00, pos:[2.15,3.4,0], dist:6,
    info:['24 Airbus reaction-control thrusters in 6 pods of 4, 220 N each (5.28 kN total).','Attitude control and small translation burns.','The crew module has its own 12 RCS thrusters for re-entry.']},
   {id:'cma', type:'ext', group:'Exterior', name:'Crew Module Adapter', short:'CM Adapter', gr:'', mult:0.80, pos:[2.25,4.35,0], dist:7,
    info:['Structural ring that joins the crew module to the service module (built by Lockheed Martin).','A second adapter joins the ESM to the SLS upper stage.','Separated before re-entry together with the service module.']},
   {id:'heat', type:'ext', group:'Exterior', name:'Heat Shield (Avcoat)', short:'Heat Shield', gr:'', mult:0.70, pos:[0,4.6,0], dist:9, cam:[0.5,2.0],
    info:['5.02 m (16.5 ft): the largest ablative heat shield ever built.','186 Avcoat blocks bonded to a titanium skeleton and composite skin.','Withstands ≈ 5,000 °F (≈ 2,760 °C) at ≈ 25,000 mph during return.']},
   {id:'back', type:'ext', group:'Exterior', name:'Backshell · Thermal Tiles', short:'Backshell', gr:'', mult:0.90, pos:[-1.57,6.4,-0.98], dist:7,
    info:['≈ 1,300 thermal-protection tiles, ≈ 8 × 8 in each.','Aluminium-lithium pressure vessel in a 57.5° frustum shape.','Seven large welded elements (friction-stir welded), 5.02 m wide × 3.3 m tall.']},
   {id:'las', type:'ext', group:'Exterior', name:'Launch Abort System (launch only)', short:'Launch Abort System', gr:'', mult:1.00, pos:[0,15,0], dist:22, launchOnly:true,
    info:['≈ 13.4 m tall tower on top of the capsule: it is NOT present in orbit.','3 solid motors: abort (≈ 2,200 kN), attitude control and jettison.','A fiberglass Boost Protective Cover shields the capsule during the first ≈ 2.5 minutes of ascent.']},

   {id:'fwdbay', type:'both', group:'Crew Module', name:'Forward Bay & Docking Hatch', short:'Forward Bay', gr:'', mult:0.70, pos:[0,7.7,0], dist:5,
    info:['Top of the capsule: the forward bay cover protects the parachutes and is jettisoned at ≈ 23,000 ft.','11 parachutes (36,000 ft² of canopy): 3 mains, each 116 ft wide.','Docking hatch with an IDSS port lets the crew transfer to another spacecraft (e.g. Gateway).']},
   {id:'hatch', type:'both', group:'Crew Module', name:'Side Hatch', short:'Side Hatch', gr:'', mult:0.65, pos:[1.9,6.3,0], dist:4.2,
    info:['Primary entry and exit for the crew, with its own window.','Closing it before launch takes ≈ 1 hour.','The exercise device sits right below it and doubles as a step.']},
   {id:'windows', type:'both', group:'Crew Module', name:'Crew Windows', short:'Windows', gr:'', mult:0.75, pos:[0.82,6.7,1.42], dist:3.6,
    info:['Windows sit in the angled mid-section of the pressure vessel (NASA engineer: four windows).','The side hatch and the launch-abort hatch also have windows.','Glass gives less shielding than the walls.']},
   {id:'cockpit', type:'int', group:'Crew Module', name:'Glass Cockpit', short:'Cockpit', gr:'', mult:0.55, pos:[-0.6,6.7,-1.3], dist:2.8,
    vol:[[-0.6,6.75,-1.3, 1.9,0.8,0.5]],
    info:['Commander and pilot flight controls: 3 large display units and 7 switch panels.','Rotational and translational hand controllers for manual flying.','Glass-cockpit design derived from modern airliner avionics.']},
   {id:'seats', type:'int', group:'Crew Module', name:'Crew Seats (4)', short:'Crew Seats', gr:'', mult:0.55, pos:[-0.6,6.05,-0.3], dist:3.4,
    vol:[[-0.6,6.05,-0.3, 1.6,0.8,2.1]],
    info:['4 adjustable seats sized for roughly the 1st–99th percentile, 5-point harness and impact attenuation.','In orbit the crew removes the lower half of the seats and the suits and stows them under cargo nets to free the cabin.','Cabin ≈ 9 m³ habitable (sources quote 316–380 ft³), about 50% more than Apollo.']},
   {id:'galley', type:'int', group:'Crew Module', name:'Galley', short:'Galley', gr:'', mult:0.50, pos:[1.35,6.4,0.95], dist:2.6,
    vol:[[1.35,6.4,0.95, 0.55,0.65,0.75]],
    info:['Potable-water dispenser and a briefcase-style food warmer.','On the left side, nearest the hatch.','Water comes from the service-module tanks (240 kg of water).']},
   {id:'exercise', type:'int', group:'Crew Module', name:'Exercise Area (Flywheel)', short:'Exercise', gr:'', mult:0.50, pos:[1.4,6.1,-0.1], dist:2.8,
    vol:[[1.4,6.1,-0.1, 0.65,0.55,0.95]],
    info:['Compact flywheel exerciser, similar to a rowing machine, also used as the step under the side hatch.','Missions longer than 8 days: at least 30 min of exercise per day.','Helps protect bone density and muscle in microgravity.']},
   {id:'hygiene', type:'int', group:'Crew Module', name:'Hygiene Bay (Toilet)', short:'Hygiene Bay', gr:'', mult:0.35, pos:[0.08,6.25,1.3], dist:2.6,
    vol:[[0.08,6.25,1.3, 0.68,0.8,0.68]],
    info:['Universal Waste Management System toilet in a ≈ 0.46 m² phone-booth-sized compartment, built into the floor.','Continuous airflow; can give some privacy for medical or family calls.','Its waste canisters are also used as shielding in the storm shelter.']},
   {id:'shelter', type:'int', group:'Crew Module', name:'Storm Shelter (Radiation Safe Haven)', short:'Storm Shelter', gr:'', mult:0.12, pos:[0.55,6.3,0], dist:3.0,
    vol:[[0.55,6.3,0, 0.8,1.1,2.1]],
    info:['Built from the two large stowage lockers at the centre of the cabin (≈ 2 × 3 × 3 ft each).','The crew empties them and lines the walls with the densest items: bags of water and the toilet waste canisters.','Two people per locker; it protects for up to ≈ 24 hours. The 1972 solar storm is the design-to case.','Used when a solar particle event is detected: this is the SAFE zone.']},
   {id:'sleep', type:'int', group:'Crew Module', name:'Sleeping Area', short:'Sleeping Area', gr:'', mult:0.50, pos:[0,7.0,0], dist:3.4,
    vol:[[0,7.0,0, 2.0,0.5,1.7]],
    info:['No private cabins: the 4 crew sleep in sleeping bags strung across the cabin, attached to walls or ceiling.','Similar to Space Shuttle practice.']},
   {id:'leb', type:'int', group:'Crew Module', name:'Lower Equipment Bay', short:'Equipment Bay', gr:'', mult:0.35, pos:[0,5.55,0], dist:4,
    vol:[[0,5.55,0, 3.2,0.65,3.2]],
    info:['The lower half of the capsule, under the floor: avionics, life-support equipment and propellant tanks.','Sits behind the heat shield and the equipment itself, so it is better shielded.','Houses the plumbing for the 12 crew-module RCS thrusters.']},
   {id:'tanks', type:'int', group:'Service Module', name:'Propellant Tanks (4 × 2,000 L)', short:'Propellant Tanks', gr:'', mult:0.45, pos:[0,2.2,0], dist:6,
    vol:[[0,2.2,0, 2.6,1.9,2.6]],
    info:['4 tanks of 2,000 L: two MON oxidiser and two MMH fuel.','≈ 9,000 kg of propellant, ≈ 8,600 kg usable.','Feed the main engine, the 8 auxiliary engines and the 24 RCS thrusters.']},
   {id:'fluids', type:'int', group:'Service Module', name:'Water · Oxygen · Nitrogen Tanks', short:'Life-support Tanks', gr:'', mult:0.45, pos:[0,2.1,0], dist:6.5,
    vol:[[0,0.85,0, 2.7,0.7,2.7],[0,3.35,0, 2.7,0.7,2.7]],
    info:['240 kg of water in 4 tanks (drinking water; also used for thermal control).','90 kg of oxygen in 3 tanks and 30 kg of nitrogen in 1 tank to keep the cabin air breathable.','Water is also very good radiation shielding.']}
  ];
  var zoneById = {};
  ZONES.forEach(function(z){ zoneById[z.id]=z; z.meshes=[]; z.hit=[]; z.vmeshes=[]; z.level=LEVELS[0]; z.dose=0; z.frac=0; });

  /* ------------------------------------------------------------ renderer / scene */
  var view = $('view');
  var renderer = new THREE.WebGLRenderer({antialias:true});
  renderer.setPixelRatio(Math.min(window.devicePixelRatio||1, 2));
  view.appendChild(renderer.domElement);
  var scene = new THREE.Scene();
  scene.background = new THREE.Color(0x02060a);
  var camera = new THREE.PerspectiveCamera(42, 1, 0.05, 900);
  scene.add(new THREE.AmbientLight(0x89a898, 0.6));
  var sunDir = new THREE.Vector3(-0.55,0.38,0.74).normalize();
  var sunLight = new THREE.DirectionalLight(0xfff3dd, 1.35);
  sunLight.position.copy(sunDir).multiplyScalar(60);
  scene.add(sunLight);
  var fillLight = new THREE.DirectionalLight(0x4aa3ff, 0.35);
  fillLight.position.set(8,-6,-10);
  scene.add(fillLight);

  var exterior = new THREE.Group();
  var interior = new THREE.Group();
  var space = new THREE.Group();
  var lasGroup = new THREE.Group();
  scene.add(exterior); scene.add(interior); scene.add(space);
  exterior.add(lasGroup);
  lasGroup.visible = false;
  var inLight = new THREE.PointLight(0xbfffe0, 1.15, 9);
  inLight.position.set(0,6.8,0);
  interior.add(inLight);
  interior.visible = false;

  /* ------------------------------------------------------------ textures */
  function tex(w,h,draw,rx,ry){
    var c=document.createElement('canvas'); c.width=w; c.height=h;
    draw(c.getContext('2d'),w,h);
    var t=new THREE.CanvasTexture(c);
    t.wrapS=THREE.RepeatWrapping; t.wrapT=THREE.RepeatWrapping;
    if(rx){ t.repeat.set(rx,ry||rx); }
    t.anisotropy=4;
    return t;
  }
  var tileTex = tex(1024,512,function(g,w,h){
    g.fillStyle='#1c2024'; g.fillRect(0,0,w,h);
    var cols=96, rows=24, cw=w/cols, ch=h/rows;
    for(var j=0;j<rows;j++){ for(var i=0;i<cols;i++){
      var s=120+Math.floor(Math.random()*34);
      g.fillStyle='rgb('+s+','+(s+4)+','+(s+8)+')';
      g.fillRect(i*cw+1.2,j*ch+1.2,cw-2.4,ch-2.4);
    } }
  });
  var heatTex = tex(1024,512,function(g,w,h){
    g.fillStyle='#a56a38'; g.fillRect(0,0,w,h);
    var cols=48, rows=12, cw=w/cols, ch=h/rows;
    for(var j=0;j<rows;j++){ for(var i=0;i<cols;i++){
      var k=Math.floor(Math.random()*40);
      g.fillStyle='rgb('+(150+k)+','+(95+k/2)+','+(52+k/3)+')';
      g.fillRect(i*cw+1.5,j*ch+1.5,cw-3,ch-3);
    } }
  });
  var esmTex = tex(1024,256,function(g,w,h){
    g.fillStyle='#e6eaec'; g.fillRect(0,0,w,h);
    g.strokeStyle='rgba(60,70,80,.55)'; g.lineWidth=2;
    for(var i=0;i<=16;i++){ g.beginPath(); g.moveTo(i*w/16,0); g.lineTo(i*w/16,h); g.stroke(); }
    for(var j=1;j<4;j++){ g.beginPath(); g.moveTo(0,j*h/4); g.lineTo(w,j*h/4); g.stroke(); }
    g.fillStyle='rgba(90,100,110,.35)';
    for(var k=0;k<16;k+=2){ g.fillRect(k*w/16+6,h*0.25+6,w/16-12,h*0.25-12); }
  });
  var solarTex = tex(256,256,function(g,w,h){
    g.fillStyle='#0c2a6a'; g.fillRect(0,0,w,h);
    g.strokeStyle='#c9a64b'; g.lineWidth=1.5;
    for(var i=0;i<=8;i++){ g.beginPath(); g.moveTo(i*w/8,0); g.lineTo(i*w/8,h); g.stroke(); }
    for(var j=0;j<=16;j++){ g.beginPath(); g.moveTo(0,j*h/16); g.lineTo(w,j*h/16); g.stroke(); }
    var gr=g.createLinearGradient(0,0,w,h); gr.addColorStop(0,'rgba(255,255,255,.10)'); gr.addColorStop(1,'rgba(0,0,0,.18)');
    g.fillStyle=gr; g.fillRect(0,0,w,h);
  });

  /* ------------------------------------------------------------ builders */
  function mat(color, o){
    var p = {color:color, metalness:0.35, roughness:0.55, side:THREE.DoubleSide};
    if(o){ for(var k in o){ p[k]=o[k]; } }
    return new THREE.MeshStandardMaterial(p);
  }
  function reg(zid, mesh, parent, o){
    (parent||exterior).add(mesh);
    var z = zoneById[zid];
    mesh.userData.zone = zid;
    if(o){ for(var k in o){ mesh.userData[k]=o[k]; } }
    if(mesh.material && mesh.material.color && !(o && o.notint)){ mesh.userData.base = mesh.material.color.clone(); z.meshes.push(mesh); }
    z.hit.push(mesh);
    return mesh;
  }
  function lathe(points, seg){
    return new THREE.LatheGeometry(points.map(function(p){ return new THREE.Vector2(p[0],p[1]); }), seg||72);
  }
  function box(w,h,d){ return new THREE.BoxGeometry(w,h,d); }
  function cyl(rt,rb,h,s){ return new THREE.CylinderGeometry(rt,rb,h,s||32); }
  function place(m,x,y,z){ m.position.set(x,y,z); return m; }

  var ALPHA = Math.atan(0.668);                    // wall angle of the 57.5° frustum (from the axis ≈ 33.7°)
  var COSA = Math.cos(ALPHA), SINA = Math.sin(ALPHA);
  function wallR(y){ return 2.47 - (y-0.76)*0.668; }          // crew-module outer radius at local height y
  function wallPt(theta, y){ var r=wallR(y); return new THREE.Vector3(r*Math.cos(theta), y, r*Math.sin(theta)); }
  function wallN(theta){ return new THREE.Vector3(COSA*Math.cos(theta), SINA, COSA*Math.sin(theta)); }

  /* ---------- Service module (y 0 .. 4) ---------- */
  var esmBody = new THREE.Mesh(cyl(2.05,2.05,4.0,72,1,true), mat(0xffffff,{map:esmTex,metalness:0.2,roughness:0.6}));
  esmBody.geometry = new THREE.CylinderGeometry(2.05,2.05,4.0,72,1,true);
  reg('esm', place(esmBody,0,2.0,0));
  reg('esm', place(new THREE.Mesh(new THREE.CircleGeometry(2.05,48), mat(0x9aa4aa,{metalness:0.6})),0,0.0,0), null, {}).rotation.x = Math.PI/2;
  reg('esm', place(new THREE.Mesh(new THREE.TorusGeometry(2.05,0.045,10,72), mat(0x8e979c,{metalness:0.7})),0,0.02,0), null, {}).rotation.x = Math.PI/2;
  reg('esm', place(new THREE.Mesh(new THREE.TorusGeometry(2.05,0.045,10,72), mat(0x8e979c,{metalness:0.7})),0,3.98,0), null, {}).rotation.x = Math.PI/2;
  // main engine bell
  var bell = lathe([[0.10,0.25],[0.16,-0.05],[0.27,-0.45],[0.38,-0.85],[0.44,-1.10],[0.42,-1.10],[0.35,-0.85],[0.24,-0.45],[0.12,-0.05],[0.08,0.25]], 40);
  reg('engine', place(new THREE.Mesh(bell, mat(0x6a6f73,{metalness:0.8,roughness:0.35})),0,0,0));
  reg('engine', place(new THREE.Mesh(cyl(0.22,0.22,0.35,24), mat(0x44484c,{metalness:0.6})),0,0.18,0));
  // 8 auxiliary engines
  for(var a=0;a<8;a++){
    var ang=(a+0.5)*Math.PI/4, ax=1.35*Math.cos(ang), az=1.35*Math.sin(ang);
    reg('aux', place(new THREE.Mesh(cyl(0.08,0.02,0.34,16), mat(0x777c80,{metalness:0.8,roughness:0.35})),ax,-0.12,az));
    reg('aux', place(new THREE.Mesh(new THREE.ConeGeometry(0.075,0.22,16,1,true), mat(0x9a6a3a,{metalness:0.8})),ax,-0.40,az)).rotation.x = Math.PI;
  }
  // 6 RCS pods x 4 thrusters
  for(var p=0;p<6;p++){
    var pa=p*Math.PI/3, g=new THREE.Group();
    g.position.set(2.08*Math.cos(pa),3.4,2.08*Math.sin(pa));
    g.rotation.y=-pa;
    exterior.add(g);
    reg('rcs', place(new THREE.Mesh(box(0.22,0.46,0.46), mat(0x8d969b,{metalness:0.6})),0.05,0,0), g);
    for(var t=0;t<4;t++){
      var tt=place(new THREE.Mesh(new THREE.ConeGeometry(0.05,0.12,12), mat(0x3a3d40,{metalness:0.8})), 0.2, (t<2?0.14:-0.14), (t%2?0.12:-0.12));
      tt.rotation.z=-Math.PI/2;
      reg('rcs', tt, g);
    }
  }
  // 4 solar wings x 3 panels
  var WING_LEN=2.46, WING_W=1.9, WING_R0=2.2;
  for(var w=0; w<4; w++){
    var wg=new THREE.Group();
    wg.position.set(0,1.25,0);
    wg.rotation.y = -(Math.PI/4 + w*Math.PI/2);
    exterior.add(wg);
    for(var s=0;s<3;s++){
      var px = WING_R0 + (s+0.5)*WING_LEN + s*0.05;
      reg('arrays', place(new THREE.Mesh(box(WING_LEN-0.05,WING_W,0.035), mat(0xffffff,{map:solarTex,metalness:0.5,roughness:0.35})),px,0,0), wg);
      reg('arrays', place(new THREE.Mesh(box(WING_LEN-0.05,0.05,0.07), mat(0xb9a36a,{metalness:0.7})),px,WING_W/2,0), wg);
      reg('arrays', place(new THREE.Mesh(box(WING_LEN-0.05,0.05,0.07), mat(0xb9a36a,{metalness:0.7})),px,-WING_W/2,0), wg);
    }
    reg('arrays', place(new THREE.Mesh(cyl(0.035,0.035,3*WING_LEN+0.3,10), mat(0xb9a36a,{metalness:0.7})),WING_R0+1.5*WING_LEN,0,0), wg).rotation.z=Math.PI/2;
    reg('arrays', place(new THREE.Mesh(box(0.25,0.35,0.12), mat(0x9aa4aa,{metalness:0.7})),2.12,0,0), wg);
  }

  /* ---------- Crew module adapter (y 4.0 .. 4.7) ---------- */
  var cma = lathe([[2.05,4.0],[2.05,4.12],[2.28,4.52],[2.12,4.72]], 72);
  reg('cma', new THREE.Mesh(cma, mat(0xc79a3c,{metalness:0.75,roughness:0.4})));
  for(var f=0; f<3; f++){
    var fa=f*2*Math.PI/3+0.5;
    var fg=new THREE.Mesh(box(0.14,0.55,0.9), mat(0xd9dde0,{metalness:0.5}));
    fg.position.set(2.2*Math.cos(fa),4.38,2.2*Math.sin(fa)); fg.rotation.y=-fa;
    reg('cma', fg);
  }

  /* ---------- Crew module (local frame: y 0 = bottom of the heat shield) ---------- */
  var cm = new THREE.Group(); cm.position.y = 4.7; exterior.add(cm);
  var hs=[]; for(var i=0;i<=28;i++){ var r=2.51*i/28; hs.push([r, 6-Math.sqrt(36-r*r)]); }
  reg('heat', new THREE.Mesh(lathe(hs,72), mat(0xffffff,{map:heatTex,metalness:0.1,roughness:0.85})), cm);
  reg('back', new THREE.Mesh(lathe([[2.51,0.55],[2.54,0.66],[2.48,0.76],[1.374,2.4]],72), mat(0xffffff,{map:tileTex,metalness:0.25,roughness:0.7})), cm);
  reg('fwdbay', new THREE.Mesh(lathe([[1.374,2.4],[0.78,3.28],[0.70,3.30]],72), mat(0xcfd6da,{metalness:0.45,roughness:0.5})), cm);
  var ring=place(new THREE.Mesh(new THREE.TorusGeometry(0.62,0.07,12,48), mat(0xd5dadd,{metalness:0.85,roughness:0.3})),0,3.3,0); ring.rotation.x=Math.PI/2; reg('fwdbay', ring, cm);
  reg('fwdbay', place(new THREE.Mesh(cyl(0.46,0.5,0.34,40), mat(0xb9c0c4,{metalness:0.8,roughness:0.35})),0,3.47,0), cm);
  var pet=place(new THREE.Mesh(new THREE.TorusGeometry(0.46,0.035,10,40), mat(0xe9edef,{metalness:0.9,roughness:0.25})),0,3.66,0); pet.rotation.x=Math.PI/2; reg('fwdbay', pet, cm);
  // side hatch (theta 0)
  (function(){
    var th=0, p=wallPt(th,1.6), n=wallN(th);
    var hatch=new THREE.Mesh(new THREE.CircleGeometry(0.55,40), mat(0x9ca7ad,{metalness:0.6,roughness:0.4}));
    hatch.position.copy(p).add(n.clone().multiplyScalar(0.025)); hatch.quaternion.setFromUnitVectors(new THREE.Vector3(0,0,1), n);
    reg('hatch', hatch, cm);
    var hr=new THREE.Mesh(new THREE.TorusGeometry(0.55,0.035,10,40), mat(0x4a5258,{metalness:0.8}));
    hr.position.copy(p).add(n.clone().multiplyScalar(0.03)); hr.quaternion.setFromUnitVectors(new THREE.Vector3(0,0,1), n);
    reg('hatch', hr, cm);
    var hw=new THREE.Mesh(new THREE.CircleGeometry(0.15,24), mat(0x5aa8ff,{metalness:0.2,roughness:0.1,transparent:true,opacity:0.6}));
    hw.position.copy(p).add(n.clone().multiplyScalar(0.05)); hw.quaternion.setFromUnitVectors(new THREE.Vector3(0,0,1), n);
    reg('hatch', hw, cm, {baseTransparent:true, baseOpacity:0.6, ghostOpacity:0.3});
  })();
  // four windows
  [1.047, 2.094, 4.189, 5.236].forEach(function(th){
    var p=wallPt(th,2.0), n=wallN(th);
    var gl=new THREE.Mesh(new THREE.CircleGeometry(0.17,28), mat(0x5aa8ff,{metalness:0.2,roughness:0.08,transparent:true,opacity:0.6}));
    gl.position.copy(p).add(n.clone().multiplyScalar(0.03)); gl.quaternion.setFromUnitVectors(new THREE.Vector3(0,0,1), n);
    reg('windows', gl, cm, {baseTransparent:true, baseOpacity:0.6, ghostOpacity:0.3});
    var fr=new THREE.Mesh(new THREE.TorusGeometry(0.17,0.02,8,28), mat(0x3a4146,{metalness:0.8}));
    fr.position.copy(p).add(n.clone().multiplyScalar(0.035)); fr.quaternion.setFromUnitVectors(new THREE.Vector3(0,0,1), n);
    reg('windows', fr, cm);
  });

  /* ---------- Launch Abort System (13.4 m above the crew module top, y 8.0 -> 21.4) ---------- */
  reg('las', new THREE.Mesh(lathe([[2.65,4.65],[2.65,5.4],[1.25,8.2],[0.62,9.3],[0.5,9.5]],64), mat(0xe8ebec,{metalness:0.2,roughness:0.55})), lasGroup);
  for(var ls=0; ls<4; ls++){
    var la=ls*Math.PI/2+Math.PI/4;
    var leg=new THREE.Mesh(cyl(0.05,0.05,2.45,10), mat(0xb9c0c4,{metalness:0.8}));
    leg.position.set(0.42*Math.cos(la),10.6,0.42*Math.sin(la)); leg.rotation.z=0; reg('las', leg, lasGroup);
  }
  [9.9,10.7,11.5].forEach(function(yy){ var rr=place(new THREE.Mesh(new THREE.TorusGeometry(0.43,0.03,8,32), mat(0xb9c0c4,{metalness:0.8})),0,yy,0); rr.rotation.x=Math.PI/2; reg('las', rr, lasGroup); });
  reg('las', place(new THREE.Mesh(cyl(0.46,0.46,4.4,36), mat(0xdfe3e5,{metalness:0.3,roughness:0.5})),0,14.0,0), lasGroup);
  reg('las', place(new THREE.Mesh(cyl(0.40,0.40,2.2,36), mat(0xc8ced1,{metalness:0.35})),0,17.3,0), lasGroup);
  reg('las', place(new THREE.Mesh(cyl(0.30,0.30,1.9,32), mat(0xe8ebec,{metalness:0.3})),0,19.35,0), lasGroup);
  reg('las', place(new THREE.Mesh(new THREE.ConeGeometry(0.30,1.15,32), mat(0xf2f4f5,{metalness:0.2})),0,20.85,0), lasGroup);

  /* ------------------------------------------------------------ interior (hidden in OUTSIDE mode) */
  function structMat(c){ return new THREE.MeshBasicMaterial({color:c, transparent:true, opacity:0.5}); }
  // cabin floor and frame rings
  var floor=place(new THREE.Mesh(new THREE.CircleGeometry(2.08,56), mat(0x16342a,{metalness:0.2,roughness:0.9})),0,5.85,0); floor.rotation.x=-Math.PI/2; interior.add(floor);
  var fl2=place(new THREE.Mesh(new THREE.RingGeometry(0.5,2.08,56,6), new THREE.MeshBasicMaterial({color:0x1f6b49,wireframe:true,transparent:true,opacity:0.35})),0,5.852,0); fl2.rotation.x=-Math.PI/2; interior.add(fl2);
  [0.9,1.5,2.1,2.7].forEach(function(y){
    var rr=place(new THREE.Mesh(new THREE.TorusGeometry(wallR(y)*0.975,0.012,6,56), structMat(0x3dd68c)),0,4.7+y,0); rr.rotation.x=Math.PI/2; interior.add(rr);
  });
  [0.2,1.2,2.2,3.2,3.9].forEach(function(y){
    var rr=place(new THREE.Mesh(new THREE.TorusGeometry(2.0,0.014,6,64), structMat(0x3dd68c)),0,y,0); rr.rotation.x=Math.PI/2; interior.add(rr);
  });
  // room volumes (translucent boxes + outline) -> the clickable "rooms"
  ZONES.forEach(function(z){
    if(!z.vol) return;
    z.vol.forEach(function(v){
      var m=new THREE.Mesh(box(v[3],v[4],v[5]), new THREE.MeshBasicMaterial({color:0x00ff66,transparent:true,opacity:0.14,depthWrite:false}));
      m.position.set(v[0],v[1],v[2]);
      var e=new THREE.LineSegments(new THREE.EdgesGeometry(box(v[3],v[4],v[5])), new THREE.LineBasicMaterial({color:0x00ff66,transparent:true,opacity:0.9}));
      e.position.set(v[0],v[1],v[2]);
      m.userData.zone=z.id; interior.add(m); interior.add(e);
      z.hit.push(m); z.vmeshes.push(m); z.vmeshes.push(e);
    });
  });
  function iprop(zid, geo, color, x,y,z, o){ var m=new THREE.Mesh(geo, mat(color,o)); m.position.set(x,y,z); reg(zid, m, interior); return m; }
  // cockpit: 3 displays + 7 switch panels + 2 hand controllers
  [-1.1,-0.6,-0.1].forEach(function(x){
    var d=new THREE.Mesh(box(0.46,0.34,0.03), new THREE.MeshBasicMaterial({color:0x14573b})); d.position.set(x,6.85,-1.43); d.rotation.x=-0.25; reg('cockpit', d, interior);
  });
  for(var sp=0;sp<7;sp++){ var sx=-1.35+sp*0.25; iprop('cockpit', box(0.2,0.16,0.03), 0x2a3338, sx, 6.55, -1.42, {metalness:0.5}).rotation.x=-0.25; }
  [-1.0,-0.2].forEach(function(x){ iprop('cockpit', cyl(0.025,0.03,0.22,10), 0x1f2528, x,6.12,-0.62); iprop('cockpit', new THREE.SphereGeometry(0.05,12,10), 0x1f2528, x,6.26,-0.62); });
  // 4 seats (2 x 2) + cargo net on the mission-specialist side
  [[-1.05,-0.95],[-0.15,-0.95],[-1.05,0.35],[-0.15,0.35]].forEach(function(sp2){
    var sx=sp2[0], sz=sp2[1];
    iprop('seats', box(0.5,0.07,0.55), 0x3b5568, sx,6.0,sz, {metalness:0.2,roughness:0.8});
    iprop('seats', box(0.5,0.55,0.07), 0x3b5568, sx,6.27,sz+0.27, {metalness:0.2,roughness:0.8}).rotation.x=-0.18;
    iprop('seats', box(0.3,0.16,0.08), 0x4a6b82, sx,6.62,sz+0.3, {metalness:0.2,roughness:0.8});
    iprop('seats', box(0.45,0.3,0.05), 0x2b3b47, sx,5.9,sz-0.15, {metalness:0.2,roughness:0.8});
  });
  var net=new THREE.Mesh(new THREE.PlaneGeometry(1.8,0.7,9,4), new THREE.MeshBasicMaterial({color:0x7be0a8,wireframe:true,transparent:true,opacity:0.5})); net.position.set(-0.6,6.2,0.7); net.rotation.x=-0.25; reg('seats', net, interior);
  // galley (wall panel, water dispenser, food warmer)
  iprop('galley', box(0.5,0.62,0.12), 0x8ba0aa, 1.35,6.45,1.02, {metalness:0.5}).rotation.y=-0.65;
  iprop('galley', cyl(0.07,0.07,0.3,16), 0x4aa3ff, 1.22,6.5,0.88, {metalness:0.3});
  iprop('galley', box(0.3,0.16,0.22), 0x2c3438, 1.42,6.2,0.9, {metalness:0.5});
  // exercise (flywheel, base, handle bar, step)
  iprop('exercise', cyl(0.27,0.27,0.12,32), 0xa8b1b6, 1.4,6.22,-0.1, {metalness:0.7,roughness:0.3});
  iprop('exercise', box(0.62,0.18,0.9), 0x39444a, 1.4,6.0,-0.1, {metalness:0.5});
  var hb=new THREE.Mesh(new THREE.TorusGeometry(0.2,0.025,8,24,Math.PI), mat(0xc8d0d4,{metalness:0.8})); hb.position.set(1.4,6.42,0.28); reg('exercise', hb, interior);
  // hygiene bay booth
  iprop('hygiene', box(0.68,0.8,0.68), 0x9aa9b1, 0.08,6.25,1.3, {metalness:0.3,roughness:0.6});
  iprop('hygiene', box(0.3,0.5,0.02), 0x4f5c63, 0.08,6.25,0.95, {metalness:0.3});
  // storm shelter: two lockers + water bags / canisters
  [-0.5,0.5].forEach(function(z){
    iprop('shelter', box(0.6,0.9,0.9), 0x6f8c9c, 0.55,6.3,z, {metalness:0.3,roughness:0.6});
    var le=new THREE.LineSegments(new THREE.EdgesGeometry(box(0.6,0.9,0.9)), new THREE.LineBasicMaterial({color:0xcffff0})); le.position.set(0.55,6.3,z); interior.add(le);
  });
  for(var wb=0; wb<6; wb++){ var wy=6.0+(wb%3)*0.3, wz=(wb<3?-0.5:0.5); var bag=iprop('shelter', new THREE.SphereGeometry(0.1,12,10), 0x6ec1ff, 0.25,wy,wz+(wb%2?0.18:-0.18), {metalness:0.1,roughness:0.3}); bag.scale.set(1,0.7,1.2); }
  // sleeping bags
  [-0.9,-0.3,0.3,0.9].forEach(function(x){
    var sb=iprop('sleep', cyl(0.16,0.16,1.4,18), 0x6b4e8f, x,7.0,0, {metalness:0.1,roughness:0.9}); sb.rotation.x=Math.PI/2;
    iprop('sleep', new THREE.SphereGeometry(0.16,14,10), 0x6b4e8f, x,7.0,0.7, {metalness:0.1,roughness:0.9});
    iprop('sleep', new THREE.SphereGeometry(0.16,14,10), 0x6b4e8f, x,7.0,-0.7, {metalness:0.1,roughness:0.9});
  });
  // lower equipment bay: avionics boxes + 2 tanks
  for(var ab=0; ab<8; ab++){ var aa=ab*Math.PI/4+0.2; var av=iprop('leb', box(0.5,0.4,0.32), 0x4a5a63, 1.45*Math.cos(aa),5.55,1.45*Math.sin(aa), {metalness:0.5}); av.rotation.y=-aa; }
  [-0.6,0.6].forEach(function(x){ iprop('leb', cyl(0.28,0.28,0.5,24), 0xb5aa7a, x,5.55,0, {metalness:0.6,roughness:0.4}); });
  // forward bay inside: 3 main + 2 drogue parachute canisters + docking tunnel
  for(var mp=0; mp<3; mp++){ var ma=mp*2*Math.PI/3; iprop('fwdbay', cyl(0.2,0.2,0.65,20), 0xd8553c, 0.48*Math.cos(ma),7.55,0.48*Math.sin(ma), {metalness:0.2,roughness:0.8}); }
  [0.9,2.4].forEach(function(a2){ iprop('fwdbay', cyl(0.1,0.1,0.5,16), 0xe39a3c, 0.5*Math.cos(a2+3),7.45,0.5*Math.sin(a2+3), {metalness:0.2,roughness:0.8}); });
  iprop('fwdbay', cyl(0.36,0.36,0.9,32), 0xb9c0c4, 0,7.55,0, {metalness:0.7,roughness:0.4, transparent:true, opacity:0.5});
  // ESM propellant tanks: 2 MON + 2 MMH
  [[0.95,0.95,0x6f9fb5],[-0.95,0.95,0x6f9fb5],[0.95,-0.95,0xb58a6f],[-0.95,-0.95,0xb58a6f]].forEach(function(t){
    iprop('tanks', cyl(0.55,0.55,1.8,36), t[2], t[0],2.2,t[1], {metalness:0.6,roughness:0.35});
    iprop('tanks', new THREE.SphereGeometry(0.55,28,16), t[2], t[0],3.1,t[1], {metalness:0.6,roughness:0.35}).scale.set(1,0.4,1);
    iprop('tanks', new THREE.SphereGeometry(0.55,28,16), t[2], t[0],1.3,t[1], {metalness:0.6,roughness:0.35}).scale.set(1,0.4,1);
  });
  // ESM water (4), oxygen (3), nitrogen (1)
  for(var wt=0; wt<4; wt++){ var wa=wt*Math.PI/2+Math.PI/4; iprop('fluids', new THREE.SphereGeometry(0.27,24,16), 0x4aa3ff, 1.35*Math.cos(wa),0.85,1.35*Math.sin(wa), {metalness:0.3,roughness:0.3}); }
  for(var ot=0; ot<3; ot++){ var oa=ot*2*Math.PI/3; iprop('fluids', new THREE.SphereGeometry(0.22,24,16), 0xcfe8ff, 1.3*Math.cos(oa),3.35,1.3*Math.sin(oa), {metalness:0.5,roughness:0.3}); }
  iprop('fluids', new THREE.SphereGeometry(0.2,24,16), 0xa7e07c, 0.0,3.35,0, {metalness:0.5,roughness:0.3});

  /* ------------------------------------------------------------ space (OUTSIDE mode only) */
  (function(){
    var N=1800, pos=new Float32Array(N*3), col=new Float32Array(N*3);
    for(var i=0;i<N;i++){
      var u=Math.random()*2-1, th=Math.random()*Math.PI*2, rr=Math.sqrt(1-u*u), R=330+Math.random()*60;
      pos[i*3]=R*rr*Math.cos(th); pos[i*3+1]=R*u; pos[i*3+2]=R*rr*Math.sin(th);
      var c=0.55+Math.random()*0.45; col[i*3]=c*0.85; col[i*3+1]=c; col[i*3+2]=c*0.9;
    }
    var g=new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(pos,3));
    g.setAttribute('color', new THREE.BufferAttribute(col,3));
    space.add(new THREE.Points(g, new THREE.PointsMaterial({size:1.4,vertexColors:true,sizeAttenuation:false})));
  })();
  var earthTex = tex(1024,512,function(g,w,h){
    var gr=g.createLinearGradient(0,0,0,h); gr.addColorStop(0,'#0c3f86'); gr.addColorStop(1,'#08306a'); g.fillStyle=gr; g.fillRect(0,0,w,h);
    for(var i=0;i<70;i++){ g.fillStyle=(i%3?'#2f7d3a':'#8a7b4a'); g.beginPath(); g.ellipse(Math.random()*w,h*0.15+Math.random()*h*0.7,12+Math.random()*60,8+Math.random()*34,Math.random()*3,0,Math.PI*2); g.fill(); }
    for(var j=0;j<90;j++){ g.fillStyle='rgba(255,255,255,'+(0.18+Math.random()*0.22)+')'; g.beginPath(); g.ellipse(Math.random()*w,Math.random()*h,20+Math.random()*70,5+Math.random()*14,Math.random()*3,0,Math.PI*2); g.fill(); }
    g.fillStyle='rgba(255,255,255,.85)'; g.fillRect(0,0,w,14); g.fillRect(0,h-14,w,14);
  });
  var earth = new THREE.Mesh(new THREE.SphereGeometry(24,48,32), new THREE.MeshStandardMaterial({map:earthTex,roughness:0.9,metalness:0}));
  earth.position.set(-70,-48,-130); space.add(earth);
  var atmo = new THREE.Mesh(new THREE.SphereGeometry(25.2,48,32), new THREE.MeshBasicMaterial({color:0x4a9cff,transparent:true,opacity:0.18,side:THREE.BackSide,blending:THREE.AdditiveBlending,depthWrite:false}));
  atmo.position.copy(earth.position); space.add(atmo);
  var moonTex = tex(512,256,function(g,w,h){
    g.fillStyle='#8c8c88'; g.fillRect(0,0,w,h);
    for(var i=0;i<140;i++){ var s=140-Math.random()*60; g.fillStyle='rgba('+s+','+s+','+(s-6)+',.55)'; g.beginPath(); g.arc(Math.random()*w,Math.random()*h,3+Math.random()*18,0,Math.PI*2); g.fill(); }
  });
  var moon = new THREE.Mesh(new THREE.SphereGeometry(6.5,40,28), new THREE.MeshStandardMaterial({map:moonTex,roughness:1,metalness:0}));
  moon.position.set(95,38,-210); space.add(moon);
  var sunTex = tex(128,128,function(g,w,h){ var gr=g.createRadialGradient(w/2,h/2,2,w/2,h/2,w/2); gr.addColorStop(0,'rgba(255,255,235,1)'); gr.addColorStop(0.25,'rgba(255,220,140,.7)'); gr.addColorStop(1,'rgba(255,160,40,0)'); g.fillStyle=gr; g.fillRect(0,0,w,h); });
  var sunMat = new THREE.SpriteMaterial({map:sunTex,color:0xffffff,blending:THREE.AdditiveBlending,depthWrite:false,transparent:true});
  var sunSprite = new THREE.Sprite(sunMat); sunSprite.scale.set(70,70,1); sunSprite.position.copy(sunDir).multiplyScalar(240); space.add(sunSprite);

  // proton stream from the Sun (visible while the event dose > 0)
  var PN=720, pPos=new Float32Array(PN*3), pT=new Float32Array(PN), pA=new Float32Array(PN), pB=new Float32Array(PN);
  var ux=new THREE.Vector3(0,1,0).cross(sunDir).normalize(), uy=sunDir.clone().cross(ux).normalize();
  for(var pi=0; pi<PN; pi++){ pT[pi]=Math.random()*90; pA[pi]=(Math.random()*2-1)*13; pB[pi]=(Math.random()*2-1)*13; }
  var pGeo=new THREE.BufferGeometry(); pGeo.setAttribute('position', new THREE.BufferAttribute(pPos,3));
  var pMat=new THREE.PointsMaterial({size:0.22,color:0xff8a00,transparent:true,opacity:0.85,depthWrite:false,blending:THREE.AdditiveBlending});
  var particles=new THREE.Points(pGeo,pMat); particles.frustumCulled=false; space.add(particles);
  function stepParticles(dt, speed){
    var o=new THREE.Vector3(0,4,0);
    for(var i=0;i<PN;i++){
      pT[i]+=dt*speed; if(pT[i]>90){ pT[i]-=90; pA[i]=(Math.random()*2-1)*13; pB[i]=(Math.random()*2-1)*13; }
      var d=45-pT[i];
      pPos[i*3]  =o.x+sunDir.x*d+ux.x*pA[i]+uy.x*pB[i];
      pPos[i*3+1]=o.y+sunDir.y*d+ux.y*pA[i]+uy.y*pB[i];
      pPos[i*3+2]=o.z+sunDir.z*d+ux.z*pA[i]+uy.z*pB[i];
    }
    pGeo.attributes.position.needsUpdate=true;
  }

  /* ------------------------------------------------------------ hull (ghosted in INSIDE mode) */
  var hull=[];
  exterior.traverse(function(o){ if(o.isMesh && o.userData.zone){ hull.push(o); } });
  function setGhost(on){
    hull.forEach(function(m){
      var mt=m.material;
      mt.transparent = on ? true : !!m.userData.baseTransparent;
      mt.opacity = on ? (m.userData.ghostOpacity||0.09) : (m.userData.baseOpacity||1);
      mt.depthWrite = !on;
      mt.needsUpdate = true;
    });
  }

  /* ------------------------------------------------------------ radiation -> colors */
  var tmpC=new THREE.Color();
  function recalc(){
    var worst=0;
    ZONES.forEach(function(z){
      z.dose=eventMsv*z.mult; z.frac=z.dose/LIMIT; z.level=levelFor(z.frac); worst=Math.max(worst,z.frac);
      tmpC.setHex(z.level.hex);
      z.meshes.forEach(function(m){
        var mt=m.material;
        mt.color.copy(m.userData.base).lerp(tmpC,0.62);
        if(mt.emissive){ mt.emissive.copy(tmpC).multiplyScalar(0.17); }
      });
      z.vmeshes.forEach(function(m){ m.material.color.copy(tmpC); });
    });
    // sun + stream color follow the worst level
    var wl=levelFor(worst); tmpC.setHex(eventMsv>0?wl.hex:0xffffff); sunMat.color.copy(tmpC); pMat.color.copy(tmpC);
    particles.visible = (mode==='out' && eventMsv>0);
    pGeo.setDrawRange(0, Math.floor(PN*clamp(0.18+eventMsv/330,0.18,1)));
    updateRoomDots(); updateLegend(); updateStormUi(); updateWarn();
    if(selected){ showPanel(selected); }
  }

  /* ------------------------------------------------------------ UI: rooms list, legend, panel */
  var mode='out', selected=null, lasOn=false, labelsOn=true, auto=false, voiceOn=true;
  var roomsEl=$('rooms'), labelsEl=$('labels');
  function buildRooms(){
    var html='', groups=['Exterior','Crew Module','Service Module'];
    groups.forEach(function(g){
      html+='<h4>'+g.toUpperCase()+'</h4>';
      ZONES.forEach(function(z){ if(z.group===g){ html+='<button class="zbtn" data-id="'+z.id+'"><span class="dot" style="color:#00ff66;background:#00ff66"></span><span>'+(z.short||z.name)+'</span></button>'; } });
    });
    roomsEl.innerHTML=html;
    var btns=roomsEl.querySelectorAll('.zbtn');
    for(var i=0;i<btns.length;i++){ (function(b){ b.addEventListener('click', function(){ selectZone(b.getAttribute('data-id')); }); })(btns[i]); }
  }
  function updateRoomDots(){
    var btns=roomsEl.querySelectorAll('.zbtn');
    for(var i=0;i<btns.length;i++){
      var z=zoneById[btns[i].getAttribute('data-id')], d=btns[i].firstChild;
      if(!z||!d) continue;
      d.style.color=z.level.css; d.style.background=z.level.css;
      if(btns[i].classList){ if(selected && selected.id===z.id) btns[i].classList.add('sel'); else btns[i].classList.remove('sel'); }
    }
  }
  function updateLegend(){
    var h='<b style="font-family:Orbitron;letter-spacing:.1em;color:#eafff1">RADIATION</b>';
    LEVELS.forEach(function(l){ h+='<span><i class="dot" style="color:'+l.css+';background:'+l.css+'"></i>'+l.name+' '+l.rng+'</span>'; });
    $('legend').innerHTML=h;
  }
  function updateStormUi(){
    $('ev').value=eventMsv; $('evv').textContent=Math.round(eventMsv)+' mSv';
    var changed=Math.abs(eventMsv-APP_EVENT)>0.5;
    $('src').textContent=(CFG.source||'')+(changed?'  ·  manual override (simulated)':'');
  }
  function li(t){ return '<li>'+t+'</li>'; }
  function showPanel(z){
    if(!z){
      $('panel').innerHTML='<div class="ptitle">ORION · MPCV</div><div class="pgr">Multi-Purpose Crew Vehicle · NASA / ESA / Lockheed Martin / Airbus</div>'
        +'<ul>'+[
          'Crew module: 5.02 m wide × 3.3 m tall, 4 crew, up to 21 days undocked, ≈ 9 m³ habitable volume.',
          'European Service Module: 4.1 m × 4 m, 4 solar wings (≈ 19 m span, ≈ 11 kW).',
          'Press <b>OUTSIDE</b> / <b>INSIDE</b>, drag to rotate 360°, scroll to zoom.',
          'Click any part or room (3D or list) to zoom in and hear its name.',
          'Colors: red = full radiation, orange = medium, yellow = low, green = safe.'
        ].map(li).join('')+'</ul>'+fcDetail();
      return;
    }
    var lv=z.level;
    var h='<div class="ptitle">'+z.name+'</div><div class="pgr">'+z.group+'</div>'
      +'<div class="rad" style="border-color:'+lv.css+';color:'+lv.css+'">RADIATION · '+lv.name+' · '+z.dose.toFixed(0)+' mSv ('+Math.round(z.frac*100)+'% of '+LIMIT+' mSv)</div>'
      +'<div class="small">event '+eventMsv.toFixed(0)+' mSv × shielding factor '+z.mult.toFixed(2)+' (assumption)</div>'
      +'<ul>'+z.info.map(li).join('')+'</ul>';
    $('panel').innerHTML=h;
  }

  /* ------------------------------------------------------------ camera */
  var cam={target:new THREE.Vector3(0,4,0), theta:0.75, phi:1.3, r:30};
  var tw=null;
  function applyCam(){
    var s=Math.sin(cam.phi);
    camera.position.set(cam.target.x+cam.r*s*Math.sin(cam.theta), cam.target.y+cam.r*Math.cos(cam.phi), cam.target.z+cam.r*s*Math.cos(cam.theta));
    camera.lookAt(cam.target);
  }
  function flyTo(tx,ty,tz,theta,phi,r,ms){
    tw={t0:performance.now(), ms:ms||1000, f:{x:cam.target.x,y:cam.target.y,z:cam.target.z,th:cam.theta,ph:cam.phi,r:cam.r}, t:{x:tx,y:ty,z:tz,th:theta,ph:phi,r:r}};
  }
  function stepTween(now){
    if(!tw) return;
    var k=Math.min(1,(now-tw.t0)/tw.ms), e=k<0.5?2*k*k:1-Math.pow(-2*k+2,2)/2, f=tw.f, t=tw.t;
    cam.target.set(lerp(f.x,t.x,e),lerp(f.y,t.y,e),lerp(f.z,t.z,e));
    cam.theta=f.th+angDiff(f.th,t.th)*e; cam.phi=lerp(f.ph,t.ph,e); cam.r=lerp(f.r,t.r,e);
    if(k>=1) tw=null;
  }
  function home(){
    if(mode==='in'){ flyTo(0,6.4,0, 0.9,1.15, 5.4, 1100); }
    else if(lasOn){ flyTo(0,10,0, 0.75,1.32, 52, 1100); }
    else { flyTo(0,3.8,0, 0.75,1.3, 29, 1100); }
  }

  /* ------------------------------------------------------------ mode / selection */
  var marker=new THREE.Mesh(new THREE.TorusGeometry(0.4,0.014,8,48), new THREE.MeshBasicMaterial({color:0xffffff,transparent:true,opacity:0.9,depthTest:false}));
  marker.visible=false; marker.renderOrder=10; scene.add(marker);
  function setMode(m, noFly){
    mode=m;
    interior.visible=(m==='in');
    space.visible=(m==='out');
    setGhost(m==='in');
    scene.background.setHex(m==='in'?0x04140d:0x02060a);
    particles.visible=(m==='out' && eventMsv>0);
    $('bOut').classList.toggle('on', m==='out'); $('bIn').classList.toggle('on', m==='in');
    buildLabels();
    if(!noFly){ selected=null; marker.visible=false; showPanel(null); updateRoomDots(); home(); }
  }
  function setLas(on){
    lasOn=on; lasGroup.visible=on; $('bLas').classList.toggle('on', on); buildLabels();
    if(mode==='out' && !tw){ home(); }
  }
  function speak(z){
    if(!voiceOn || !window.speechSynthesis || !window.SpeechSynthesisUtterance) return;
    try{
      window.speechSynthesis.cancel();
      var u=new SpeechSynthesisUtterance(z.name+'. Radiation level '+z.level.name.toLowerCase()+'. '+z.info[0]);
      u.lang='en-US'; u.rate=0.95; window.speechSynthesis.speak(u);
    }catch(e){}
  }
  function selectZone(id){
    var z=zoneById[id]; if(!z) return;
    if(z.type==='int' && mode!=='in'){ setMode('in', true); }
    if(z.type==='ext' && mode!=='out'){ setMode('out', true); }
    if(z.launchOnly && !lasOn){ setLas(true); }
    selected=z; showPanel(z); updateRoomDots(); speak(z);
    marker.visible=true; marker.position.set(z.pos[0],z.pos[1],z.pos[2]);
    var th=cam.theta, ph=(z.cam?z.cam[1]:(mode==='in'?1.15:1.3));
    var hx=(mode==='in'?-z.pos[0]:z.pos[0]), hz=(mode==='in'?-z.pos[2]:z.pos[2]);
    if(z.cam){ th=z.cam[0]; }
    else if(Math.sqrt(hx*hx+hz*hz)>0.45){ th=Math.atan2(hx,hz); }
    flyTo(z.pos[0],z.pos[1],z.pos[2], th, ph, z.dist, 1000);
  }

  /* ------------------------------------------------------------ labels (HTML tags following 3D points) */
  var labels=[];
  function eligible(z){
    if(z.launchOnly && !lasOn) return false;
    if(z.type==='both') return true;
    return (mode==='in') ? z.type==='int' : z.type==='ext';
  }
  function buildLabels(){
    labelsEl.innerHTML=''; labels=[];
    ZONES.forEach(function(z){
      if(!eligible(z)) return;
      var d=document.createElement('div'); d.className='lbl'; d.textContent=z.short||z.name;
      d.addEventListener('click', function(ev){ ev.stopPropagation(); selectZone(z.id); });
      labelsEl.appendChild(d); labels.push({z:z, el:d, v:new THREE.Vector3(z.pos[0],z.pos[1]+0.05,z.pos[2])});
    });
  }
  function updateLabels(){
    var W=view.clientWidth, H=view.clientHeight, vis=labelsOn;
    labelsEl.style.display=vis?'block':'none';
    if(!vis) return;
    var p=new THREE.Vector3();
    labels.forEach(function(L){
      p.copy(L.v).project(camera);
      if(p.z>1 || p.z<-1){ L.el.style.display='none'; return; }
      L.el.style.display='block';
      L.el.style.left=((p.x*0.5+0.5)*W)+'px'; L.el.style.top=((-p.y*0.5+0.5)*H)+'px';
      L.el.style.borderColor=L.z.level.css; L.el.style.color=(selected&&selected.id===L.z.id)?'#ffffff':L.z.level.css;
    });
  }

  /* ------------------------------------------------------------ pointer controls: rotate 360°, zoom, pan, click-to-select */
  var dom=renderer.domElement, pointers={}, dragging=false, moved=0, lastPinch=0, downAt=null;
  function minR(){ return mode==='in'?0.7:2.5; }
  function maxR(){ return mode==='in'?30:110; }
  dom.addEventListener('contextmenu', function(e){ e.preventDefault(); });
  dom.addEventListener('pointerdown', function(e){
    pointers[e.pointerId]={x:e.clientX,y:e.clientY,b:e.button};
    try{ dom.setPointerCapture(e.pointerId); }catch(x){}
    dragging=true; moved=0; tw=null; downAt={x:e.clientX,y:e.clientY};
    dom.style.cursor='grabbing';
  });
  dom.addEventListener('pointermove', function(e){
    var p=pointers[e.pointerId];
    if(!p){ hover(e); return; }
    var ids=Object.keys(pointers);
    if(ids.length===2){
      var a=pointers[ids[0]], b=pointers[ids[1]];
      a=(ids[0]==e.pointerId)?{x:e.clientX,y:e.clientY}:a; b=(ids[1]==e.pointerId)?{x:e.clientX,y:e.clientY}:b;
      var d=Math.hypot(a.x-b.x,a.y-b.y);
      if(lastPinch>0){ cam.r=clamp(cam.r*(lastPinch/d), minR(), maxR()); }
      lastPinch=d; moved+=10;
    } else {
      var dx=e.clientX-p.x, dy=e.clientY-p.y; moved+=Math.abs(dx)+Math.abs(dy);
      if(p.b===2 || e.shiftKey){                                      // pan
        var s=cam.r*0.0016, right=new THREE.Vector3(), up=new THREE.Vector3();
        right.setFromMatrixColumn(camera.matrix,0); up.setFromMatrixColumn(camera.matrix,1);
        cam.target.addScaledVector(right,-dx*s); cam.target.addScaledVector(up,dy*s);
      } else {                                                         // rotate
        cam.theta-=dx*0.0065; cam.phi=clamp(cam.phi-dy*0.0065,0.06,Math.PI-0.06);
      }
    }
    if(pointers[e.pointerId]){ pointers[e.pointerId].x=e.clientX; pointers[e.pointerId].y=e.clientY; }
  });
  function up(e){
    var had=pointers[e.pointerId];
    delete pointers[e.pointerId]; lastPinch=0;
    if(Object.keys(pointers).length===0){ dragging=false; dom.style.cursor='grab'; }
    if(had && moved<6 && downAt){ pick(e.clientX,e.clientY); }
  }
  dom.addEventListener('pointerup', up); dom.addEventListener('pointercancel', up);
  dom.addEventListener('wheel', function(e){ e.preventDefault(); tw=null; cam.r=clamp(cam.r*Math.exp(e.deltaY*0.0011), minR(), maxR()); }, {passive:false});

  var ray=new THREE.Raycaster(), ndc=new THREE.Vector2();
  function pickables(){
    var out=[];
    ZONES.forEach(function(z){ if(eligible(z)){ z.hit.forEach(function(m){ out.push(m); }); } });
    return out;
  }
  function zoneAt(cx,cy){
    var r=dom.getBoundingClientRect();
    ndc.set(((cx-r.left)/r.width)*2-1, -((cy-r.top)/r.height)*2+1);
    ray.setFromCamera(ndc, camera);
    var hits=ray.intersectObjects(pickables(), false);
    for(var i=0;i<hits.length;i++){ var id=hits[i].object.userData.zone; if(id) return id; }
    return null;
  }
  function pick(cx,cy){ var id=zoneAt(cx,cy); if(id){ selectZone(id); } }
  function hover(e){ if(dragging) return; dom.style.cursor = zoneAt(e.clientX,e.clientY) ? 'pointer' : 'grab'; }

  /* ------------------------------------------------------------ buttons */
  function zoom(f){ tw=null; cam.r=clamp(cam.r*f,minR(),maxR()); }
  $('bOut').addEventListener('click', function(){ setMode('out'); });
  $('bIn').addEventListener('click', function(){ setMode('in'); });
  $('bLas').addEventListener('click', function(){ setLas(!lasOn); });
  $('bLbl').addEventListener('click', function(){ labelsOn=!labelsOn; $('bLbl').classList.toggle('on', labelsOn); });
  $('bAuto').addEventListener('click', function(){ auto=!auto; $('bAuto').classList.toggle('on', auto); });
  $('bVoice').addEventListener('click', function(){ voiceOn=!voiceOn; $('bVoice').classList.toggle('on', voiceOn); if(!voiceOn && window.speechSynthesis){ window.speechSynthesis.cancel(); } });
  $('bZi').addEventListener('click', function(){ zoom(0.72); });
  $('bZo').addEventListener('click', function(){ zoom(1.38); });
  $('bHome').addEventListener('click', function(){ selected=null; marker.visible=false; showPanel(null); updateRoomDots(); home(); });
  $('ev').addEventListener('input', function(){ eventMsv=+$('ev').value; recalc(); });
  $('bApp').addEventListener('click', function(){ eventMsv=APP_EVENT; recalc(); });
  $('bStorm').addEventListener('click', function(){ eventMsv=266; recalc(); });


  /* ------------------------------------------------------------ ML forecast (from 05_predict.py / 06_live.py) */
  var FC = CFG.forecast || null;
  /* TEAM ASSUMPTION: forecast peak flux (pfu, >10 MeV) -> free-space event dose (mSv).
     log-linear: 10 pfu (S1) = 0 mSv ... 10^5 pfu (S5) = 400 mSv. NOT NASA data. */
  function peakToMsv(pfu){ return clamp(400*(Math.log(pfu)/Math.LN10 - 1)/4, 0, 400); }
  function pct(x){ return (x===null||x===undefined||isNaN(x)) ? 'n/a' : Math.round(x*100)+'%'; }
  function fcText(){
    if(!FC){ return 'no forecast loaded (run 05_predict.py or 06_live.py)'; }
    if(!FC.peak_pfu){ return (FC.status||'ALL CLEAR')+(FC.time?' · '+FC.time+' UTC':''); }
    return FC.status+' · '+(+FC.hours).toFixed(1)+' h · peak '+Math.round(FC.peak_pfu).toLocaleString('en-US')+' pfu (S'+FC.s_level+')';
  }
  function fcDetail(){
    if(!FC || !FC.peak_pfu) return '';
    var f=FC.fluence||{}, h='<div class="small" style="margin-top:8px">ML FORECAST · '+(FC.time||'')+' UTC</div><ul>'
      +'<li>peak &gt;10 MeV: <b>'+Math.round(FC.peak_pfu).toLocaleString('en-US')+' pfu</b> (NOAA S'+FC.s_level+')</li>'
      +'<li>fluence 10–30 / 30–50 / 50–100 / &gt;100 MeV: 10^'+[f.f10_30,f.f30_50,f.f50_100,f.f100].map(function(v){return (+v).toFixed(1);}).join(' / 10^')+'</li>'
      +'<li>peak already passed: '+pct(FC.p_passed)+' · peak within 6 h: '+pct(FC.p_within6)+'</li>';
    if(FC.outside>0) h+='<li style="color:#ff8a00">outside the training range: forecast probably too LOW</li>';
    return h+'</ul>';
  }
  function updateWarn(){
    var el=$('warn'), sh=zoneById.shelter, se=zoneById.seats, w=$('warn');
    if(eventMsv<=0.5){ el.className='hud'; return; }
    var lv=se.level, shelterNow=(se.frac>=0.15);
    var head = lv.id==='high' ? 'SOLAR RADIATION STORM · SEVERE' : lv.id==='med' ? 'SOLAR RADIATION STORM · WARNING' : lv.id==='low' ? 'SOLAR RADIATION · WATCH' : 'SOLAR RADIATION · NOMINAL';
    var col = lv.css;
    var t='<b style="color:'+col+'">⚠ '+head+'</b><br>';
    if(FC && FC.peak_pfu && Math.abs(eventMsv-Math.round(peakToMsv(FC.peak_pfu)))<1){ t+='ML forecast: '+Math.round(FC.peak_pfu).toLocaleString('en-US')+' pfu (S'+FC.s_level+') · '; }
    t+='crew seats '+se.dose.toFixed(0)+' mSv ('+Math.round(se.frac*100)+'%)';
    if(shelterNow){ t+=' → <b style="color:#00ff66">MOVE TO THE STORM SHELTER</b>: '+sh.dose.toFixed(0)+' mSv ('+Math.round(sh.frac*100)+'%)'; }
    else { t+=' · no shelter action needed'; }
    el.innerHTML=t; el.style.borderColor=col; el.className='hud show';
  }

  /* ------------------------------------------------------------ PICTURES gallery */
  var GALLERY = [
   {cat:'ML FORECAST', items:[
    {k:'pred_vs_obs', t:'Predicted vs observed', c:'Leave-one-solar-cycle-out test, 1 hour after onset. Left: peak flux &gt;10 MeV. Right: fluence &gt;100 MeV. Dashed line = perfect forecast, grey band = within a factor of 2. Fluence follows the line closely; the peak is harder and the largest storms are often under-predicted.'},
    {k:'skill_by_hour', t:'Skill by hour since onset', c:'Left: R² for how big the storm will be. It grows with time, from about 0.3 for the peak at 30 min to about 0.72 at 6 h, and fluences reach 0.84–0.88. Right: AUC for when the peak comes. "Peak passed" is useful from 1–2 h (≈0.85); "peak within 6 h" is still weak early, which is why it is hidden before 4 h.'}]},
   {cat:'ISS · DOSTEL', items:[
    {k:'iss_event', t:'ISS dose, Sept 2017 event', c:'DosTel2 inside the ISS, 4–16 Sept 2017. Orange = South Atlantic Anomaly passes (up to a few hundred µGy/h, every orbit), blue = high latitudes, grey = rest of the orbit. The solar storm of 11–12 Sept shows as a jump in the blue high-latitude points, up to about 90 µGy/h.'},
    {k:'iss_daily', t:'Daily dose, 2009–2024', c:'Daily median dose at high latitudes from DosTel1 and DosTel2. Level is about 6–8 µGy/h and follows the solar cycle, with short spikes during storms. The straight lines are data gaps.'},
    {k:'iss_map', t:'Where the dose is high', c:'Dose along the ISS orbit (±51.6° latitude) on a longitude/latitude map. The dark region is the South Atlantic Anomaly; the high-latitude bands at the top and bottom are the other source.'},
    {k:'iss_regions', t:'Dose by orbit region', c:'Absorbed dose rate by region, 2009–2024 (log scale). Median: about 3 µGy/h in the rest of the orbit, about 7 at high latitudes, and about 80 in the South Atlantic Anomaly, with a long tail above 400.'}]}
  ];
  GALLERY.forEach(function(c){ c.items=c.items.filter(function(i){ return PICS[i.k]; }); });
  GALLERY=GALLERY.filter(function(c){ return c.items.length>0; });
  var pCat=0, pIdx=0;
  function pOpen(open){ $('pics').className='hud'+(open?' open':''); $('bPics').classList.toggle('on', open); if(open) pRender(); }
  function pRender(){
    if(!GALLERY.length){ $('pimg').innerHTML='<div style="color:#333;padding:20px">No pictures found. Put the PNG files in a folder called orion_pics next to orion_3d.py.</div>'; $('ptabs').innerHTML=''; $('pthumbs').innerHTML=''; $('pcap').innerHTML=''; return; }
    var tabs='', cats=GALLERY;
    cats.forEach(function(c,i){ tabs+='<div class="btn'+(i===pCat?' on':'')+'" data-c="'+i+'">'+c.cat+'</div>'; });
    $('ptabs').innerHTML=tabs;
    var tb=$('ptabs').querySelectorAll('.btn');
    for(var i=0;i<tb.length;i++){ (function(b){ b.addEventListener('click', function(){ pCat=+b.getAttribute('data-c'); pIdx=0; pRender(); }); })(tb[i]); }
    var items=cats[pCat].items, th='';
    items.forEach(function(it,i){ th+='<div class="th'+(i===pIdx?' sel':'')+'" data-i="'+i+'"><img src="'+PICS[it.k]+'" alt=""><div style="margin-top:3px">'+it.t+'</div></div>'; });
    $('pthumbs').innerHTML=th;
    var ts=$('pthumbs').querySelectorAll('.th');
    for(var j=0;j<ts.length;j++){ (function(b){ b.addEventListener('click', function(){ pIdx=+b.getAttribute('data-i'); pRender(); }); })(ts[j]); }
    var cur=items[pIdx];
    $('pimg').innerHTML='<img src="'+PICS[cur.k]+'" alt="'+cur.t+'">';
    $('pcap').innerHTML='<b>'+cur.t.toUpperCase()+'</b> · '+(pIdx+1)+'/'+items.length+'<br>'+cur.c;
  }
  function pStep(d){ var n=GALLERY[pCat].items.length; pIdx=(pIdx+d+n)%n; pRender(); }
  $('bPics').addEventListener('click', function(){ pOpen(!$('pics').classList.contains('open')); });
  $('pClose').addEventListener('click', function(){ pOpen(false); });
  $('pPrev').addEventListener('click', function(){ pStep(-1); });
  $('pNext').addEventListener('click', function(){ pStep(1); });
  window.addEventListener('keydown', function(e){
    if(!$('pics').classList.contains('open')) return;
    if(e.key==='Escape') pOpen(false); else if(e.key==='ArrowLeft') pStep(-1); else if(e.key==='ArrowRight') pStep(1);
  });
  $('fct').textContent=fcText();
  (function(){ var o=window.__fcDetail=fcDetail; })();

  /* ------------------------------------------------------------ main loop */
  function resize(){
    var w=view.clientWidth||800, h=view.clientHeight||600;
    renderer.setSize(w,h,false); camera.aspect=w/h; camera.updateProjectionMatrix();
  }
  window.addEventListener('resize', resize);
  if(window.ResizeObserver){ new ResizeObserver(resize).observe(view); }
  var last=performance.now(), failed=false;
  function frame(now){
    if(failed) return;
    requestAnimationFrame(frame);
    try{
      var dt=Math.min(0.05,(now-last)/1000); last=now;
      stepTween(now);
      if(auto && !dragging && !tw){ cam.theta+=dt*0.25; }
      applyCam();
      if(particles.visible){ stepParticles(dt, 22+eventMsv*0.12); }
      earth.rotation.y+=dt*0.01;
      if(marker.visible){ marker.lookAt(camera.position); var pu=1+0.12*Math.sin(now*0.006); marker.scale.set(pu,pu,pu); if(selected){ marker.material.color.setHex(selected.level.hex); } }
      updateLabels();
      renderer.render(scene,camera);
    }catch(e){ failed=true; fail('Rendering error: '+(e&&e.message?e.message:e)); if(window.console) console.error(e); }
  }

  if(CFG.applyForecast){ eventMsv=FC && FC.peak_pfu ? Math.round(peakToMsv(FC.peak_pfu)) : 0; }
  else if(FC && FC.peak_pfu && APP_EVENT===0 && CFG.autoForecast){ eventMsv=Math.round(peakToMsv(FC.peak_pfu)); }
  buildRooms(); buildLabels(); resize(); setMode('out', true); recalc(); showPanel(null); applyCam();
  home();
  requestAnimationFrame(frame);

  window.__orion = {setMode:setMode, selectZone:selectZone, setEvent:function(v){ eventMsv=v; recalc(); }, zones:ZONES, setLas:setLas, zoom:zoom, pick:pick};
}
})();
</script>
</body></html>
"""


def load_forecast(path: str | None = None) -> dict | None:
    """Newest forecast from 06_live.py (live_log.csv) or 05_predict.py (forecast_output.csv).
    Returns None if no file is found. Columns are the ones those scripts write."""
    import pandas as pd
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [path] if path else [
        os.path.join(here, "live", "data", "live_log.csv"),
        os.path.join(here, "data", "live_log.csv"),
        os.path.join(here, "forecast", "data", "processed", "forecast_output.csv"),
        os.path.join(here, "data", "processed", "forecast_output.csv")]
    for p in candidates:
        if not p or not os.path.exists(p):
            continue
        df = pd.read_csv(p)
        if len(df) == 0:
            continue
        last = df.iloc[-1]
        t = last.get("time", "")
        if "pred_log_peak" not in df.columns or pd.isna(df["pred_log_peak"]).all():
            return {"status": str(last.get("status", "ALL CLEAR")), "time": str(t)}
        has = df.dropna(subset=["pred_log_peak"]).iloc[-1]          # newest row with a forecast
        peak = float(10 ** has["pred_log_peak"])
        g = lambda c: float(has[c]) if c in has and pd.notna(has[c]) else None
        return {"status": str(has.get("status", "STORM")) if "status" in has else "STORM",
                "time": str(has.get("time", t)), "hours": g("hours_since_onset") or 0.0,
                "peak_pfu": peak, "s_level": int(min(max(has["pred_log_peak"] // 1, 0), 5)),
                "fluence": {"f10_30": g("pred_log_fluence_10_30"), "f30_50": g("pred_log_fluence_30_50"),
                            "f50_100": g("pred_log_fluence_50_100"), "f100": g("pred_log_fluence_100")},
                "p_passed": g("prob_peak_passed"), "p_within6": g("prob_peak_within_6h"),
                "outside": int(g("outside_training") or 0)}
    return None


def _forecast_from_flux(flux, saved: dict, now, data_delay_min: float) -> tuple[dict, dict]:
    import numpy as np
    import pandas as pd
    from features import make_features

    threshold = 10
    onset_points = 3
    end_points = 12
    first_forecast_h = 0.5
    max_hours = 6
    above = (flux["p10"] >= threshold).to_numpy()
    onset = None
    below = 0
    for i in range(len(above) - onset_points + 1):
        if onset is None:
            if above[i:i + onset_points].all():
                onset = flux.index[i]
                below = 0
        else:
            below = 0 if above[i] else below + 1
            if below >= end_points:
                onset = None

    row = {"time": now, "p10_now": float(flux["p10"].iloc[-1]), "onset": onset}
    if onset is None:
        row["status"] = "ALL CLEAR"
    else:
        hours = (now - onset).total_seconds() / 3600
        model_time = min(now, onset + pd.Timedelta(hours=max_hours))
        if hours < first_forecast_h:
            row["status"] = "STORM STARTED"
        else:
            feature_values = make_features(flux, onset, model_time)
            if feature_values is None:
                row["status"] = "NO FORECAST"
            else:
                X = pd.DataFrame([feature_values])[saved["features"]]
                if X.isna().to_numpy().any():
                    row["status"] = "NO FORECAST"
                else:
                    row["status"] = "STORM" if hours <= max_hours else "STORM (forecast frozen at 6 h)"
                    row["hours_since_onset"] = hours
                    for target, model in saved["size"].items():
                        row["pred_" + target] = float(model.predict(X)[0])
                    for target, model in saved["time"].items():
                        row["prob_" + target] = float(model.predict_proba(X)[0, 1])
                    row["prob_peak_within_6h"] = max(
                        row["prob_peak_within_6h"], row["prob_peak_passed"])
                    model_hours = X["hours_since_onset"].iloc[0]
                    if model_hours < 1:
                        row["prob_peak_passed"] = np.nan
                    if model_hours < 4:
                        row["prob_peak_within_6h"] = np.nan
                    row["outside_training"] = int(
                        ((X < saved["ranges"].loc["min"]) |
                         (X > saved["ranges"].loc["max"])).sum(axis=1).iloc[0])

    log_columns = [
        "time", "status", "p10_now", "onset", "hours_since_onset",
        "pred_log_peak", "pred_log_fluence_10_30", "pred_log_fluence_30_50",
        "pred_log_fluence_50_100", "pred_log_fluence_100",
        "prob_peak_passed", "prob_peak_within_6h", "outside_training",
    ]
    log_row = {column: row.get(column) for column in log_columns}

    def finite_or_none(value):
        return float(value) if value is not None and np.isfinite(value) else None

    forecast = {
        "status": row["status"],
        "time": now.strftime("%Y-%m-%d %H:%M:%S"),
        "data_delay_min": round(data_delay_min, 1),
    }
    if "pred_log_peak" in row:
        forecast.update({
            "hours": float(row["hours_since_onset"]),
            "peak_pfu": float(10 ** row["pred_log_peak"]),
            "s_level": int(np.clip(np.floor(row["pred_log_peak"]), 0, 5)),
            "fluence": {
                "f10_30": finite_or_none(row.get("pred_log_fluence_10_30")),
                "f30_50": finite_or_none(row.get("pred_log_fluence_30_50")),
                "f50_100": finite_or_none(row.get("pred_log_fluence_50_100")),
                "f100": finite_or_none(row.get("pred_log_fluence_100")),
            },
            "p_passed": finite_or_none(row.get("prob_peak_passed")),
            "p_within6": finite_or_none(row.get("prob_peak_within_6h")),
            "outside": int(row.get("outside_training", 0)),
        })
    return forecast, log_row


def run_live_forecast_once() -> dict:
    """Fetch NOAA's current proton flux and run one live forecast."""
    import pickle
    import ssl
    from urllib.request import urlopen

    import certifi
    import pandas as pd
    from features import GSEP_QUIET

    live_url = "https://services.swpc.noaa.gov/json/goes/primary/integral-protons-7-day.json"
    energies = {
        ">=10 MeV": "p10",
        ">=30 MeV": "p30",
        ">=50 MeV": "p50",
        ">=100 MeV": "p100",
    }
    here = os.path.dirname(os.path.abspath(__file__))
    model_file = os.path.join(here, "models", "forecast_models.pkl")
    if not os.path.exists(model_file):
        raise FileNotFoundError(f"Forecast model not found: {model_file}. Run forecast/04_train.py first.")
    with open(model_file, "rb") as model_stream:
        saved = pickle.load(model_stream)

    with urlopen(
        live_url,
        context=ssl.create_default_context(cafile=certifi.where()),
        timeout=30,
    ) as response:
        raw = pd.read_json(response)
    required = {"time_tag", "energy", "flux"}
    if not required.issubset(raw.columns):
        raise ValueError("NOAA response is missing required fields: time_tag, energy, flux.")
    raw = raw[raw["energy"].isin(energies)]
    raw["time_tag"] = pd.to_datetime(raw["time_tag"], utc=True, errors="coerce").dt.tz_localize(None)
    raw["flux"] = pd.to_numeric(raw["flux"], errors="coerce")
    raw = raw.dropna(subset=["time_tag", "flux"])
    if raw.empty:
        raise ValueError("NOAA returned no usable proton-flux data.")
    missing_energies = set(energies) - set(raw["energy"])
    if missing_energies:
        raise ValueError("NOAA response is missing energy channels: " + ", ".join(sorted(missing_energies)))

    flux = raw.pivot_table(index="time_tag", columns="energy", values="flux").rename(columns=energies)
    flux = flux[list(energies.values())].resample("5min").mean().interpolate(limit=6)
    now = flux.index.max()
    if pd.isna(now):
        raise ValueError("NOAA returned no timestamped proton-flux data.")
    data_delay_min = (pd.Timestamp.now(tz="UTC").tz_localize(None) - now).total_seconds() / 60

    quiet = flux.quantile(0.10)
    for column in flux.columns:
        flux[column] = (flux[column] - quiet[column]).clip(lower=0) + GSEP_QUIET[column]

    forecast, log_row = _forecast_from_flux(flux, saved, now, data_delay_min)
    log_file = os.path.join(here, "live", "data", "live_log.csv")
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    columns = [
        "time", "status", "p10_now", "onset", "hours_since_onset",
        "pred_log_peak", "pred_log_fluence_10_30", "pred_log_fluence_30_50",
        "pred_log_fluence_50_100", "pred_log_fluence_100",
        "prob_peak_passed", "prob_peak_within_6h", "outside_training",
    ]
    pd.DataFrame([log_row], columns=columns).to_csv(
        log_file, mode="a", header=not os.path.exists(log_file), index=False)
    return forecast


def build_html(event_msv: float = 0.0, source: str = "", limit: float = 250.0,
               forecast: dict | None = None, auto_forecast: bool = False,
               apply_forecast: bool = False) -> str:
    cfg = {"eventMsv": float(event_msv), "source": str(source), "limit": float(limit),
           "forecast": forecast, "autoForecast": bool(auto_forecast),
           "applyForecast": bool(apply_forecast)}
    return (HTML.replace("__THREE_URL__", THREE_URL)
                .replace("__PICS__", json.dumps(PICS))
                .replace("__CONFIG__", json.dumps(cfg)))


def radiation_input(real_astro, sim_event_msv: float, scenario: str):
    """Event dose (mSv) for the Orion map and a label saying where it comes from.

    REAL when the database has a radiation dose-rate indicator and an event is detected for the selected
    astronaut; otherwise the simulated scenario of the dashboard (clearly labelled SIMULATED).
    """
    try:
        import ichor_radiation as ir
        import ichor_3d_panel as p3
        if real_astro:
            conn = p3._conn(ir.DB_PATH)
            if not ir.missing_slugs(conn):
                a = ir.assess(conn, real_astro["id"])
                return (float(a.event["dose_msv"]) if a.event else 0.0), "REAL · database dose rate"
    except Exception:
        pass
    return float(sim_event_msv or 0.0), f"SIMULATED · scenario: {scenario}"


def render_orion(event_msv: float = 0.0, source: str = "", height: int = 800,
                 forecast: dict | None = None, auto_forecast: bool = False) -> None:
    import streamlit as st
    import streamlit.components.v1 as components

    if forecast is None:
        forecast = st.session_state.get("orion_live_forecast") or load_forecast()
    st.markdown("#### ML FORECAST")
    forecast_col, app_value_col = st.columns(2)
    with forecast_col:
        run_forecast = st.button("🤖 ML FORECAST", key="orion_run_live_forecast")
    with app_value_col:
        use_app_value = st.button("APP VALUE", key="orion_use_app_value")
    if use_app_value:
        st.session_state["orion_apply_live_forecast"] = False
    if run_forecast:
        st.session_state["orion_apply_live_forecast"] = False
        with st.spinner("Fetching NOAA proton flux and running the forecast..."):
            try:
                forecast = run_live_forecast_once()
            except (OSError, ValueError, KeyError, RuntimeError, ImportError) as error:
                st.error(f"Live forecast failed: {error}")
            else:
                st.session_state["orion_live_forecast"] = forecast
                st.session_state["orion_apply_live_forecast"] = True
    if forecast:
        st.caption(f"Latest forecast: {forecast.get('status', 'unknown')} · {forecast.get('time', '')} UTC")
        if forecast.get("data_delay_min", 0) > 20:
            st.warning(f"The newest NOAA data are {forecast['data_delay_min']:.0f} minutes old.")
    components.html(build_html(
        event_msv,
        source,
        forecast=forecast,
        auto_forecast=auto_forecast,
        apply_forecast=st.session_state.get("orion_apply_live_forecast", False),
    ),
                    height=height, scrolling=False)


# =====================================================================================================
# Standalone Streamlit page:  streamlit run orion_site.py
# =====================================================================================================
def main() -> None:
    import streamlit as st

    st.set_page_config(page_title="Orion 3D", page_icon="🛰", layout="wide", initial_sidebar_state="collapsed")
    st.markdown(
        "<style>#MainMenu, footer, header {visibility:hidden;} .stApp {background:#04100a;} "
        ".block-container {padding:0.6rem 0.8rem 0 0.8rem; max-width:100%;} "
        "h1,p,label,span,div {color:#d4ffe2;}</style>", unsafe_allow_html=True)
    with st.sidebar:
        st.markdown("### Orion 3D")
        dose = st.slider("Starting solar-event dose (mSv)", 0, 400, 0, 5)
        height = st.slider("Viewer height (px)", 600, 1200, 860, 20)
        st.markdown("### ML forecast")
        fc_path = st.text_input("Forecast CSV (empty = auto-find live_log.csv / forecast_output.csv)", "")
        use_fc = st.checkbox("Color the model from the forecast", value=False)
        forecast = load_forecast(fc_path.strip() or None)
        st.caption("Forecast found: " + (forecast.get("status", "yes") if forecast else "none"))
    render_orion(float(dose), "Orion site · " + ("ML forecast" if (use_fc and forecast) else "simulated dose"),
                 int(height), forecast, use_fc)
    st.caption("Orion geometry: public NASA / ESA / Lockheed Martin / Airbus figures. Interior layout is schematic and the "
               "per-room shielding factors are team assumptions. Needs internet in the browser (three.js).")


if __name__ == "__main__":
    main()