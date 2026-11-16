from unittest.mock import AsyncMock
import pytest
from fastapi import HTTPException
from commands.lease_gate import reject_if_zone_lease_held, reject_if_operator_estop_active

@pytest.mark.asyncio
@pytest.mark.parametrize('source',['laravel','automation-engine'])
@pytest.mark.parametrize('cmd,params',[('dose',{'ml':1}),('run_pump',{'duration_ms':100}),('set_relay',{'state':True}),('exit_safe_mode',{})])
async def test_operator_latch_blocks_every_principal(source,cmd,params):
    fetch=AsyncMock(return_value=[{'type':'EMERGENCY_STOP_ACTIVATED'}])
    with pytest.raises(HTTPException) as exc:
        await reject_if_zone_lease_held(zone_id=7,cmd=cmd,params=params,source=source,fetch_fn=fetch)
    assert exc.value.status_code==409 and exc.value.detail['error']=='estop_active'
    assert 'zone_events' in fetch.await_args.args[0]

@pytest.mark.asyncio
@pytest.mark.parametrize('cmd,params',[('enter_safe_mode',{}),('set_relay',{'state':False}),('set_pwm',{'duty':0}),('state',{})])
async def test_off_and_read_remain_available_when_db_unavailable(cmd,params):
    fetch=AsyncMock(side_effect=ConnectionError())
    await reject_if_operator_estop_active(zone_id=7,cmd=cmd,params=params,fetch_fn=fetch)
    fetch.assert_not_awaited()

@pytest.mark.asyncio
async def test_operator_latch_lookup_failure_is_fail_closed():
    with pytest.raises(HTTPException) as exc:
        await reject_if_operator_estop_active(zone_id=7,cmd='dose',params={'ml':1},fetch_fn=AsyncMock(side_effect=ConnectionError()))
    assert exc.value.status_code==503

@pytest.mark.asyncio
async def test_stop_activated_between_transport_retries_prevents_second_publish(monkeypatch):
    from commands import publisher
    query = AsyncMock(side_effect=[[], [{'type': 'EMERGENCY_STOP_ACTIVATED'}]])
    publish = AsyncMock(side_effect=ConnectionError('retry'))
    failed = AsyncMock()
    monkeypatch.setattr(publisher, 'fetch', query)
    monkeypatch.setattr(publisher, 'get_mqtt_client', AsyncMock())
    monkeypatch.setattr(publisher, 'publish_command_mqtt', publish)
    monkeypatch.setattr(publisher, 'mark_command_send_failed', failed)
    monkeypatch.setattr(publisher.asyncio, 'sleep', AsyncMock())
    with pytest.raises(HTTPException) as exc:
        await publisher.publish_command_with_retry(
            payload={'params': {'state': True}}, cmd_id='test-stop-retry', cmd_name='set_relay',
            zone_id=7, node_uid='nd-1', channel='fan_A', effective_gh_uid='gh-1', zone_uid='zn-1',
        )
    assert exc.value.status_code == 409
    assert publish.await_count == 1
    failed.assert_awaited_once_with('test-stop-retry', 'operator_estop_admission_refused')
