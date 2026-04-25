// Hydroflow Launch Wizard — main app (5 шагов, ae3 GrowCycleLauncher manifest).
const { useState, useEffect, useMemo } = React;

const STEPS = [
  { id:'zone', label:'Зона',           sub:'теплица + зона' },
  { id:'rec',  label:'Рецепт',         sub:'культура + фазы' },
  { id:'aut',  label:'Автоматика',     sub:'узлы и роли' },
  { id:'cal',  label:'Калибровка',     sub:'5 подсистем' },
  { id:'run',  label:'Подтверждение',  sub:'diff + запуск' },
];

const GREENHOUSES = [
  { id:'gh-01', name:'Berry', type:'Плёночная', area:420, zones:4, nodes:6 },
  { id:'gh-02', name:'Leafy', type:'Стеклянная', area:240, zones:2, nodes:3 },
  { id:'gh-03', name:'R&D',   type:'Контейнер',  area:80,  zones:1, nodes:2 },
];

const RECIPES = [
  { id:1, name:'Tomato Launch', revisionNumber:3, status:'PUBLISHED', plantId:'p-1',
    system:'NFT', substrate:'Rockwool', targetPh:5.8, targetEc:1.6,
    phases:[
      { name:'Germination', days:7,  ph:5.8, ec:0.8, lightOn:18, lightOff:6, irrigInterval:60, irrigDuration:60,  npk:'A · 1.0', cal:'B · 0.5', mag:'C · 0.3', micro:'D · 0.1' },
      { name:'Vegetation',  days:21, ph:5.8, ec:1.6, lightOn:16, lightOff:8, irrigInterval:30, irrigDuration:120, npk:'A · 2.0', cal:'B · 1.0', mag:'C · 0.6', micro:'D · 0.2' },
      { name:'Flowering',   days:28, ph:6.0, ec:2.2, lightOn:12, lightOff:12, irrigInterval:30, irrigDuration:120, npk:'A · 3.0', cal:'B · 1.5', mag:'C · 0.9', micro:'D · 0.3' },
      { name:'Harvest',     days:14, ph:6.0, ec:1.4, lightOn:10, lightOff:14, irrigInterval:60, irrigDuration:90,  npk:'A · 1.0', cal:'B · 0.5', mag:'C · 0.3', micro:'D · 0.1' },
    ]},
  { id:2, name:'Lettuce Butterhead', revisionNumber:1, status:'PUBLISHED', plantId:'p-2',
    system:'DWC', substrate:'—', targetPh:5.6, targetEc:1.2,
    phases:[
      { name:'Seedling',   days:10, ph:5.8, ec:0.6, lightOn:16, lightOff:8, irrigInterval:60, irrigDuration:60, npk:'A · 0.5', cal:'B · 0.3', mag:'C · 0.2', micro:'D · 0.05' },
      { name:'Vegetative', days:25, ph:5.6, ec:1.2, lightOn:16, lightOff:8, irrigInterval:30, irrigDuration:60, npk:'A · 1.5', cal:'B · 0.8', mag:'C · 0.4', micro:'D · 0.15' },
      { name:'Harvest',    days:5,  ph:5.6, ec:0.9, lightOn:14, lightOff:10,irrigInterval:60, irrigDuration:60, npk:'A · 1.0', cal:'B · 0.5', mag:'C · 0.3', micro:'D · 0.1' },
    ]},
  { id:3, name:'Basil Genovese', revisionNumber:2, status:'DRAFT', plantId:'p-3',
    system:'Drip · drip_emitter', substrate:'Coco', targetPh:6.0, targetEc:1.4,
    phases:[
      { name:'Seedling',  days:14, ph:6.0, ec:0.8, lightOn:16,lightOff:8, irrigInterval:60,irrigDuration:60, npk:'A · 0.8', cal:'B · 0.4', mag:'C · 0.3', micro:'D · 0.1' },
      { name:'Vegetative',days:21, ph:6.0, ec:1.4, lightOn:14,lightOff:10,irrigInterval:30,irrigDuration:90, npk:'A · 2.0', cal:'B · 1.0', mag:'C · 0.6', micro:'D · 0.2' },
      { name:'Harvest',   days:7,  ph:6.0, ec:1.0, lightOn:12,lightOff:12,irrigInterval:60,irrigDuration:60, npk:'A · 1.0', cal:'B · 0.5', mag:'C · 0.3', micro:'D · 0.1' },
    ]},
];

