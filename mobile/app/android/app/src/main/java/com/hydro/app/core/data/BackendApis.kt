package com.hydro.app.core.data

import com.hydro.app.core.domain.Alert
import com.hydro.app.core.domain.Greenhouse
import com.hydro.app.core.domain.TelemetryLast
import com.hydro.app.core.domain.Zone
import retrofit2.http.GET
import retrofit2.http.Path
import retrofit2.http.Query

interface GreenhousesApi {
	@GET("/api/greenhouses")
	suspend fun list(): List<Greenhouse>
}

interface ZonesApi {
	@GET("/api/zones")
	suspend fun list(@Query("greenhouseId") greenhouseId: String): List<Zone>

	@GET("/api/zones/{id}/telemetry/last")
	suspend fun last(@Path("id") zoneId: String): TelemetryLast
}

interface AlertsApi {
	@GET("/api/alerts")
	suspend fun list(): List<Alert>
}


