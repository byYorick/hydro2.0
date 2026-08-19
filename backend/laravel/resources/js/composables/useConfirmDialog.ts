import { ref } from 'vue'

export function useConfirmDialog() {
  const open = ref(false)
  const title = ref('Подтверждение')
  const message = ref('')
  let settle: ((ok: boolean) => void) | null = null
  const finish = (ok: boolean) => { open.value = false; settle?.(ok); settle = null }
  const ask = (msg: string, nextTitle = 'Подтверждение') => {
    settle?.(false); title.value = nextTitle; message.value = msg; open.value = true
    return new Promise<boolean>((resolve) => { settle = resolve })
  }
  return { open, title, message, ask, close: () => finish(false), confirm: () => finish(true) }
}
