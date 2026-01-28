package com.hydro.app.core.database

import androidx.room.Room
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.hydro.app.core.database.entity.GreenhouseEntity
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.test.runTest
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

/**
 * Интеграционные тесты для Room database.
 */
@RunWith(AndroidJUnit4::class)
class HydroDatabaseTest {
    private lateinit var database: HydroDatabase

    @Before
    fun setup() {
        database = Room.inMemoryDatabaseBuilder(
            ApplicationProvider.getApplicationContext(),
            HydroDatabase::class.java
        ).allowMainThreadQueries()
            .build()
    }

    @After
    fun tearDown() {
        database.close()
    }

    @Test
    fun insertAndGetGreenhouse() = runTest {
        // Given
        val greenhouse = GreenhouseEntity(
            id = 1,
            uid = "test-uid",
            name = "Test Greenhouse",
            location = "Test Location"
        )

        // When
        database.greenhouseDao().insertAll(listOf(greenhouse))
        val result = database.greenhouseDao().getById(1)

        // Then
        assertNotNull(result)
        assertEquals(greenhouse.id, result?.id)
        assertEquals(greenhouse.name, result?.name)
    }

    @Test
    fun getAllGreenhouses() = runTest {
        // Given
        val greenhouses = listOf(
            GreenhouseEntity(id = 1, uid = "uid1", name = "Greenhouse 1"),
            GreenhouseEntity(id = 2, uid = "uid2", name = "Greenhouse 2")
        )

        // When
        database.greenhouseDao().insertAll(greenhouses)
        val result = database.greenhouseDao().getAll().first()

        // Then
        assertEquals(2, result.size)
    }
}