const INITIAL = {
  gh:  { greenhouseId:'gh-01', ghType:'Плёночная' },
  zn:  { mode:'select', zoneId:'z-4', name:'Zone Launch 2026-03-23', desc:'Front launch zone',
         area:'12', h:'180', topology:'NFT · рециркуляция' },
  rec: { mode:'select', recipeId:1, revisionNumber:3, status:'PUBLISHED', plantId:'p-1',
         name:'Tomato Launch', system:'NFT', substrate:'Rockwool', targetPh:5.8, targetEc:1.6,
         phases: RECIPES[0].phases, cycle:70,
         plantingAt:'2026-03-23T16:02', batch:'batch-2026-03', usageCount:1 },
  // Расширенная автоматика — миррорит automationProfile.ts (waterForm + lightingForm + zoneClimateForm + assignments).
  aut: {
    waterForm: {
      systemType:'nft', tanksCount:2,
      cleanTankFillL:100, nutrientTankTargetL:100, irrigationBatchL:10,
      intervalMinutes:30, durationSeconds:120,
      fillTemperatureC:22, fillWindowStart:'08:00', fillWindowEnd:'09:30',
      targetPh:5.8, targetEc:1.6, phPct:5, ecPct:5,
      // Correction strategy
      correctionProfile:'balanced',
      correctionDeadbandPh:0.2, correctionDeadbandEc:0.15,
      correctionStepPhMl:2.0, correctionStepEcMl:5.0,
      correctionMaxDosePhMl:8.0, correctionMaxDoseEcMl:25.0,
      correctionMaxStepsPerWindow:6,
      correctionStepIntervalSec:90, correctionCooldownSec:300,
      correctionRecirculationBeforeDoseSec:30,
      correctionPhDirection:'auto', // 'down' | 'up' | 'auto'
      correctionEcSource:'mix_ab', // 'mix_ab' | 'a_only' | 'a_then_b'
      valveSwitching:false, correctionDuringIrrigation:false,
      enableDrainControl:true, drainTargetPercent:20,
      diagnosticsEnabled:true, diagnosticsIntervalMinutes:60, diagnosticsWorkflow:'cycle_start',
      cleanTankFullThreshold:95, refillDurationSeconds:60, refillTimeoutSeconds:300,
      mainPumpFlowLpm:10, cleanWaterFlowLpm:15, workingTankL:50,
      startupCleanFillTimeoutSeconds:600, startupSolutionFillTimeoutSeconds:600,
      startupPrepareRecirculationTimeoutSeconds:300, startupCleanFillRetryCycles:2,
      cleanFillMinCheckDelayMs:2000, solutionFillCleanMinCheckDelayMs:2000,
      solutionFillSolutionMinCheckDelayMs:2000,
      recirculationStopOnSolutionMin:true, estopDebounceMs:200,
      irrigationDecisionStrategy:'task',
      irrigationDecisionLookbackSeconds:600, irrigationDecisionMinSamples:5,
      irrigationDecisionStaleAfterSeconds:300, irrigationDecisionHysteresisPct:5,
      irrigationDecisionSpreadAlertThresholdPct:15,
      irrigationRecoveryMaxContinueAttempts:3, irrigationRecoveryTimeoutSeconds:120,
      irrigationAutoReplayAfterSetup:true, irrigationMaxSetupReplays:1,
      stopOnSolutionMin:false,
      correctionMaxEcCorrectionAttempts:5, correctionMaxPhCorrectionAttempts:5,
      correctionPrepareRecirculationMaxAttempts:3,
      correctionPrepareRecirculationMaxCorrectionAttempts:5,
      correctionStabilizationSec:45,
      refillRequiredNodeTypes:'pump,valve', refillPreferredChannel:'main',
      solutionChangeEnabled:false, solutionChangeIntervalMinutes:10080, solutionChangeDurationSeconds:120,
      manualIrrigationSeconds:60,
    },
    lightingForm: {
      enabled:true, luxDay:30000, luxNight:0, hoursOn:16, intervalMinutes:60,
      scheduleStart:'06:00', scheduleEnd:'22:00',
      manualIntensity:70, manualDurationHours:1,
    },
    zoneClimateForm: { enabled:false },
    assignments: {
      irrigation:14, ph_correction:15, ec_correction:16,
      light:null, soil_moisture_sensor:null, co2_sensor:null,
      co2_actuator:null, root_vent_actuator:null,
    },
  },
  cal: {
    sensors: {
      ph: { sensor:'ph-sensor-01', ok:true,  value:'5.82', offset:'-0.04', slope:'1.002',
            at:'2026-03-23T12:14' },
      ec: { sensor:'ec-sensor-01', ok:false, value:'1.58', offset:'0.00',  slope:'1.000', at:null },
    },
    pumps: [
      { component:'ph_up',     label:'pH up',     channel:'pump_base', duration:10, actualMl:10,  rate:'1.000', status:'done' },
      { component:'ph_down',   label:'pH down',   channel:'pump_acid', duration:10, actualMl:10,  rate:'1.000', status:'done' },
      { component:'npk',       label:'A · NPK',   channel:'pump_a',    duration:10, actualMl:9.8, rate:'0.980', status:'done' },
      { component:'calcium',   label:'B · Ca',    channel:'pump_b',    duration:10, actualMl:null, rate:null,   status:'todo' },
      { component:'magnesium', label:'C · Mg',    channel:'pump_c',    duration:10, actualMl:null, rate:null,   status:'todo' },
      { component:'micro',     label:'D · micro', channel:'pump_d',    duration:10, actualMl:null, rate:null,   status:'todo' },
    ],
    pid: {
      ph:{ target:5.8, dead_zone:0.05, close_zone:0.3, far_zone:1.0,
           zone_coeffs:{close:{kp:5,ki:0.05,kd:0}, far:{kp:8,ki:0.02,kd:0}},
           max_output:20, min_interval_ms:90000, max_integral:20, saved:true },
      ec:{ target:1.6, dead_zone:0.1, close_zone:0.5, far_zone:1.5,
           zone_coeffs:{close:{kp:30,ki:0.3,kd:0}, far:{kp:50,ki:0.1,kd:0}},
           max_output:50, min_interval_ms:120000, max_integral:100, saved:false },
    },
    proc: { solution_fill:true, tank_recirc:true, irrigation:false, generic:false },
    correction: {
      authority:'zone', max_step_ml:'5.0', step_interval:'90', cooldown:'180',
      tol_ph:'0.15', tol_ec:'0.20', dry_run:'false', saved:false,
    },
  },
};

