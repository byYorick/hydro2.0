<template>
  <AppLayout>
    <section class="ui-hero p-5 space-y-4 mb-4">
      <p class="text-[11px] uppercase tracking-[0.28em] text-[color:var(--text-dim)]">
        fertigation guide
      </p>
      <h1 class="text-2xl font-semibold tracking-tight text-[color:var(--text-primary)]">
        Документация по калибровке и дозированию EC/pH
      </h1>
      <p class="text-sm text-[color:var(--text-muted)]">
        Практический регламент для клубники на капле (осмос), схема pH (кислота/щёлочь) + EC A/B/C/D.
      </p>
    </section>

    <Card class="mb-4">
      <h2 class="text-sm font-semibold mb-2">
        1) Калибровка насосов и коэффициента k
      </h2>
      <div class="text-xs text-[color:var(--text-muted)] space-y-1">
        <p>Цель: получить гидравлическую производительность насоса (`ml_per_sec`) и вклад в EC (`k`, mS/cm на мл/л).</p>
        <p>Рекомендуемый тест: чистая вода 10-20 л, температура стабильная, интенсивное перемешивание 2-3 минуты после каждой дозы.</p>
      </div>
      <pre class="mt-3 rounded-lg bg-[color:var(--bg-elevated)] p-3 text-xs overflow-auto"><code>ml_per_sec = actual_ml / duration_sec
delta_ec = ec_after - ec_before
ml_per_l = actual_ml / test_volume_l
k = delta_ec / ml_per_l</code></pre>
      <div class="text-xs text-[color:var(--text-muted)] mt-3 space-y-1">
        <p>Если `EC_base` нестабилен, фиксируйте `ec_before` перед каждым тестом и делайте минимум 3 повтора на насос.</p>
        <p>Перекалибровка: при смене партии удобрений, после обслуживания насоса, и планово 1 раз в 2-4 недели.</p>
      </div>
    </Card>

    <Card class="mb-4">
      <h2 class="text-sm font-semibold mb-2">
        2) Что такое ΔEC
      </h2>
      <pre class="rounded-lg bg-[color:var(--bg-elevated)] p-3 text-xs overflow-auto"><code>delta_ec = ec_target - ec_base</code></pre>
      <div class="text-xs text-[color:var(--text-muted)] mt-3 space-y-1">
        <p>`ec_base` — EC исходной воды/бака до внесения удобрений.</p>
        <p>Для осмоса обычно низкое `ec_base`, но измерение перед каждым циклом обязательно.</p>
      </div>
    </Card>

    <Card class="mb-4">
      <h2 class="text-sm font-semibold mb-2">
        3) Режимы расчёта дозирования
      </h2>
      <div class="text-xs text-[color:var(--text-muted)] space-y-2">
        <p><span class="font-semibold text-[color:var(--text-primary)]">A. По долям ΔEC:</span> задаются доли `pA..pD` (сумма = 1.0), затем считаются дозы через `k`.</p>
      </div>
      <pre class="mt-2 rounded-lg bg-[color:var(--bg-elevated)] p-3 text-xs overflow-auto"><code>delta_ec_i = p_i * delta_ec
