import { createBrowserRouter } from 'react-router-dom'

import { AppShell } from '@/app/shell'
import { FilingDetailPage } from '@/routes/filing-detail-page'
import { HomePage } from '@/routes/home-page'
import { NotFoundPage } from '@/routes/not-found-page'

export const router = createBrowserRouter([
  {
    path: '/',
    element: <AppShell />,
    children: [
      { index: true, element: <HomePage /> },
      { path: 'filings/:source/:sourceId', element: <FilingDetailPage /> },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
])
