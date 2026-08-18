import { get } from './client.js'

export const dataQualityApi = {
  summary: () => get('/data-quality/summary'),
  fields: () => get('/data-quality/fields'),
}
