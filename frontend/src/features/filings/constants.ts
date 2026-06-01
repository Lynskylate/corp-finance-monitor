export const SOURCE_OPTIONS = [
  { value: 'sse', label: '上交所' },
  { value: 'szse', label: '深交所' },
  { value: 'hkex', label: '港交所' },
] as const

export const KIND_OPTIONS = [
  { value: 'annual', label: '年报' },
  { value: 'semi', label: '中报' },
  { value: 'q1', label: '一季报' },
  { value: 'q3', label: '三季报' },
  { value: 'interim', label: '中期报告' },
  { value: 'prospectus', label: '招股书' },
  { value: 'quarterly', label: '季度报告' },
  { value: 'esg', label: 'ESG' },
  { value: 'other', label: '其他' },
] as const
