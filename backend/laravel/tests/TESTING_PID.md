# Testing PID authority (AE3 canon)

## Что тестировать

1. `zone.pid.{ph,ec}` через automation-configs (не legacy `/pid-configs`).
2. LiveEdit correction caps/observe/`max_integral` (не kp/ki/kd — они в PidConfigForm).
3. AE3 planner: zoned coeffs, integral clamp из `controllers.*.max_integral`, dead_zone merge.

## Команды

```bash
# Laravel
docker compose -f backend/docker-compose.dev.yml exec laravel php artisan test --filter=ZonePid
docker compose -f backend/docker-compose.dev.yml exec laravel php artisan test tests/Feature/ZoneCorrectionLiveEditControllerTest.php

# Frontend
cd backend/laravel && npm run test -- Components/__tests__/CorrectionLiveEditCard.spec.ts Components/__tests__/PidConfigForm.spec.ts

# Python AE3
make test-ae PYTEST_ARGS="-q test_ae3lite_correction_planner.py test_ae3lite_pid_output_event.py test_ae3lite_pid_state_repository.py"
```

См. также `README_PID_TESTS.md` и `PID_CONFIG_REFERENCE.md` §0.
