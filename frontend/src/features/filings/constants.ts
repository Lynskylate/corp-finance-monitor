export const EXCHANGE_OPTIONS = [
  { value: 'SSE', label: '上交所' },
  { value: 'SZSE', label: '深交所' },
  { value: 'HKEX', label: '港交所' },
] as const

/** @deprecated Use EXCHANGE_OPTIONS instead */
export const SOURCE_OPTIONS = EXCHANGE_OPTIONS

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
