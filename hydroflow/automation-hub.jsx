// Step 3 — Automation Hub (full): 6 subpages mirroring AutomationHub.vue
// Matches automationProfile.ts (waterForm/lightingForm/zoneClimateForm/assignments).
// Designed for visual parity with Step 4 Calibration hub.

const { useState: useStA, useMemo: useMA } = React;

// ---- shared atoms (re-imported via window) ------------------------------
// Field, Input, Select, Btn, Chip, Card, Hint, Stat, KV, Ic — already global.

// ============================================================
// AUTOMATION HUB — outer shell
// ============================================================
// Recipe-derived fields are READ-ONLY here. Editable only in step 2 (Recipe).
const RECIPE_LOCKED = ['systemType','targetPh','targetEc'];

function Step3AutomationHub({ data, set, hints, nodes, recipe }){
  const [sub, setSub] = useStA('correction');

  // Sync recipe-driven fields into waterForm if recipe changed
  React.useEffect(()=>{
    if (!recipe) return;
    const sysMap = { 'NFT':'nft', 'DWC':'substrate_trays', 'Ebb & Flow':'substrate_trays',
                     'Aeroponics':'substrate_trays', 'Drip · drip_tape':'drip', 'Drip · drip_emitter':'drip' };
    const nextSys = sysMap[recipe.system] || data.waterForm.systemType;
    const nextPh = recipe.targetPh ?? data.waterForm.targetPh;
    const nextEc = recipe.targetEc ?? data.waterForm.targetEc;
    if (nextSys !== data.waterForm.systemType || nextPh !== data.waterForm.targetPh || nextEc !== data.waterForm.targetEc) {
      set({...data, waterForm:{...data.waterForm, systemType:nextSys, targetPh:nextPh, targetEc:nextEc}});
    }
  }, [recipe?.recipeId, recipe?.system, recipe?.targetPh, recipe?.targetEc]);

  // contracts evaluation (simplified vs. useAutomationContracts)
  const a = data.assignments;
  const w = data.waterForm;
  const l = data.lightingForm;
  const c = data.zoneClimateForm;

  const bindReqOk = !!(a.irrigation && a.ph_correction && a.ec_correction);
  const bindReqCount = `${[a.irrigation,a.ph_correction,a.ec_correction].filter(Boolean).length}/3`;
  const bindOptCount = `${[a.light,a.soil_moisture_sensor,a.co2_sensor,a.co2_actuator,a.root_vent_actuator].filter(Boolean).length}/5`;

  const contourOk = !!w.systemType && w.tanksCount>=2 && w.workingTankL>0;
  const irrigOk   = w.intervalMinutes>0 && w.durationSeconds>0;
  const corrOk    = w.targetPh>0 && w.targetEc>0;
  const lightOk   = !l.enabled || (l.scheduleStart && l.scheduleEnd);
  const climOk    = !c.enabled || true;

  const nav = {
    bindings:   { state: bindReqOk?'passed':'blocker', count: bindReqCount, optCount: bindOptCount },
    contour:    { state: contourOk?'passed':'active',  count: `${w.tanksCount} бак(ов)` },
    irrigation: { state: irrigOk?'passed':'active',    count: w.irrigationDecisionStrategy==='smart_soil_v1'?'SMART':'TIME' },
    correction: { state: corrOk?'passed':'active',     count: `pH ${w.targetPh}·EC ${w.targetEc}` },
    lighting:   { state: l.enabled?(lightOk?'passed':'active'):'optional', count: l.enabled?`${l.hoursOn}ч`:'выкл' },
    climate:    { state: c.enabled?(climOk?'passed':'active'):'optional',  count: c.enabled?'CO₂':'выкл' },
  };

  const blockers = [
    !bindReqOk && 'bindings',
    !contourOk && 'contour',
    !irrigOk && 'irrigation',
    !corrOk && 'correction',
  ].filter(Boolean).length;

  return (
    <div style={{display:'flex',flexDirection:'column',gap:12}}>
      <AutomationReadinessBar blockers={blockers} nav={nav}/>
      {recipe && <RecipeBadge recipe={recipe}/>}
      <div style={{display:'grid',gridTemplateColumns:'240px 1fr',gap:12,alignItems:'start'}}>
        <AutoSidebar current={sub} onPick={setSub} nav={nav}/>
        <div style={{background:'var(--bg-panel)',border:'1px solid var(--line)',borderRadius:8,
          padding:16,minHeight:420}}>
          <AutoBreadcrumb sub={sub}/>
          {sub==='bindings'   && <BindingsSub   data={data} set={set} nodes={nodes} hints={hints}/>}
          {sub==='contour'    && <ContourSub    data={data} set={set} hints={hints} recipe={recipe}/>}
          {sub==='irrigation' && <IrrigationSub data={data} set={set} hints={hints}/>}
          {sub==='correction' && <CorrectionTargetsSub data={data} set={set} hints={hints} recipe={recipe}/>}
          {sub==='lighting'   && <LightingSub   data={data} set={set} hints={hints}/>}
          {sub==='climate'    && <ClimateSub    data={data} set={set} hints={hints}/>}
        </div>
      </div>
    </div>
  );
}

function AutomationReadinessBar({ blockers, nav }){
  const tone = blockers===0 ? 'growth' : 'warn';
  return (
    <div style={{display:'flex',alignItems:'center',gap:14,padding:'10px 14px',
      background:'var(--bg-panel)',border:'1px solid var(--line)',borderRadius:8,flexWrap:'wrap'}}>
      <Chip tone={tone} icon={blockers===0?<Ic.check/>:<Ic.warn/>}>
        Автоматика {blockers===0 ? 'готова' : `· ${blockers} блокер(а)`}
      </Chip>
      <span style={{width:1,height:20,background:'var(--line)'}}/>
      <NavChip label="Привязки"   n={nav.bindings} />
      <NavChip label="Контур"     n={nav.contour} />
      <NavChip label="Полив"      n={nav.irrigation} />
      <NavChip label="Коррекция"  n={nav.correction} />
      <NavChip label="Свет"       n={nav.lighting} />
      <NavChip label="Климат"     n={nav.climate} />
    </div>
  );
}
function NavChip({ label, n }){
  const tone = n.state==='passed'?'growth':n.state==='blocker'?'alert':n.state==='optional'?'neutral':'warn';
  return <Chip tone={tone}>{label} <span className="mono">{n.count}</span></Chip>;
}

