import { computed, type ComputedRef, type Ref } from 'vue'

/**
 * Единый источник геометрии P&ID-схемы зоны (AutomationProcessDiagram).
 * Все координаты в системе viewBox (см. `view`). Логика потока слева направо:
 * вход → бак чистой воды / бак раствора → магистраль (V2/V3) → насос P1 →
 * дозирование pH/EC → тройник → рециркуляция (V4) / полив (V5).
 */
export const DIAGRAM_LAYOUT = {
  view: { w: 520, h: 188 },
  tank: { top: 28, h: 84, w: 82, radius: 10 },
  cleanX: 26,
  solutionX: 124,
  inlet: { top: 12, valveY: 16 },
  busY: 150,
  drainValveY: 118,
  titleY: 170,
  pump: { cx: 252, r: 17 },
  dosing: { x: 298, y: 130, w: 84, h: 40 },
  teeX: 408,
  recirc: { topY: 24, valveY: 78 },
  irr: { valveX: 442, endX: 488 },
} as const

const T = DIAGRAM_LAYOUT

export const DIAGRAM_GEO = {
  cleanCx: T.cleanX + T.tank.w / 2,
  solutionCx: T.solutionX + T.tank.w / 2,
  tankBottom: T.tank.top + T.tank.h,
  pumpInletX: T.pump.cx - T.pump.r,
  pumpOutletX: T.pump.cx + T.pump.r,
  dosingRight: T.dosing.x + T.dosing.w,
} as const

export interface DiagramFlowPoints {
  waterInletFlowY: ComputedRef<number>
  cleanDrainFlowY: ComputedRef<number>
  solutionDrainFlowY: ComputedRef<number>
  cleanBusFlowX: ComputedRef<number>
  solutionBusFlowX: ComputedRef<number>
  pumpOutletFlowX: ComputedRef<number>
  recircFlowX: ComputedRef<number>
  recircFlowY: ComputedRef<number>
  irrigationFlowX: ComputedRef<number>
}

/** Анимация «движущейся капли» по сегментам трубопровода. */
export function createDiagramFlow(flowOffset: Ref<number>): DiagramFlowPoints {
  const waterInletFlowY = computed(
    () => T.inlet.top + (T.tank.top - T.inlet.top) * flowOffset.value,
  )

  const cleanDrainFlowY = computed(
    () => DIAGRAM_GEO.tankBottom + (T.busY - DIAGRAM_GEO.tankBottom) * flowOffset.value,
  )

  const solutionDrainFlowY = computed(
    () => DIAGRAM_GEO.tankBottom + (T.busY - DIAGRAM_GEO.tankBottom) * flowOffset.value,
  )

  const cleanBusFlowX = computed(
    () => DIAGRAM_GEO.cleanCx + (DIAGRAM_GEO.pumpInletX - DIAGRAM_GEO.cleanCx) * flowOffset.value,
  )

  const solutionBusFlowX = computed(
    () => DIAGRAM_GEO.solutionCx + (DIAGRAM_GEO.pumpInletX - DIAGRAM_GEO.solutionCx) * flowOffset.value,
  )

  const pumpOutletFlowX = computed(
    () => DIAGRAM_GEO.pumpOutletX + (T.dosing.x - DIAGRAM_GEO.pumpOutletX) * flowOffset.value,
  )

  const recircFlowX = computed(() => {
    const t = flowOffset.value
    if (t < 0.4) {
      return T.teeX
    }
    if (t < 0.75) {
      return T.teeX - (T.teeX - DIAGRAM_GEO.solutionCx) * ((t - 0.4) / 0.35)
    }
    return DIAGRAM_GEO.solutionCx
  })

  const recircFlowY = computed(() => {
    const t = flowOffset.value
    if (t < 0.4) {
      return T.busY - (T.busY - T.recirc.topY) * (t / 0.4)
    }
    if (t < 0.75) {
      return T.recirc.topY
    }
    return T.recirc.topY + (T.tank.top - T.recirc.topY) * ((t - 0.75) / 0.25)
  })

  const irrigationFlowX = computed(
    () => T.teeX + (T.irr.endX - T.teeX) * flowOffset.value,
  )

  return {
    waterInletFlowY,
    cleanDrainFlowY,
    solutionDrainFlowY,
    cleanBusFlowX,
    solutionBusFlowX,
    pumpOutletFlowX,
    recircFlowX,
    recircFlowY,
    irrigationFlowX,
  }
}