// Mock available nodes for bindings (mirrors SetupWizard Node type).
const NODES = [
  { id:14, name:'Node-14', role:'irrigation' },
  { id:15, name:'Node-15', role:'ph_dose' },
  { id:16, name:'Node-16', role:'ec_dose' },
  { id:17, name:'Node-17', role:'light_actuator' },
  { id:18, name:'Node-18', role:'soil_moisture_sensor' },
  { id:19, name:'Node-19', role:'co2_sensor' },
  { id:20, name:'Node-20', role:'co2_actuator' },
  { id:21, name:'Node-21', role:'root_vent_actuator' },
];

function buildReadiness(state){
  const pumpsDone = state.cal.pumps.every(p=>p.status==='done');
  const pidDone   = state.cal.pid.ph.saved && state.cal.pid.ec.saved;
  const procDone  = Object.values(state.cal.proc).every(Boolean);
  const sensorsDone = state.cal.sensors.ph.ok && state.cal.sensors.ec.ok;
  return [
    { key:'gh',   label:'Теплица выбрана',          status: state.gh.greenhouseId?'ok':'err', note: state.gh.greenhouseId?.toUpperCase() ?? '—' },
    { key:'zn',   label:'Зона создана и привязана', status: state.zn.zoneId?'ok':'err',        note:'id 4' },
    { key:'pl',   label:'Рецепт активен',            status: state.rec.recipeId?'ok':'err',     note:`r${state.rec.revisionNumber||'?'}` },
    { key:'aut',  label:'Контуры привязаны',         status: state.aut.assignments.irrigation && state.aut.assignments.ph_correction && state.aut.assignments.ec_correction?'ok':'warn', note:'3/3'},
    { key:'sens', label:'Сенсоры откалиброваны',     status: sensorsDone?'ok':'warn', note: `${[state.cal.sensors.ph.ok,state.cal.sensors.ec.ok].filter(Boolean).length}/2` },
    { key:'pumps',label:'Все насосы откалиброваны',  status: pumpsDone?'ok':'warn', note:`${state.cal.pumps.filter(p=>p.status==='done').length}/6` },
    { key:'pid',  label:'PID pH и EC сохранены',     status: pidDone?'ok':'warn',   note: pidDone?'ph, ec':'ec —' },
    { key:'proc', label:'Процессы настроены',        status: procDone?'ok':'warn',  note: `${Object.values(state.cal.proc).filter(Boolean).length}/4` },
    { key:'ae',   label:'automation-engine online',  status:'ok', note:'9405' },
  ];
}

