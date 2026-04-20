import { createBrowserRouter } from 'react-router-dom'
import App from '../App'
import { HomePage } from '../pages/Home'
import { ResultPage } from '../pages/Result'
import { SettingsPage } from '../pages/Settings'
import { TaskCreatePage } from '../pages/TaskCreate'
import { TaskRunPage } from '../pages/TaskRun'

export const router = createBrowserRouter([
  {
    path: '/',
    element: <App />,
    children: [
      { index: true, element: <HomePage /> },
      { path: 'tasks/create', element: <TaskCreatePage /> },
      { path: 'tasks/:taskId', element: <TaskRunPage /> },
      { path: 'results/:taskId', element: <ResultPage /> },
      { path: 'settings', element: <SettingsPage /> },
    ],
  },
])
