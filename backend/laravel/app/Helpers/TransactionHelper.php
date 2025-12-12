<?php

namespace App\Helpers;

use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;
use Illuminate\Database\QueryException;

/**
 * Helper для работы с транзакциями и retry логикой при serialization failures.
 * 
 * Используется для критичных операций, требующих SERIALIZABLE isolation level.
 */
class TransactionHelper
{
    /**
     * Выполнить транзакцию с SERIALIZABLE isolation level и retry на serialization failures.
     * 
     * @param callable $callback Функция для выполнения в транзакции
     * @param int $maxRetries Максимальное количество попыток (по умолчанию 5)
     * @param int $baseDelayMs Базовая задержка между попытками в миллисекундах (по умолчанию 50ms)
     * @return mixed Результат выполнения callback
     * @throws \Exception Если все попытки исчерпаны или произошла другая ошибка
     */
    public static function withSerializableRetry(
        callable $callback,
        int $maxRetries = 5,
        int $baseDelayMs = 50
    ) {
        $attempt = 0;
        $lastException = null;

        while ($attempt < $maxRetries) {
            try {
                return DB::transaction(function () use ($callback) {
                    // Устанавливаем SERIALIZABLE isolation level для критичных операций
                    DB::statement('SET TRANSACTION ISOLATION LEVEL SERIALIZABLE');
                    
                    return $callback();
                });
            } catch (QueryException $e) {
                $lastException = $e;
                
                // Проверяем, является ли это serialization failure
                $isSerializationFailure = self::isSerializationFailure($e);
                
                // Инкрементируем счетчик попыток перед проверкой
                $attempt++;
                
                if ($isSerializationFailure && $attempt < $maxRetries) {
                    $delay = $baseDelayMs * (2 ** ($attempt - 1)); // Exponential backoff
                    
                    Log::warning('Transaction serialization failure, retrying', [
                        'attempt' => $attempt,
                        'max_retries' => $maxRetries,
                        'delay_ms' => $delay,
                        'error' => $e->getMessage(),
                        'code' => $e->getCode(),
                    ]);
                    
                    // Задержка перед следующей попыткой
                    usleep($delay * 1000);
                    
                    continue;
                }
                
                // Если это не serialization failure или попытки исчерпаны, пробрасываем исключение
                throw $e;
            } catch (\Exception $e) {
                // Для других исключений не делаем retry
                throw $e;
            }
        }
        
        // Если все попытки исчерпаны
        Log::error('Transaction failed after all retries', [
            'max_retries' => $maxRetries,
            'last_error' => $lastException?->getMessage(),
        ]);
        
        throw $lastException ?? new \RuntimeException('Transaction failed after all retries');
    }

    /**
     * Проверить, является ли исключение serialization failure.
     * 
     * @param QueryException $e
     * @return bool
     */
    private static function isSerializationFailure(QueryException $e): bool
    {
        // PostgreSQL error code для serialization failure
        $serializationErrorCodes = ['40001', '40P01', 40001];
        
        $errorCode = $e->getCode();
        $errorMessage = $e->getMessage();
        
        // Проверяем код ошибки (может быть строкой или числом)
        $errorCodeStr = (string) $errorCode;
        if (in_array($errorCode, $serializationErrorCodes, true) || 
            in_array($errorCodeStr, $serializationErrorCodes, true)) {
            return true;
        }
        
        // Проверяем SQLSTATE из деталей ошибки (если доступно)
        $errorInfo = $e->errorInfo ?? null;
        if ($errorInfo && isset($errorInfo[0])) {
            $sqlState = $errorInfo[0];
            if (in_array($sqlState, ['40001', '40P01'], true)) {
                return true;
            }
        }
        
        // Проверяем сообщение об ошибке (на случай, если код не установлен)
        $serializationKeywords = [
            'serialization failure',
            'could not serialize access',
            'deadlock detected',
        ];
        
        foreach ($serializationKeywords as $keyword) {
            if (stripos($errorMessage, $keyword) !== false) {
                return true;
            }
        }
        
        return false;
    }

    /**
     * Получить advisory lock для операции.
     * 
     * @param string|int $lockKey Ключ блокировки (будет преобразован в число через crc32, если строка)
     * @param callable $callback Функция для выполнения под блокировкой
     * @return mixed Результат выполнения callback
     * @throws \RuntimeException Если не удалось получить блокировку
     */
    public static function withAdvisoryLock(string|int $lockKey, callable $callback)
    {
        // Преобразуем строку в число через crc32
        $lockId = is_string($lockKey) ? crc32($lockKey) : $lockKey;
        
        // Advisory lock должен использоваться внутри транзакции
        // pg_try_advisory_xact_lock работает только внутри транзакции
        // Вызывающий код должен обернуть это в транзакцию с SERIALIZABLE
        
        // Проверяем, что мы внутри транзакции
        if (!DB::transactionLevel()) {
            throw new \RuntimeException('withAdvisoryLock must be called within a transaction');
        }
        
        $result = DB::selectOne("SELECT pg_try_advisory_xact_lock(?) as locked", [$lockId]);
        
        if (!$result || !$result->locked) {
            // Если не удалось получить блокировку, это не ошибка - просто пропускаем выполнение
            // Это нормально для дедупликации
            Log::debug('Advisory lock not acquired, skipping operation', [
                'lock_id' => $lockId,
                'lock_key' => is_string($lockKey) ? $lockKey : "int:{$lockKey}",
            ]);
            
            return null; // Возвращаем null вместо исключения для дедупликации
        }
        
        return $callback();
    }
}