function AutoSidebar({ current, onPick, nav }){
  const groups = [
    { title:'Инфраструктура', items:[
      {id:'bindings', title:'Привязки узлов', sub:'полив · pH · EC · опц.', idx:1},
      {id:'contour',  title:'Водный контур',  sub:'баки · насосы · окна',   idx:2},
    ]},
    { title:'Подсистемы', items:[
      {id:'irrigation', title:'Полив',          sub:'интервал · стратегия', idx:3},
      {id:'correction', title:'Коррекция pH/EC',sub:'цели · допуски',       idx:4},
    ]},
    { title:'Опциональные', items:[
      {id:'lighting',   title:'Свет',          sub:'расписание · lux',        idx:5},
      {id:'climate',    title:'Климат зоны',   sub:'CO₂ · вентиляция',        idx:6},
    ]},
  ];
  return (
    <aside style={{display:'flex',flexDirection:'column',gap:14,padding:10,
      border:'1px solid var(--line)',borderRadius:8,background:'var(--bg-panel)'}}>
      {groups.map(g => (
        <div key={g.title} style={{display:'flex',flexDirection:'column',gap:2}}>
          <div style={{fontSize:10,letterSpacing:'.08em',textTransform:'uppercase',
            fontWeight:700,color:'var(--text-faint)',padding:'0 6px 4px'}}>{g.title}</div>
          {g.items.map(it => {
            const n = nav[it.id];
            const active = current===it.id;
            const stateBg = {
              passed:'var(--growth)', blocker:'var(--alert)',
              optional:'var(--line-strong)', active:'var(--brand)',
            }[n.state] || 'var(--line-strong)';
            const stateIcon = {
              passed:<Ic.check style={{color:'#fff'}}/>,
              blocker:<Ic.warn style={{color:'#fff'}}/>,
            }[n.state];
            return (
              <button key={it.id} onClick={()=>onPick(it.id)} style={{
                display:'flex',alignItems:'center',gap:8,padding:'8px 8px',
                border:0,borderRadius:6,cursor:'default',
                background: active?'var(--brand-soft)':'transparent',
                color: active?'var(--brand-ink)':'var(--text)',
                textAlign:'left',
              }}>
                <span style={{width:20,height:20,borderRadius:'50%',
                  display:'inline-flex',alignItems:'center',justifyContent:'center',
                  background: active?'var(--brand)':stateBg,color:'#fff'}}>
                  {stateIcon || <span className="mono" style={{fontSize:11,fontWeight:600}}>{it.idx}</span>}
                </span>
                <span style={{display:'flex',flexDirection:'column',lineHeight:1.2,flex:1,minWidth:0}}>
                  <span style={{fontSize:13,fontWeight:500,display:'flex',justifyContent:'space-between',gap:6}}>
                    {it.title}
                    <span className="mono" style={{fontSize:11,color:active?'var(--brand-ink)':'var(--text-faint)'}}>
                      {n.count}
                    </span>
                  </span>
                  <span style={{fontSize:11,color:'var(--text-faint)'}}>{it.sub}</span>
                </span>
              </button>
            );
          })}
        </div>
      ))}
    </aside>
  );
}

function AutoBreadcrumb({ sub }){
  const map = {
    bindings:['Привязки узлов','Обязательные роли (полив / pH / EC) и опциональные (свет, влажность, CO₂, вентиляция).'],
    contour:['Водный контур','Топология из рецепта, баки, насосы, таймауты диагностики и recovery.'],
    irrigation:['Полив','Интервал, длительность, стратегия (по времени или SMART soil v1).'],
    correction:['Коррекция pH/EC','Целевые значения и допуски. Стек калибровок — на шаге «Калибровка».'],
    lighting:['Свет','Расписание, lux день/ночь, manual override.'],
    climate:['Климат зоны','CO₂, корневая вентиляция — если включено.'],
  };
  const [t,d] = map[sub];
  return (
    <div style={{display:'flex',flexDirection:'column',gap:2,paddingBottom:6,
      borderBottom:'1px solid var(--line)',marginBottom:14}}>
      <div className="mono" style={{fontSize:11,color:'var(--text-faint)'}}>/ зона / автоматика / {sub}</div>
      <div style={{fontSize:15,fontWeight:600}}>{t}</div>
      <div style={{fontSize:12,color:'var(--text-muted)'}}>{d}</div>
    </div>
  );
}

// ============================================================
// SUB 1 — Bindings
// ============================================================
function BindingsSub({ data, set, nodes, hints }){
  const a = data.assignments;
  const upd = (k,v)=> set({...data, assignments:{...a, [k]:v||null}});
  const required = [
    {key:'irrigation',     label:'Полив',         icon:<Ic.drop/>,   role:'pump_main / irrigation'},
    {key:'ph_correction',  label:'Коррекция pH',  icon:<Ic.beaker/>, role:'ph_dose'},
    {key:'ec_correction',  label:'Коррекция EC',  icon:<Ic.zap/>,    role:'ec_dose'},
  ];
  const optional = [
    {key:'light',                label:'Свет',                role:'light_actuator'},
    {key:'soil_moisture_sensor', label:'Влажность субстрата', role:'soil_moisture_sensor'},
    {key:'co2_sensor',           label:'Сенсор CO₂',          role:'co2_sensor'},
    {key:'co2_actuator',         label:'Исполнитель CO₂',     role:'co2_actuator'},
    {key:'root_vent_actuator',   label:'Корневая вентиляция', role:'root_vent_actuator'},
  ];
  const opts = [{value:'',label:'— не задано —'}, ...nodes.map(n=>({value:String(n.id),label:`${n.name} · ${n.role}`}))];

  return (
    <div style={{display:'flex',flexDirection:'column',gap:14}}>
      <div>
        <SectionLabel>Обязательные роли</SectionLabel>
        <div style={{border:'1px solid var(--line)',borderRadius:6,overflow:'hidden'}}>
          <BindHeader/>
          {required.map(r=>(
            <BindRow key={r.key} icon={r.icon} label={r.label} role={r.role}
              value={a[r.key]} onChange={v=>upd(r.key,v)} options={opts} required/>
          ))}
        </div>
      </div>
      <div>
        <SectionLabel>Опциональные роли</SectionLabel>
        <div style={{border:'1px solid var(--line)',borderRadius:6,overflow:'hidden'}}>
          <BindHeader/>
          {optional.map(r=>(
            <BindRow key={r.key} label={r.label} role={r.role}
              value={a[r.key]} onChange={v=>upd(r.key,v)} options={opts}/>
          ))}
        </div>
      </div>
      <Hint show={hints}>
        Привязки идентичны схеме <span className="mono">assignmentsSchema</span>.
        ESP32 узлы публикуют список ролей в bridge — выбор канала фиксируется в zone.assignments.
      </Hint>
    </div>
  );
}
function BindHeader(){
  return (
    <div style={{display:'grid',gridTemplateColumns:'170px 200px 1fr 130px',
      padding:'8px 12px',background:'var(--bg-sunken)',
      fontSize:11,color:'var(--text-faint)',textTransform:'uppercase',letterSpacing:'.05em'}}>
      <span>Роль</span><span>Узел</span><span>Канал/комментарий</span><span>Статус</span>
    </div>
  );
}
function BindRow({ icon, label, role, value, onChange, options, required }){
  return (
    <div style={{display:'grid',gridTemplateColumns:'170px 200px 1fr 130px',
      padding:'8px 12px',gap:8,alignItems:'center',borderTop:'1px solid var(--line)'}}>
      <span style={{display:'flex',alignItems:'center',gap:6,fontSize:13}}>
        {icon && <span style={{color:'var(--brand)'}}>{icon}</span>}
        {label}
        {required && <span style={{color:'var(--alert)',marginLeft:2}}>*</span>}
      </span>
      <Select value={String(value??'')} onChange={v=>onChange(v?Number(v):null)} options={options} mono/>
      <span className="mono" style={{fontSize:11,color:'var(--text-faint)'}}>role: {role}</span>
      <span>
        {value
          ? <Chip tone="growth" icon={<Ic.check/>}>привязано</Chip>
          : (required ? <Chip tone="alert">не задано</Chip> : <Chip tone="neutral">опц.</Chip>)}
      </span>
    </div>
  );
}

