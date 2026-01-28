package com.hydro.app.core.data

import com.hydro.app.core.database.HydroDatabase
import com.hydro.app.core.database.entity.AlertEntity
import com.hydro.app.core.database.entity.GreenhouseEntity
import com.hydro.app.core.database.entity.NodeEntity
import com.hydro.app.core.database.entity.TelemetryEntity
import com.hydro.app.core.database.entity.ZoneEntity
import com.hydro.app.core.domain.Alert
import com.hydro.app.core.domain.Greenhouse
import com.hydro.app.core.domain.Node
import com.hydro.app.core.domain.TelemetryHistoryPoint
import com.hydro.app.core.domain.TelemetryLast
import com.hydro.app.core.domain.Zone
import com.hydro.app.core.prefs.PreferencesDataSource
import com.hydro.app.features.auth.data.AuthRepository
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import retrofit2.HttpException
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Repository для работы с данными о теплицах.
 * 
 * Объединяет данные из API и локальной базы данных Room.
 * Предоставляет реактивный интерфейс через Flow.
 */
@Singleton
class GreenhousesRepository @Inject constructor(
    private val api: GreenhousesApi,
    private val db: HydroDatabase,
    private val authRepository: AuthRepository
) {
    /**
     * Получает поток всех теплиц из локальной базы данных.
     * 
     * @return Flow со списком теплиц
     */
    fun getAll(): Flow<List<Greenhouse>> {
        return db.greenhouseDao().getAll().map { entities ->
            entities.map { it.toDomain() }
        }
    }

    /**
     * Обновляет данные о теплицах из API и сохраняет в локальную базу данных.
     * 
     * В случае ошибки использует кэшированные данные.
     * При 401 Unauthorized выполняет logout.
     */
    suspend fun refresh() {
        try {
            val response = api.list()
            if (response.status == "ok" && response.data != null) {
                val entities = response.data.map { it.toEntity() }
                db.greenhouseDao().insertAll(entities)
            } else {
                android.util.Log.w("GreenhousesRepository", "API returned error: ${response.message}")
            }
        } catch (e: HttpException) {
            if (e.code() == 401) {
                android.util.Log.w("GreenhousesRepository", "Unauthorized (401) - performing logout")
                authRepository.logout()
            } else {
                android.util.Log.e("GreenhousesRepository", "HTTP error ${e.code()}: ${e.message()}", e)
            }
            // Use cached data
        } catch (e: Exception) {
            android.util.Log.e("GreenhousesRepository", "Failed to refresh greenhouses", e)
            // Use cached data
        }
    }

    /**
     * Получает теплицу по ID из локальной базы данных.
     * 
     * @param id ID теплицы
     * @return Теплица или null, если не найдена
     */
    suspend fun getById(id: Int): Greenhouse? {
        return db.greenhouseDao().getById(id)?.toDomain()
    }
}

@Singleton
class ZonesRepository @Inject constructor(
    private val api: ZonesApi,
    private val db: HydroDatabase
) {
    fun getByGreenhouse(greenhouseId: Int): Flow<List<Zone>> {
        return db.zoneDao().getByGreenhouse(greenhouseId).map { entities ->
            entities.map { it.toDomain() }
        }
    }

    fun getAll(): Flow<List<Zone>> {
        return db.zoneDao().getAll().map { entities ->
            entities.map { it.toDomain() }
        }
    }

    suspend fun refresh(greenhouseId: Int? = null) {
        try {
            val response = api.list(greenhouseId)
            if (response.status == "ok" && response.data != null) {
                val entities = response.data.map { it.toEntity() }
                db.zoneDao().insertAll(entities)
            } else {
                android.util.Log.w("ZonesRepository", "API returned error: ${response.message}")
            }
        } catch (e: Exception) {
            android.util.Log.e("ZonesRepository", "Failed to refresh zones", e)
        }
    }

    suspend fun getById(id: Int): Zone? {
        return db.zoneDao().getById(id)?.toDomain()
    }
}

@Singleton
class NodesRepository @Inject constructor(
    private val api: NodesApi,
    private val db: HydroDatabase
) {
    fun getByZone(zoneId: Int): Flow<List<Node>> {
        return db.nodeDao().getByZone(zoneId).map { entities ->
            entities.map { it.toDomain() }
        }
    }

    fun getAll(): Flow<List<Node>> {
        return db.nodeDao().getAll().map { entities ->
            entities.map { it.toDomain() }
        }
    }

    suspend fun refresh(zoneId: Int? = null) {
        try {
            val response = api.list(zoneId)
            if (response.status == "ok" && response.data != null) {
                val entities = response.data.map { it.toEntity() }
                db.nodeDao().insertAll(entities)
            } else {
                android.util.Log.w("NodesRepository", "API returned error: ${response.message}")
            }
        } catch (e: Exception) {
            android.util.Log.e("NodesRepository", "Failed to refresh nodes", e)
        }
    }

    suspend fun getById(id: Int): Node? {
        return db.nodeDao().getById(id)?.toDomain()
    }
}

