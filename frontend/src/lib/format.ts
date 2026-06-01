export function formatDateTime(value: string) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return value
  }

  return new Intl.DateTimeFormat('zh-CN', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date)
}

export function formatKind(kind: string) {
  const labels: Record<string, string> = {
    annual: '年报',
    semi: '中报',
    q1: '一季报',
    q3: '三季报',
    interim: '中期报告',
    prospectus: '招股书',
    quarterly: '季度报告',
    esg: 'ESG',
    other: '其他',
  }

  return labels[kind] ?? kind
}