// ============================================================
// SUB 2 — Water contour
// ============================================================
function RecipeBadge({ recipe }){
  return (
    <div style={{display:'flex',alignItems:'center',gap:10,padding:'8px 12px',
      background:'var(--brand-soft)',border:'1px solid var(--brand)',borderRadius:6,fontSize:12,flexWrap:'wrap'}}>
      <Ic.lock style={{color:'var(--brand)'}}/>
      <span>Из рецепта <b className="mono">{recipe.name} · r{recipe.revisionNumber}</b>:</span>
      <span className="mono">system = {recipe.system||'—'}</span>
      <span style={{color:'var(--text-faint)'}}>·</span>
      <span className="mono">targetPh = {recipe.targetPh ?? '—'}</span>
      <span style={{color:'var(--text-faint)'}}>·</span>
      <span className="mono">targetEc = {recipe.targetEc ?? '—'}</span>
      <span style={{flex:1}}/>
      <span style={{fontSize:11,color:'var(--text-muted)'}}>Изменения — только в шаге «Рецепт».</span>
    </div>
  );
}

function ContourSub({ data, set, hints, recipe }){
  const w = data.waterForm;
  const upd = (k,v)=> set({...data, waterForm:{...w,[k]:v}});
  return (
    <div style={{display:'flex',flexDirection:'column',gap:14}}>
      <PresetSelector waterForm={w}
        onApply={(preset)=>{
          // applyPresetToWaterForm — simplified inline version
          set({...data, waterForm:{
            ...w,
            tanksCount: preset.tanks_count,
            intervalMinutes: Math.round(preset.config.irrigation.interval_sec/60),
            durationSeconds: preset.config.irrigation.duration_sec,
            correctionDuringIrrigation: preset.config.irrigation.correction_during_irrigation,
            irrigationDecisionStrategy: preset.config.irrigation.decision_strategy || 'task',
            startupCleanFillTimeoutSeconds: preset.config.startup?.clean_fill ?? w.startupCleanFillTimeoutSeconds,
            startupSolutionFillTimeoutSeconds: preset.config.startup?.solution_fill ?? w.startupSolutionFillTimeoutSeconds,
            startupPrepareRecirculationTimeoutSeconds: preset.config.startup?.recirculation ?? w.startupPrepareRecirculationTimeoutSeconds,
            correctionMaxEcCorrectionAttempts: preset.config.correction?.max_ec_attempts ?? w.correctionMaxEcCorrectionAttempts,
            correctionMaxPhCorrectionAttempts: preset.config.correction?.max_ph_attempts ?? w.correctionMaxPhCorrectionAttempts,
            correctionStabilizationSec: preset.config.correction?.stabilization_sec ?? w.correctionStabilizationSec,
            _preset: { id: preset.id, name: preset.name, scope: preset.scope,
                       correction_profile: preset.correction_profile,
                       irrigation_system_type: preset.irrigation_system_type, baseline: { ...w } },
          }});
        }}
        onClear={()=> set({...data, waterForm:{...w, _preset:null}})}/>
      <SectionLabel>Топология и баки</SectionLabel>
      <div style={{display:'grid',gridTemplateColumns:'repeat(4,1fr)',gap:10}}>
        <Field label="systemType" required hint="из рецепта">
          <Input value={w.systemType} mono readOnly
            prefix={<Ic.lock style={{color:'var(--text-faint)'}}/>}/>
        </Field>
        <Field label="tanksCount" hint="2…3"><Input value={w.tanksCount} onChange={v=>upd('tanksCount',+v)} mono/></Field>
        <Field label="workingTankL"><Input value={w.workingTankL} onChange={v=>upd('workingTankL',+v)} mono suffix="л"/></Field>
        <Field label="cleanTankFillL"><Input value={w.cleanTankFillL} onChange={v=>upd('cleanTankFillL',+v)} mono suffix="л"/></Field>
        <Field label="nutrientTankTargetL"><Input value={w.nutrientTankTargetL} onChange={v=>upd('nutrientTankTargetL',+v)} mono suffix="л"/></Field>
        <Field label="irrigationBatchL"><Input value={w.irrigationBatchL} onChange={v=>upd('irrigationBatchL',+v)} mono suffix="л"/></Field>
        <Field label="mainPumpFlowLpm"><Input value={w.mainPumpFlowLpm} onChange={v=>upd('mainPumpFlowLpm',+v)} mono suffix="л/мин"/></Field>
        <Field label="cleanWaterFlowLpm"><Input value={w.cleanWaterFlowLpm} onChange={v=>upd('cleanWaterFlowLpm',+v)} mono suffix="л/мин"/></Field>
      </div>

      <SectionLabel>Окно наполнения и температура</SectionLabel>
      <div style={{display:'grid',gridTemplateColumns:'repeat(4,1fr)',gap:10}}>
        <Field label="fillWindowStart"><Input value={w.fillWindowStart} onChange={v=>upd('fillWindowStart',v)} mono/></Field>
        <Field label="fillWindowEnd"><Input value={w.fillWindowEnd} onChange={v=>upd('fillWindowEnd',v)} mono/></Field>
        <Field label="fillTemperatureC"><Input value={w.fillTemperatureC} onChange={v=>upd('fillTemperatureC',+v)} mono suffix="°C"/></Field>
        <Field label="cleanTankFullThreshold"><Input value={w.cleanTankFullThreshold} onChange={v=>upd('cleanTankFullThreshold',+v)} mono suffix="%"/></Field>
        <Field label="refillDurationSeconds"><Input value={w.refillDurationSeconds} onChange={v=>upd('refillDurationSeconds',+v)} mono suffix="с"/></Field>
        <Field label="refillTimeoutSeconds"><Input value={w.refillTimeoutSeconds} onChange={v=>upd('refillTimeoutSeconds',+v)} mono suffix="с"/></Field>
        <Field label="refillRequiredNodeTypes"><Input value={w.refillRequiredNodeTypes} onChange={v=>upd('refillRequiredNodeTypes',v)} mono placeholder="напр. pump,valve"/></Field>
        <Field label="refillPreferredChannel"><Input value={w.refillPreferredChannel} onChange={v=>upd('refillPreferredChannel',v)} mono/></Field>
      </div>

      <SectionLabel>Диагностика и стартовые таймауты</SectionLabel>
      <div style={{display:'grid',gridTemplateColumns:'repeat(4,1fr)',gap:10,alignItems:'center'}}>
        <ToggleField label="diagnosticsEnabled" value={w.diagnosticsEnabled} onChange={v=>upd('diagnosticsEnabled',v)}/>
        <Field label="diagnosticsIntervalMinutes"><Input value={w.diagnosticsIntervalMinutes} onChange={v=>upd('diagnosticsIntervalMinutes',+v)} mono suffix="мин"/></Field>
        <Field label="diagnosticsWorkflow">
          <Select value={w.diagnosticsWorkflow??'cycle_start'} onChange={v=>upd('diagnosticsWorkflow',v)}
            options={['startup','cycle_start','diagnostics']}/>
        </Field>
        <Field label="estopDebounceMs"><Input value={w.estopDebounceMs??0} onChange={v=>upd('estopDebounceMs',+v)} mono suffix="мс"/></Field>
        <Field label="startupCleanFillTimeoutSeconds"><Input value={w.startupCleanFillTimeoutSeconds??0} onChange={v=>upd('startupCleanFillTimeoutSeconds',+v)} mono suffix="с"/></Field>
        <Field label="startupSolutionFillTimeoutSeconds"><Input value={w.startupSolutionFillTimeoutSeconds??0} onChange={v=>upd('startupSolutionFillTimeoutSeconds',+v)} mono suffix="с"/></Field>
        <Field label="startupPrepareRecirculationTimeoutSeconds"><Input value={w.startupPrepareRecirculationTimeoutSeconds??0} onChange={v=>upd('startupPrepareRecirculationTimeoutSeconds',+v)} mono suffix="с"/></Field>
        <Field label="startupCleanFillRetryCycles"><Input value={w.startupCleanFillRetryCycles??0} onChange={v=>upd('startupCleanFillRetryCycles',+v)} mono/></Field>
        <Field label="cleanFillMinCheckDelayMs"><Input value={w.cleanFillMinCheckDelayMs??0} onChange={v=>upd('cleanFillMinCheckDelayMs',+v)} mono suffix="мс"/></Field>
        <Field label="solutionFillCleanMinCheckDelayMs"><Input value={w.solutionFillCleanMinCheckDelayMs??0} onChange={v=>upd('solutionFillCleanMinCheckDelayMs',+v)} mono suffix="мс"/></Field>
        <Field label="solutionFillSolutionMinCheckDelayMs"><Input value={w.solutionFillSolutionMinCheckDelayMs??0} onChange={v=>upd('solutionFillSolutionMinCheckDelayMs',+v)} mono suffix="мс"/></Field>
        <ToggleField label="recirculationStopOnSolutionMin" value={!!w.recirculationStopOnSolutionMin} onChange={v=>upd('recirculationStopOnSolutionMin',v)}/>
        <ToggleField label="stopOnSolutionMin" value={!!w.stopOnSolutionMin} onChange={v=>upd('stopOnSolutionMin',v)}/>
        <ToggleField label="enableDrainControl" value={w.enableDrainControl} onChange={v=>upd('enableDrainControl',v)}/>
        <Field label="drainTargetPercent"><Input value={w.drainTargetPercent} onChange={v=>upd('drainTargetPercent',+v)} mono suffix="%"/></Field>
        <ToggleField label="valveSwitching" value={w.valveSwitching} onChange={v=>upd('valveSwitching',v)}/>
      </div>

      <SectionLabel>Смена раствора</SectionLabel>
      <div style={{display:'grid',gridTemplateColumns:'repeat(4,1fr)',gap:10,alignItems:'center'}}>
        <ToggleField label="solutionChangeEnabled" value={w.solutionChangeEnabled} onChange={v=>upd('solutionChangeEnabled',v)}/>
        <Field label="solutionChangeIntervalMinutes"><Input value={w.solutionChangeIntervalMinutes} onChange={v=>upd('solutionChangeIntervalMinutes',+v)} mono suffix="мин"/></Field>
        <Field label="solutionChangeDurationSeconds"><Input value={w.solutionChangeDurationSeconds} onChange={v=>upd('solutionChangeDurationSeconds',+v)} mono suffix="с"/></Field>
        <Field label="manualIrrigationSeconds" hint="ручной запуск из панели"><Input value={w.manualIrrigationSeconds} onChange={v=>upd('manualIrrigationSeconds',+v)} mono suffix="с"/></Field>
      </div>

      <Hint show={hints}>
        Полный набор полей <span className="mono">waterFormSchema</span>. AE3 валидирует значения через
        zod и пишет в <span className="mono">automation_configs/zone/{'{id}'}/zone.water</span>.
      </Hint>
    </div>
  );
}

