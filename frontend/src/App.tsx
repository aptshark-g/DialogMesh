import { lazy } from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { Layout } from './components/Layout.tsx';
import { ChatPage } from './pages/ChatPage.tsx';
import { NotFoundPage } from './pages/NotFoundPage.tsx';
import { FloatingActionButton } from './components/FloatingActionButton.tsx';
import { ContentScriptBridge } from './components/ContentScriptBridge.tsx';

const DashboardPage = lazy(() => import('./pages/DashboardPage.tsx').then((m) => ({ default: m.DashboardPage })));
const SessionsPage = lazy(() => import('./pages/SessionsPage.tsx').then((m) => ({ default: m.SessionsPage })));
const SettingsPage = lazy(() => import('./pages/SettingsPage.tsx').then((m) => ({ default: m.SettingsPage })));
const ConversationGraphPage = lazy(() => import('./pages/ConversationGraphPage.tsx').then((m) => ({ default: m.ConversationGraphPage })));
const CognitiveProfilePage = lazy(() => import('./pages/CognitiveProfilePage.tsx').then((m) => ({ default: m.CognitiveProfilePage })));
const TaskPlanningPage = lazy(() => import('./pages/TaskPlanningPage.tsx').then((m) => ({ default: m.TaskPlanningPage })));

export default function App() {
  return (
    <BrowserRouter>
      <ContentScriptBridge />
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<DashboardPage />} />
          <Route path="chat/:sessionId" element={<ChatPage />} />
          <Route path="graph" element={<ConversationGraphPage />} />
          <Route path="profile" element={<CognitiveProfilePage />} />
          <Route path="tasks" element={<TaskPlanningPage />} />
          <Route path="sessions" element={<SessionsPage />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Routes>
      <FloatingActionButton />
    </BrowserRouter>
  );
}
