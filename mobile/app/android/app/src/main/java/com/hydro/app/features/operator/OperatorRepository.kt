package com.hydro.app.features.operator

import com.hydro.app.core.data.AlertsApi
import com.hydro.app.core.data.GreenhousesApi
import com.hydro.app.core.data.NodesApi
import com.hydro.app.core.data.ZonesApi
import com.hydro.app.core.domain.Alert
import com.hydro.app.core.domain.CommandParams
import com.hydro.app.core.domain.CommandRequest
import com.hydro.app.core.domain.ControlModeRequest
import com.hydro.app.core.domain.Greenhouse
import com.hydro.app.core.domain.LevelReading
import com.hydro.app.core.domain.Node
import com.hydro.app.core.domain.NodeCommandRequest
import com.hydro.app.core.domain.NodeTelemetrySample
import com.hydro.app.core.domain.TelemetryLast
import com.hydro.app.core.domain.Zone
import com.hydro.app.core.domain.levelReading
import com.hydro.app.core.network.ApiErrorParser
import com.hydro.app.core.network.ApiResponse
import retrofit2.HttpException
import java.io.IOException
import javax.inject.Inject
import javax.inject.Singleton

data class ZoneDashboard(
    val zone: Zone,
    val telemetry: TelemetryLast?,
    val nodes: List<Node>,
    val level: LevelReading?,
    val controlMode: String?,
    val stage: String?,
    val controlModeNote: String?,
)

data class NodeDashboard(
    val node: Node,
    val samples: List<NodeTelemetrySample>,
)

@Singleton
class OperatorRepository @Inject constructor(
    private val greenhousesApi: GreenhousesApi,
    private val zonesApi: ZonesApi,
    private val nodesApi: NodesApi,
    private val alertsApi: AlertsApi,
    private val apiErrorParser: ApiErrorParser,
) {
    suspend fun greenhouses(): Result<List<Greenhouse>> = call {
        greenhousesApi.list().requireItems()
    }

    suspend fun zones(greenhouseId: Int): Result<List<Zone>> = call {
        zonesApi.list(greenhouseId).requireItems()
    }

    suspend fun zoneDashboard(zoneId: Int): Result<ZoneDashboard> = call {
        val zone = zonesApi.getById(zoneId).requireData()
        val telemetry = runCatching { zonesApi.getTelemetryLast(zoneId) }
            .getOrNull()
            ?.takeIf { it.status == "ok" }
            ?.data
        val nodes = runCatching { nodesApi.list(zoneId) }.getOrNull()?.data?.data.orEmpty()
        var level: com.hydro.app.core.domain.LevelReading? = null
        for (node in nodes.take(LEVEL_PROBE_LIMIT)) {
            val samples = runCatching { nodesApi.telemetryLast(node.id) }.getOrNull()?.data.orEmpty()
            level = levelReading(samples)
            if (level != null) break
        }
        val modeResponse = runCatching { zonesApi.controlMode(zoneId) }.getOrNull()
        val mode = modeResponse?.takeIf { it.status == "ok" }?.data
        ZoneDashboard(
            zone = zone,
            telemetry = telemetry,
            nodes = nodes,
            level = level,
            controlMode = mode?.controlMode ?: zone.controlMode,
            stage = mode?.currentStage ?: mode?.workflowPhase,
            controlModeNote = if (mode == null) {
                "Живой control-mode automation-engine недоступен. Показан control_mode зоны."
            } else {
                null
            },
        )
    }

    suspend fun nodeDashboard(nodeId: Int): Result<NodeDashboard> = call {
        NodeDashboard(
            node = nodesApi.getById(nodeId).requireData(),
            samples = runCatching { nodesApi.telemetryLast(nodeId) }.getOrNull()?.data.orEmpty(),
        )
    }

    suspend fun alerts(status: String? = "ACTIVE"): Result<List<Alert>> = call {
        alertsApi.list(status = status).requireItems()
    }

    suspend fun acknowledge(alertId: Int): Result<Alert> = call {
        alertsApi.acknowledge(alertId).requireData()
    }

    suspend fun forceIrrigation(zoneId: Int, durationSec: Int): Result<String> = call {
        val response = zonesApi.sendCommand(
            zoneId,
            CommandRequest(
                type = "FORCE_IRRIGATION",
                params = CommandParams(durationSec = durationSec),
            ),
        )
        response.requireCommandId("Полив отправлен")
    }

    suspend fun emergencyManual(zoneId: Int, reason: String): Result<String> = call {
        val response = zonesApi.setControlMode(
            zoneId,
            ControlModeRequest(controlMode = "manual", reason = reason.trim()),
        )
        if (response.status != "ok") {
            error(response.humanErrorMessage ?: response.message ?: "Не удалось перевести зону в ручной режим")
        }
        "Зона переведена в ручной режим"
    }

    suspend fun restartNode(nodeId: Int): Result<String> = call {
        nodesApi.sendCommand(nodeId, NodeCommandRequest(cmd = "restart")).requireCommandId("Перезапуск отправлен")
    }

    suspend fun setRelay(nodeId: Int, channel: String, enabled: Boolean): Result<String> = call {
        nodesApi.sendCommand(
            nodeId,
            NodeCommandRequest(
                cmd = "set_relay",
                channel = channel,
                params = CommandParams(state = enabled),
            ),
        ).requireCommandId(if (enabled) "Реле включено" else "Реле выключено")
    }

    private suspend fun <T> call(block: suspend () -> T): Result<T> {
        return try {
            Result.success(block())
        } catch (error: HttpException) {
            Result.failure(IllegalStateException(apiErrorParser.parseHttpException(error)))
        } catch (error: IOException) {
            Result.failure(IllegalStateException("Нет связи с сервером. Проверьте адрес и что backend запущен."))
        } catch (error: IllegalStateException) {
            Result.failure(error)
        } catch (error: Exception) {
            Result.failure(IllegalStateException(apiErrorParser.localizedMessage(error)))
        }
    }

    private fun <T> ApiResponse<T>.requireData(): T {
        if (status != "ok" || data == null) {
            error(humanErrorMessage ?: message ?: "Пустой ответ API")
        }
        return data
    }

    private fun <T> ApiResponse<com.hydro.app.core.network.LaravelPage<T>>.requireItems(): List<T> {
        if (status != "ok" || data == null) {
            error(humanErrorMessage ?: message ?: "Пустой список API")
        }
        return data.data
    }

    private fun ApiResponse<com.hydro.app.core.domain.CommandResponse>.requireCommandId(fallback: String): String {
        if (status != "ok") {
            error(humanErrorMessage ?: message ?: "Команда отклонена")
        }
        return data?.resolvedId ?: fallback
    }

    private companion object {
        const val LEVEL_PROBE_LIMIT = 6
    }
}