// ============================================================
// SUB 3 — Irrigation
// ============================================================
function IrrigationSub({ data, set, hints }){
  const w = data.waterForm;
  const upd = (k,v)=> set({...data, waterForm:{...w,[k]:v}});
  const smart = w.irrigationDecisionStrategy==='smart_soil_v1';
  return (
    <div style={{display:'flex',flexDirection:'column',gap:14}}>
      <SectionLabel right={
        <div style={{display:'flex',gap:6}}>
          <Btn size="sm" variant={!smart?'primary':'secondary'} onClick={()=>upd('irrigationDecisionStrategy','task')}>По времени</Btn>
          <Btn size="sm" variant={smart?'primary':'secondary'} onClick={()=>upd('irrigationDecisionStrategy','smart_soil_v1')}>SMART soil v1</Btn>
        </div>
      }>Стратегия и расписание</SectionLabel>
      <div style={{display:'grid',gridTemplateColumns:'repeat(4,1fr)',gap:10}}>
        <Field label="intervalMinutes" required><Input value={w.intervalMinutes} onChange={v=>upd('intervalMinutes',+v)} mono suffix="мин"/></Field>
        <Field label="durationSeconds" required><Input value={w.durationSeconds} onChange={v=>upd('durationSeconds',+v)} mono suffix="с"/></Field>
        <ToggleField label="correctionDuringIrrigation" value={w.correctionDuringIrrigation} onChange={v=>upd('correctionDuringIrrigation',v)}/>
        <ToggleField label="irrigationAutoReplayAfterSetup" value={!!w.irrigationAutoReplayAfterSetup} onChange={v=>upd('irrigationAutoReplayAfterSetup',v)}/>
      </div>

      {smart && (
        <>
          <SectionLabel>SMART soil v1 — параметры решения</SectionLabel>
          <div style={{display:'grid',gridTemplateColumns:'repeat(4,1fr)',gap:10}}>
            <Field label="irrigationDecisionLookbackSeconds"><Input value={w.irrigationDecisionLookbackSeconds??0} onChange={v=>upd('irrigationDecisionLookbackSeconds',+v)} mono suffix="с"/></Field>
            <Field label="irrigationDecisionMinSamples"><Input value={w.irrigationDecisionMinSamples??0} onChange={v=>upd('irrigationDecisionMinSamples',+v)} mono/></Field>
            <Field label="irrigationDecisionStaleAfterSeconds"><Input value={w.irrigationDecisionStaleAfterSeconds??0} onChange={v=>upd('irrigationDecisionStaleAfterSeconds',+v)} mono suffix="с"/></Field>
            <Field label="irrigationDecisionHysteresisPct"><Input value={w.irrigationDecisionHysteresisPct??0} onChange={v=>upd('irrigationDecisionHysteresisPct',+v)} mono suffix="%"/></Field>
            <Field label="irrigationDecisionSpreadAlertThresholdPct"><Input value={w.irrigationDecisionSpreadAlertThresholdPct??0} onChange={v=>upd('irrigationDecisionSpreadAlertThresholdPct',+v)} mono suffix="%"/></Field>
          </div>
        </>
      )}

      <SectionLabel>Recovery / повторы</SectionLabel>
      <div style={{display:'grid',gridTemplateColumns:'repeat(4,1fr)',gap:10}}>
        <Field label="irrigationRecoveryMaxContinueAttempts"><Input value={w.irrigationRecoveryMaxContinueAttempts??0} onChange={v=>upd('irrigationRecoveryMaxContinueAttempts',+v)} mono/></Field>
        <Field label="irrigationRecoveryTimeoutSeconds"><Input value={w.irrigationRecoveryTimeoutSeconds??0} onChange={v=>upd('irrigationRecoveryTimeoutSeconds',+v)} mono suffix="с"/></Field>
        <Field label="irrigationMaxSetupReplays"><Input value={w.irrigationMaxSetupReplays??0} onChange={v=>upd('irrigationMaxSetupReplays',+v)} mono/></Field>
      </div>

      <Hint show={hints}>
        SMART soil v1 принимает решение о поливе по выборке датчиков влажности. Без сенсора —
        используйте <span className="mono">task</span> (по времени).
      </Hint>
    </div>
  );
}

