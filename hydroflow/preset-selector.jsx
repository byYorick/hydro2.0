// PresetSelector — based on AutomationForms/PresetSelector.vue
// Filters presets by waterForm.systemType and tanksCount; emits onApply / onClear.

const SYSTEM_MAP = {
  drip: ['drip_tape','drip_emitter'],
  substrate_trays: ['dwc','ebb_flow','aeroponics'],
  nft: ['nft'],
};

const PRESETS = [
  { id:1, scope:'system', name:'NFT · Salad Mix · Balanced',
    irrigation_system_type:'nft', tanks_count:2, correction_profile:'balanced',
    description:'Базовый NFT-профиль для зелени. Полив каждые 15 минут, мягкая коррекция.',
    config:{ irrigation:{ interval_sec:900, duration_sec:60, correction_during_irrigation:false, decision_strategy:'task' },
             startup:{ clean_fill:600, solution_fill:600, recirculation:300 },
             correction:{ max_ec_attempts:5, max_ph_attempts:5, stabilization_sec:45 } } },
  { id:2, scope:'system', name:'NFT · Tomato · Aggressive',
    irrigation_system_type:'nft', tanks_count:2, correction_profile:'aggressive',
    description:'Для томатов на NFT. Полив каждые 10 минут, активная коррекция при поливе.',
    config:{ irrigation:{ interval_sec:600, duration_sec:90, correction_during_irrigation:true, decision_strategy:'task' },
             startup:{ clean_fill:600, solution_fill:600, recirculation:300 },
             correction:{ max_ec_attempts:8, max_ph_attempts:8, stabilization_sec:30 } } },
  { id:3, scope:'system', name:'DWC · Lettuce · Safe',
    irrigation_system_type:'dwc', tanks_count:2, correction_profile:'safe',
    description:'DWC для салата. Минимум вмешательства, длинные интервалы.',
    config:{ irrigation:{ interval_sec:1800, duration_sec:120, correction_during_irrigation:false, decision_strategy:'task' },
             startup:{ clean_fill:900, solution_fill:900, recirculation:300 },
             correction:{ max_ec_attempts:3, max_ph_attempts:3, stabilization_sec:60 } } },
  { id:4, scope:'system', name:'Drip · Strawberry · Balanced',
    irrigation_system_type:'drip_tape', tanks_count:2, correction_profile:'balanced',
    description:'Капельный полив для клубники.',
    config:{ irrigation:{ interval_sec:1800, duration_sec:120, correction_during_irrigation:false, decision_strategy:'smart_soil_v1' },
             startup:{ clean_fill:600, solution_fill:600, recirculation:300 },
             correction:{ max_ec_attempts:5, max_ph_attempts:5, stabilization_sec:45 } } },
  { id:5, scope:'system', name:'Ebb & Flow · Universal · Test',
    irrigation_system_type:'ebb_flow', tanks_count:2, correction_profile:'test',
    description:'Тестовый профиль для отладки систем приливов.',
    config:{ irrigation:{ interval_sec:1200, duration_sec:180, correction_during_irrigation:false, decision_strategy:'task' },
             startup:{ clean_fill:600, solution_fill:600, recirculation:300 },
             correction:{ max_ec_attempts:5, max_ph_attempts:5, stabilization_sec:45 } } },
  { id:101, scope:'custom', name:'Мой Tomato r3 · копия',
    irrigation_system_type:'nft', tanks_count:2, correction_profile:'balanced',
    description:'Сохранённый из Zone-A 2026-02-14.',
    config:{ irrigation:{ interval_sec:600, duration_sec:120, correction_during_irrigation:true, decision_strategy:'task' },
             startup:{ clean_fill:480, solution_fill:480, recirculation:240 },
             correction:{ max_ec_attempts:6, max_ph_attempts:6, stabilization_sec:35 } } },
];

const PROFILE_LABELS = { safe:'Мягкий', balanced:'Оптимальный', aggressive:'Агрессивный', test:'Тестовый' };
const PROFILE_TONES  = { safe:'growth', balanced:'brand', aggressive:'warn', test:'neutral' };

