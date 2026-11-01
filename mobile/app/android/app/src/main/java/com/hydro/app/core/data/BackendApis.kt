package com.hydro.app.core.data

import com.hydro.app.core.domain.Alert
import com.hydro.app.core.domain.CommandRequest
import com.hydro.app.core.domain.CommandResponse
import com.hydro.app.core.domain.ControlModeData
import com.hydro.app.core.domain.ControlModeRequest
import com.hydro.app.core.domain.Greenhouse
import com.hydro.app.core.domain.Node
import com.hydro.app.core.domain.NodeCommandRequest
import com.hydro.app.core.domain.NodeTelemetrySample
import com.hydro.app.core.domain.TelemetryHistoryPoint
import com.hydro.app.core.domain.TelemetryLast
import com.hydro.app.core.domain.Zone
import com.hydro.app.core.network.ApiResponse
import com.hydro.app.core.network.LaravelPage
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.PATCH
import retrofit2.http.POST
import retrofit2.http.Path
import retrofit2.http.Query

interface GreenhousesApi {
    @GET("api/greenhouses")
    suspend fun list(): ApiResponse<LaravelPage<Greenhouse>>

    @GET("api/greenhouses/{id}")
    suspend fun getById(@Path("id") id: Int): ApiResponse<Greenhouse>
}

interface ZonesApi {
    @GET("api/zones")
    suspend fun list(@Query("greenhouse_id") greenhouseId: Int? = null): ApiResponse<LaravelPage<Zone>>

    @GET("api/zones/{id}")
    suspend fun getById(@Path("id") id: Int): ApiResponse<Zone>

    @GET("api/zones/{id}/telemetry/last")
    suspend fun getTelemetryLast(@Path("id") id: Int): ApiResponse<TelemetryLast>

    @GET("api/zones/{id}/telemetry/history")
    suspend fun getTelemetryHistory(
        @Path("id") id: Int,
        @Query("metric") metric: String,
        @Query("from") from: String? = null,
        @Query("to") to: String? = null,
    ): ApiResponse<List<TelemetryHistoryPoint>>

    @POST("api/zones/{id}/commands")
    suspend fun sendCommand(
        @Path("id") id: Int,
        @Body command: CommandRequest,
    ): ApiResponse<CommandResponse>

    @GET("api/zones/{id}/control-mode")
    suspend fun controlMode(@Path("id") id: Int): ApiResponse<ControlModeData>

    @POST("api/zones/{id}/control-mode")
    suspend fun setControlMode(
        @Path("id") id: Int,
        @Body body: ControlModeRequest,
    ): ApiResponse<ControlModeData>
}

interface NodesApi {
    @GET("api/nodes")
    suspend fun list(@Query("zone_id") zoneId: Int? = null): ApiResponse<LaravelPage<Node>>

    @GET("api/nodes/{id}")
    suspend fun getById(@Path("id") id: Int): ApiResponse<Node>

    @POST("api/nodes/{id}/commands")
    suspend fun sendCommand(
        @Path("id") id: Int,
        @Body command: NodeCommandRequest,
    ): ApiResponse<CommandResponse>

    @GET("api/nodes/{id}/telemetry/last")
    suspend fun telemetryLast(@Path("id") id: Int): ApiResponse<List<NodeTelemetrySample>>
}

interface AlertsApi {
    @GET("api/alerts")
    suspend fun list(
        @Query("zone_id") zoneId: Int? = null,
        @Query("status") status: String? = null,
    ): ApiResponse<LaravelPage<Alert>>

    @GET("api/alerts/{id}")
    suspend fun getById(@Path("id") id: Int): ApiResponse<Alert>

    @PATCH("api/alerts/{id}/ack")
    suspend fun acknowledge(@Path("id") id: Int): ApiResponse<Alert>
}