// ============================================================
// SUB 4 — Correction targets
// ============================================================
const CORRECTION_PRESETS = {
  safe: {
    label:'Мягкий',
    desc:'Большой deadband, маленькая доза, длинный кулдаун. Минимум вмешательства, но медленная стабилизация.',
    config: {
      correctionDeadbandPh:0.3, correctionDeadbandEc:0.25,
      correctionStepPhMl:1.0, correctionStepEcMl:3.0,
      correctionMaxDosePhMl:5.0, correctionMaxDoseEcMl:15.0,
      correctionMaxStepsPerWindow:4,
      correctionStepIntervalSec:120, correctionCooldownSec:600,
      correctionRecirculationBeforeDoseSec:45,
      correctionStabilizationSec:60,
      correctionMaxPhCorrectionAttempts:3, correctionMaxEcCorrectionAttempts:3,
      phPct:8, ecPct:8,
    },
  },
  balanced: {
    label:'Оптимальный',
    desc:'Сбалансированный профиль для большинства культур. Стандарт.',
    config: {
      correctionDeadbandPh:0.2, correctionDeadbandEc:0.15,
      correctionStepPhMl:2.0, correctionStepEcMl:5.0,
      correctionMaxDosePhMl:8.0, correctionMaxDoseEcMl:25.0,
      correctionMaxStepsPerWindow:6,
      correctionStepIntervalSec:90, correctionCooldownSec:300,
      correctionRecirculationBeforeDoseSec:30,
      correctionStabilizationSec:45,
      correctionMaxPhCorrectionAttempts:5, correctionMaxEcCorrectionAttempts:5,
      phPct:5, ecPct:5,
    },
  },
  aggressive: {
    label:'Агрессивный',
    desc:'Малый deadband, крупные дозы, короткий кулдаун. Быстро держит цель, но риск перелива.',
    config: {
      correctionDeadbandPh:0.1, correctionDeadbandEc:0.08,
      correctionStepPhMl:3.0, correctionStepEcMl:8.0,
      correctionMaxDosePhMl:12.0, correctionMaxDoseEcMl:40.0,
      correctionMaxStepsPerWindow:10,
      correctionStepIntervalSec:60, correctionCooldownSec:180,
      correctionRecirculationBeforeDoseSec:20,
      correctionStabilizationSec:30,
      correctionMaxPhCorrectionAttempts:8, correctionMaxEcCorrectionAttempts:8,
      phPct:3, ecPct:3,
    },
  },
  test: {
    label:'Тестовый',
    desc:'Малая доза, длинный stabilization. Для отладки PID и калибровки.',
    config: {
      correctionDeadbandPh:0.15, correctionDeadbandEc:0.10,
      correctionStepPhMl:0.5, correctionStepEcMl:1.0,
      correctionMaxDosePhMl:2.0, correctionMaxDoseEcMl:5.0,
      correctionMaxStepsPerWindow:3,
      correctionStepIntervalSec:180, correctionCooldownSec:900,
      correctionRecirculationBeforeDoseSec:60,
      correctionStabilizationSec:120,
      correctionMaxPhCorrectionAttempts:2, correctionMaxEcCorrectionAttempts:2,
      phPct:5, ecPct:5,
    },
  },
};
const CP_TONES = { safe:'growth', balanced:'brand', aggressive:'warn', test:'neutral' };