function computeCompletion(state){
  const r = buildReadiness(state);
  const g = (k)=> r.find(x=>x.key===k)?.status;
  return [
    (g('gh')==='ok' && g('zn')==='ok')?'done':'todo',
    g('pl')==='ok'?'done':'todo',
    g('aut')==='ok'?'done':(g('aut')==='warn'?'warn':'todo'),
    (g('pumps')==='ok'&&g('pid')==='ok'&&g('proc')==='ok'&&g('sens')==='ok')?'done':'warn',
    r.every(x=>x.status==='ok')?'done':'todo',
  ];
}

// Mock diff for preview step — what will be merged into zone.logic_profile
const DIFF = [
  { op:'replace', path:'/pid/ph/target',            from:'6.0',   to:'5.8' },
  { op:'replace', path:'/pid/ec/target',            from:'1.4',   to:'1.6' },
  { op:'replace', path:'/irrigation/interval_sec',  from:'1800',  to:'1800' },
  { op:'add',     path:'/overrides/correction/tolerance_ph', from:null, to:'0.15' },
  { op:'add',     path:'/bindings/irrigation_pump_node_id',  from:null, to:'14' },
  { op:'replace', path:'/pid/ec/zone_coeffs/far/kp', from:'40', to:'50' },
];

function App(){
  const [t, setTweak] = useTweaks(window.TWEAK_DEFAULTS);
  const [active, setActive] = useState(2); // открыть на Автоматике → Коррекция
  const [state, setState] = useState(INITIAL);
  const [modal, setModal] = useState({ open:false, idx:0 });
  const [toast, setToast] = useState(null);

  useEffect(()=>{
    document.documentElement.setAttribute('data-theme', t.dark?'dark':'light');
    document.documentElement.setAttribute('data-density', t.density);
  },[t.dark, t.density]);

  const readiness  = useMemo(()=>buildReadiness(state),[state]);
  const completion = useMemo(()=>computeCompletion(state),[state]);

  const setGh  = v => setState(s => ({...s, gh:v}));
  const setZn  = v => setState(s => ({...s, zn:v}));
  const setRec = v => setState(s => ({...s, rec:v}));
  const setAut = v => setState(s => ({...s, aut:v}));
  const setCal = v => setState(s => ({...s, cal:v}));

  const launch = () => {
    setToast('POST /api/zones/4/grow-cycles → 201 Created');
    setTimeout(()=>setToast(null), 3500);
  };

  const snap = {
    gh:      'GH-01 Berry',
    zone:    state.zn.name || 'Zone Launch 03-23',
    plant:   'Tomato r3',
    system:  'NFT · recirc',
    ph:      '5.8',
    ec:      '1.6 mS/cm',
    irrig:   'каждые 30 мин · 120 с',
    harvest: 'через 70 д',
  };

  return (
    <div style={{minHeight:'100vh',display:'flex',flexDirection:'column'}}>
      <TopBar/>
      {t.stepper==='horizontal' ? (
        <HStepper steps={STEPS} active={active} setActive={setActive} completion={completion}/>
      ) : null}
      <div style={{display:'flex',flex:1,minHeight:0}}>
        {t.stepper==='vertical' && (
          <VStepper steps={STEPS} active={active} setActive={setActive} completion={completion}/>
        )}
        <main style={{flex:1,padding:'18px 20px 80px',minWidth:0,
          background:'var(--bg)',display:'flex',flexDirection:'column',gap:14}}>
          <StepHeader step={STEPS[active]} index={active} total={STEPS.length}/>
          {active===0 && <Step1ZoneV2 gh={state.gh} zn={state.zn} setGh={setGh} setZn={setZn} hints={t.showHints}
                            greenhouses={GREENHOUSES} onCreateGh={(g)=>{ GREENHOUSES.push({id:g.uid,name:g.name,type:({film:'Плёночная',glass:'Стеклянная',poly:'Поликарбонат',container:'Контейнер'})[g.greenhouse_type_id]||'Другое',area:+g.area||0,zones:0,nodes:0}); setGh({...state.gh,greenhouseId:g.uid}); }}/>}
          {active===1 && <Step2RecipeV2 data={state.rec} set={setRec} hints={t.showHints} recipes={RECIPES}/>}
          {active===2 && <Step3AutomationHub data={state.aut} set={setAut} nodes={NODES} hints={t.showHints}
                            recipe={state.rec}/>}
          {active===3 && <Step4Calibration data={state.cal} set={setCal} hints={t.showHints}
                            onOpenPumpWizard={(idx)=>setModal({open:true,idx})}/>}
          {active===4 && <Step5Preview snap={snap} readiness={readiness} diff={DIFF} hints={t.showHints} onLaunch={launch}/>}
        </main>
      </div>

      <FooterNav active={active} setActive={setActive} total={STEPS.length}
                 completion={completion} onLaunch={launch}/>

      <PumpCalibrationModal open={modal.open} idx={modal.idx}
        data={state.cal} set={setCal}
        onClose={()=>setModal({open:false,idx:0})}/>

      {toast && (
        <div style={{position:'fixed',left:'50%',bottom:80,transform:'translateX(-50%)',
          padding:'10px 16px',background:'var(--growth)',color:'#fff',borderRadius:8,
          fontSize:13,boxShadow:'0 8px 30px rgba(0,0,0,.25)',zIndex:2000}}>
          <span style={{marginRight:8}}>✓</span>{toast}
        </div>
      )}

      <TweaksPanel>
        <TweakSection label="Плотность"/>
        <TweakRadio label="density" value={t.density}
          options={['compact','comfortable']}
          onChange={v=>setTweak('density',v)}/>
        <TweakSection label="Тема"/>
        <TweakToggle label="Тёмная" value={t.dark} onChange={v=>setTweak('dark',v)}/>
        <TweakSection label="Навигация"/>
        <TweakRadio label="stepper" value={t.stepper}
          options={['horizontal','vertical']}
          onChange={v=>setTweak('stepper',v)}/>
        <TweakSection label="Подсказки"/>
        <TweakToggle label="Показывать советы" value={t.showHints} onChange={v=>setTweak('showHints',v)}/>
        <TweakSection label="Быстрый переход"/>
        {STEPS.map((s,i)=>(
          <TweakButton key={s.id} label={`${i+1}. ${s.label}`} onClick={()=>setActive(i)}/>
        ))}
      </TweaksPanel>
    </div>
  );
}

