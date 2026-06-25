interface FieldHelpInput {
  title: string
  summary?: string
  help?: string
}

export function resolveSettingsFieldHelp(input: FieldHelpInput): string {
  const help = input.help?.trim()
  if (help) {
    return help
  }

  const summary = input.summary?.trim()
  if (summary) {
    return summary
  }

  return `Параметр «${input.title}». Подробное описание пока не задано — обратитесь к инженеру автоматизации.`
}