function CorrectionTargetsSub({ data, set, hints, recipe }){
  const w = data.waterForm;
  const upd = (k,v)=> set({...data, waterForm:{...w,[k]:v}});
  const applyPreset = (key) => {
    const p = CORRECTION_PRESETS[key];
    if (!p) return;
    set({...data, waterForm:{...w, ...p.config, correctionProfile:key}});
  };
  const cur = CORRECTION_PRESETS[w.correctionProfile];
  // detect if user tweaked preset
  const isModified = cur && Object.entries(cur.config).some(([k,v])=> w[k]!==v);

  return (
    <div style={{display:'flex',flexDirection:'column',gap:14}}>

      {/* ── Preset chooser ── */}
      <div style={{padding:12,border:'1px solid var(--brand)',borderRadius:6,
        background:'var(--brand-soft)',display:'flex',flexDirection:'column',gap:10}}>
        <div style={{display:'flex',alignItems:'center',gap:10,flexWrap:'wrap'}}>
          <Ic.bookmark style={{color:'var(--brand)'}}/>
          <span style={{fontSize:12,fontWeight:600,color:'var(--brand-ink)'}}>Профиль коррекции</span>
          {isModified && <Chip tone="warn">изменено</Chip>}
        </div>
        <div style={{display:'flex',gap:6,flexWrap:'wrap'}}>
          {Object.entries(CORRECTION_PRESETS).map(([k,p])=>{
            const active = w.correctionProfile===k;
            return (
              <button key={k} onClick={()=>applyPreset(k)}
                style={{padding:'8px 12px',border:`1px solid ${active?'var(--brand)':'var(--line)'}`,
                  borderRadius:4,background:active?'var(--brand)':'var(--bg-panel)',
                  color:active?'#fff':'var(--text)',fontSize:12,fontWeight:active?600:400,
                  cursor:'pointer',display:'flex',flexDirection:'column',alignItems:'flex-start',
                  gap:2,minWidth:120,textAlign:'left'}}>
                <span style={{fontWeight:600}}>{p.label}</span>
                <span style={{fontSize:10,opacity:.75,fontFamily:'var(--mono)'}}>
                  ±{p.config.correctionDeadbandPh}pH · {p.config.correctionStepPhMl}мл
                </span>
              </button>
            );
          })}
        </div>
        {cur && (
          <div style={{fontSize:11,color:'var(--text-muted)',lineHeight:1.5,
            padding:'8px 10px',background:'var(--bg-panel)',
            border:'1px solid var(--line)',borderRadius:4}}>
            {cur.desc}
          </div>
        )}
      </div>

      <SectionLabel>Целевые значения <span style={{fontSize:10,color:'var(--brand)',marginLeft:8,textTransform:'none',letterSpacing:0}}>← из рецепта, read-only</span></SectionLabel>
      <div style={{display:'grid',gridTemplateColumns:'repeat(4,1fr)',gap:10}}>
        <Field label="targetPh" required hint="из рецепта">
          <Input value={w.targetPh} mono readOnly prefix={<Ic.lock style={{color:'var(--text-faint)'}}/>}/>
        </Field>
        <Field label="targetEc" required hint="из рецепта">
          <Input value={w.targetEc} mono readOnly suffix="mS/cm" prefix={<Ic.lock style={{color:'var(--text-faint)'}}/>}/>
        </Field>
        <Field label="phPct" hint="допуск"><Input value={w.phPct} onChange={v=>upd('phPct',+v)} mono suffix="%"/></Field>
        <Field label="ecPct" hint="допуск"><Input value={w.ecPct} onChange={v=>upd('ecPct',+v)} mono suffix="%"/></Field>
      </div>

      <SectionLabel>Deadband и шаг дозы</SectionLabel>
      <div style={{display:'grid',gridTemplateColumns:'repeat(4,1fr)',gap:10}}>
        <Field label="deadbandPh" hint="мёртвая зона"><Input value={w.correctionDeadbandPh} onChange={v=>upd('correctionDeadbandPh',+v)} mono suffix="pH"/></Field>
        <Field label="deadbandEc" hint="мёртвая зона"><Input value={w.correctionDeadbandEc} onChange={v=>upd('correctionDeadbandEc',+v)} mono suffix="mS/cm"/></Field>
        <Field label="stepPhMl" hint="доза за шаг"><Input value={w.correctionStepPhMl} onChange={v=>upd('correctionStepPhMl',+v)} mono suffix="мл"/></Field>
        <Field label="stepEcMl" hint="доза за шаг"><Input value={w.correctionStepEcMl} onChange={v=>upd('correctionStepEcMl',+v)} mono suffix="мл"/></Field>
        <Field label="maxDosePhMl" hint="за окно"><Input value={w.correctionMaxDosePhMl} onChange={v=>upd('correctionMaxDosePhMl',+v)} mono suffix="мл"/></Field>
        <Field label="maxDoseEcMl" hint="за окно"><Input value={w.correctionMaxDoseEcMl} onChange={v=>upd('correctionMaxDoseEcMl',+v)} mono suffix="мл"/></Field>
        <Field label="maxStepsPerWindow"><Input value={w.correctionMaxStepsPerWindow} onChange={v=>upd('correctionMaxStepsPerWindow',+v)} mono/></Field>
        <Field label="stepInterval"><Input value={w.correctionStepIntervalSec} onChange={v=>upd('correctionStepIntervalSec',+v)} mono suffix="с"/></Field>
      </div>

      <SectionLabel>Тайминги и источники</SectionLabel>
      <div style={{display:'grid',gridTemplateColumns:'repeat(4,1fr)',gap:10}}>
        <Field label="cooldown" hint="между окнами"><Input value={w.correctionCooldownSec} onChange={v=>upd('correctionCooldownSec',+v)} mono suffix="с"/></Field>
        <Field label="recircBeforeDose"><Input value={w.correctionRecirculationBeforeDoseSec} onChange={v=>upd('correctionRecirculationBeforeDoseSec',+v)} mono suffix="с"/></Field>
        <Field label="stabilizationSec"><Input value={w.correctionStabilizationSec??0} onChange={v=>upd('correctionStabilizationSec',+v)} mono suffix="с"/></Field>
        <Field label="phDirection">
          <Select value={w.correctionPhDirection} onChange={v=>upd('correctionPhDirection',v)}
            options={['auto','down','up']}/>
        </Field>
        <Field label="ecSource" hint="как добавлять EC">
          <Select value={w.correctionEcSource} onChange={v=>upd('correctionEcSource',v)}
            options={['mix_ab','a_only','a_then_b']}/>
        </Field>
      </div>

      <SectionLabel>Лимиты попыток</SectionLabel>
      <div style={{display:'grid',gridTemplateColumns:'repeat(4,1fr)',gap:10}}>
        <Field label="maxEcAttempts"><Input value={w.correctionMaxEcCorrectionAttempts??0} onChange={v=>upd('correctionMaxEcCorrectionAttempts',+v)} mono/></Field>
        <Field label="maxPhAttempts"><Input value={w.correctionMaxPhCorrectionAttempts??0} onChange={v=>upd('correctionMaxPhCorrectionAttempts',+v)} mono/></Field>
        <Field label="prepareRecirculationMaxAttempts"><Input value={w.correctionPrepareRecirculationMaxAttempts??0} onChange={v=>upd('correctionPrepareRecirculationMaxAttempts',+v)} mono/></Field>
        <Field label="prepareRecircMaxCorrAttempts"><Input value={w.correctionPrepareRecirculationMaxCorrectionAttempts??0} onChange={v=>upd('correctionPrepareRecirculationMaxCorrectionAttempts',+v)} mono/></Field>
      </div>

      <SectionLabel>Гистерезис и фильтрация</SectionLabel>
      <div style={{display:'grid',gridTemplateColumns:'repeat(4,1fr)',gap:10}}>
        <Field label="errorEnter" hint="вход в окно коррекции"><Input value={w.correctionErrorEnter??0.05} onChange={v=>upd('correctionErrorEnter',+v)} mono suffix="pH/EC"/></Field>
        <Field label="errorExit"  hint="выход в норму"><Input value={w.correctionErrorExit??0.02} onChange={v=>upd('correctionErrorExit',+v)} mono suffix="pH/EC"/></Field>
        <Field label="emaWindowSec" hint="сглаживание сенсора"><Input value={w.correctionEmaWindowSec??30} onChange={v=>upd('correctionEmaWindowSec',+v)} mono suffix="с"/></Field>
        <Field label="confirmReadings" hint="подряд для триггера"><Input value={w.correctionConfirmReadings??3} onChange={v=>upd('correctionConfirmReadings',+v)} mono/></Field>
        <Field label="outlierGuard" hint="отброс выбросов">
          <Select value={String(w.correctionOutlierGuard??'mad_3')} onChange={v=>upd('correctionOutlierGuard',v)}
            options={[{value:'off',label:'off · откл.'},{value:'mad_2',label:'mad_2 · σ×2'},
                     {value:'mad_3',label:'mad_3 · σ×3'},{value:'iqr',label:'iqr · межкварт.'}]}/>
        </Field>
        <Field label="sensorAgeMaxSec" hint="устар. данные"><Input value={w.correctionSensorAgeMaxSec??60} onChange={v=>upd('correctionSensorAgeMaxSec',+v)} mono suffix="с"/></Field>
        <Field label="rateLimitPhPerMin" hint="макс. дрейф"><Input value={w.correctionRateLimitPhPerMin??0.4} onChange={v=>upd('correctionRateLimitPhPerMin',+v)} mono suffix="pH/мин"/></Field>
        <Field label="rateLimitEcPerMin"><Input value={w.correctionRateLimitEcPerMin??0.3} onChange={v=>upd('correctionRateLimitEcPerMin',+v)} mono suffix="mS/мин"/></Field>
      </div>

      <SectionLabel>Аварийные стопы и блокировки</SectionLabel>
      <div style={{display:'grid',gridTemplateColumns:'repeat(4,1fr)',gap:10}}>
        <Field label="phHardMin" hint="kill-switch"><Input value={w.correctionPhHardMin??4.5} onChange={v=>upd('correctionPhHardMin',+v)} mono suffix="pH"/></Field>
        <Field label="phHardMax"><Input value={w.correctionPhHardMax??7.5} onChange={v=>upd('correctionPhHardMax',+v)} mono suffix="pH"/></Field>
        <Field label="ecHardMax"><Input value={w.correctionEcHardMax??3.5} onChange={v=>upd('correctionEcHardMax',+v)} mono suffix="mS/cm"/></Field>
        <Field label="tempHardMaxC" hint="блок. дозирования"><Input value={w.correctionTempHardMaxC??32} onChange={v=>upd('correctionTempHardMaxC',+v)} mono suffix="°C"/></Field>
        <Field label="lockoutAfterFailMin"><Input value={w.correctionLockoutAfterFailMin??15} onChange={v=>upd('correctionLockoutAfterFailMin',+v)} mono suffix="мин"/></Field>
        <Field label="lockoutOnSensorLossMin"><Input value={w.correctionLockoutOnSensorLossMin??10} onChange={v=>upd('correctionLockoutOnSensorLossMin',+v)} mono suffix="мин"/></Field>
        <Field label="emergencyDrainOnEcSpike">
          <ToggleField inline value={w.correctionEmergencyDrainOnEcSpike??false} onChange={v=>upd('correctionEmergencyDrainOnEcSpike',v)}/>
        </Field>
        <Field label="alertOnAttemptsExhaust">
          <ToggleField inline value={w.correctionAlertOnAttemptsExhaust??true} onChange={v=>upd('correctionAlertOnAttemptsExhaust',v)}/>
        </Field>
      </div>

      <SectionLabel>Восстановление и расписание</SectionLabel>
      <div style={{display:'grid',gridTemplateColumns:'repeat(4,1fr)',gap:10}}>
        <Field label="recoveryStrategy" hint="после провала">
          <Select value={String(w.correctionRecoveryStrategy??'hold_and_alert')} onChange={v=>upd('correctionRecoveryStrategy',v)}
            options={[{value:'hold_and_alert',label:'hold_and_alert · удержать + алерт'},
                     {value:'flush_and_retry',label:'flush_and_retry · промыть и повторить'},
                     {value:'pause_irrig',label:'pause_irrig · отключить полив'},
                     {value:'manual_only',label:'manual_only · только вручную'}]}/>
        </Field>
        <Field label="retryBackoffMin"><Input value={w.correctionRetryBackoffMin??20} onChange={v=>upd('correctionRetryBackoffMin',+v)} mono suffix="мин"/></Field>
        <Field label="quietHoursStart" hint="не дозировать ночью"><Input value={w.correctionQuietHoursStart??'23:00'} onChange={v=>upd('correctionQuietHoursStart',v)} mono/></Field>
        <Field label="quietHoursEnd"><Input value={w.correctionQuietHoursEnd??'05:00'} onChange={v=>upd('correctionQuietHoursEnd',v)} mono/></Field>
        <Field label="duringIrrigationOnly">
          <ToggleField inline value={w.correctionDuringIrrigationOnly??false} onChange={v=>upd('correctionDuringIrrigationOnly',v)}/>
        </Field>
        <Field label="postIrrigDelaySec" hint="ожидание после полива"><Input value={w.correctionPostIrrigDelaySec??60} onChange={v=>upd('correctionPostIrrigDelaySec',+v)} mono suffix="с"/></Field>
        <Field label="dryRunMode" hint="без дозирования">
          <ToggleField inline value={w.correctionDryRunMode??false} onChange={v=>upd('correctionDryRunMode',v)}/>
        </Field>
        <Field label="logVerbosity">
          <Select value={String(w.correctionLogVerbosity??'normal')} onChange={v=>upd('correctionLogVerbosity',v)}
            options={['quiet','normal','verbose','trace']}/>
        </Field>
      </div>

      <SectionLabel>Зонные authority / PID overrides</SectionLabel>
      <div style={{border:'1px solid var(--line)',borderRadius:6,overflow:'hidden'}}>
        <div style={{display:'grid',gridTemplateColumns:'1fr 90px 90px 90px 90px 90px',
          padding:'8px 10px',background:'var(--bg-sunken)',fontSize:10,
          textTransform:'uppercase',letterSpacing:0.4,color:'var(--text-faint)'}}>
          <span>контур</span><span>authority</span><span>kP</span><span>kI</span><span>kD</span><span>scale</span>
        </div>
        {[
          {k:'ph', label:'pH-коррекция'},
          {k:'ec', label:'EC-коррекция'},
          {k:'temp', label:'Температура раствора'},
          {k:'do', label:'Растворённый O₂'},
        ].map(row=>{
          const o = (w.correctionZoneOverrides||{})[row.k] || {};
          const set2 = (k2,v)=> upd('correctionZoneOverrides',{
            ...(w.correctionZoneOverrides||{}),
            [row.k]:{...o,[k2]:v}
          });
          return (
            <div key={row.k} style={{display:'grid',gridTemplateColumns:'1fr 90px 90px 90px 90px 90px',
              padding:'8px 10px',borderTop:'1px solid var(--line)',alignItems:'center',
              fontSize:12}}>
              <span>{row.label}</span>
              <Input value={o.authority??''} onChange={v=>set2('authority',v)} mono placeholder="—"/>
              <Input value={o.kP??''} onChange={v=>set2('kP',+v||null)} mono placeholder="—"/>
              <Input value={o.kI??''} onChange={v=>set2('kI',+v||null)} mono placeholder="—"/>
              <Input value={o.kD??''} onChange={v=>set2('kD',+v||null)} mono placeholder="—"/>
              <Input value={o.scale??''} onChange={v=>set2('scale',+v||null)} mono placeholder="1.0"/>
            </div>
          );
        })}
      </div>

      <Hint show={hints}>
        Профиль задаёт стратегию в один клик. После — донастройте поля вручную (появится метка
        <span className="mono"> изменено</span>). Поля ниже — гистерезис, аварийные стопы, recovery,
        пер-контурные overrides. Базовые authority/PID живут в шаге Калибровка.
      </Hint>
    </div>
  );
}

