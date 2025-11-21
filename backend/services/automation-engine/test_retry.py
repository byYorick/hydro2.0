"""Tests for utils/retry module."""
import pytest
import asyncio
from unittest.mock import AsyncMock, patch
from utils.retry import retry_with_backoff, simple_retry


@pytest.mark.asyncio
async def test_retry_with_backoff_success():
    """Test retry_with_backoff with successful execution."""
    call_count = 0
    
    @retry_with_backoff(max_attempts=3, initial_wait=0.1)
    async def test_func():
        nonlocal call_count
        call_count += 1
        return "success"
    
    result = await test_func()
    
    assert result == "success"
    assert call_count == 1


@pytest.mark.asyncio
async def test_retry_with_backoff_retry_success():
    """Test retry_with_backoff with retry and eventual success."""
    call_count = 0
    
    @retry_with_backoff(max_attempts=3, initial_wait=0.1)
    async def test_func():
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise ValueError("Temporary error")
        return "success"
    
    result = await test_func()
    
    assert result == "success"
    assert call_count == 2


@pytest.mark.asyncio
async def test_retry_with_backoff_max_attempts():
    """Test retry_with_backoff exhausts all attempts."""
    call_count = 0
    
    @retry_with_backoff(max_attempts=3, initial_wait=0.1)
    async def test_func():
        nonlocal call_count
        call_count += 1
        raise ValueError("Persistent error")
    
    with pytest.raises(ValueError, match="Persistent error"):
        await test_func()
    
    assert call_count == 3


@pytest.mark.asyncio
async def test_retry_with_backoff_exponential_wait():
    """Test retry_with_backoff uses exponential backoff."""
    call_times = []
    
    @retry_with_backoff(max_attempts=3, initial_wait=0.1, max_wait=1.0)
    async def test_func():
        call_times.append(asyncio.get_event_loop().time())
        raise ValueError("Error")
    
    start_time = asyncio.get_event_loop().time()
    
    with pytest.raises(ValueError):
        await test_func()
    
    # Проверяем, что были задержки между попытками
    assert len(call_times) == 3
    # Вторая попытка должна быть после первой с задержкой
    assert call_times[1] > call_times[0]
    # Третья попытка должна быть после второй с большей задержкой
    assert call_times[2] > call_times[1]


@pytest.mark.asyncio
async def test_retry_with_backoff_retry_on_specific_exception():
    """Test retry_with_backoff only retries on specific exceptions."""
    call_count = 0
    
    @retry_with_backoff(max_attempts=3, initial_wait=0.1, retry_on=[ValueError])
    async def test_func():
        nonlocal call_count
        call_count += 1
        raise TypeError("Different error")
    
    with pytest.raises(TypeError):
        await test_func()
    
    # Не должно быть retry для TypeError
    assert call_count == 1


@pytest.mark.asyncio
async def test_simple_retry_success():
    """Test simple_retry with successful execution."""
    call_count = 0
    
    @simple_retry(max_attempts=3, delay=0.1)
    async def test_func():
        nonlocal call_count
        call_count += 1
        return "success"
    
    result = await test_func()
    
    assert result == "success"
    assert call_count == 1


@pytest.mark.asyncio
async def test_simple_retry_retry_success():
    """Test simple_retry with retry and eventual success."""
    call_count = 0
    
    @simple_retry(max_attempts=3, delay=0.1)
    async def test_func():
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise ValueError("Temporary error")
        return "success"
    
    result = await test_func()
    
    assert result == "success"
    assert call_count == 2


@pytest.mark.asyncio
async def test_simple_retry_max_attempts():
    """Test simple_retry exhausts all attempts."""
    call_count = 0
    
    @simple_retry(max_attempts=3, delay=0.1)
    async def test_func():
        nonlocal call_count
        call_count += 1
        raise ValueError("Persistent error")
    
    with pytest.raises(ValueError, match="Persistent error"):
        await test_func()
    
    assert call_count == 3


@pytest.mark.asyncio
async def test_simple_retry_retry_on_specific_exception():
    """Test simple_retry only retries on specific exceptions."""
    call_count = 0
    
    @simple_retry(max_attempts=3, delay=0.1, retry_on=[ValueError])
    async def test_func():
        nonlocal call_count
        call_count += 1
        raise TypeError("Different error")
    
    with pytest.raises(TypeError):
        await test_func()
    
    # Не должно быть retry для TypeError
    assert call_count == 1

