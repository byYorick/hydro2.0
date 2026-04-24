import { z } from 'zod'

/**
 * Схема одного шага причинно-следственной цепочки для cockpit UI.
 *
 * Контракт зеркалит PHP `ExecutionChainAssembler` и Python
 * `chain_webhook.emit_execution_step`. Расширяется атомарно:
 * добавили шаг → добавили тип сюда.
 */
export const chainStepSchema = z.object({
  step: z.enum([
    'SNAPSHOT',
    'DECISION',
    'TASK',
    'DISPATCH',
    'RUNNING',
    'COMPLETE',
    'FAIL',
    'SKIP',
  ]),
  at: z.string().nullable().optional(),
  ref: z.string(),
  detail: z.string().default(''),
  status: z.enum(['ok', 'err', 'skip', 'run', 'warn']),
  live: z.boolean().optional(),
})

export type ChainStep = z.infer<typeof chainStepSchema>

export const chainSchema = z.array(chainStepSchema)

/**
 * Payload события `ExecutionChainUpdated` из Laravel Reverb.
 */
export const chainUpdatedEventSchema = z.object({
  zone_id: z.number().int(),
  execution_id: z.string(),
  step: chainStepSchema,
  event_id: z.number().int().optional(),
  server_ts: z.number().int().optional(),
})

export type ChainUpdatedEvent = z.infer<typeof chainUpdatedEventSchema>