// ============================================================
// SUB 5 — Lighting
// ============================================================
function LightingSub({ data, set, hints }){
  const l = data.lightingForm;
  const upd = (k,v)=> set({...data, lightingForm:{...l,[k]:v}});
  return (
    <div style={{display:'flex',flexDirection:'column',gap:14}}>
      <SectionLabel right={
        <ToggleField inline label="enabled" value={l.enabled} onChange={v=>upd('enabled',v)}/>
      }>Освещение</SectionLabel>
      <div style={{display:'grid',gridTemplateColumns:'repeat(4,1fr)',gap:10,opacity:l.enabled?1:0.55}}>
        <Field label="luxDay"><Input value={l.luxDay} onChange={v=>upd('luxDay',+v)} mono suffix="lux" disabled={!l.enabled}/></Field>
        <Field label="luxNight"><Input value={l.luxNight} onChange={v=>upd('luxNight',+v)} mono suffix="lux" disabled={!l.enabled}/></Field>
        <Field label="hoursOn"><Input value={l.hoursOn} onChange={v=>upd('hoursOn',+v)} mono suffix="ч" disabled={!l.enabled}/></Field>
        <Field label="intervalMinutes"><Input value={l.intervalMinutes} onChange={v=>upd('intervalMinutes',+v)} mono suffix="мин" disabled={!l.enabled}/></Field>
        <Field label="scheduleStart"><Input value={l.scheduleStart} onChange={v=>upd('scheduleStart',v)} mono disabled={!l.enabled}/></Field>
        <Field label="scheduleEnd"><Input value={l.scheduleEnd} onChange={v=>upd('scheduleEnd',v)} mono disabled={!l.enabled}/></Field>
        <Field label="manualIntensity"><Input value={l.manualIntensity} onChange={v=>upd('manualIntensity',+v)} mono suffix="%" disabled={!l.enabled}/></Field>
        <Field label="manualDurationHours"><Input value={l.manualDurationHours} onChange={v=>upd('manualDurationHours',+v)} mono suffix="ч" disabled={!l.enabled}/></Field>
      </div>
      <DayNightStrip start={l.scheduleStart} end={l.scheduleEnd} luxDay={l.luxDay} luxNight={l.luxNight} enabled={l.enabled}/>
      <Hint show={hints}>
        Если свет выключен на этом этапе — поле <span className="mono">light</span> в assignments
        можно оставить пустым; readiness не блокирует запуск.
      </Hint>
    </div>
  );
}

