import { describe, expect, it } from 'vitest'
import { ref } from 'vue'
import {
  DIAGRAM_GEO,
  DIAGRAM_LAYOUT,
  createDiagramFlow,
} from '@/composables/automationDiagramLayout'

describe('automationDiagramLayout', () => {
  it('экспортирует согласованную геометрию баков и насоса', () => {
    const T = DIAGRAM_LAYOUT
    expect(DIAGRAM_GEO.tankBottom).toBe(T.tank.top + T.tank.h)
    expect(DIAGRAM_GEO.pumpInletX).toBe(T.pump.cx - T.pump.r)
    expect(DIAGRAM_GEO.pumpOutletX).toBe(T.pump.cx + T.pump.r)
    expect(DIAGRAM_GEO.dosingRight).toBe(T.dosing.x + T.dosing.w)
  })

  it('интерполирует каплю входа и магистрали по flowOffset', () => {
    const flowOffset = ref(0)
    const flow = createDiagramFlow(flowOffset)

    expect(flow.waterInletFlowY.value).toBe(DIAGRAM_LAYOUT.inlet.top)
    expect(flow.cleanDrainFlowY.value).toBe(DIAGRAM_GEO.tankBottom)
    expect(flow.cleanBusFlowX.value).toBe(DIAGRAM_GEO.cleanCx)
    expect(flow.solutionBusFlowX.value).toBe(DIAGRAM_GEO.solutionCx)

    flowOffset.value = 1
    expect(flow.waterInletFlowY.value).toBe(DIAGRAM_LAYOUT.tank.top)
    expect(flow.cleanDrainFlowY.value).toBe(DIAGRAM_LAYOUT.busY)
    expect(flow.solutionDrainFlowY.value).toBe(DIAGRAM_LAYOUT.busY)
    expect(flow.cleanBusFlowX.value).toBe(DIAGRAM_GEO.pumpInletX)
    expect(flow.solutionBusFlowX.value).toBe(DIAGRAM_GEO.pumpInletX)
  })

  it('двигает каплю полива от тройника к выходу', () => {
    const flowOffset = ref(0)
    const flow = createDiagramFlow(flowOffset)
    const { teeX, irr } = DIAGRAM_LAYOUT

    expect(flow.irrigationFlowX.value).toBe(teeX)

    flowOffset.value = 1
    expect(flow.irrigationFlowX.value).toBe(irr.endX)
  })

  it('проводит каплю рециркуляции по трём сегментам', () => {
    const flowOffset = ref(0)
    const flow = createDiagramFlow(flowOffset)
    const T = DIAGRAM_LAYOUT

    flowOffset.value = 0.2
    expect(flow.recircFlowX.value).toBe(T.teeX)
    expect(flow.recircFlowY.value).toBeLessThan(T.busY)
    expect(flow.recircFlowY.value).toBeGreaterThan(T.recirc.topY)

    flowOffset.value = 0.5
    expect(flow.recircFlowY.value).toBe(T.recirc.topY)
    expect(flow.recircFlowX.value).toBeLessThan(T.teeX)
    expect(flow.recircFlowX.value).toBeGreaterThan(DIAGRAM_GEO.solutionCx)

    flowOffset.value = 1
    expect(flow.recircFlowX.value).toBe(DIAGRAM_GEO.solutionCx)
    expect(flow.recircFlowY.value).toBe(T.tank.top)
  })
})
