package com.hydro.app.core.data

import com.hydro.app.core.domain.Alert
import com.hydro.app.core.domain.Greenhouse
import com.hydro.app.core.domain.TelemetryLast
import com.hydro.app.core.domain.Zone
import com.hydro.app.core.realtime.RealtimeService
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class GreenhousesRepository @Inject constructor(
	private val api: GreenhousesApi,
	private val realtime: RealtimeService
) {
	suspend fun list(): List<Greenhouse> {
		realtime.start()
		return api.list()
	}
}

@Singleton
class ZonesRepository @Inject constructor(
	private val api: ZonesApi
) {
	suspend fun list(greenhouseId: String): List<Zone> = api.list(greenhouseId)
	suspend fun last(zoneId: String): TelemetryLast = api.last(zoneId)
}

@Singleton
class AlertsRepository @Inject constructor(
	private val api: AlertsApi
) {
	suspend fun list(): List<Alert> = api.list()
}


