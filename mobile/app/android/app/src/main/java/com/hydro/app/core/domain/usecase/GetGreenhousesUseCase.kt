package com.hydro.app.core.domain.usecase

import com.hydro.app.core.data.GreenhousesRepository
import com.hydro.app.core.domain.AppError
import com.hydro.app.core.domain.AppResult
import com.hydro.app.core.domain.Greenhouse
import com.hydro.app.core.domain.toAppError
import kotlinx.coroutines.flow.Flow
import javax.inject.Inject

/**
 * Use Case для получения списка теплиц.
 * 
 * Следует принципам Clean Architecture:
 * - Инкапсулирует бизнес-логику получения теплиц
 * - Не зависит от деталей реализации (UI, Database, Network)
 * - Может быть легко протестирован
 */
class GetGreenhousesUseCase @Inject constructor(
    private val repository: GreenhousesRepository
) {
    /**
     * Получает поток всех теплиц.
     * 
     * @return Flow со списком теплиц
     */
    fun invoke(): Flow<List<Greenhouse>> {
        return repository.getAll()
    }

    /**
     * Получает теплицу по ID.
     * 
     * @param id ID теплицы
     * @return Результат с теплицей или ошибкой
     */
    suspend fun getById(id: Int): AppResult<Greenhouse> {
        return try {
            val greenhouse = repository.getById(id)
            if (greenhouse != null) {
                Result.success(greenhouse)
            } else {
                Result.failure(AppError.UnknownError("Greenhouse not found"))
            }
        } catch (e: Exception) {
            Result.failure(e.toAppError())
        }
    }

    /**
     * Обновляет список теплиц из API.
     * 
     * @return Результат операции
     */
    suspend fun refresh(): AppResult<Unit> {
        return try {
            repository.refresh()
            Result.success(Unit)
        } catch (e: Exception) {
            Result.failure(e.toAppError())
        }
    }
}

