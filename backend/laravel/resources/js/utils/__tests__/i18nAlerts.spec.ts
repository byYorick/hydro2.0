import { describe, expect, it } from 'vitest'

import {
  formatAlertHumanTitle,
  translateAlertSeverity,
  translateAlertSource,
  translateAlertType,
  translateEventKind,
  translateStatus,
} from '../i18n'

describe('translateAlertSource', () => {
  it('переводит канонические source без смены machine values', () => {
    expect(translateAlertSource('biz')).toBe('Процесс')
    expect(translateAlertSource('infra')).toBe('Инфраструктура')
    expect(translateAlertSource('node')).toBe('Узел')
  })

  it('принимает регистр и неизвестные значения оставляет как есть', () => {
    expect(translateAlertSource('BIZ')).toBe('Процесс')
    expect(translateAlertSource('Infra')).toBe('Инфраструктура')
    expect(translateAlertSource('custom')).toBe('custom')
    expect(translateAlertSource('')).toBe('')
    expect(translateAlertSource(null)).toBe('')
    expect(translateAlertSource(undefined)).toBe('')
  })
})

describe('translateAlertSeverity', () => {
  it('переводит канонические severity на русский', () => {
    expect(translateAlertSeverity('critical')).toBe('Критическая')
    expect(translateAlertSeverity('error')).toBe('Ошибка')
    expect(translateAlertSeverity('warning')).toBe('Предупреждение')
    expect(translateAlertSeverity('info')).toBe('Информация')
  })

  it('принимает регистр и неизвестные значения оставляет как есть', () => {
    expect(translateAlertSeverity('CRITICAL')).toBe('Критическая')
    expect(translateAlertSeverity('Warning')).toBe('Предупреждение')
    expect(translateAlertSeverity('other')).toBe('other')
    expect(translateAlertSeverity('')).toBe('')
    expect(translateAlertSeverity(null)).toBe('')
    expect(translateAlertSeverity(undefined)).toBe('')
  })
})

describe('i18n alert helpers не ломают соседние словари', () => {
  it('translateStatus и translateEventKind остаются прежними', () => {
    expect(translateStatus('WARNING')).toBe('Предупреждение')
    expect(translateStatus('ALARM')).toBe('Тревога')
    expect(translateStatus('active')).toBe('Активно')
    expect(translateStatus('resolved')).toBe('Решено')
    expect(translateEventKind('ALERT_CREATED')).toBe('Тревога создана')
    expect(translateEventKind('NO_FLOW')).toBe('Нет потока')
  })
})

describe('formatAlertHumanTitle', () => {
  it('собирает фразу из type/code и имени зоны', () => {
    expect(translateAlertType('PH_HIGH')).toBe('pH выше нормы')
    expect(formatAlertHumanTitle({
      type: 'PH_HIGH',
      code: 'biz_high_ph',
      zone: { name: 'Салат-1' },
    })).toBe('pH выше нормы в Салат-1')
  })

  it('не подставляет machine code в заголовок', () => {
    expect(formatAlertHumanTitle({
      type: 'EC_LOW',
      code: 'biz_ec_low',
      zone: { name: 'Zone B2' },
    })).toBe('EC ниже нормы в Zone B2')
    expect(formatAlertHumanTitle({
      type: 'EC_LOW',
      code: 'biz_ec_low',
      zone: { name: 'Zone B2' },
    })).not.toContain('biz_ec_low')
  })
})
