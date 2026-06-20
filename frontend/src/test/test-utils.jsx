import { render as rtlRender } from '@testing-library/react'
import { ThemeProvider } from '../context/ThemeContext'

export function render(ui, options) {
  return rtlRender(
    <ThemeProvider>{ui}</ThemeProvider>,
    options
  )
}

export * from '@testing-library/react'
