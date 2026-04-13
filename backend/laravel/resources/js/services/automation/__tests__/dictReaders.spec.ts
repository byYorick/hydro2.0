import { describe, expect, it } from 'vitest'
import {
  asArray,
  asRecord,
  readBoolean,
  readNumber,
  readString,
  readStringList,
  toTimeHHmm,
} from '@/services/automation/dictReaders'

describe('asRecord', () => {
  it('принимает plain object', () => {
    expect(asRecord({ a: 1 })).toEqual({ a: 1 })
  })

  it('отклоняет null/undefined/primitive/array', () => {
    expect(asRecord(null)).toBeNull()
    expect(asRecord(undefined)).toBeNull()
    expect(asRecord(42)).toBeNull()
    expect(asRecord('str')).toBeNull()
    expect(asRecord([1, 2])).toBeNull()
  })
})

describe('asArray', () => {
  it('возвращает массив как есть', () => {
    expect(asArray([1, 2, 3])).toEqual([1, 2, 3])
  })

  it('возвращает null для не-массивов', () => {
    expect(asArray({})).toBeNull()
    expect(asArray('str')).toBeNull()
    expect(asArray(null)).toBeNull()
  })
})

describe('readNumber', () => {
  it('возвращает первое финитное число', () => {
    expect(readNumber(1, 2)).toBe(1)
    expect(readNumber(undefined, 5)).toBe(5)
    expect(readNumber(NaN, 7)).toBe(7)
  })

  it('парсит числовые строки', () => {
    expect(readNumber('3.14')).toBe(3.14)
    expect(readNumber('  42  ')).toBe(42)
  })

  it('пропускает невалидные значения', () => {
    expect(readNumber('abc', 'not a number', 10)).toBe(10)
    expect(readNumber(null, undefined, Infinity, 99)).toBe(99)
  })

  it('возвращает null если все невалидны', () => {
    expect(readNumber(null, 'abc', NaN)).toBeNull()
    expect(readNumber()).toBeNull()
  })
})

describe('readBoolean', () => {
  it('принимает настоящий boolean', () => {
    expect(readBoolean(true)).toBe(true)
    expect(readBoolean(false)).toBe(false)
  })

  it('принимает 1/0 и строки "1"/"0"', () => {
    expect(readBoolean(1)).toBe(true)
    expect(readBoolean(0)).toBe(false)
    expect(readBoolean('1')).toBe(true)
    expect(readBoolean('0')).toBe(false)
  })

  it('принимает строки "true"/"false"', () => {
    expect(readBoolean('true')).toBe(true)
    expect(readBoolean('false')).toBe(false)
  })

  it('возвращает первый валидный, пропуская invalid', () => {
    expect(readBoolean(null, undefined, 'bogus', true)).toBe(true)
  })

  it('возвращает null для неизвестных', () => {
    expect(readBoolean('yes', 'no', 2, null)).toBeNull()
    expect(readBoolean()).toBeNull()
  })
})

describe('readString', () => {
  it('trim и возвращает непустую', () => {
    expect(readString('  hello  ')).toBe('hello')
  })

  it('пропускает пустые и whitespace', () => {
    expect(readString('', '   ', 'real')).toBe('real')
  })

  it('игнорирует не-строки', () => {
    expect(readString(42, true, null, 'str')).toBe('str')
  })

  it('возвращает null если все пусто/невалидны', () => {
    expect(readString('', '   ', null, 123)).toBeNull()
  })
})

describe('readStringList', () => {
  it('возвращает массив строк', () => {
    expect(readStringList(['a', 'b', 'c'])).toEqual(['a', 'b', 'c'])
  })

  it('парсит CSV строку', () => {
    expect(readStringList('a,b,c')).toEqual(['a', 'b', 'c'])
    expect(readStringList(' a , b ,, c ')).toEqual(['a', 'b', 'c'])
  })

  it('trim и отбрасывает пустые элементы массива', () => {
    expect(readStringList([' a ', '', 'b', '  '])).toEqual(['a', 'b'])
  })

  it('конвертирует не-строки массива через String()', () => {
    expect(readStringList([1, 'b', true])).toEqual(['1', 'b', 'true'])
  })

  it('возвращает null если все пусто', () => {
    expect(readStringList([], '', ' ')).toBeNull()
    expect(readStringList()).toBeNull()
  })

  it('возвращает первый валидный, пропуская пустые массивы', () => {
    expect(readStringList([], ['x'])).toEqual(['x'])
  })
})

describe('toTimeHHmm', () => {
  it('нормализует к HH:MM', () => {
    expect(toTimeHHmm('6:30')).toBe('06:30')
    expect(toTimeHHmm('06:30')).toBe('06:30')
    expect(toTimeHHmm('23:59')).toBe('23:59')
  })

  it('отрезает секунды', () => {
    expect(toTimeHHmm('06:30:45')).toBe('06:30')
  })

  it('отклоняет вне диапазонов', () => {
    expect(toTimeHHmm('24:00')).toBeNull()
    expect(toTimeHHmm('12:60')).toBeNull()
  })

  it('отклоняет невалидный формат', () => {
    expect(toTimeHHmm('abc')).toBeNull()
    expect(toTimeHHmm('12-30')).toBeNull()
    expect(toTimeHHmm('')).toBeNull()
    expect(toTimeHHmm(null)).toBeNull()
  })
})