function StepHeader({ step, index, total }){
  return (
    <div style={{display:'flex',alignItems:'baseline',justifyContent:'space-between',gap:12}}>
      <div>
        <div style={{fontSize:11,color:'var(--text-faint)',textTransform:'uppercase',letterSpacing:'.1em',fontWeight:600}}>
          Шаг <span className="mono">{index+1}/{total}</span>
        </div>
        <h1 style={{margin:'2px 0 0',fontSize:22,fontWeight:600,letterSpacing:'-0.01em'}}>
          {step.label} <span style={{color:'var(--text-faint)',fontWeight:400,fontSize:15}}>· {step.sub}</span>
        </h1>
      </div>
      <div style={{display:'flex',gap:6,alignItems:'center'}}>
        <Chip tone="neutral" icon={<Ic.dot style={{color:'var(--growth)'}}/>}>AE3</Chip>
        <Chip tone="neutral" icon={<Ic.dot style={{color:'var(--growth)'}}/>}>history-logger</Chip>
        <Chip tone="neutral" icon={<Ic.dot style={{color:'var(--growth)'}}/>}>mqtt-bridge</Chip>
      </div>
    </div>
  );
}

function FooterNav({ active, setActive, total, completion, onLaunch }){
  return (
    <footer style={{position:'sticky',bottom:0,display:'flex',alignItems:'center',
      justifyContent:'space-between',gap:12,padding:'10px 20px',
      borderTop:'1px solid var(--line)',background:'var(--bg-panel)',zIndex:5}}>
      <div style={{display:'flex',gap:6,alignItems:'center'}}>
        <Btn onClick={()=>setActive(Math.max(0,active-1))} disabled={active===0}>
          Назад
        </Btn>
        <span style={{fontSize:12,color:'var(--text-faint)'}} className="mono">
          {active+1}/{total}
        </span>
      </div>
      <div style={{display:'flex',gap:8,alignItems:'center'}}>
        <span style={{fontSize:12,color:'var(--text-muted)'}}>
          {completion.filter(s=>s==='done').length} из {total} завершено
        </span>
        {active < total-1 ? (
          <Btn variant="primary" onClick={()=>setActive(active+1)} icon={<Ic.chev/>}>
            Дальше
          </Btn>
        ) : (
          <Btn variant="growth" onClick={onLaunch} icon={<Ic.play/>}>
            Запустить цикл
          </Btn>
        )}
      </div>
    </footer>
  );
}

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(<App/>);
