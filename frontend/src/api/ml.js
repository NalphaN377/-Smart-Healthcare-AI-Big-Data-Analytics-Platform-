import { get, post } from './client.js'

export const mlApi = {
  status: () => get('/ml/cost-prediction/status'),
  predict: (features) => post('/ml/cost-prediction/predict', features),
}