function PresetSelector({ waterForm, onApply, onClear }){
  const compat = SYSTEM_MAP[waterForm.systemType] || [];
  const filtered = PRESETS.filter(p =>
    p.tanks_count === waterForm.tanksCount &&
    (compat.length===0 || compat.includes(p.irrigation_system_type))
  );
  const system = filtered.filter(p=>p.scope==='system');
  const custom = filtered.filter(p=>p.scope==='custom');
  const current = waterForm._preset;
  const isModified = current && (
    current.baseline?.intervalMinutes !== waterForm.intervalMinutes ||
    current.baseline?.durationSeconds !== waterForm.durationSeconds ||
    current.baseline?.correctionDuringIrrigation !== waterForm.correctionDuringIrrigation ||
    current.baseline?.tanksCount !== waterForm.tanksCount
  );

  const onChange = (e) => {
    const v = e.target.value;
    if (!v) return onClear();
    const p = PRESETS.find(x => x.id === Number(v));
    if (p) onApply(p);
  };

  return (
    <div style={{padding:12,border:'1px solid var(--brand)',borderRadius:6,
      background:'var(--brand-soft)',display:'flex',flexDirection:'column',gap:10}}>
      <div style={{display:'flex',alignItems:'center',gap:10,flexWrap:'wrap'}}>
        <Ic.bookmark style={{color:'var(--brand)'}}/>
        <span style={{fontSize:12,fontWeight:600,color:'var(--brand-ink)'}}>Профиль автоматики (preset)</span>
        <select value={current?.id ?? ''} onChange={onChange}
          style={{padding:'6px 8px',border:'1px solid var(--line-strong)',borderRadius:4,
            background:'var(--bg-panel)',color:'var(--text)',fontSize:12,minWidth:340,
            fontFamily:'var(--mono)'}}>
          <option value="">— Настроить с нуля —</option>
          {system.length>0 && (
            <optgroup label="Системные">
              {system.map(p=>(
                <option key={p.id} value={p.id}>
                  {p.name} · {Math.round(p.config.irrigation.interval_sec/60)}мин/{p.config.irrigation.duration_sec}с
                </option>
              ))}
            </optgroup>
          )}
          {custom.length>0 && (
            <optgroup label="Мои профили">
              {custom.map(p=>(<option key={p.id} value={p.id}>{p.name}</option>))}
            </optgroup>
          )}
        </select>
        {isModified && <Chip tone="warn">изменено</Chip>}
        {filtered.length===0 && (
          <span style={{fontSize:11,color:'var(--text-muted)'}}>
            Нет совместимых: <span className="mono">{waterForm.systemType}</span> · <span className="mono">{waterForm.tanksCount} бак(ов)</span>
          </span>
        )}
      </div>

      {current ? (
        <div style={{display:'flex',flexDirection:'column',gap:6,padding:'8px 10px',
          background:'var(--bg-panel)',border:'1px solid var(--line)',borderRadius:4}}>
          <div style={{fontSize:11,color:'var(--text-muted)',lineHeight:1.5}}>
            {PRESETS.find(p=>p.id===current.id)?.description}
          </div>
          <div style={{display:'flex',gap:6,flexWrap:'wrap'}}>
            {current.correction_profile && (
              <Chip tone={PROFILE_TONES[current.correction_profile]||'neutral'}>
                {PROFILE_LABELS[current.correction_profile]||current.correction_profile}
              </Chip>
            )}
            <Chip tone="neutral"><span className="mono">{current.irrigation_system_type}</span></Chip>
            <Chip tone="neutral">{waterForm.tanksCount} бака</Chip>
            <Chip tone="neutral">
              Полив: <span className="mono">{waterForm.intervalMinutes}м/{waterForm.durationSeconds}с</span>
            </Chip>
            <Chip tone="neutral">
              Корр. при поливе: {waterForm.correctionDuringIrrigation?'да':'нет'}
            </Chip>
          </div>
        </div>
      ) : (
        <div style={{fontSize:11,color:'var(--text-muted)'}}>
          Ручная настройка — заполните параметры вручную ниже.
        </div>
      )}
    </div>
  );
}

Object.assign(window, { PresetSelector });
