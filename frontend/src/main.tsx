import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { App } from '@/app/App'
import './index.css'
import './theme/theme.css'
import './theme/brand.css'
import { installAutoHideScrollbars } from './theme/scrollbars'

installAutoHideScrollbars()

const root = document.getElementById('root')
if (!root) throw new Error('Root element #root not found')

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
