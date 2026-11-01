package com.hydro.app.core.domain

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class OperatorSignalsTest {
    @Test
    fun levelSwitchIsNotTreatedAsContinuousLevel() {
        val reading = levelReading(
            listOf(
                NodeTelemetrySample(metricType = "WATER_LEVEL_SWITCH", channel = "level_switch", value = 1.0),
            ),
        )
        assertEquals("Датчик уровня", reading?.label)
        assertEquals("замкнут", reading?.valueText)
    }

    @Test
    fun snapshotWithoutLevelStaysEmpty() {
        assertNull(levelReading(listOf(NodeTelemetrySample(metricType = "PH", value = 6.2))))
    }

    @Test
    fun statusTones() {
        assertEquals(StatusTone.Ok, statusTone("online"))
        assertEquals(StatusTone.Warning, statusTone("warning"))
        assertEquals(StatusTone.Critical, statusTone("critical"))
        assertEquals(StatusTone.Offline, statusTone("offline"))
    }
}
