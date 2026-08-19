import { describe, expect, it } from 'vitest'
import { useConfirmDialog } from '../useConfirmDialog'

describe('useConfirmDialog', () => {
  it('resolves true on confirm and false on close', async () => {
    const dialog = useConfirmDialog()
    const pending = dialog.ask('Удалить?', 'Подтверждение')
    expect(dialog.open.value).toBe(true)
    expect(dialog.message.value).toBe('Удалить?')
    dialog.confirm()
    await expect(pending).resolves.toBe(true)
    expect(dialog.open.value).toBe(false)

    const cancelled = dialog.ask('Отменить?')
    dialog.close()
    await expect(cancelled).resolves.toBe(false)
  })
})