@Singleton
class TelemetryRepository @Inject constructor(
    private val api: ZonesApi,
    private val db: HydroDatabase
) {
    suspend fun getLast(zoneId: Int): TelemetryLast? {
        return try {
            val response = api.getTelemetryLast(zoneId)
            if (response.status == "ok" && response.data != null) {
                response.data
            } else null
        } catch (e: Exception) {
            null
        }
    }

    fun getHistory(zoneId: Int, metric: String): Flow<List<TelemetryHistoryPoint>> {
        return db.telemetryDao().getHistory(zoneId, metric).map { entities ->
            entities.map { TelemetryHistoryPoint(it.timestamp, it.value) }
        }
    }

    suspend fun refreshHistory(zoneId: Int, metric: String, from: String? = null, to: String? = null) {
        try {
            val response = api.getTelemetryHistory(zoneId, metric, from, to)
            if (response.status == "ok" && response.data != null) {
                val entities = response.data.map { point ->
                    TelemetryEntity(
                        zoneId = zoneId,
                        metric = metric,
                        value = point.value,
                        timestamp = point.timestamp
                    )
                }
                db.telemetryDao().insertAll(entities)
            } else {
                android.util.Log.w("TelemetryRepository", "API returned error: ${response.message}")
            }
        } catch (e: Exception) {
            android.util.Log.e("TelemetryRepository", "Failed to refresh telemetry history", e)
        }
    }
}

@Singleton
class AlertsRepository @Inject constructor(
    private val api: AlertsApi,
    private val db: HydroDatabase
) {
    fun getAll(): Flow<List<Alert>> {
        return db.alertDao().getAll().map { entities ->
            entities.map { it.toDomain() }
        }
    }

    fun getByStatus(status: String): Flow<List<Alert>> {
        return db.alertDao().getByStatus(status).map { entities ->
            entities.map { it.toDomain() }
        }
    }

    fun getByZone(zoneId: Int): Flow<List<Alert>> {
        return db.alertDao().getByZone(zoneId).map { entities ->
            entities.map { it.toDomain() }
        }
    }

    suspend fun refresh(zoneId: Int? = null, status: String? = null) {
        try {
            val response = api.list(zoneId, status)
            if (response.status == "ok" && response.data != null) {
                val entities = response.data.map { it.toEntity() }
                db.alertDao().insertAll(entities)
            } else {
                android.util.Log.w("AlertsRepository", "API returned error: ${response.message}")
            }
        } catch (e: Exception) {
            android.util.Log.e("AlertsRepository", "Failed to refresh alerts", e)
        }
    }

    suspend fun acknowledge(id: Int): Result<Alert> {
        return try {
            val response = api.acknowledge(id)
            if (response.status == "ok" && response.data != null) {
                val alert = response.data
                db.alertDao().acknowledge(
                    id = alert.id,
                    status = alert.status ?: "acknowledged",
                    acknowledgedAt = alert.acknowledgedAt ?: ""
                )
                Result.success(alert)
            } else {
                Result.failure(Exception(response.message ?: "Failed to acknowledge"))
            }
        } catch (e: Exception) {
            Result.failure(e)
        }
    }
}

// Extension functions for entity conversion
private fun Greenhouse.toEntity(): GreenhouseEntity {
    return GreenhouseEntity(
        id = id,
        uid = uid,
        name = name,
        location = location,
        status = status,
        zonesCount = zonesCount
    )
}

private fun GreenhouseEntity.toDomain(): Greenhouse {
    return Greenhouse(
        id = id,
        uid = uid,
        name = name,
        location = location,
        status = status,
        zonesCount = zonesCount
    )
}

private fun Zone.toEntity(): ZoneEntity {
    return ZoneEntity(
        id = id,
        uid = uid,
        name = name,
        greenhouseId = greenhouseId,
        greenhouseUid = greenhouseUid,
        status = status,
        culture = culture,
        recipeId = recipeId,
        recipeName = recipeName
    )
}

private fun ZoneEntity.toDomain(): Zone {
    return Zone(
        id = id,
        uid = uid,
        name = name,
        greenhouseId = greenhouseId,
        greenhouseUid = greenhouseUid,
        status = status,
        culture = culture,
        recipeId = recipeId,
        recipeName = recipeName
    )
}

private fun Node.toEntity(): NodeEntity {
    return NodeEntity(
        id = id,
        uid = uid,
        name = name,
        type = type,
        status = status,
        zoneId = zoneId,
        zoneUid = zoneUid,
        rssi = rssi,
        firmware = firmware,
        uptime = uptime
    )
}

private fun NodeEntity.toDomain(): Node {
    return Node(
        id = id,
        uid = uid,
        name = name,
        type = type,
        status = status,
        zoneId = zoneId,
        zoneUid = zoneUid,
        rssi = rssi,
        firmware = firmware,
        uptime = uptime
    )
}

private fun Alert.toEntity(): AlertEntity {
    return AlertEntity(
        id = id,
        level = level,
        type = type,
        zoneId = zoneId,
        zoneName = zoneName,
        nodeId = nodeId,
        nodeName = nodeName,
        message = message,
        timestamp = timestamp,
        status = status,
        acknowledgedAt = acknowledgedAt
    )
}

private fun AlertEntity.toDomain(): Alert {
    return Alert(
        id = id,
        level = level,
        type = type,
        zoneId = zoneId,
        zoneName = zoneName,
        nodeId = nodeId,
        nodeName = nodeName,
        message = message,
        timestamp = timestamp,
        status = status,
        acknowledgedAt = acknowledgedAt
    )
}
