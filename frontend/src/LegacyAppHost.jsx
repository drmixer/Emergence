import { BrowserRouter } from 'react-router-dom'
import App from './App'

export default function LegacyAppHost() {
  return (
    <BrowserRouter>
      <App />
    </BrowserRouter>
  )
}
