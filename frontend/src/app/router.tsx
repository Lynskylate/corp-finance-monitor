import { createBrowserRouter } from 'react-router-dom'

import { AppShell } from '@/app/shell'
import { FilingDetailPage } from '@/routes/filing-detail-page'
import { HomePage } from '@/routes/home-page'
import { LatestPage } from '@/routes/latest-page'
import { LookupPage } from '@/routes/lookup-page'
import { NotFoundPage } from '@/routes/not-found-page'
import { SubscriptionsPage } from '@/routes/subscriptions-page'
import { SyncPage } from '@/routes/sync-page'

export const router = createBrowserRouter([
  {
    path: '/',
    element: <AppShell />,
    children: [
      { index: true, element: <HomePage /> },
      { path: 'latest', element: <LatestPage /> },
      { path: 'lookup', element: <LookupPage /> },
      { path: 'sync', element: <SyncPage /> },
      { path: 'subscriptions', element: <SubscriptionsPage /> },
      { path: 'filings/:source/:sourceId', element: <FilingDetailPage /> },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
])
