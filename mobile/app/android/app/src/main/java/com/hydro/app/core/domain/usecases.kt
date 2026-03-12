package com.hydro.app.core.domain

import com.hydro.app.core.data.AlertsRepository
import com.hydro.app.core.data.GreenhousesRepository
import com.hydro.app.core.data.ZonesRepository
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class GetGreenhousesUseCase @Inject constructor(
	private val repo: GreenhousesRepository
) {
	suspend operator fun invoke(): List<Greenhouse> = repo.list()
}

@Singleton
class GetZonesUseCase @Inject constructor(
	private val repo: ZonesRepository
) {
	suspend operator fun invoke(greenhouseId: String): List<Zone> = repo.list(greenhouseId)
}

@Singleton
class GetZoneDetailsUseCase @Inject constructor(
	private val repo: ZonesRepository
) {
	suspend operator fun invoke(zoneId: String): TelemetryLast = repo.last(zoneId)
}

@Singleton
class GetAlertsUseCase @Inject constructor(
	private val repo: AlertsRepository
) {
	suspend operator fun invoke(): List<Alert> = repo.list()
}