function DayNightStrip({ start='06:00', end='18:00', luxDay, luxNight, enabled }){
  const [sH,sM] = start.split(':').map(Number);
  const [eH,eM] = end.split(':').map(Number);
  const sPct = ((sH*60+sM)/1440)*100;
  const ePct = ((eH*60+eM)/1440)*100;
  return (
    <div style={{border:'1px solid var(--line)',borderRadius:6,padding:10,
      background:'var(--bg-sunken)',opacity:enabled?1:0.55}}>
      <div style={{position:'relative',height:28,borderRadius:4,overflow:'hidden',
        background:'linear-gradient(90deg, #1a2832 0%, #1a2832 100%)'}}>
        <div style={{position:'absolute',left:`${sPct}%`,width:`${ePct-sPct}%`,top:0,bottom:0,
          background:'linear-gradient(180deg, #f5d97a, #e8a93c)'}}/>
        <div style={{position:'absolute',left:`${sPct}%`,top:0,bottom:0,width:1,background:'#fff',opacity:.6}}/>
        <div style={{position:'absolute',left:`${ePct}%`,top:0,bottom:0,width:1,background:'#fff',opacity:.6}}/>
        {[0,6,12,18,24].map(h=>(
          <div key={h} style={{position:'absolute',left:`${(h/24)*100}%`,top:0,bottom:0,
            width:1,background:'rgba(255,255,255,.08)'}}/>
        ))}
      </div>
      <div style={{display:'flex',justifyContent:'space-between',marginTop:6,
        fontFamily:'var(--mono)',fontSize:10,color:'var(--text-faint)'}}>
        <span>00:00</span><span>06:00</span><span>12:00</span><span>18:00</span><span>24:00</span>
      </div>
      <div style={{display:'flex',gap:14,marginTop:6,fontSize:11,color:'var(--text-muted)'}}>
        <span>День: <span className="mono">{start}–{end}</span> · {luxDay} lux</span>
        <span>Ночь: <span className="mono">{luxNight}</span> lux</span>
      </div>
    </div>
  );
}

// ============================================================
// SUB 6 — Climate
// ============================================================
function ClimateSub({ data, set, hints }){
  const c = data.zoneClimateForm;
  const a = data.assignments;
  const upd = (k,v)=> set({...data, zoneClimateForm:{...c,[k]:v}});
  return (
    <div style={{display:'flex',flexDirection:'column',gap:14}}>
      <SectionLabel right={<ToggleField inline label="enabled" value={c.enabled} onChange={v=>upd('enabled',v)}/>}>
        Климат зоны
      </SectionLabel>
      <div style={{opacity:c.enabled?1:0.55,display:'grid',gridTemplateColumns:'1fr 1fr',gap:10}}>
        <Card title="CO₂" pad={true}>
          <KV rows={[
            ['co2_sensor', a.co2_sensor?`Node ${a.co2_sensor}`:'не задано'],
            ['co2_actuator', a.co2_actuator?`Node ${a.co2_actuator}`:'не задано'],
            ['target ppm', '900'],
            ['hysteresis', '±50'],
          ]}/>
        </Card>
        <Card title="Корневая вентиляция" pad={true}>
          <KV rows={[
            ['root_vent_actuator', a.root_vent_actuator?`Node ${a.root_vent_actuator}`:'не задано'],
            ['включение', '> 26°C subroot'],
            ['длительность', '5 мин'],
            ['cooldown', '15 мин'],
          ]}/>
        </Card>
      </div>
      <Hint show={hints}>
        Климатический контур опционален. Привязки задаются в <b>Привязках узлов</b>;
        целевые ppm и пороги — в <span className="mono">automation_configs/zone.climate</span>.
      </Hint>
    </div>
  );
}

// ============================================================
// Helpers
// ============================================================
function SectionLabel({ children, right }){
  return (
    <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',
      gap:8,paddingBottom:4,borderBottom:'1px dashed var(--line)'}}>
      <div style={{fontSize:11,letterSpacing:'.08em',textTransform:'uppercase',
        fontWeight:700,color:'var(--text-faint)'}}>{children}</div>
      {right}
    </div>
  );
}

function ToggleField({ label, value, onChange, inline }){
  return (
    <label style={{display:'flex',alignItems:'center',gap:8,
      padding: inline?0:'0 0',height: inline?'auto':'var(--input-h)',
      fontSize:12,color:'var(--text-muted)',cursor:'default'}}>
      <button type="button" onClick={()=>onChange(!value)} aria-pressed={value} style={{
        width:30,height:18,borderRadius:999,
        background: value?'var(--brand)':'var(--line-strong)',
        position:'relative',border:0,cursor:'default',padding:0,
        transition:'background .15s'
      }}>
        <span style={{position:'absolute',top:2,left: value?14:2,width:14,height:14,
          background:'#fff',borderRadius:'50%',transition:'left .15s',
          boxShadow:'0 1px 2px rgba(0,0,0,.2)'}}/>
      </button>
      <span className="mono" style={{fontSize:11}}>{label}</span>
    </label>
  );
}

Object.assign(window, { Step3AutomationHub });
