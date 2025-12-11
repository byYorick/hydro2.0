package com.hydro.app.core.database

import androidx.room.Database
import androidx.room.RoomDatabase
import androidx.room.TypeConverters
import com.hydro.app.core.database.dao.AlertDao
import com.hydro.app.core.database.dao.GreenhouseDao
import com.hydro.app.core.database.dao.NodeDao
import com.hydro.app.core.database.dao.TelemetryDao
import com.hydro.app.core.database.dao.ZoneDao
import com.hydro.app.core.database.entity.AlertEntity
import com.hydro.app.core.database.entity.GreenhouseEntity
import com.hydro.app.core.database.entity.NodeEntity
import com.hydro.app.core.database.entity.TelemetryEntity
import com.hydro.app.core.database.entity.ZoneEntity

@Database(
    entities = [
        GreenhouseEntity::class,
        ZoneEntity::class,
        NodeEntity::class,
        TelemetryEntity::class,
        AlertEntity::class
    ],
    version = 1,
    exportSchema = false
)
@TypeConverters(Converters::class)
abstract class HydroDatabase : RoomDatabase() {
    abstract fun greenhouseDao(): GreenhouseDao
    abstract fun zoneDao(): ZoneDao
    abstract fun nodeDao(): NodeDao
    abstract fun telemetryDao(): TelemetryDao
    abstract fun alertDao(): AlertDao
}

