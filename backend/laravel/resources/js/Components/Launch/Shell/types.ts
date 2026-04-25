/** Состояние ячейки степпера. */
export type StepCompletion = 'todo' | 'current' | 'warn' | 'done'

/** Описание шага мастера. */
export interface LaunchStep {
  /** Стабильный machine-id шага (zone | recipe | automation | calibration | preview). */
  id: string
  /** Подпись шага в степпере. */
  label: string
  /** Расширение под подписью (короткое описание подэтапа). */
  sub: string
}