x_i (ml/l) = delta_ec_i / k_i
M_i (ml на бак) = x_i * V</code></pre>
      <div class="text-xs text-[color:var(--text-muted)] mt-3 space-y-1">
        <p><span class="font-semibold text-[color:var(--text-primary)]">B. Ratio + EC PID:</span> PID задаёт интенсивность коррекции по ошибке EC, а доли компонентов распределяют вклад между насосами.</p>
        <p><span class="font-semibold text-[color:var(--text-primary)]">C. По элементам (ppm):</span> целевые ppm N/K/Ca/Mg/Fe переводятся в дозы солей (расчёт ведётся через матрицу состава солей).</p>
      </div>
    </Card>

    <Card class="mb-4">
      <h2 class="text-sm font-semibold mb-2">
        4) Стартовые доли для клубники
      </h2>
      <div class="text-xs text-[color:var(--text-muted)] space-y-1">
        <p>Вега (A:Ca, B:NPK, C:MgSO4, D:Micro+Fe): `0.32 / 0.48 / 0.17 / 0.03`.</p>
        <p>Плодоношение: `0.36 / 0.42 / 0.19 / 0.03`.</p>
        <p>Микро (D) обычно 1-3% от ΔEC.</p>
        <p>Tipburn/дефицит Ca: увеличить A. Межжилковый хлороз: увеличить C и/или D. Плохая плотность/вкус ягоды: проверить баланс K/Ca и дренаж.</p>
      </div>
    </Card>

    <Card class="mb-4">
      <h2 class="text-sm font-semibold mb-2">
        5) Практические правила смешивания
      </h2>
      <ul class="list-disc pl-5 text-xs text-[color:var(--text-muted)] space-y-1">
        <li>Кальций держать отдельно от фосфатов и сульфатов в маточниках.</li>
        <li>MgSO4 отдельно от кальциевого маточника.</li>
        <li>Микро/Fe (хелаты) отдельной линией, с контролем pH рабочего раствора.</li>
        <li>Для капли по клубнике держать pH раствора 5.3-5.8 (особенно при pH субстрата около 7.8).</li>
        <li>Использовать задержку между дозами и промежуточный re-check EC.</li>
      </ul>
    </Card>

    <Card class="mb-4">
      <h2 class="text-sm font-semibold mb-2">
        6) Чек-лист калибровки
      </h2>
      <ul class="list-disc pl-5 text-xs text-[color:var(--text-muted)] space-y-1">
        <li>Зафиксировать: `test_volume_l`, `ec_before`, `temperature_c`.</li>
        <li>Запустить насос на фиксированное время (обычно 20-60 сек).</li>
        <li>Измерить фактический объём (`actual_ml`).</li>
        <li>После перемешивания измерить `ec_after`.</li>
        <li>Сохранить калибровку и повторить не менее 3 раз для каждого насоса.</li>
        <li>Взять медиану по `ml_per_sec` и `k` как рабочее значение.</li>
      </ul>
    </Card>

    <Card>
      <h2 class="text-sm font-semibold mb-2">
        7) Пример расчёта
      </h2>
      <div class="text-xs text-[color:var(--text-muted)] mb-3">
        `EC_base=0.1`, `EC_target=2.0`, `V=100 л`, значит `ΔEC=1.9`.
      </div>
      <div class="overflow-auto rounded-lg border border-[color:var(--border-muted)]">
        <table class="w-full border-collapse text-xs">
          <thead class="bg-[color:var(--bg-elevated)] text-[color:var(--text-muted)]">
            <tr>
              <th class="text-left px-3 py-2 border-b border-[color:var(--border-muted)]">
                Насос
              </th>
              <th class="text-left px-3 py-2 border-b border-[color:var(--border-muted)]">
                k (mS/(ml/L))
              </th>
              <th class="text-left px-3 py-2 border-b border-[color:var(--border-muted)]">
                p
              </th>
              <th class="text-left px-3 py-2 border-b border-[color:var(--border-muted)]">
                ΔEC_i
              </th>
              <th class="text-left px-3 py-2 border-b border-[color:var(--border-muted)]">
                мл/л
              </th>
              <th class="text-left px-3 py-2 border-b border-[color:var(--border-muted)]">
                мл на 100 л
              </th>
            </tr>
          </thead>
          <tbody>
            <tr class="border-b border-[color:var(--border-muted)]">
              <td class="px-3 py-2">
                A (Ca)
              </td>
              <td class="px-3 py-2">
                0.62
              </td>
              <td class="px-3 py-2">
                0.32
              </td>
              <td class="px-3 py-2">
                0.608
              </td>
              <td class="px-3 py-2">
                0.981
              </td>
              <td class="px-3 py-2">
                98.1
              </td>
            </tr>
            <tr class="border-b border-[color:var(--border-muted)]">
              <td class="px-3 py-2">
                B (NPK)
              </td>
              <td class="px-3 py-2">
                0.85
              </td>
              <td class="px-3 py-2">
                0.48
              </td>
              <td class="px-3 py-2">
                0.912
              </td>
              <td class="px-3 py-2">
                1.073
              </td>
              <td class="px-3 py-2">
                107.3
              </td>
            </tr>
            <tr class="border-b border-[color:var(--border-muted)]">
              <td class="px-3 py-2">
                C (MgSO4)
              </td>
              <td class="px-3 py-2">
                0.50
              </td>
              <td class="px-3 py-2">
                0.17
              </td>
              <td class="px-3 py-2">
                0.323
              </td>
              <td class="px-3 py-2">
                0.646
              </td>
              <td class="px-3 py-2">
                64.6
              </td>
            </tr>
            <tr>
              <td class="px-3 py-2">
                D (Micro+Fe)
              </td>
              <td class="px-3 py-2">
                0.30
              </td>
              <td class="px-3 py-2">
                0.03
              </td>
              <td class="px-3 py-2">
                0.057
              </td>
              <td class="px-3 py-2">
                0.190
              </td>
              <td class="px-3 py-2">
                19.0
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </Card>
  </AppLayout>
</template>

<script setup lang="ts">
import AppLayout from '@/Layouts/AppLayout.vue'
import Card from '@/Components/Card.vue'
</script>
